"""
Модуль для автоматизации ввода данных в 1С.
"""
import sys
import os
import pyautogui
import random
from decimal import Decimal
import ctypes
import pygetwindow as gw
import time
import pyperclip
from config import (
    BROWSER_TITLE,
    ONE_C_TAB_MARKERS,
    MAX_BROWSER_TAB_SWITCHES,
    ADD_BUTTON_IMAGE,
    MISSING_NOMENCLATURE_IMAGE,
    TOTAL_SUM_IMAGE,
    TABLE_IMAGE,
    BUSY_IMAGE,
    WINDOW_ACTIVATION_DELAY,
    BROWSER_TAB_SWITCH_DELAY,
    BETWEEN_ROWS_DELAY,
    NOMENCLATURE_INPUT_DELAY,
    FIELD_DELAY,
    PASTE_AFTER_COPY_DELAY,
    TOTAL_SUM_BEFORE_COPY_DELAY,
    BUSY_POLL_INTERVAL,
    BUSY_TIMEOUT,
    BUSY_STABLE_POLLS,
    TYPING_INTERVAL,
    IMAGE_CONFIDENCE,
    BATCH_CHECK_PERCENT,
    BATCH_CHECK_MIN,
    MAX_SUM_RETRY_ATTEMPTS,
    ERROR_INJECTION_PERCENT,
    TOTAL_SUM_VAT_RATE,
    NOMENCLATURE_ENTERS,
    QUANTITY_TO_PRICE_TABS,
)
from data_processor import to_decimal

# Кэш последнего прочитанного "Всего" из 1С (чтобы не читать дважды подряд)
_last_read_total = 0

# WinAPI константы курсора ожидания
_IDC_WAIT = 32514
_IDC_APPSTARTING = 32650


def _cursor_is_busy():
    """True, если системный курсор — песочные часы / appstarting."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class CURSORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint),
            ("flags", ctypes.c_uint),
            ("hCursor", ctypes.c_void_p),
            ("ptScreenPos", POINT),
        ]

    info = CURSORINFO()
    info.cbSize = ctypes.sizeof(CURSORINFO)
    if not user32.GetCursorInfo(ctypes.byref(info)):
        return False

    wait_cursor = user32.LoadCursorW(None, _IDC_WAIT)
    appstarting_cursor = user32.LoadCursorW(None, _IDC_APPSTARTING)
    return info.hCursor in (wait_cursor, appstarting_cursor)


def _busy_image_visible():
    """True, если на экране виден индикатор загрузки (busy.PNG)."""
    if not BUSY_IMAGE or not os.path.isfile(BUSY_IMAGE):
        return False
    try:
        return pyautogui.locateOnScreen(BUSY_IMAGE, confidence=IMAGE_CONFIDENCE) is not None
    except pyautogui.ImageNotFoundException:
        return False


def is_ui_busy():
    """Браузер/1С заняты: курсор ожидания или картинка pending/загрузки."""
    return _cursor_is_busy() or _busy_image_visible()


def wait_while_busy(timeout=None, reason=""):
    """
    Ждёт, пока UI не перестанет быть «занятым» (pending/загрузка).
    Считает готовым после нескольких подряд опросов без busy.
    """
    timeout = BUSY_TIMEOUT if timeout is None else timeout
    deadline = time.time() + timeout
    stable = 0
    announced = False

    while time.time() < deadline:
        if is_ui_busy():
            stable = 0
            if not announced:
                suffix = f" ({reason})" if reason else ""
                print(f"⏳ Жду, пока 1С/браузер загрузится{suffix}...")
                announced = True
            time.sleep(BUSY_POLL_INTERVAL)
            continue

        stable += 1
        if stable >= BUSY_STABLE_POLLS:
            return
        time.sleep(BUSY_POLL_INTERVAL)

    raise TimeoutError(
        f"1С/браузер всё ещё заняты после {timeout} с"
        + (f" ({reason})" if reason else "")
    )


def _send_ctrl_combo_vk(vk_code):
    """
    Надежно отправляет сочетание Ctrl+<key> через WinAPI.
    Используется как fallback, когда pyautogui иногда не передает Home/End.
    """
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    keyup = 0x0002
    vk_ctrl = 0x11
    user32.keybd_event(vk_ctrl, 0, 0, 0)
    user32.keybd_event(vk_code, 0, 0, 0)
    user32.keybd_event(vk_code, 0, keyup, 0)
    user32.keybd_event(vk_ctrl, 0, keyup, 0)


def _navigate_table_to_edges():
    """
    Переходит к первой и последней строкам таблицы.
    Сначала пробует pyautogui, затем дублирует ввод через WinAPI.
    """
    # Ctrl+Home — переход на первую строку.
    # pyautogui.hotkey("ctrl", "home")
    # time.sleep(FIELD_DELAY)
    _send_ctrl_combo_vk(0x24)  # VK_HOME
    time.sleep(FIELD_DELAY)
    # Ctrl+End — переход на последнюю строку.
    # pyautogui.hotkey("ctrl", "end")
    # time.sleep(FIELD_DELAY)
    _send_ctrl_combo_vk(0x23)  # VK_END


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


def _force_restore_and_foreground(window):
    """Разворачивает свёрнутое окно на весь экран и выводит его на передний план."""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    hwnd = int(window._hWnd)
    sw_restore = 9
    sw_maximize = 3

    user32.ShowWindow(hwnd, sw_restore)
    if window.isMinimized:
        window.restore()

    user32.ShowWindow(hwnd, sw_maximize)
    try:
        window.maximize()
    except Exception:
        pass

    foreground = user32.GetForegroundWindow()
    if foreground == hwnd:
        return

    current_thread = user32.GetWindowThreadProcessId(foreground, 0)
    target_thread = user32.GetWindowThreadProcessId(hwnd, 0)
    my_thread = kernel32.GetCurrentThreadId()

    user32.AttachThreadInput(my_thread, current_thread, True)
    user32.AttachThreadInput(my_thread, target_thread, True)
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    user32.AttachThreadInput(my_thread, target_thread, False)
    user32.AttachThreadInput(my_thread, current_thread, False)

    try:
        window.activate()
    except Exception:
        pass


def _find_yandex_browser_window():
    """
    Ищет окно Яндекс Браузера (в т.ч. свёрнутое).
    Предпочитает окно, в заголовке которого уже видна вкладка 1С.
    """
    windows = [w for w in gw.getAllWindows() if w.title and BROWSER_TITLE in w.title]
    if not windows:
        raise Exception(
            f"Яндекс Браузер не найден (заголовок должен содержать '{BROWSER_TITLE}'). "
            f"Откройте браузер со вкладкой 1С и сверните его перед запуском."
        )

    for marker in ONE_C_TAB_MARKERS:
        for window in windows:
            if marker in window.title:
                return window
    return windows[0]


def _window_has_one_c_tab(window):
    title = window.title or ""
    return any(marker in title for marker in ONE_C_TAB_MARKERS)


def _switch_to_one_c_browser_tab(window):
    """
    Переключает вкладки браузера (Ctrl+Tab), пока в заголовке не появится 1С.
    """
    if _window_has_one_c_tab(window):
        return

    for _ in range(MAX_BROWSER_TAB_SWITCHES):
        pyautogui.hotkey("ctrl", "tab")
        time.sleep(BROWSER_TAB_SWITCH_DELAY)
        # pygetwindow обновляет title у того же объекта
        if _window_has_one_c_tab(window):
            return

    raise Exception(
        "Во вкладках Яндекс Браузера не найдена вкладка 1С "
        f"(ожидались маркеры: {', '.join(ONE_C_TAB_MARKERS)})"
    )


def activate_one_c_window():
    """
    Разворачивает свёрнутый Яндекс Браузер и активирует вкладку с 1С.
    Нужный документ внутри 1С уже должен быть открыт.

    Raises:
        Exception: Если браузер или вкладка 1С не найдены
    """
    window = _find_yandex_browser_window()
    _force_restore_and_foreground(window)
    time.sleep(WINDOW_ACTIVATION_DELAY)
    _switch_to_one_c_browser_tab(window)
    time.sleep(BROWSER_TAB_SWITCH_DELAY)
    wait_while_busy(reason="после открытия браузера")


def click_add_button(is_first_row):
    """
    Нажимает кнопку "Добавить" в интерфейсе 1С.

    Raises:
        Exception: Если кнопка не найдена
    """
    location = pyautogui.locateOnScreen(ADD_BUTTON_IMAGE, confidence=IMAGE_CONFIDENCE)
    if location is None:
        raise Exception('Кнопка "Добавить" не найдена')
    wait_while_busy(reason="перед «Добавить»")
    pyautogui.click(location)
    if not is_first_row:
        pyautogui.click(location)
    wait_while_busy(reason="после «Добавить»")


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
    _navigate_table_to_edges()


def _normalize_read_total(raw: Decimal) -> Decimal:
    """Если TOTAL_SUM_VAT_RATE > 0, сумма из 1С трактуется как с НДС: делим на (1 + ставка)."""
    rate = to_decimal(TOTAL_SUM_VAT_RATE)
    if rate == 0:
        return raw
    divisor = Decimal("1") + rate
    if divisor == 0:
        return raw
    return raw / divisor


def read_total_from_1c():
    """
    Кликает по полю «Всего:» (клик → пауза → два даблклика), копирует число (Ctrl+C).

    Учёт НДС задаётся в config: TOTAL_SUM_VAT_RATE (0 или, например, 0.22).

    Returns:
        Decimal | None: Сумма для сравнения с расчётом или None, если не удалось найти поле
    """
    wait_while_busy(reason="перед чтением «Всего»")
    location = pyautogui.locateOnScreen(TOTAL_SUM_IMAGE, confidence=IMAGE_CONFIDENCE)
    if location is None:
        return None
    pyautogui.click(location)
    time.sleep(TOTAL_SUM_BEFORE_COPY_DELAY)
    for _ in range(3):
        pyautogui.doubleClick(location)
        time.sleep(FIELD_DELAY)
    time.sleep(TOTAL_SUM_BEFORE_COPY_DELAY)
    pyautogui.hotkey('ctrl', 'c')
    time.sleep(PASTE_AFTER_COPY_DELAY)
    raw = pyperclip.paste().strip()
    parsed = to_decimal(raw)
    return _normalize_read_total(parsed)


def paste_text(text):
    """Вставляет текст через буфер. Перед Ctrl+V ждём, чтобы буфер точно обновился."""
    text = str(text).strip()
    z = text
    pyperclip.copy(text)
    time.sleep(PASTE_AFTER_COPY_DELAY)
    pyautogui.hotkey('ctrl', 'v')


def _ensure_nomenclature_exists(nomenclature):
    """
    Если в выпадающем списке есть пункт создания — номенклатуры нет в базе.
    Raises:
        ValueError: с именем отсутствующей номенклатуры
    """
    try:
        found = pyautogui.locateOnScreen(
            MISSING_NOMENCLATURE_IMAGE,
            confidence=IMAGE_CONFIDENCE,
        )
    except pyautogui.ImageNotFoundException:
        found = None
    if found is not None:
        raise ValueError(f"Номенклатура не найдена в 1С: {nomenclature}")


def fill_nomenclature(nomenclature):
    """
    Заполняет поле номенклатуры (создание новой не выполняется).
    Если номенклатуры нет в базе — ошибка с её именем.
    Затем Enter переходит к количеству.

    Args:
        nomenclature (str): Наименование номенклатуры
    """
    expected = str(nomenclature).strip()
    pyautogui.press('del')
    paste_text(expected)
    time.sleep(NOMENCLATURE_INPUT_DELAY)

    _ensure_nomenclature_exists(expected)

    # Проверка: копируем содержимое поля и сравниваем с ожидаемым
    pyautogui.hotkey('ctrl', 'a')
    pyautogui.hotkey('ctrl', 'c')
    actual = pyperclip.paste().strip()

    if not actual or actual != expected:
        pyautogui.press('del')
        paste_text(expected)
        time.sleep(NOMENCLATURE_INPUT_DELAY)
        _ensure_nomenclature_exists(expected)

    for _ in range(NOMENCLATURE_ENTERS):
        pyautogui.press('enter')
        time.sleep(FIELD_DELAY)


def fill_quantity(quantity):
    """
    Заполняет поле количества и Tab'ом переходит к цене.

    Args:
        quantity (str): Количество
    """
    pyautogui.write(quantity, interval=TYPING_INTERVAL)
    for _ in range(QUANTITY_TO_PRICE_TABS):
        pyautogui.press('tab')
        time.sleep(FIELD_DELAY)


def fill_price(price):
    """
    Заполняет поле цены. Дальше строка не ведётся — следующая начнётся с «Добавить».

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


def _last_batch_expected_vs_actual(batch_offset: int, expected_rows: int) -> tuple[int, int]:
    """
    Сравнивает ожидание по файлу с фактом в таблице для последнего батча.

    Предполагается, что до начала батча в таблице было batch_offset строк
    (как индекс начала чанка в product_data). Тогда хвост таблицы после батча —
    это все строки с индекса batch_offset; их число и есть факт.

    Args:
        batch_offset: Сколько строк в таблице должно было быть до этого батча.
        expected_rows: Сколько строк должен добавить батч по файлу (len(chunk)).

    Returns:
        (expected_rows, actual_rows) — по файлу и по факту в таблице для этого хвоста.
        Удалять нужно actual_rows последних строк (при дублях actual > expected).
    """
    if expected_rows <= 0:
        return (0, 0)
    focus_table_and_navigate_rows()
    time.sleep(FIELD_DELAY)
    pyautogui.hotkey('ctrl', 'a')
    pyautogui.hotkey('ctrl', 'c')
    time.sleep(PASTE_AFTER_COPY_DELAY)
    raw = pyperclip.paste().strip()
    lines = raw.split('\n')
    actual_rows = max(0, len(lines) - batch_offset)
    return (expected_rows, actual_rows)


def with_batch_sum_check(fn):
    """
    Декоратор: после каждых batch_size записей сравнивает
    ожидаемую сумму с суммой в 1С.
    batch_size вычисляется как BATCH_CHECK_PERCENT от общего числа записей, но не меньше BATCH_CHECK_MIN.
    """

    def wrapper(product_data, **kwargs):
        global _last_read_total
        cumulative_expected = _last_read_total
        batch_size = max(BATCH_CHECK_MIN, int(len(product_data) * BATCH_CHECK_PERCENT))
        for i in range(0, len(product_data), batch_size):
            chunk = product_data[i : i + batch_size]
            fn(chunk, batch_offset=i, **kwargs)
            chunk_sum = _calc_expected_sum(chunk)
            cumulative_expected += chunk_sum
            actual = _read_and_cache_total()
            records_count = i + len(chunk)
            if actual is not None:
                if actual == cumulative_expected:
                    print(f"✅ Проверка после {records_count} записей: сумма сошлась ({cumulative_expected})")
                else:
                    print(
                        f"⚠ После {records_count} записей: ожидалось {cumulative_expected}, в 1С: {actual}"
                    )
                    for attempt in range(1, MAX_SUM_RETRY_ATTEMPTS + 1):
                        exp_rows, act_rows = _last_batch_expected_vs_actual(i, len(chunk))
                        if act_rows > 0:
                            print(
                                f"  Попытка {attempt}/{MAX_SUM_RETRY_ATTEMPTS}: по файлу ожидалось "
                                f"{exp_rows} строк, в таблице {act_rows} — удаляю {act_rows} и ввожу заново {exp_rows}..."
                            )
                            focus_table_and_navigate_rows()
                            time.sleep(FIELD_DELAY)
                            _delete_last_n_rows(act_rows)
                            time.sleep(FIELD_DELAY)
                        else:
                            print(f"  Попытка {attempt}/{MAX_SUM_RETRY_ATTEMPTS}: в батч не добавилось ни одной записи, повторяю ввод...")
                        fn(chunk, batch_offset=i, **kwargs)
                        actual_retry = _read_and_cache_total()
                        if actual_retry is not None and actual_retry == cumulative_expected:
                            print(f"✅ После повторного ввода сумма сошлась ({cumulative_expected})")
                            break
                        print(f"⚠ После попытки {attempt}: ожидалось {cumulative_expected}, в 1С: {actual_retry}")
                    else:
                        print(f"❌ Сумма не сошлась после {MAX_SUM_RETRY_ATTEMPTS} попыток. Завершение работы.")
                        sys.exit(1)
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
