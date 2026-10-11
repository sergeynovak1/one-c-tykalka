"""
Главный модуль: парсинг и группировка Excel («Анализ контрагентов»).
"""
from data_processor import process_excel_file, get_total_sum


def main():
    try:
        products_list = process_excel_file()

        if not products_list:
            print("\n⚠ Нет товаров для загрузки.")
            return

        file_total = get_total_sum(products_list)
        print(f"\n💰 Сумма по файлу (все позиции): {file_total}")

    except FileNotFoundError as e:
        print(f"\n❌ Ошибка: {e}")
    except ValueError as e:
        print(f"\n❌ Ошибка: {e}")


if __name__ == "__main__":
    main()
