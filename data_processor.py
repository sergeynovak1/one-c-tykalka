"""
Модуль для обработки Excel файлов и подготовки данных.
"""
import pandas as pd
from decimal import Decimal, getcontext
import glob
import os
import re

from config import XLSX_FILE_PATTERN, REFUND_TYPE, RECEIPT_TYPE

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

    Args:
        value: Значение для преобразования

    Returns:
        Decimal: Преобразованное значение
    """
    if pd.isna(value):
        return Decimal("0")
    return Decimal(
        str(value)
        .replace(" ", "")
        .replace(",", ".")
    )


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


def load_and_prepare_data(file_path):
    """
    Загружает и подготавливает данные из Excel файла.
    Фильтрует по "Приход" и "Возврат прихода" в столбце "Признак расчета".

    Args:
        file_path (str): Путь к Excel файлу

    Returns:
        pd.DataFrame: Подготовленный DataFrame
    """
    df = pd.read_excel(file_path, dtype={"Наименование": str})

    # Ищем столбец "Признак расчета"
    calc_col = _find_calculation_type_column(df)
    if calc_col is None:
        raise ValueError(
            "Не найден столбец с 'Признак расчета' в названии. "
            "Проверьте структуру Excel файла."
        )

    # Выбираем нужные столбцы
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

    # Фильтруем только Приход и Возврат прихода
    allowed_values = {"Приход", "Возврат прихода"}
    df["calculation_type"] = df["calculation_type"].astype(str).str.strip()
    df = df[df["calculation_type"].isin(allowed_values)]

    if df.empty:
        raise ValueError(
            "После фильтрации по 'Приход' и 'Возврат прихода' данных не осталось."
        )

    # Преобразование строк с деньгами в Decimal
    df["price"] = df["price"].apply(to_decimal)
    df["cost"] = df["cost"].apply(to_decimal)

    # Количество тоже в Decimal (на случай дробных единиц)
    df["quantity"] = df["quantity"].apply(lambda x: Decimal(str(x)))

    df["nomenclature"] = df["nomenclature"].apply(clean_spaces)

    return df


def group_data(df):
    """
    Группирует данные по номенклатуре, цене и признаку расчёта (Приход/Возврат прихода).

    Args:
        df (pd.DataFrame): DataFrame с данными

    Returns:
        pd.DataFrame: Сгруппированный DataFrame
    """
    grouped = (
        df.groupby(["nomenclature", "price", "calculation_type"], as_index=False)
        .agg({
            "quantity": "sum",
            "cost": "sum"
        })
    )
    return grouped


def get_total_difference(refunds_list, products_list):
    """
    Вычисляет общую сумму — разницу между суммой (цена*колво) продуктов и возвратов.

    Args:
        refunds_list: список кортежей (nomenclature, quantity, price, cost)
        products_list: список кортежей (nomenclature, quantity, price, cost)

    Returns:
        Decimal: products_sum - refunds_sum
    """
    products_sum = sum(to_decimal(item[2]) * to_decimal(item[1]) for item in products_list)
    refunds_sum = sum(to_decimal(item[2]) * to_decimal(item[1]) for item in refunds_list)
    return products_sum - refunds_sum


def prepare_result_list(grouped_df):
    """
    Подготавливает список кортежей в нужном формате.

    Args:
        grouped_df (pd.DataFrame): Сгруппированный DataFrame

    Returns:
        list: Список кортежей (nomenclature, quantity, price)
    """
    result = [
        (row.nomenclature, str(row.quantity), str(row.price))
        for row in grouped_df.itertuples(index=False)
    ]
    return result


def process_excel_file():
    """
    Основная функция для обработки Excel файла.
    Разделяет данные на возвраты (Возврат прихода) и обычные товары (Приход).

    Returns:
        tuple: (refunds_list, products_list) — списки кортежей (nomenclature, quantity, price, cost)
    """
    # Находим файл
    file_path = find_xlsx_file()
    print(f"📁 Обрабатываю файл: {file_path}")

    # Загружаем и подготавливаем данные
    df = load_and_prepare_data(file_path)

    # Группируем данные (по номенклатуре, цене и признаку расчёта)
    grouped = group_data(df)

    # Разделяем на возвраты и обычные товары
    refunds_df = grouped[grouped["calculation_type"] == REFUND_TYPE]
    products_df = grouped[grouped["calculation_type"] == RECEIPT_TYPE]

    refunds_list = prepare_result_list(refunds_df.drop(columns=["calculation_type"]))
    products_list = prepare_result_list(products_df.drop(columns=["calculation_type"]))

    print(f"\n📊 Возвраты (Возврат прихода): {len(refunds_list)} позиций")
    for item in refunds_list:
        print(f"  ↩ {item}")

    print(f"\n📊 Обычные товары (Приход): {len(products_list)} позиций")
    for item in products_list:
        print(f"  → {item}")

    return refunds_list, products_list
