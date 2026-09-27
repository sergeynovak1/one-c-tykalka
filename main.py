"""
Главный модуль для запуска приложения.
Обрабатывает Excel файл и автоматизирует ввод данных в 1С
(веб-клиент в Яндекс Браузере, документ «Реализация товаров»).
"""
from data_processor import process_excel_file, get_total_sum
from automation import (
    automate_data_entry,
    activate_one_c_window,
    set_english_layout,
    read_total_from_1c,
)


def main():
    """
    Главная функция приложения.
    Загружает товары (Приход) в документ «Реализация товаров» в Яндекс Браузере.
    """
    try:
        products_list = process_excel_file()

        if not products_list:
            print("\n⚠ Нет товаров (Приход) для загрузки.")
            return

        total_sum = get_total_sum(products_list)
        print(f"\n💰 Общая сумма (товары): {total_sum}")

        print("\n🤖 Разворачиваю Яндекс Браузер...")
        set_english_layout()
        activate_one_c_window()

        print("\n→ Загружаю товары в «Реализация товаров»...")
        automate_data_entry(products_list)

        print("\n✅ Готово! Все данные успешно введены.")

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
    # except Exception as e:
    #     print(f"\n❌ Произошла ошибка: {e}")


if __name__ == "__main__":
    main()
