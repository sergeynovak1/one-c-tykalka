"""
Модуль для автоматизации ввода данных в 1С.
"""
import pyautogui
from decimal import Decimal
import ctypes
import pygetwindow as gw
import time
import pyperclip
from config import (
    ONE_C_TITLE,
    ADD_BUTTON_IMAGE,
    CREATE_NOMENCLATURE_IMAGE,
    REFUND_BUTTON_IMAGE,
    PRODUCT_BUTTON_IMAGE,
    TOTAL_SUM_IMAGE,
    WINDOW_ACTIVATION_DELAY,
    BETWEEN_ROWS_DELAY,
    NOMENCLATURE_INPUT_DELAY,
    AFTER_CREATE_DELAY,
    AFTER_CTRL_ENTER_DELAY,
    FIELD_DELAY,
    PASTE_AFTER_COPY_DELAY,
    TYPING_INTERVAL,
    IMAGE_CONFIDENCE,
    BATCH_CHECK_SIZE,
)
from data_processor import to_decimal

# Кэш последнего прочитанного "Всего" из 1С (чтобы не читать дважды подряд)
_last_read_total = 0


def _read_and_cache_total():
    """Читает сумму из 1С и сохраняет в кэш."""
    global _last_read_total
    _last_read_total = read_total_from_1c()
    return _last_read_total


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


def click_refund_button():
    """
    Нажимает кнопку "Возвраты" в интерфейсе 1С.

    Raises:
        Exception: Если кнопка не найдена
    """
    location = pyautogui.locateOnScreen(REFUND_BUTTON_IMAGE, confidence=IMAGE_CONFIDENCE)
    if location is None:
        raise Exception('Кнопка "Возвраты" не найдена')
    pyautogui.click(location)
    time.sleep(WINDOW_ACTIVATION_DELAY)


def click_product_button():
    """
    Нажимает кнопку "Товары" в интерфейсе 1С.

    Raises:
        Exception: Если кнопка не найдена
    """
    location = pyautogui.locateOnScreen(PRODUCT_BUTTON_IMAGE, confidence=IMAGE_CONFIDENCE)
    if location is None:
        raise Exception('Кнопка "Товары" не найдена')
    pyautogui.click(location)
    time.sleep(WINDOW_ACTIVATION_DELAY)


def read_total_from_1c():
    """
    Кликает по полю «Всего:», считывает число из него (Ctrl+A, Ctrl+C) и возвращает Decimal.

    Returns:
        Decimal | None: Прочитанная сумма или None, если не удалось найти поле или распарсить
    """
    try:
        location = pyautogui.locateOnScreen(TOTAL_SUM_IMAGE, confidence=IMAGE_CONFIDENCE)
        if location is None:
            return None
        pyautogui.click(location)
        time.sleep(FIELD_DELAY)
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(PASTE_AFTER_COPY_DELAY)
        raw = pyperclip.paste().strip()
        return to_decimal(raw)
    except Exception:
            return None


def paste_text(text):
    """Вставляет текст через буфер. Перед Ctrl+V ждём, чтобы буфер точно обновился."""
    text = str(text).strip()
    z = text
    pyperclip.copy(text)
    time.sleep(PASTE_AFTER_COPY_DELAY)
    pyautogui.hotkey('ctrl', 'v')


def fill_nomenclature(nomenclature):
    """
    Заполняет поле номенклатуры.
    Сначала очищает поле (Del), вставляет текст через буфер.
    После ввода проверяет содержимое поля; при несовпадении очищает и вставляет ещё раз.

    Args:
        nomenclature (str): Наименование номенклатуры
    """
    expected = str(nomenclature).strip()
    pyautogui.press('del')
    paste_text(expected)
    time.sleep(NOMENCLATURE_INPUT_DELAY)

    # Проверка: копируем содержимое поля и сравниваем с ожидаемым
    pyautogui.hotkey('ctrl', 'a')
    pyautogui.hotkey('ctrl', 'c')
    actual = pyperclip.paste().strip()

    if actual != expected:
        pyautogui.press('del')
        paste_text(expected)
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
    pyautogui.press('enter')


def fill_price(price):
    """
    Заполняет поле цены.
    Сначала выделяет всё содержимое (Ctrl+A), затем ввод заменяет старую цену.
    После ввода проверяет содержимое поля; при несовпадении перезаписывает ещё раз.

    Args:
        price (str): Цена
    """
    expected = str(price).strip()
    pyautogui.hotkey('ctrl', 'a')
    pyautogui.write(expected, interval=TYPING_INTERVAL)

    # Проверка: копируем содержимое поля и сравниваем с ожидаемым
    pyautogui.hotkey('ctrl', 'a')
    pyautogui.hotkey('ctrl', 'c')
    actual = pyperclip.paste().strip()

    if actual != expected:
        pyautogui.hotkey('ctrl', 'a')
        pyautogui.write(expected, interval=TYPING_INTERVAL)

    pyautogui.press('enter')


def fill_product_row(nomenclature, quantity, price, is_first_row=False):
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


def _calc_expected_sum(product_data):
    """Считает ожидаемую сумму (цена * количество) по списку."""
    return sum(to_decimal(item[2]) * to_decimal(item[1]) for item in product_data)


def with_batch_sum_check(fn):
    """
    Декоратор: после каждых BATCH_CHECK_SIZE записей сравнивает
    ожидаемую сумму с суммой в 1С.
    """

    def wrapper(product_data, is_refund=False, **kwargs):
        global _last_read_total
        cumulative_expected = _last_read_total
        for i in range(0, len(product_data), BATCH_CHECK_SIZE):
            chunk = product_data[i : i + BATCH_CHECK_SIZE]
            fn(chunk, batch_offset=i, **kwargs)
            chunk_sum = _calc_expected_sum(chunk)
            cumulative_expected += -chunk_sum if is_refund else chunk_sum
            actual = _read_and_cache_total()
            records_count = i + len(chunk)
            if actual is not None:
                if actual == cumulative_expected:
                    print(f"✅ Проверка после {records_count} записей: сумма сошлась ({cumulative_expected})")
                else:
                    print(
                        f"⚠ После {records_count} записей: ожидалось {cumulative_expected}, в 1С: {actual}"
                    )
            else:
                print(f"⚠ Не удалось прочитать сумму из 1С после {records_count} записей")

    return wrapper


@with_batch_sum_check
def automate_data_entry(product_data, batch_offset=0, **kwargs):
    """
    Автоматизирует ввод данных в 1С.

    Args:
        product_data (list): Список кортежей (nomenclature, quantity, price, cost)
        batch_offset (int): Смещение для чанков (используется декоратором)
    """
    # Заполняем строки
    for idx, (nomenclature, quantity, price) in enumerate(product_data):
        fill_product_row(
            nomenclature,
            quantity,
            price,
            is_first_row=(batch_offset == 0 and idx == 0),
        )
