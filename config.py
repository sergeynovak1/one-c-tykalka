"""
Конфигурационные константы.
"""
ONE_C_TITLE = "Бухгалтерия"

REFUND_TYPE = "Возврат прихода"
RECEIPT_TYPE = "Приход"

# Если цена строго выше порога и кратна 10: при группировке и вводе «×10 шт.», цена ÷10
BULK_PRICE_THRESHOLD = 1000

# Путь к Excel файлам
XLSX_FILE_PATTERN = '~/Desktop/ОФД/*.xlsx'

# Пути к изображениям для автоматизации
ADD_BUTTON_IMAGE = 'C:/1c_images/add_button.PNG'
CREATE_NOMENCLATURE_IMAGE = 'C:/1c_images/create_nomenclature.PNG'
REFUND_BUTTON_IMAGE = 'C:/1c_images/refund_button.PNG'
PRODUCT_BUTTON_IMAGE = 'C:/1c_images/product_button.PNG'
TOTAL_SUM_IMAGE = 'C:/1c_images/total_sum.PNG'
TABLE_IMAGE = 'C:/1c_images/table.PNG'

# Задержки (в секундах)
WINDOW_ACTIVATION_DELAY = 0.7
BETWEEN_ROWS_DELAY = 0.05
NOMENCLATURE_INPUT_DELAY = 0.3
AFTER_CREATE_DELAY = 0.3
AFTER_CTRL_ENTER_DELAY = 0.5
FIELD_DELAY = 0.03
PASTE_AFTER_COPY_DELAY = 0.15

# Интервалы ввода
TYPING_INTERVAL = 0.01

# Уровень уверенности для поиска изображений
IMAGE_CONFIDENCE = 0.9

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
