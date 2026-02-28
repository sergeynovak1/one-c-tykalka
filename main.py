"""
Главный модуль для запуска приложения.
Обрабатывает Excel файл и автоматизирует ввод данных в 1С.
"""
from data_processor import process_excel_file
from automation import (
    automate_data_entry,
    click_refund_button,
    click_product_button,
    activate_one_c_window,
    set_english_layout,
)


def main():
    """
    Главная функция приложения.
    Сначала загружает возвраты (Возврат прихода), затем обычные товары (Приход).
    """
    try:
        # Обрабатываем Excel файл: разделяем на возвраты и товары
        refunds_list, products_list = process_excel_file()

        # Автоматизируем ввод данных в 1С
        print("\n🤖 Начинаю автоматизацию ввода данных в 1С...")
        set_english_layout()
        activate_one_c_window()

        # 1. Сначала возвраты — нажать "Возвраты" и загрузить по стандартному алгоритму
        if refunds_list:
            print("\n↩ Загружаю возвраты...")
            click_refund_button()
            automate_data_entry(refunds_list)

        # 2. Затем обычные товары — нажать "Товары" и загрузить по базовому алгоритму
        if products_list:
            print("\n→ Загружаю обычные товары...")
            click_product_button()
            automate_data_entry(products_list)

        if not refunds_list and not products_list:
            print("\n⚠ Нет данных для загрузки (ни возвратов, ни товаров).")
        else:
            print("\n✅ Готово! Все данные успешно введены.")

    except FileNotFoundError as e:
        print(f"\n❌ Ошибка: {e}")
    except ValueError as e:
        print(f"\n❌ Ошибка: {e}")
    except Exception as e:
        print(f"\n❌ Произошла ошибка: {e}")


if __name__ == "__main__":
    main()