"""
Модуль для обработки Excel файлов и подготовки данных.
Ожидается отчёт «Анализ контрагентов» (лист «Документ»).
"""
import pandas as pd
from decimal import Decimal, InvalidOperation, getcontext
import glob
import os
import re

from config import (
    XLSX_FILE_PATTERN,
)

# Устанавливаем точность для Decimal
getcontext().prec = 28

# Лист отчёта «Анализ контрагентов»; колонки ищем по заголовкам
# (в разных выгрузках число служебных колонок до «Приход» отличается)
DOCUMENT_SHEET_NAME = "Документ"
HEADER_ROWS = 3


def find_xlsx_file():
    """
    Находит единственный XLSX файл по шаблону из config.

    Returns:
        str: Путь к найденному файлу

    Raises:
        FileNotFoundError: Если файлы не найдены
        ValueError: Если найдено несколько файлов
    """
    path = os.path.expanduser(XLSX_FILE_PATTERN)
    xlsx_files = glob.glob(path)

    if not xlsx_files:
        raise FileNotFoundError(f"Не найдено XLSX файлов по шаблону: {XLSX_FILE_PATTERN}")

    if len(xlsx_files) > 1:
        file_list = "\n".join([f"  - {f}" for f in xlsx_files])
        raise ValueError(
            f"Найдено несколько XLSX файлов:\n{file_list}\n"
            f"Оставьте только один файл."
        )

    return xlsx_files[0]


# Сумма в тексте: 1 234,56 / 1.234.567,89 / 1,234,567.89 / 1234.56
_GROUP_SPACE = " \u00a0\u202f\u2009"
_AMOUNT_BODY = (
    r"-?(?:"
    r"\d{1,3}(?:[" + _GROUP_SPACE + r"]\d{3})+(?:[.,]\d+)?"
    r"|\d{1,3}(?:\.\d{3})+(?:,\d+)?"
    r"|\d{1,3}(?:,\d{3})+(?:\.\d+)?"
    r"|\d+(?:[.,]\d+)?"
    r")"
)
_AMOUNT_RE = re.compile(r"(?<![\d.,])(" + _AMOUNT_BODY + r")(?![\d.,])")
# «Всего 10 позиций» не берём: у денежной подписи должны быть копейки или группы разрядов
_LABELED_TOTAL_RE = re.compile(
    r"(?<!\w)Всего(?!\s*с\s+НДС)\s*:?\s*(" + _AMOUNT_BODY + r")",
    re.IGNORECASE,
)


def _canonicalize_number(body: str) -> str:
    """
    Приводит уже очищенную строку (цифры, запятая, точка, без пробелов) к виду Decimal.
    """
    if "," in body and "." in body:
        if body.rfind(",") > body.rfind("."):
            int_part, frac = body.rsplit(",", 1)
            int_part = int_part.replace(".", "").replace(",", "")
        else:
            int_part, frac = body.rsplit(".", 1)
            int_part = int_part.replace(",", "").replace(".", "")
        if int_part.isdigit() and frac.isdigit():
            return f"{int_part}.{frac}"
        raise InvalidOperation

    sep = "," if "," in body else ("." if "." in body else None)
    if sep is None:
        if body.isdigit():
            return body
        raise InvalidOperation

    parts = body.split(sep)
    if len(parts) == 2:
        if parts[0].isdigit() and parts[1].isdigit():
            return f"{parts[0]}.{parts[1]}"
        raise InvalidOperation

    # 1.234.567 или 1,234,567 — группы по 3, без дробной части
    if (
        parts[0].isdigit()
        and 1 <= len(parts[0]) <= 3
        and all(len(part) == 3 and part.isdigit() for part in parts[1:])
    ):
        return "".join(parts)
    raise InvalidOperation


def to_decimal(value):
    """
    Преобразует значение в Decimal, обрабатывая строки с деньгами.
    Поддерживает: запятая как разделитель тысяч (122,368.00),
    запятая как десятичный разделитель (122,38), пробелы,
    группы разрядов точкой или запятой (1.234.567).

    Args:
        value: Значение для преобразования

    Returns:
        Decimal: Преобразованное значение
    """
    if pd.isna(value):
        return Decimal("0")
    if isinstance(value, Decimal):
        return value

    s = str(value).strip()
    if not s:
        return Decimal("0")

    # Удаляем пробелы/неразрывные пробелы и оставляем только "числовые" символы.
    s = s.replace("\xa0", "").replace("\u202f", "").replace("\u2009", "")
    s = re.sub(r"\s+", "", s)
    s = s.replace("−", "-").replace("–", "-")
    s = re.sub(r"[^0-9,.\-]", "", s)
    if not s or s in {"-", ".", ",", "-.", "-,"}:
        return Decimal("0")

    negative = s.startswith("-")
    body = s[1:] if negative else s
    # Хвост вроде «руб.» оставляет точку после копеек: 12345,67. → не съедать запятую
    body = body.strip(".,")
    if not body:
        return Decimal("0")
    if "-" in body:
        raise InvalidOperation

    canonical = _canonicalize_number(body)
    if negative:
        canonical = "-" + canonical
    return Decimal(canonical)


def _is_money_token(token: str) -> bool:
    """Сумма с копейками или с группами разрядов, не голое целое вроде «10»."""
    spaced = token.strip()
    compact = (
        spaced.replace(" ", "")
        .replace("\xa0", "")
        .replace("\u202f", "")
        .replace("\u2009", "")
    )
    if re.fullmatch(r"-?\d{1,3}(?:[" + _GROUP_SPACE + r"]\d{3})+(?:[.,]\d+)?", spaced):
        return True
    if re.fullmatch(r"-?\d+,\d+", compact):
        return True
    if re.fullmatch(r"-?\d{1,3}(?:\.\d{3})+(?:,\d+)?", compact):
        return True
    if re.fullmatch(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?", compact):
        return True
    if re.fullmatch(r"-?\d+\.\d+", compact):
        return True
    return False


def parse_total_text(text):
    """
    Достаёт одну сумму из буфера «Всего».

    Одно число — берём его. Если чисел несколько (Ctrl+A захватил страницу),
    берём сумму только у единственной подписи «Всего». Иначе None, без падения.
    """
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    raw = str(text).replace("\xa0", " ").replace("\u202f", " ").replace("\u2009", " ")
    raw = raw.replace("−", "-").replace("–", "-").strip()
    if not raw:
        return None

    tokens = _AMOUNT_RE.findall(raw)
    if len(tokens) == 1:
        try:
            return to_decimal(tokens[0])
        except InvalidOperation:
            return None

    parsed = []
    for token in tokens:
        if not _is_money_token(token):
            continue
        try:
            parsed.append(to_decimal(token))
        except InvalidOperation:
            continue
    if parsed and len(parsed) == len(tokens) and len(set(parsed)) == 1:
        return parsed[0]

    labeled = []
    for token in _LABELED_TOTAL_RE.findall(raw):
        if not _is_money_token(token):
            continue
        try:
            labeled.append(to_decimal(token))
        except InvalidOperation:
            continue
    if labeled and len(set(labeled)) == 1:
        return labeled[0]
    return None


def clean_spaces(text, max_length=100):
    """
    Очищает строку:
    - удаляет лишние пробелы
    - обрезает до max_length символов
    - если обрезано, добавляет ' ...'
    """
    if pd.isna(text):
        return ""

    cleaned = re.sub(r"\s+", " ", str(text)).strip()

    if len(cleaned) > max_length:
        return cleaned[:max_length - 4] + " ..."

    return cleaned


def _cell_str(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def detect_columns(file_path):
    """
    По шапке листа находит колонки: Товар, Приход→Количество, Приход→Цена.

    Returns:
        tuple[int, int, int]: (nomenclature_col, quantity_col, price_col)
    """
    header = pd.read_excel(
        file_path,
        sheet_name=DOCUMENT_SHEET_NAME,
        header=None,
        nrows=HEADER_ROWS,
    )
    row0 = [_cell_str(v) for v in header.iloc[0].tolist()]
    row1 = [_cell_str(v) for v in header.iloc[1].tolist()]

    try:
        nomenclature_col = row0.index("Товар")
    except ValueError as exc:
        raise ValueError("В шапке листа «Документ» не найдена колонка «Товар».") from exc

    try:
        prihod_start = row0.index("Приход")
    except ValueError as exc:
        raise ValueError("В шапке листа «Документ» не найден блок «Приход».") from exc

    # Блок «Приход» идёт до «Расход» (если есть)
    try:
        prihod_end = row0.index("Расход", prihod_start + 1)
    except ValueError:
        prihod_end = len(row1)

    quantity_col = None
    price_col = None
    for col in range(prihod_start, prihod_end):
        label = row1[col] if col < len(row1) else ""
        if label == "Количество" and quantity_col is None:
            quantity_col = col
        elif label == "Цена" and price_col is None:
            price_col = col

    if quantity_col is None or price_col is None:
        raise ValueError(
            "В блоке «Приход» не найдены колонки «Количество» и/или «Цена»."
        )

    return nomenclature_col, quantity_col, price_col


def load_and_prepare_data(file_path):
    """
    Загружает лист «Документ» из «Анализа контрагентов».
    Берёт товар, количество и цену из блока «Приход».

    Args:
        file_path (str): Путь к Excel файлу

    Returns:
        pd.DataFrame: колонки nomenclature, quantity, price
    """
    nomenclature_col, quantity_col, price_col = detect_columns(file_path)

    df = pd.read_excel(
        file_path,
        sheet_name=DOCUMENT_SHEET_NAME,
        header=None,
        skiprows=HEADER_ROWS,
        dtype={nomenclature_col: str},
    )

    needed = max(nomenclature_col, quantity_col, price_col)
    if df.shape[1] <= needed:
        raise ValueError(
            f"В листе '{DOCUMENT_SHEET_NAME}' ожидалось минимум {needed + 1} колонок, "
            f"получено {df.shape[1]}."
        )

    df = pd.DataFrame({
        "nomenclature": df.iloc[:, nomenclature_col],
        "quantity": df.iloc[:, quantity_col],
        "price": df.iloc[:, price_col],
    })

    df["nomenclature"] = df["nomenclature"].apply(clean_spaces)
    df["quantity"] = df["quantity"].apply(to_decimal)
    df["price"] = df["price"].apply(to_decimal)

    # Пропускаем пустые строки и позиции без прихода
    df = df[(df["nomenclature"] != "") & (df["quantity"] != 0)]

    if df.empty:
        raise ValueError(
            "После чтения «Анализа контрагентов» не осталось позиций с приходом."
        )

    return df.reset_index(drop=True)


def group_data(df):
    """
    Группирует данные по номенклатуре и цене прихода.

    Args:
        df (pd.DataFrame): DataFrame с данными

    Returns:
        pd.DataFrame: Сгруппированный DataFrame
    """
    return (
        df.groupby(["nomenclature", "price"], as_index=False)
        .agg({"quantity": "sum"})
    )


def get_total_sum(products_list):
    """
    Вычисляет общую сумму товаров (цена * количество).

    Args:
        products_list: список кортежей (nomenclature, quantity, price)

    Returns:
        Decimal: сумма по всем позициям
    """
    return sum(to_decimal(item[2]) * to_decimal(item[1]) for item in products_list)


def format_for_input(value):
    """Форматирует число для ввода в 1С без лишних нулей (3.0 → 3, 18.30 → 18.3)."""
    d = to_decimal(value)
    s = f"{d:f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s or "0"


def prepare_result_list(grouped_df):
    """
    Подготавливает список кортежей в нужном формате.

    Args:
        grouped_df (pd.DataFrame): Сгруппированный DataFrame

    Returns:
        list: Список кортежей (nomenclature, quantity, price)
    """
    return [
        (row.nomenclature, format_for_input(row.quantity), format_for_input(row.price))
        for row in grouped_df.itertuples(index=False)
    ]


def process_excel_file():
    """
    Основная функция для обработки «Анализа контрагентов».
    Берёт позиции прихода (количество и цена).

    Returns:
        list: список кортежей (nomenclature, quantity, price)
    """
    file_path = find_xlsx_file()
    print(f"📁 Обрабатываю файл: {file_path}")

    df = load_and_prepare_data(file_path)
    grouped = group_data(df)
    products_list = prepare_result_list(grouped)

    print(f"\n📊 Товары (приход): {len(products_list)} позиций")
    for item in products_list:
        print(f"  → {item}")

    return products_list
