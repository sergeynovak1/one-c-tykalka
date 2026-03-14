"""
Главный модуль для запуска приложения.
Обрабатывает Excel файл и автоматизирует ввод данных в 1С.
"""
from data_processor import process_excel_file, get_total_difference
from automation import (
    automate_data_entry,
    click_refund_button,
    click_product_button,
    activate_one_c_window,
    set_english_layout,
    read_total_from_1c,
)


def main():
    """
    Главная функция приложения.
    Сначала загружает возвраты (Возврат прихода), затем обычные товары (Приход).
    """
    try:
        # Обрабатываем Excel файл: разделяем на возвраты и товары
        refunds_list, products_list = process_excel_file()

        if not refunds_list and not products_list:
            print("\n⚠ Нет данных для загрузки (ни возвратов, ни товаров).")
            return

        # Общая сумма: разница между продуктами и возвратами (цена*колво)
        total_sum = get_total_difference(refunds_list, products_list)
        print(f"\n💰 Общая сумма (продукты − возвраты): {total_sum}")

        # Автоматизируем ввод данных в 1С
        print("\n🤖 Начинаю автоматизацию ввода данных в 1С...")
        set_english_layout()
        activate_one_c_window()

        # 1. Сначала возвраты — нажать "Возвраты" и загрузить по стандартному алгоритму
        if refunds_list:
            print("\n↩ Загружаю возвраты...")
            click_refund_button()
            automate_data_entry(refunds_list, is_refund=True)

        # 2. Затем обычные товары — нажать "Товары" и загрузить по базовому алгоритму
        if products_list:
            print("\n→ Загружаю обычные товары...")
            click_product_button()
            automate_data_entry(products_list)

        print("\n✅ Готово! Все данные успешно введены.")

        # Проверка суммы: читаем из 1С и сравниваем с расчётной
        actual_sum = read_total_from_1c()
        if actual_sum is not None:
            if actual_sum == total_sum:
                print(f"✅ Сумма сошлась: {total_sum}")
            else:
                print(f"⚠ Сумма не сошлась! Расчётная: {total_sum}, в 1С: {actual_sum}")
        else:
            print("⚠ Не удалось прочитать сумму из поля «Всего» в 1С.")

    except FileNotFoundError as e:
        print(f"\n❌ Ошибка: {e}")
    except ValueError as e:
        print(f"\n❌ Ошибка: {e}")
    except Exception as e:
        print(f"\n❌ Произошла ошибка: {e}")


if __name__ == "__main__":
    main()