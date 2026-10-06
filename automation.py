"""
Модуль для автоматизации ввода данных в 1С.
"""
import sys
import os
import re
import pyautogui
import random
from decimal import Decimal, InvalidOperation
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
    AFTER_ADD_SETTLE_DELAY,
    NOMENCLATURE_MISSING_RECHECK_DELAY,
    FIELD_DELAY,
    PASTE_AFTER_COPY_DELAY,
    TOTAL_SUM_BEFORE_COPY_DELAY,
    TOTAL_SUM_READ_RETRIES,
    COPY_RETRY_DELAY,
    TOTAL_SUM_CLICK_X_RATIO,
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
from data_processor import parse_total_text, to_decimal

# Кэш последнего прочитанного "Всего" из 1С (чтобы не читать дважды подряд)
_last_read_total = 0
# Пропущенные позиции (номенклатуры нет в 1С) — не входят в ожидаемую сумму
_skipped_products = []
# Пропуски внутри текущего вызова automate_data_entry (одного чанка)
_chunk_skipped = []
# Последние успешные координаты клика по иконке/заголовку таблицы
_table_click_point = None
# Сколько раз искать table.png, если после «Всего»/скролла картинка временно не матчится
TABLE_LOCATE_RETRIES = 5
TABLE_LOCATE_RETRY_DELAY = 0.35
# На каждой неудачной попытке confidence уменьшается на этот шаг
TABLE_LOCATE_CONFIDENCE_STEP = 0.05
# Нижняя граница confidence при поиске таблицы
TABLE_LOCATE_MIN_CONFIDENCE = 0.75

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


def _as_money(value) -> Decimal:
    """Округление до копеек — как в поле «Всего» 1С."""
    return to_decimal(value).quantize(Decimal("0.01"))


def _copy_to_clipboard(select_all=False):
    """
    Ctrl+A (опционально) + Ctrl+C через pyautogui, с повторами.
    Returns:
        str | None: текст из буфера или None, если копирование не сработало
    """
    for attempt in range(1, TOTAL_SUM_READ_RETRIES + 1):
        before = str(pyperclip.paste() or "")
        if select_all:
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(FIELD_DELAY)
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(COPY_RETRY_DELAY)
        text = str(pyperclip.paste() or "").strip()
        # Успех: буфер изменился или похож на число (не остался старый мусор)
        if text and (text != before.strip() or _looks_like_amount(text)):
            return text
        print(f"⚠ Ctrl+C не скопировал данные (попытка {attempt}/{TOTAL_SUM_READ_RETRIES})")
        time.sleep(COPY_RETRY_DELAY)
    return None


def _looks_like_amount(text: str) -> bool:
    """Грубая проверка, что в буфере денежная сумма, а не маркер/мусор."""
    s = text.strip().replace("\xa0", "").replace(" ", "")
    if not s:
        return False
    # допускаем 1234,56 / 1234.56 / -12
    return bool(re.fullmatch(r"-?\d+[.,]?\d*", s)) or bool(
        re.fullmatch(r"-?\d{1,3}([ .,]\d{3})+([.,]\d+)?", s)
    )


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


def _read_and_cache_total(min_plausible=None):
    """Читает сумму из 1С и сохраняет в кэш."""
    global _last_read_total
    value = read_total_from_1c(min_plausible=min_plausible)
    _last_read_total = value if value is not None else 0
    return value


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
    # Новая строка появляется не мгновенно — иначе ввод уходит не в номенклатуру
    time.sleep(AFTER_ADD_SETTLE_DELAY)


def _try_locate_table(confidence):
    """locateOnScreen для TABLE_IMAGE; None если не найдено."""
    try:
        return pyautogui.locateOnScreen(TABLE_IMAGE, confidence=confidence)
    except pyautogui.ImageNotFoundException:
        return None


def _click_point_from_location(location):
    """Центр бокса locateOnScreen → (x, y)."""
    return (
        location.left + location.width // 2,
        location.top + location.height // 2,
    )


def _locate_table_click_point(nudge_scroll=True):
    """
    Ищет иконку/заголовок таблицы на экране.
    После чтения «Всего» или при длинной таблице locate иногда мигает —
    поэтому ретраи со снижением confidence на шаг и кэш координат.

    Args:
        nudge_scroll: если True, на неудачной попытке жмёт PageUp
            (перед первым вводом лучше False — иначе сбивается фокус).
    """
    global _table_click_point

    wait_while_busy(reason="перед фокусом таблицы")

    confidence = float(IMAGE_CONFIDENCE)
    for attempt in range(1, TABLE_LOCATE_RETRIES + 1):
        location = _try_locate_table(confidence)
        if location is not None:
            point = _click_point_from_location(location)
            _table_click_point = point
            return point

        next_confidence = max(
            TABLE_LOCATE_MIN_CONFIDENCE,
            confidence - TABLE_LOCATE_CONFIDENCE_STEP,
        )
        if next_confidence < confidence:
            print(
                f"⚠ table.png не найден (попытка {attempt}/{TABLE_LOCATE_RETRIES}), "
                f"confidence {confidence:.2f} → {next_confidence:.2f}"
            )
            confidence = next_confidence
        elif attempt < TABLE_LOCATE_RETRIES:
            print(
                f"⚠ table.png не найден (попытка {attempt}/{TABLE_LOCATE_RETRIES}), "
                f"confidence {confidence:.2f}"
            )

        if attempt < TABLE_LOCATE_RETRIES:
            # Иногда шапка уезжает после скролла — пробуем поднять таблицу
            if nudge_scroll:
                pyautogui.press('pageup')
            time.sleep(TABLE_LOCATE_RETRY_DELAY)

    if _table_click_point is not None:
        print(
            "⚠ table.png не найден на экране — кликаю по запомненным координатам таблицы"
        )
        return _table_click_point

    # Запасной вариант: таблица обычно под кнопкой «Добавить»
    try:
        add_loc = pyautogui.locateOnScreen(ADD_BUTTON_IMAGE, confidence=IMAGE_CONFIDENCE)
    except pyautogui.ImageNotFoundException:
        add_loc = None
    if add_loc is not None:
        point = (
            add_loc.left + add_loc.width // 2,
            add_loc.top + add_loc.height + 40,
        )
        print("⚠ table.png не найден — кликаю под кнопкой «Добавить»")
        _table_click_point = point
        return point

    raise Exception('Таблица отчёта (table.png) не найдена')


def focus_table_and_navigate_rows():
    """
    Кликает по таблице отчёта, затем переходит на первую строку (Ctrl+Home)
    и на последнюю строку (Ctrl+End).

    Raises:
        Exception: Если изображение таблицы не найдено и нет запасной точки клика
    """
    x, y = _locate_table_click_point()
    pyautogui.click(x, y)
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


def _click_total_sum_field(location):
    """Кликает в поле суммы справа от лейбла «Всего:», не по самому тексту."""
    x = location.left + int(location.width * TOTAL_SUM_CLICK_X_RATIO)
    y = location.top + location.height // 2
    pyautogui.click(x, y)
    return x, y


def read_total_from_1c(min_plausible=None):
    """
    Кликает по полю «Всего:», Ctrl+A, Ctrl+C (с повторами).
    Сравнивает с 1С по копейкам.

    Args:
        min_plausible: если задано, отбрасывает слишком маленькие значения.

    Returns:
        Decimal | None
    """
    wait_while_busy(reason="перед чтением «Всего»")
    location = pyautogui.locateOnScreen(TOTAL_SUM_IMAGE, confidence=IMAGE_CONFIDENCE)
    if location is None:
        return None

    last_ok = None
    for attempt in range(1, TOTAL_SUM_READ_RETRIES + 1):
        x, y = _click_total_sum_field(location)
        time.sleep(TOTAL_SUM_BEFORE_COPY_DELAY)
        pyautogui.doubleClick(x, y)
        time.sleep(FIELD_DELAY)
        time.sleep(TOTAL_SUM_BEFORE_COPY_DELAY)

        raw = _copy_to_clipboard(select_all=True)
        if raw is None:
            print(f"⚠ Не удалось скопировать «Всего» (попытка {attempt}/{TOTAL_SUM_READ_RETRIES})")
            continue

        try:
            parsed_amount = parse_total_text(raw)
        except (InvalidOperation, ValueError):
            parsed_amount = None
        if parsed_amount is None:
            preview = " ".join(str(raw).split())
            if len(preview) > 160:
                preview = preview[:160] + "…"
            print(
                f"⚠ «Всего» скопировалось не числом "
                f"(попытка {attempt}/{TOTAL_SUM_READ_RETRIES}): {preview}"
            )
            continue

        parsed = _as_money(_normalize_read_total(parsed_amount))
        if min_plausible is not None and parsed < _as_money(min_plausible):
            print(
                f"⚠ Подозрительно малое «Всего»: {parsed} "
                f"(ожидали ≥ {_as_money(min_plausible)}), повтор чтения..."
            )
            last_ok = None
            time.sleep(COPY_RETRY_DELAY)
            continue

        if last_ok is not None and parsed == last_ok:
            return parsed
        last_ok = parsed
        time.sleep(COPY_RETRY_DELAY)

    return last_ok


def get_skipped_products():
    """Позиции, пропущенные из‑за отсутствия номенклатуры в 1С."""
    return list(_skipped_products)


def clear_skipped_products():
    global _skipped_products
    _skipped_products = []


def _nomenclature_missing_on_screen():
    """True, если в выпадающем списке виден пункт создания (= номенклатуры нет)."""
    try:
        found = pyautogui.locateOnScreen(
            MISSING_NOMENCLATURE_IMAGE,
            confidence=IMAGE_CONFIDENCE,
        )
    except pyautogui.ImageNotFoundException:
        found = None
    return found is not None


def _nomenclature_confirmed_missing():
    """
    1С сначала рисует «создать», потом подгружает совпадения.
    Считаем пропуском только если пункт остался после ожидания поиска.
    """
    if not _nomenclature_missing_on_screen():
        return False
    time.sleep(NOMENCLATURE_MISSING_RECHECK_DELAY)
    wait_while_busy(reason="пока ищется номенклатура")
    return _nomenclature_missing_on_screen()


def _read_active_field():
    """Ctrl+A/C из текущего поля. Буфер сначала очищаем, чтобы не принять старую вставку."""
    pyperclip.copy("")
    time.sleep(PASTE_AFTER_COPY_DELAY)
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(FIELD_DELAY)
    pyautogui.hotkey('ctrl', 'c')
    time.sleep(COPY_RETRY_DELAY)
    return str(pyperclip.paste() or "").strip()


def _restore_table_focus():
    """Возвращает фокус в таблицу после клика по «Всего» — без Ctrl+Home/End."""
    if _table_click_point is not None:
        pyautogui.click(*_table_click_point)
        time.sleep(FIELD_DELAY)
        return
    try:
        x, y = _locate_table_click_point(nudge_scroll=False)
        pyautogui.click(x, y)
        time.sleep(FIELD_DELAY)
    except Exception:
        pass


def _cancel_incomplete_row():
    """
    Закрывает выпадающий список и удаляет недозаполненную строку
    так же, как при ретрае батча: клик по иконке/заголовку таблицы →
    Ctrl+Home/End → Del на последней строке.
    """
    pyautogui.press('esc')
    time.sleep(FIELD_DELAY)
    pyautogui.press('esc')
    time.sleep(FIELD_DELAY)
    _delete_last_n_rows(1)


def paste_text(text):
    """Вставляет текст через буфер. Перед Ctrl+V ждём, чтобы буфер точно обновился."""
    text = str(text).strip()
    pyperclip.copy(text)
    time.sleep(PASTE_AFTER_COPY_DELAY)
    pyautogui.hotkey('ctrl', 'v')


def fill_nomenclature(nomenclature):
    """
    Заполняет поле номенклатуры (создание новой не выполняется).

    Returns:
        bool: True если номенклатура найдена и выбрана, False если её нет в базе.
    """
    expected = str(nomenclature).strip()
    wait_while_busy(reason="перед вводом номенклатуры")
    pyautogui.press('del')
    paste_text(expected)
    time.sleep(NOMENCLATURE_INPUT_DELAY)
    wait_while_busy(reason="после ввода номенклатуры")

    if _nomenclature_confirmed_missing():
        return False

    actual = _read_active_field()
    if not actual or actual != expected:
        pyautogui.press('del')
        paste_text(expected)
        time.sleep(NOMENCLATURE_INPUT_DELAY)
        wait_while_busy(reason="после повторного ввода номенклатуры")
        if _nomenclature_confirmed_missing():
            return False

    for _ in range(NOMENCLATURE_ENTERS):
        pyautogui.press('enter')
        time.sleep(FIELD_DELAY)
    # Пока 1С выбирает товар, фокус ещё в названии — количество/цена уедут туда же
    wait_while_busy(reason="после выбора номенклатуры")
    time.sleep(FIELD_DELAY)
    return True


def fill_quantity(quantity):
    """
    Заполняет поле количества и Tab'ом переходит к цене.

    Args:
        quantity (str): Количество
    """
    wait_while_busy(reason="перед количеством")
    pyautogui.write(quantity, interval=TYPING_INTERVAL)
    for _ in range(QUANTITY_TO_PRICE_TABS):
        pyautogui.press('tab')
        time.sleep(FIELD_DELAY)
    wait_while_busy(reason="перед ценой")


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

    wait_while_busy(reason="после ввода цены")


def fill_product_row(nomenclature, quantity, price, row_number=1, is_first_row=False):
    """
    Заполняет одну строку товара.
    Если номенклатуры нет — удаляет недозаполненную строку и возвращает False.

    Returns:
        bool: True если строка заполнена, False если пропущена (строки в таблице нет).
    """
    global _skipped_products, _chunk_skipped
    time.sleep(BETWEEN_ROWS_DELAY)

    click_add_button(is_first_row)
    time.sleep(FIELD_DELAY)

    if not fill_nomenclature(nomenclature):
        _cancel_incomplete_row()
        item = (nomenclature, quantity, price)
        _skipped_products.append(item)
        _chunk_skipped.append(item)
        print(
            f"⚠ Пропуск строки {row_number}: номенклатуры нет в 1С — "
            f"наименование={nomenclature}, количество={quantity}, цена={price} "
            f"(строку удаляю, в сумму не входит)"
        )
        return False

    fill_quantity(quantity)
    fill_price(price)
    return True


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


def _last_batch_expected_vs_actual(table_rows_before: int, expected_filled_rows: int) -> tuple[int, int]:
    """
    Сравнивает ожидание с фактом в таблице для последнего батча.
    Учитываются только реально заполненные строки (пропуски без номенклатуры
    в таблицу не попадают).

    Args:
        table_rows_before: Сколько заполненных строк было в таблице до этого батча.
        expected_filled_rows: Сколько заполненных строк должен добавить батч.

    Returns:
        (expected_filled_rows, actual_rows) — хвост таблицы после батча.
    """
    if expected_filled_rows <= 0:
        return (0, 0)
    focus_table_and_navigate_rows()
    time.sleep(FIELD_DELAY)
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(FIELD_DELAY)
    raw = _copy_to_clipboard()
    if not raw:
        return (expected_filled_rows, 0)
    lines = raw.split('\n') if raw else []
    actual_rows = max(0, len(lines) - table_rows_before)
    return (expected_filled_rows, actual_rows)


def with_batch_sum_check(fn):
    """
    Декоратор: после каждых batch_size записей сравнивает
    ожидаемую сумму с суммой в 1С.
    Пропуски (нет номенклатуры) исключаются из суммы и не считаются строками таблицы.
    """

    def wrapper(product_data, **kwargs):
        global _last_read_total, _chunk_skipped, _skipped_products
        clear_skipped_products()
        cumulative_expected = _last_read_total
        table_rows_before = 0  # только успешно заполненные строки
        # Запоминаем координаты таблицы, пока шапка ещё хорошо видна
        try:
            _locate_table_click_point(nudge_scroll=False)
        except Exception as exc:
            print(f"⚠ Не удалось заранее найти таблицу: {exc}")
        batch_size = max(BATCH_CHECK_MIN, int(len(product_data) * BATCH_CHECK_PERCENT))
        for i in range(0, len(product_data), batch_size):
            chunk = product_data[i : i + batch_size]
            base_before_chunk = cumulative_expected
            skips_before_chunk = len(_skipped_products)
            rows_before_chunk = table_rows_before

            def _run_chunk():
                global _chunk_skipped, _skipped_products
                _skipped_products = _skipped_products[:skips_before_chunk]
                _chunk_skipped = []
                fn(chunk, batch_offset=i, **kwargs)
                skipped = list(_chunk_skipped)
                chunk_sum = _calc_expected_sum(chunk) - _calc_expected_sum(skipped)
                filled = len(chunk) - len(skipped)
                return skipped, chunk_sum, filled

            chunk_skipped, chunk_sum, filled_count = _run_chunk()
            cumulative_expected = base_before_chunk + chunk_sum
            min_plausible = (
                cumulative_expected * Decimal("0.5") if cumulative_expected > 0 else None
            )
            actual = _read_and_cache_total(min_plausible=min_plausible)
            _restore_table_focus()
            records_count = i + len(chunk)
            if chunk_skipped:
                print(
                    f"  (из {len(chunk)} позиций файла заполнено {filled_count}, "
                    f"пропущено {len(chunk_skipped)}, в сумму чанка {chunk_sum})"
                )
            if actual is not None:
                if _as_money(actual) == _as_money(cumulative_expected):
                    print(
                        f"✅ Проверка после {records_count} записей: "
                        f"сумма сошлась ({_as_money(cumulative_expected)})"
                    )
                    table_rows_before = rows_before_chunk + filled_count
                else:
                    print(
                        f"⚠ После {records_count} записей: "
                        f"ожидалось {_as_money(cumulative_expected)}, "
                        f"в 1С: {_as_money(actual)}"
                    )
                    for attempt in range(1, MAX_SUM_RETRY_ATTEMPTS + 1):
                        exp_rows, act_rows = _last_batch_expected_vs_actual(
                            rows_before_chunk, filled_count
                        )
                        if act_rows > 0:
                            print(
                                f"  Попытка {attempt}/{MAX_SUM_RETRY_ATTEMPTS}: ожидалось "
                                f"{exp_rows} заполненных строк, в таблице {act_rows} — "
                                f"удаляю {act_rows} и ввожу заново..."
                            )
                            _delete_last_n_rows(act_rows)
                            time.sleep(FIELD_DELAY)
                        else:
                            print(
                                f"  Попытка {attempt}/{MAX_SUM_RETRY_ATTEMPTS}: "
                                f"в батч не добавилось ни одной записи, повторяю ввод..."
                            )
                        chunk_skipped, chunk_sum, filled_count = _run_chunk()
                        cumulative_expected = base_before_chunk + chunk_sum
                        min_plausible = (
                            cumulative_expected * Decimal("0.5")
                            if cumulative_expected > 0
                            else None
                        )
                        actual_retry = _read_and_cache_total(min_plausible=min_plausible)
                        _restore_table_focus()
                        if actual_retry is not None and _as_money(actual_retry) == _as_money(
                            cumulative_expected
                        ):
                            print(
                                f"✅ После повторного ввода сумма сошлась "
                                f"({_as_money(cumulative_expected)})"
                            )
                            table_rows_before = rows_before_chunk + filled_count
                            break
                        print(
                            f"⚠ После попытки {attempt}: "
                            f"ожидалось {_as_money(cumulative_expected)}, "
                            f"в 1С: {_as_money(actual_retry) if actual_retry is not None else None}"
                        )
                    else:
                        print(
                            f"❌ Сумма не сошлась после {MAX_SUM_RETRY_ATTEMPTS} попыток. "
                            f"Завершение работы."
                        )
                        sys.exit(1)
            else:
                print(f"⚠ Не удалось прочитать сумму из 1С после {records_count} записей")
                table_rows_before = rows_before_chunk + filled_count

    return wrapper


@with_batch_sum_check
def automate_data_entry(product_data, batch_offset=0, **kwargs):
    """
    Автоматизирует ввод данных в 1С.
    Если номенклатуры нет — оставляет пустую строку и пишет пропуск в консоль.

    Args:
        product_data (list): Список кортежей (nomenclature, quantity, price)
        batch_offset (int): Смещение для чанков (используется декоратором)
    """
    for idx, (nomenclature, quantity, price) in enumerate(product_data):
        if ERROR_INJECTION_PERCENT and random.random() < ERROR_INJECTION_PERCENT:
            if random.random() < 0.5:
                print(f"  [TEST] Пропуск записи {batch_offset + idx + 1}: {nomenclature}")
                continue
            else:
                price_dec = to_decimal(price)
                wrong_price = str(
                    price_dec + (random.choice([-1, 1]) * (abs(price_dec) * Decimal("0.1") + 1))
                )
                print(f"  [TEST] Неправильная цена для {nomenclature}: {price} -> {wrong_price}")
                price = wrong_price

        fill_product_row(
            nomenclature,
            quantity,
            price,
            row_number=batch_offset + idx + 1,
            is_first_row=(batch_offset == 0 and idx == 0),
        )
