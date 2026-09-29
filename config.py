"""
Конфигурационные константы.
"""
# Яндекс Браузер (окно может быть свёрнуто на момент запуска)
BROWSER_TITLE = "Яндекс"
# Признаки вкладки с веб-клиентом 1С в заголовке окна браузера
ONE_C_TAB_MARKERS = ("1С:Предприятие", "Бух Фаворит", "1cfresh")
# Сколько раз пробовать Ctrl+Tab в поисках вкладки 1С
MAX_BROWSER_TAB_SWITCHES = 15

# Путь к Excel: отчёт «Анализ контрагентов»
XLSX_FILE_PATTERN = 'C:/Users/novak/PycharmProjects/one-c-tykalka/Анализ контрагентов с 01.09.2026 по 15.09.2026 (1).xlsx'

# Навигация по строке «Реализация товаров»:
# Добавить → номенклатура → Enter → количество → Tab → цена → (снова Добавить)
NOMENCLATURE_ENTERS = 1
QUANTITY_TO_PRICE_TABS = 1

# Пути к изображениям для автоматизации
ADD_BUTTON_IMAGE = 'C:/Users/novak/PycharmProjects/one-c-tykalka/1c_images/add_button.PNG'
# Пункт «создать» в выпадающем списке = номенклатуры нет в базе
MISSING_NOMENCLATURE_IMAGE = 'C:/Users/novak/PycharmProjects/one-c-tykalka/1c_images/create_nomenclature.PNG'
TOTAL_SUM_IMAGE = 'C:/Users/novak/PycharmProjects/one-c-tykalka/1c_images/total_sum.PNG'
TABLE_IMAGE = 'C:/Users/novak/PycharmProjects/one-c-tykalka/1c_images/table.PNG'
# Индикатор загрузки/pending 1С (если файла нет — ждём только по курсору)
BUSY_IMAGE = 'C:/Users/novak/PycharmProjects/one-c-tykalka/1c_images/busy.PNG'

# Задержки (в секундах)
WINDOW_ACTIVATION_DELAY = 0.7
BROWSER_TAB_SWITCH_DELAY = 0.35
BETWEEN_ROWS_DELAY = 0.05
NOMENCLATURE_INPUT_DELAY = 0.3
FIELD_DELAY = 0.03
PASTE_AFTER_COPY_DELAY = 0.15
# Пауза после кликов по «Всего:», до Ctrl+C (иначе копируется не то поле)
TOTAL_SUM_BEFORE_COPY_DELAY = 0.5
# Сколько раз повторять чтение «Всего» / Ctrl+C при пустом или нестабильном буфере
TOTAL_SUM_READ_RETRIES = 5
COPY_RETRY_DELAY = 0.3
# Клик правее лейбла «Всего:», в само поле суммы (доля ширины картинки)
TOTAL_SUM_CLICK_X_RATIO = 0.75

# Ожидание, пока браузер/1С «подтупливает»
BUSY_POLL_INTERVAL = 0.2
BUSY_TIMEOUT = 60
# Сколько подряд опросов без «занято», чтобы считать UI готовым
BUSY_STABLE_POLLS = 3

# Интервалы ввода
TYPING_INTERVAL = 0.01

# Уровень уверенности для поиска изображений
IMAGE_CONFIDENCE = 0.7

# Доля записей для проверки суммы (0.1 = 10%, батч = 10% от общего числа записей)
BATCH_CHECK_PERCENT = 0.05
# Нижняя граница размера батча в штуках (батч не меньше этого значения)
BATCH_CHECK_MIN = 5

# Сколько раз повторять ввод батча при несовпадении суммы, прежде чем завершить работу
MAX_SUM_RETRY_ATTEMPTS = 3

# Ставка НДС для суммы «Всего» из 1С (сверка с расчётом из Excel).
TOTAL_SUM_VAT_RATE = "0"

# Ожидаемый процент ошибок при тестировании декоратора проверки сумм (0 = отключено).
# При > 0 в указанном % случаев вводит баг: пропуск записи или неправильная цена.
ERROR_INJECTION_PERCENT = 0
