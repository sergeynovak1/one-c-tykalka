"""
Конфигурационные константы.
"""
ONE_C_TITLE = "Бухгалтерия"

REFUND_TYPE = "Возврат прихода"
RECEIPT_TYPE = "Приход"

# Путь к Excel файлам
XLSX_FILE_PATTERN = '~/Desktop/ОФД/*.xlsx'

# Пути к изображениям для автоматизации
ADD_BUTTON_IMAGE = 'C:/1c_images/add_button.PNG'
CREATE_NOMENCLATURE_IMAGE = 'C:/1c_images/create_nomenclature.PNG'
REFUND_BUTTON_IMAGE = 'C:/1c_images/refund_button.PNG'
PRODUCT_BUTTON_IMAGE = 'C:/1c_images/product_button.PNG'
TOTAL_SUM_IMAGE = 'C:/1c_images/total_sum.PNG'

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
