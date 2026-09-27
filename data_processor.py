"""
Модуль для обработки Excel файлов и подготовки данных.
"""
import pandas as pd
from decimal import Decimal, getcontext
import glob
import os
import re

from config import (
    BULK_PRICE_THRESHOLD,
    RECEIPT_TYPE,
    XLSX_FILE_PATTERN,
)

# Устанавливаем точность для Decimal
getcontext().prec = 28


def find_xlsx_file():
    """
    Находит единственный XLSX файл в текущей директории.

    Returns:
        str: Путь к найденному файлу

    Raises:
        FileNotFoundError: Если файлы не найдены
        ValueError: Если найдено несколько файлов
    """
    path = os.path.expanduser(XLSX_FILE_PATTERN)
    xlsx_files = glob.glob(path)

    if not xlsx_files:
        raise FileNotFoundError("В текущей папке нет XLSX файлов")

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

    # Нормализация пробелов
    cleaned = re.sub(r"\s+", " ", str(text)).strip()

    # Обрезка с ' ...'
    if len(cleaned) > max_length:
        return cleaned[:max_length - 4] + " ..."

    return cleaned


def _find_calculation_type_column(df):
    """
    Находит столбец, в названии которого есть "Признак расчета".

    Returns:
        str: Имя столбца или None
    """
    for col in df.columns:
        if "Признак расчета" in str(col):
            return col
    return None


def normalize_bulk_unit_prices(df):
    """
    Строки с ценой выше BULK_PRICE_THRESHOLD и кратной 10 приводятся к штучному виду:
    quantity × 10, price ÷ 10, чтобы корректно сливались с позициями по той же цене за штуку.
    """
    ten = Decimal("10")
    zero = Decimal("0")
    mask = (df["price"] > BULK_PRICE_THRESHOLD) & ((df["price"] % ten) == zero)
    if not mask.any():
        return df
    df = df.copy()
    df.loc[mask, "quantity"] = df.loc[mask, "quantity"] * ten
    df.loc[mask, "price"] = df.loc[mask, "price"] / ten
    return df


def load_and_prepare_data(file_path):
    """
    Загружает и подготавливает данные из Excel файла.
    Фильтрует только «Приход» в столбце «Признак расчета».

    Args:
        file_path (str): Путь к Excel файлу

    Returns:
        pd.DataFrame: Подготовленный DataFrame
    """
    df = pd.read_excel(file_path, dtype={"Наименование": str})

    calc_col = _find_calculation_type_column(df)
    if calc_col is None:
        raise ValueError(
            "Не найден столбец с 'Признак расчета' в названии. "
            "Проверьте структуру Excel файла."
        )

    df = df[
        [
            "Наименование",
            "Цена товара",
            "Количество единиц измерения в чеке",
            "Сумма товара",
            calc_col,
        ]
    ].rename(columns={
        "Наименование": "nomenclature",
        "Цена товара": "price",
        "Количество единиц измерения в чеке": "quantity",
        "Сумма товара": "cost",
        calc_col: "calculation_type",
    })

    df["calculation_type"] = df["calculation_type"].astype(str).str.strip()
    df = df[df["calculation_type"] == RECEIPT_TYPE]

    if df.empty:
        raise ValueError(
            f"После фильтрации по '{RECEIPT_TYPE}' данных не осталось."
        )

    df = df.drop(columns=["calculation_type"])

    df["price"] = df["price"].apply(to_decimal)
    df["cost"] = df["cost"].apply(to_decimal)
    df["quantity"] = df["quantity"].apply(
        lambda x: Decimal("0") if pd.isna(x) else to_decimal(x)
    )
    df["nomenclature"] = df["nomenclature"].apply(clean_spaces)
    df = normalize_bulk_unit_prices(df)

    return df


def group_data(df):
    """
    Группирует данные по номенклатуре и цене.

    Args:
        df (pd.DataFrame): DataFrame с данными

    Returns:
        pd.DataFrame: Сгруппированный DataFrame
    """
    return (
        df.groupby(["nomenclature", "price"], as_index=False)
        .agg({
            "quantity": "sum",
            "cost": "sum",
        })
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


def prepare_result_list(grouped_df):
    """
    Подготавливает список кортежей в нужном формате.

    Args:
        grouped_df (pd.DataFrame): Сгруппированный DataFrame

    Returns:
        list: Список кортежей (nomenclature, quantity, price)
    """
    return [
        (row.nomenclature, str(row.quantity), str(row.price))
        for row in grouped_df.itertuples(index=False)
    ]


def process_excel_file():
    """
    Основная функция для обработки Excel файла.
    Берёт только товары с признаком «Приход».

    Returns:
        list: список кортежей (nomenclature, quantity, price)
    """
    file_path = find_xlsx_file()
    print(f"📁 Обрабатываю файл: {file_path}")

    df = load_and_prepare_data(file_path)
    grouped = group_data(df)
    products_list = prepare_result_list(grouped)

    print(f"\n📊 Товары (Приход): {len(products_list)} позиций")
    for item in products_list:
        print(f"  → {item}")

    return products_list
