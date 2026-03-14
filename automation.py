"""
Модуль для автоматизации ввода данных в 1С.
"""
import pyautogui
import random
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
    TABLE_IMAGE,
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
    ERROR_INJECTION_PERCENT,
)
from data_processor import to_decimal

# Кэш последнего прочитанного "Всего" из 1С (чтобы не читать дважды подряд)
_last_read_total = 0


def _read_and_cache_total():
    """Читает сумму из 1С и сохраняет в кэш."""
    global _last_read_total
    _last_read_total = read_total_from_1c() or 0
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


def focus_table_and_navigate_rows():
    """
    Кликает по таблице отчёта, затем переходит на первую строку (Ctrl+Home)
    и на последнюю строку (Ctrl+End).

    Raises:
        Exception: Если изображение таблицы не найдено
    """
    location = pyautogui.locateOnScreen(TABLE_IMAGE, confidence=IMAGE_CONFIDENCE)
    if location is None:
        raise Exception('Таблица отчёта (table.png) не найдена')
    pyautogui.click(location)
    time.sleep(FIELD_DELAY)
    # Ctrl+Home — переход на самую первую строку отчёта
    pyautogui.hotkey('ctrl', 'home')
    time.sleep(FIELD_DELAY)
    # Ctrl+End — переход на самую последнюю строку отчёта
    pyautogui.hotkey('ctrl', 'end')


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

    if not actual or actual != expected:
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


def _find_and_report_missing_rows(expected_rows, table_rows):
    """
    Сравнивает ожидаемые строки с полученными из таблицы.
    Находит пропущенные строки и выводит в консоль тройку (наименование, количество, цена).
    Возвращает True, если найдена хотя бы одна пропущенная строка.
    """
    table_copy = list(table_rows)
    has_missing = False
    for exp in expected_rows:
        exp_norm = (str(exp[0]).strip(), str(exp[1]).strip(), str(exp[2]).strip())
        found = False
        for i, tbl in enumerate(table_copy):
            tbl_norm = (str(tbl[0]).strip(), str(tbl[1]).strip(), str(tbl[2]).strip())
            if exp_norm == tbl_norm:
                table_copy.pop(i)
                found = True
                break
        if not found:
            has_missing = True
            print(f"  [ПРОПУЩЕНА] наименование={exp[0]}, количество={exp[1]}, цена={exp[2]}")
    return has_missing


def _delete_last_n_rows(n):
    """
    Удаляет последние n строк таблицы через Del.
    Снимает выделение, выделяет последние n строк (Ctrl+End, Shift+Up n-1 раз) и нажимает Del.
    """
    if n <= 0:
        return
    focus_table_and_navigate_rows()
    time.sleep(FIELD_DELAY)
    for _ in range(n):
        pyautogui.press('del')


def _diagnose_sum_mismatch(added_count: int):
    """
    При несовпадении суммы: фокус на таблицу, перейти в левую ячейку,
    Ctrl+A, получить содержимое, проверить пропуски и вывести в консоль.
    Возвращает True, если найдены пропущенные строки.
    """
    focus_table_and_navigate_rows()
    time.sleep(FIELD_DELAY)
    pyautogui.hotkey('ctrl', 'a')
    pyautogui.hotkey('ctrl', 'c')
    time.sleep(PASTE_AFTER_COPY_DELAY)
    raw = pyperclip.paste().strip()
    lines = raw.split('\n')
    return len(lines) % added_count or BATCH_CHECK_SIZE


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
                    n_to_delete = _diagnose_sum_mismatch(len(chunk))
                    if n_to_delete:
                        print(f"  Удаляю {n_to_delete} записей и заполняю заново...")
                        focus_table_and_navigate_rows()
                        time.sleep(FIELD_DELAY)
                        _delete_last_n_rows(n_to_delete)
                        time.sleep(FIELD_DELAY)
                        fn(chunk, batch_offset=i, **kwargs)
                        actual_retry = _read_and_cache_total()
                        if actual_retry is not None and actual_retry == cumulative_expected:
                            print(f"✅ После повторного ввода сумма сошлась ({cumulative_expected})")
                        else:
                            print(f"⚠ После повторного ввода сумма: ожидалось {cumulative_expected}, в 1С: {actual_retry}")
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
        if ERROR_INJECTION_PERCENT and random.random() < ERROR_INJECTION_PERCENT:
            if random.random() < 0.5:
                # Пропуск записи — не вводим строку
                print(f"  [TEST] Пропуск записи {batch_offset + idx + 1}: {nomenclature}")
                continue
            else:
                # Неправильная цена — добавляем/вычитаем случайную величину
                price_dec = to_decimal(price)
                wrong_price = str(price_dec + (random.choice([-1, 1]) * (abs(price_dec) * Decimal("0.1") + 1)))
                print(f"  [TEST] Неправильная цена для {nomenclature}: {price} -> {wrong_price}")
                price = wrong_price

        fill_product_row(
            nomenclature,
            quantity,
            price,
            is_first_row=(batch_offset == 0 and idx == 0),
        )
