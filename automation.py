"""
Модуль для автоматизации ввода данных в 1С.
"""
import pyautogui
import ctypes
import pygetwindow as gw
import time
import pyperclip
from config import (
    ONE_C_TITLE,
    ADD_BUTTON_IMAGE,
    CREATE_NOMENCLATURE_IMAGE,
    WINDOW_ACTIVATION_DELAY,
    BETWEEN_ROWS_DELAY,
    NOMENCLATURE_INPUT_DELAY,
    AFTER_CREATE_DELAY,
    AFTER_CTRL_ENTER_DELAY,
    FIELD_DELAY,
    QUANTITY_DELAY,
    AFTER_ENTER_DELAY,
    TYPING_INTERVAL,
    IMAGE_CONFIDENCE,
    DEFAULT_LAST_FIELDS_COUNT
)

def set_english_layout():
    # Загружаем библиотеку
    user32 = ctypes.WinDLL('user32', use_last_error=True)

    # Получаем текущий активный поток
    hwnd = user32.GetForegroundWindow()
    thread_id = user32.GetWindowThreadProcessId(hwnd, 0)
    klid = 0x409  # Английская раскладка (США) - 0x409

    # Загружаем раскладку и устанавливаем её
    kl = user32.LoadKeyboardLayoutW(str(klid), 1)
    user32.PostMessageW(hwnd, 0x50, 1, kl)


def activate_one_c_window():
    """
    Активирует окно 1С по заголовку.

    Raises:
        Exception: Если окно не найдено
    """
    # for w in pyautogui.getAllWindows():
    #     if w.title and ONE_C_TITLE in w.title:
    #         w.activate()
    #         break
    # time.sleep(WINDOW_ACTIVATION_DELAY)

    windows = gw.getWindowsWithTitle(ONE_C_TITLE)
    if windows:
        window = windows[0]
        if window.isMinimized:
            window.restore()
        window.activate()
        time.sleep(WINDOW_ACTIVATION_DELAY)
        return

    raise Exception(f"Окно с заголовком содержащим '{ONE_C_TITLE}' не найдено или не может быть активировано")


def click_add_button(is_first_row):
    """
    Нажимает кнопку "Добавить" в интерфейсе 1С.

    Raises:
        Exception: Если кнопка не найдена
    """
    location = pyautogui.locateOnScreen(ADD_BUTTON_IMAGE, confidence=IMAGE_CONFIDENCE)
    if location is None:
        raise Exception('Кнопка "Добавить" не найдена')
    pyautogui.click(location)
    if not is_first_row:
        pyautogui.click(location)


def paste_text(text):
    pyperclip.copy(text)
    time.sleep(0.1)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.1)


def fill_nomenclature(nomenclature):
    """
    Заполняет поле номенклатуры.

    Args:
        nomenclature (str): Наименование номенклатуры
    """
    pyautogui.press('del')
    paste_text(nomenclature)
    time.sleep(NOMENCLATURE_INPUT_DELAY)

    # Проверяем, нужно ли создать новую номенклатуру
    try:
        create_window = pyautogui.locateOnScreen(
            CREATE_NOMENCLATURE_IMAGE,
            confidence=IMAGE_CONFIDENCE
        )
        pyautogui.click(create_window)
        time.sleep(AFTER_CREATE_DELAY)
        pyautogui.hotkey('ctrl', 'enter')
        time.sleep(AFTER_CTRL_ENTER_DELAY)
    except pyautogui.ImageNotFoundException:
        pass

    pyautogui.press('enter')
    pyautogui.press('enter')
    time.sleep(FIELD_DELAY)


def fill_quantity(quantity):
    """
    Заполняет поле количества.

    Args:
        quantity (str): Количество
    """
    pyautogui.write(quantity, interval=TYPING_INTERVAL)
    pyautogui.hotkey('ctrl', 'enter')
    time.sleep(QUANTITY_DELAY)
    pyautogui.press('enter')
    time.sleep(AFTER_ENTER_DELAY)


def fill_price(price):
    """
    Заполняет поле цены.

    Args:
        price (str): Цена
    """
    pyautogui.press('del')
    pyautogui.write(price, interval=TYPING_INTERVAL)
    pyautogui.press('enter')


def fill_cost(cost):
    """
    Заполняет поле суммы.

    Args:
        cost (str): Сумма
    """
    pyautogui.press('del')
    pyautogui.write(cost, interval=TYPING_INTERVAL)
    pyautogui.press('enter')


def skip_default_fields():
    """
    Пропускает остальные поля по умолчанию.
    """
    for _ in range(DEFAULT_LAST_FIELDS_COUNT):
        pyautogui.press('enter')


def fill_product_row(nomenclature, quantity, price, cost, is_first_row=False):
    """
    Заполняет одну строку товара.
    """
    time.sleep(BETWEEN_ROWS_DELAY)

    # Нажимаем "Добавить" для каждой строки
    click_add_button(is_first_row)
    time.sleep(FIELD_DELAY)

    fill_nomenclature(nomenclature)
    fill_quantity(quantity)
    fill_price(price)
    fill_cost(cost)
    skip_default_fields()

    print('Строка добавлена')


def automate_data_entry(product_data):
    """
    Автоматизирует ввод данных в 1С.

    Args:
        product_data (list): Список кортежей (nomenclature, quantity, price, cost)
    """
    # Переводим на английскую клавиатуру
    set_english_layout()

    # Активируем окно 1С
    activate_one_c_window()

    # Заполняем строки
    for idx, (nomenclature, quantity, price, cost) in enumerate(product_data):
        fill_product_row(
            nomenclature,
            quantity,
            price,
            cost,
            is_first_row=(idx == 0)
        )
