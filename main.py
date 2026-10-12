"""
Главный модуль: парсинг Excel и заполнение строк в 1С (Playwright/CDP).
Сначала: python start_chromium.py → открой документ → python main.py
"""
from data_processor import as_money, process_excel_file, get_total_sum
from playwright_automation import run_fill_rows


def main():
    try:
        products_list = process_excel_file()

        if not products_list:
            print("\n⚠ Нет товаров для загрузки.")
            return

        file_total = get_total_sum(products_list)
        print(f"\n💰 Сумма по файлу (все позиции): {file_total}")

        print(f"\n🤖 Заполняю все {len(products_list)} строк через Playwright...")
        for i, item in enumerate(products_list, start=1):
            print(f"  {i}. {item}")

        skipped, expected = run_fill_rows(products_list)
        if skipped:
            skipped_sum = get_total_sum(skipped)
            print(f"\n⚠ Пропущено позиций без номенклатуры в 1С: {len(skipped)}")
            for item in skipped:
                print(f"  → {item}")
            print(f"💰 Сумма пропусков: {skipped_sum}")

        if expected is not None:
            print(f"\n💰 Итоговая ожидаемая сумма (с учётом базы в 1С): {as_money(expected)}")

    except FileNotFoundError as e:
        print(f"\n❌ Ошибка: {e}")
    except (ValueError, ConnectionError, RuntimeError, TimeoutError) as e:
        print(f"\n❌ Ошибка: {e}")


if __name__ == "__main__":
    main()
