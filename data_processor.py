"""
Модуль для обработки Excel файлов и подготовки данных.
Ожидается отчёт «Анализ контрагентов» (лист «Документ»).
"""
import pandas as pd
from decimal import Decimal, getcontext
import glob
import os
import re

from config import (
    XLSX_FILE_PATTERN,
)

# Устанавливаем точность для Decimal
getcontext().prec = 28

# Лист и колонки отчёта «Анализ контрагентов» (0-based после skiprows заголовка)
DOCUMENT_SHEET_NAME = "Документ"
HEADER_ROWS = 3
COL_NOMENCLATURE = 1   # Товар
COL_QUANTITY = 10      # Расход → Количество
COL_PRICE = 16         # Расход → Отпускные суммы → Цена


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


def to_decimal(value):
    """
    Преобразует значение в Decimal, обрабатывая строки с деньгами.
    Поддерживает: запятая как разделитель тысяч (122,368.00),
    запятая как десятичный разделитель (122,38), пробелы.

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
    s = s.replace("\xa0", "")
    s = re.sub(r"\s+", "", s)
    s = s.replace("−", "-")
    s = re.sub(r"[^0-9,.\-]", "", s)
    if not s or s in {"-", ".", ",", "-.", "-,"}:
        return Decimal("0")

    # Если есть и точка, и запятая — последний разделитель считаем десятичным.
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")

    return Decimal(s)


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


def load_and_prepare_data(file_path):
    """
    Загружает лист «Документ» из «Анализа контрагентов».
    Берёт товар, количество расхода и отпускную цену.

    Args:
        file_path (str): Путь к Excel файлу

    Returns:
        pd.DataFrame: колонки nomenclature, quantity, price
    """
    df = pd.read_excel(
        file_path,
        sheet_name=DOCUMENT_SHEET_NAME,
        header=None,
        skiprows=HEADER_ROWS,
        dtype={COL_NOMENCLATURE: str},
    )

    if df.shape[1] <= COL_PRICE:
        raise ValueError(
            f"В листе '{DOCUMENT_SHEET_NAME}' ожидалось минимум {COL_PRICE + 1} колонок, "
            f"получено {df.shape[1]}."
        )

    df = pd.DataFrame({
        "nomenclature": df.iloc[:, COL_NOMENCLATURE],
        "quantity": df.iloc[:, COL_QUANTITY],
        "price": df.iloc[:, COL_PRICE],
    })

    df["nomenclature"] = df["nomenclature"].apply(clean_spaces)
    df["quantity"] = df["quantity"].apply(to_decimal)
    df["price"] = df["price"].apply(to_decimal)

    # Пропускаем пустые строки и позиции без расхода
    df = df[(df["nomenclature"] != "") & (df["quantity"] != 0)]

    if df.empty:
        raise ValueError(
            "После чтения «Анализа контрагентов» не осталось позиций с расходом."
        )

    return df.reset_index(drop=True)


def group_data(df):
    """
    Группирует данные по номенклатуре и отпускной цене.

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
    Берёт позиции расхода с отпускной ценой.

    Returns:
        list: список кортежей (nomenclature, quantity, price)
    """
    file_path = find_xlsx_file()
    print(f"📁 Обрабатываю файл: {file_path}")

    df = load_and_prepare_data(file_path)
    grouped = group_data(df)
    products_list = prepare_result_list(grouped)

    print(f"\n📊 Товары (расход): {len(products_list)} позиций")
    for item in products_list:
        print(f"  → {item}")

    return products_list
