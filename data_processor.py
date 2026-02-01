"""
Модуль для обработки Excel файлов и подготовки данных.
"""
import pandas as pd
from decimal import Decimal, getcontext
import glob
import os
import re

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
    path = os.path.expanduser("~/Desktop/ОФД/*.xlsx")
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


def load_and_prepare_data(file_path):
    """
    Загружает и подготавливает данные из Excel файла.

    Args:
        file_path (str): Путь к Excel файлу

    Returns:
        pd.DataFrame: Подготовленный DataFrame
    """
    df = pd.read_excel(file_path)

    # Выбираем нужные столбцы
    df = df[
        [
            "Наименование",
            "Цена товара",
            "Количество единиц измерения в чеке",
            "Сумма товара"
        ]
    ].rename(columns={
        "Наименование": "nomenclature",
        "Цена товара": "price",
        "Количество единиц измерения в чеке": "quantity",
        "Сумма товара": "cost"
    })

    # Преобразование строк с деньгами в Decimal
    df["price"] = df["price"].apply(to_decimal)
    df["cost"] = df["cost"].apply(to_decimal)

    # Количество тоже в Decimal (на случай дробных единиц)
    df["quantity"] = df["quantity"].apply(lambda x: Decimal(str(x)))

    df["nomenclature"] = df["nomenclature"].apply(clean_spaces)

    return df


def group_data(df):
    """
    Группирует данные по номенклатуре и цене.

    Args:
        df (pd.DataFrame): DataFrame с данными

    Returns:
        pd.DataFrame: Сгруппированный DataFrame
    """
    grouped = (
        df.groupby(["nomenclature", "price"], as_index=False)
        .agg({
            "quantity": "sum",
            "cost": "sum"
        })
    )
    return grouped


def prepare_result_list(grouped_df):
    """
    Подготавливает список кортежей в нужном формате.

    Args:
        grouped_df (pd.DataFrame): Сгруппированный DataFrame

    Returns:
        list: Список кортежей (nomenclature, quantity, price, cost)
    """
    result = [
        (row.nomenclature, str(row.quantity), str(row.price), str(row.cost))
        for row in grouped_df.itertuples(index=False)
    ]
    return result


def process_excel_file():
    """
    Основная функция для обработки Excel файла.

    Returns:
        list: Список кортежей с обработанными данными
    """
    # Находим файл
    file_path = find_xlsx_file()
    print(f"📁 Обрабатываю файл: {file_path}")

    # Загружаем и подготавливаем данные
    df = load_and_prepare_data(file_path)

    # Группируем данные
    grouped = group_data(df)

    # Подготавливаем результат
    result = prepare_result_list(grouped)

    # Вывод результатов
    print(f"\n📊 Найдено {len(result)} уникальных позиций:")
    for item in result:
        print(item)

    return result
