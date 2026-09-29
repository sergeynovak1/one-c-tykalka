"""
Главный модуль для запуска приложения.
Обрабатывает Excel файл и автоматизирует ввод данных в 1С
(веб-клиент в Яндекс Браузере, документ «Реализация товаров»).
"""
from decimal import Decimal

from data_processor import process_excel_file, get_total_sum
from automation import (
    automate_data_entry,
    activate_one_c_window,
    set_english_layout,
    read_total_from_1c,
    get_skipped_products,
    _as_money,
)


def main():
    """
    Главная функция приложения.
    Загружает товары в документ «Реализация товаров» в Яндекс Браузере.
    """
    try:
        products_list = process_excel_file()

        if not products_list:
            print("\n⚠ Нет товаров для загрузки.")
            return

        file_total = get_total_sum(products_list)
        print(f"\n💰 Сумма по файлу (все позиции): {file_total}")

        print("\n🤖 Разворачиваю Яндекс Браузер...")
        set_english_layout()
        activate_one_c_window()

        print("\n→ Загружаю товары в «Реализация товаров»...")
        automate_data_entry(products_list)

        skipped = get_skipped_products()
        skipped_sum = get_total_sum(skipped)
        expected_sum = file_total - skipped_sum
        if skipped:
            print(f"\n⚠ Пропущено позиций без номенклатуры в 1С: {len(skipped)}")
            for item in skipped:
                print(f"  → {item}")
            print(f"💰 Ожидаемая сумма без пропусков: {expected_sum}")

        print("\n✅ Готово! Ввод завершён.")

        min_plausible = expected_sum * Decimal("0.5") if expected_sum > 0 else None
        actual_sum = read_total_from_1c(min_plausible=min_plausible)
        if actual_sum is not None:
            expected_m = _as_money(expected_sum)
            actual_m = _as_money(actual_sum)
            if actual_m == expected_m:
                print(f"✅ Сумма сошлась: {expected_m}")
            else:
                print(f"⚠ Сумма не сошлась! Расчётная: {expected_m}, в 1С: {actual_m}")
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
