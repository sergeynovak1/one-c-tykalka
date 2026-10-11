"""
Конфигурационные константы.
"""
# Путь к Excel: отчёт «Анализ контрагентов»
XLSX_FILE_PATTERN = 'C:/Users/novak/PycharmProjects/one-c-tykalka/*.xlsx'

# Chromium с remote debugging (вариант A)
CDP_URL = "http://127.0.0.1:9222"
# Стартовый URL веб-клиента 1С
ONE_C_START_URL = "https://msk1.1cfresh.com/a/ba/4099405/ru/"
# Признаки вкладки/страницы веб-клиента 1С
ONE_C_URL_MARKERS = ("1cfresh.com", "1c.ru", "4099405")
ONE_C_TITLE_MARKERS = ("1С:Предприятие", "Реализация товаров", "Бух Фаворит", "1C:Enterprise")

# Навигация по строке «Реализация товаров»:
# Добавить → номенклатура → Enter → клик Количество → клик Цена
NOMENCLATURE_ENTERS = 1
# Сколько первых позиций из Excel заполнять за запуск
FILL_ROWS_LIMIT = 5

# Задержки (мс)
AFTER_ADD_SETTLE_DELAY_MS = 250
NOMENCLATURE_INPUT_DELAY_MS = 500
# 1С сначала рисует «создать», потом может подгрузить совпадения
NOMENCLATURE_MISSING_RECHECK_DELAY_MS = 400
AFTER_NOMENCLATURE_SETTLE_MS = 700
FIELD_DELAY_MS = 120
BETWEEN_ROWS_DELAY_MS = 150
