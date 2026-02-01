"""
Главный модуль для запуска приложения.
Обрабатывает Excel файл и автоматизирует ввод данных в 1С.
"""
from data_processor import process_excel_file
from automation import automate_data_entry


def main():
    """
    Главная функция приложения.
    """
    try:
        # Обрабатываем Excel файл
        product_data = process_excel_file()

        # Автоматизируем ввод данных в 1С
        print("\n🤖 Начинаю автоматизацию ввода данных в 1С...")
        automate_data_entry(product_data)

        print("\n✅ Готово! Все данные успешно введены.")

    except FileNotFoundError as e:
        print(f"\n❌ Ошибка: {e}")
    except ValueError as e:
        print(f"\n❌ Ошибка: {e}")
    except Exception as e:
        print(f"\n❌ Произошла ошибка: {e}")


if __name__ == "__main__":
    main()