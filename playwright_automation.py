"""
Автоматизация ввода в веб-клиент 1С через Playwright + CDP.
Скрипт подключается к уже открытому Chromium (remote debugging).
"""
from playwright.sync_api import sync_playwright, Browser, Page, TimeoutError as PlaywrightTimeout

from config import (
    CDP_URL,
    ONE_C_URL_MARKERS,
    ONE_C_TITLE_MARKERS,
    NOMENCLATURE_ENTERS,
    FILL_ROWS_LIMIT,
    AFTER_ADD_SETTLE_DELAY_MS,
    NOMENCLATURE_INPUT_DELAY_MS,
    NOMENCLATURE_MISSING_RECHECK_DELAY_MS,
    AFTER_NOMENCLATURE_SETTLE_MS,
    FIELD_DELAY_MS,
    BETWEEN_ROWS_DELAY_MS,
)

# Позиции, пропущенные из‑за отсутствия номенклатуры в 1С
_skipped_products: list[tuple] = []


def get_skipped_products() -> list[tuple]:
    return list(_skipped_products)


def clear_skipped_products() -> None:
    global _skipped_products
    _skipped_products = []


def connect_browser(cdp_url: str = CDP_URL) -> tuple:
    """
    Подключается к Chromium по CDP.
    Returns:
        (playwright, browser) — playwright нужно закрыть через .stop()
    """
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(cdp_url)
    except Exception as exc:
        pw.stop()
        raise ConnectionError(
            f"Не удалось подключиться к Chromium по {cdp_url}.\n"
            f"Сначала запусти: python start_chromium.py\n"
            f"Открой документ «Реализация товаров», затем снова main.py.\n"
            f"Причина: {exc}"
        ) from exc
    return pw, browser


def find_one_c_page(browser: Browser) -> Page:
    """Ищет вкладку с веб-клиентом 1С среди открытых страниц."""
    candidates: list[Page] = []
    for context in browser.contexts:
        for page in context.pages:
            candidates.append(page)

    if not candidates:
        raise RuntimeError("В Chromium нет открытых вкладок.")

    def score(page: Page) -> int:
        url = (page.url or "").lower()
        title = page.title() or ""
        points = 0
        if any(m in url for m in ONE_C_URL_MARKERS):
            points += 2
        if any(m in title for m in ONE_C_TITLE_MARKERS):
            points += 3
        if "реализация" in title.lower():
            points += 2
        return points

    ranked = sorted(candidates, key=score, reverse=True)
    best = ranked[0]
    if score(best) == 0:
        urls = "\n".join(f"  - {p.url!r} | {p.title()!r}" for p in candidates)
        raise RuntimeError(
            "Не найдена вкладка 1С. Открытые страницы:\n"
            f"{urls}\n"
            "Открой документ «Реализация товаров» и запусти снова."
        )

    best.bring_to_front()
    print(f"📄 Страница 1С: {best.title()} ({best.url})")
    return best


def _choice_list_open(page: Page) -> bool:
    """Открыт ли выпадающий список выбора (номенклатура и т.п.)."""
    return _is_visible_text(page, "Показать все") or _is_visible_text(
        page, "нет в списке"
    )


def dismiss_overlays(page: Page) -> None:
    """
    Закрывает только открытый список выбора.
    Лишний Esc без оверлея закрывает сам документ 1С — не жать вхолостую.
    """
    for _ in range(5):
        if not _choice_list_open(page):
            return
        page.keyboard.press("Escape")
        page.wait_for_timeout(FIELD_DELAY_MS)


def click_add_button(page: Page) -> None:
    """
    Жмёт «Добавить» над табличной частью товаров.
    На форме есть ещё «Добавить» у счёта и скрытые пункты меню —
    берём кнопку тулбара таблицы (a.press / title=Добавить).
    """
    if _choice_list_open(page):
        dismiss_overlays(page)
    candidates = [
        page.locator('a.press.pressCommand', has_text="Добавить"),
        page.locator('span.framePress[title="Добавить"]'),
        page.locator('[title="Добавить"]'),
    ]
    last_error: Exception | None = None
    for loc in candidates:
        try:
            if loc.count() == 0:
                continue
            target = loc.first
            if not target.is_visible():
                continue
            target.click(timeout=5000)
            page.wait_for_timeout(AFTER_ADD_SETTLE_DELAY_MS)
            return
        except Exception as exc:
            last_error = exc

    raise TimeoutError(
        "Не удалось нажать «Добавить» в тулбаре таблицы товаров. "
        "Проверь, что документ «Реализация товаров» открыт (не закрыт Esc)."
    ) from last_error


def _paste_text(page: Page, text: str) -> None:
    """Вставляет текст в активное поле (unicode, без раскладки)."""
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.insert_text(str(text).strip())


def _header_box(page: Page, title: str) -> dict:
    """Bounding box заголовка колонки таблицы товаров."""
    loc = page.locator(".gridBoxTitle", has_text=title)
    for i in range(loc.count()):
        box = loc.nth(i).bounding_box()
        if box and box["width"] > 0 and box["height"] > 0:
            return box
    raise RuntimeError(f"Не найден заголовок колонки «{title}».")


def _selected_row_box(page: Page) -> dict:
    """Bounding box текущей (выделенной) строки табличной части."""
    loc = page.locator(".gridLine.select.eActivityBack, .gridLine.select")
    for i in range(loc.count()):
        el = loc.nth(i)
        box = el.bounding_box()
        if not box or box["width"] < 200:
            continue
        # строка товаров, не вкладка документа
        cls = el.get_attribute("class") or ""
        if "gridLine" in cls:
            return box
    raise RuntimeError("Не найдена выделенная строка таблицы товаров.")


def click_cell(page: Page, column_title: str, x_ratio: float = 0.25) -> None:
    """Кликает ячейку колонки в текущей строке (x_ratio — доля ширины колонки)."""
    header = _header_box(page, column_title)
    row = _selected_row_box(page)
    x = header["x"] + header["width"] * x_ratio
    y = row["y"] + row["height"] / 2
    page.mouse.click(x, y)
    page.wait_for_timeout(FIELD_DELAY_MS)


def _grid_edit_input(page: Page, id_substr: str):
    """
    Редактор ячейки табличной части (ТоварыКоличество / ТоварыЦена / ...).
    Не путать с полями шапки (Номер, Дата, Контрагент) — у них тоже editInput.
    """
    loc = page.locator(f'input.editInput[id*="{id_substr}"]')
    for i in range(loc.count()):
        item = loc.nth(i)
        box = item.bounding_box()
        if box and box["width"] > 0 and box["height"] > 0:
            return item
    return None


def _type_into_grid_cell(page: Page, text: str, id_substr: str) -> None:
    """
    Ввод в ячейку таблицы: после клика 1С часто держит фокус на gridBody,
    первый символ открывает input Товары*; пишем клавишами и ждём этот input.
    """
    value = str(text).strip()
    page.keyboard.press("Control+A")
    page.keyboard.type(value, delay=25)
    page.wait_for_timeout(FIELD_DELAY_MS)

    inp = _grid_edit_input(page, id_substr)
    if inp is not None:
        current = (inp.input_value() or "").replace(" ", "").replace("\xa0", "")
        # 1С может отформатировать 1 → 1,000
        normalized = current.replace(",000", "").replace(".000", "")
        expected = value.replace(".", ",")
        if expected not in current and value not in current and normalized != value:
            inp.fill(value)
            page.wait_for_timeout(FIELD_DELAY_MS)


def _is_visible_text(page: Page, text: str) -> bool:
    loc = page.get_by_text(text, exact=False)
    try:
        n = loc.count()
    except Exception:
        return False
    for i in range(min(n, 8)):
        try:
            if loc.nth(i).is_visible():
                return True
        except Exception:
            continue
    return False


def _nomenclature_missing_on_screen(page: Page) -> bool:
    """
    True, если номенклатуры нет в базе.
    Главный маркер — «нет в списке» (как на скрине с fvd).
    «+(создать)» сам по себе не используем: может мелькать и при совпадениях.
    """
    return _is_visible_text(page, "нет в списке")


def _nomenclature_confirmed_missing(page: Page) -> bool:
    """
    1С сначала рисует «создать», потом подгружает совпадения.
    Считаем пропуском только если маркер остался после повторной проверки.
    """
    if not _nomenclature_missing_on_screen(page):
        return False
    page.wait_for_timeout(NOMENCLATURE_MISSING_RECHECK_DELAY_MS)
    return _nomenclature_missing_on_screen(page)


def _confirm_delete_dialog(page: Page) -> None:
    """Если 1С спросила подтверждение удаления — подтверждаем."""
    dialog_hint = (
        _is_visible_text(page, "Удалить")
        or _is_visible_text(page, "удалить")
        or _is_visible_text(page, "будет удален")
    )
    for name in ("Да", "Удалить", "OK", "ОК"):
        btn = page.get_by_role("button", name=name)
        try:
            if btn.count() and btn.first.is_visible():
                btn.first.click(timeout=2000)
                page.wait_for_timeout(FIELD_DELAY_MS)
                return
        except Exception:
            continue
    if dialog_hint:
        page.keyboard.press("Enter")
        page.wait_for_timeout(FIELD_DELAY_MS)


def cancel_incomplete_row(page: Page) -> None:
    """
    Закрывает выпадающий список и удаляет недозаполненную строку.
    Delete в открытом выборе чистит текст, а не строку — сначала закрываем
    список, кликаем в колонку N (выделение строки без редактора), потом Delete.
    """
    dismiss_overlays(page)

    # Выделить строку кликом по номеру — без открытия номенклатуры
    try:
        click_cell(page, "N", x_ratio=0.5)
    except Exception:
        try:
            row = _selected_row_box(page)
            page.mouse.click(row["x"] + 20, row["y"] + row["height"] / 2)
            page.wait_for_timeout(FIELD_DELAY_MS)
        except Exception:
            pass

    dismiss_overlays(page)
    page.keyboard.press("Delete")
    page.wait_for_timeout(FIELD_DELAY_MS)
    _confirm_delete_dialog(page)
    dismiss_overlays(page)
    page.wait_for_timeout(BETWEEN_ROWS_DELAY_MS)


def fill_nomenclature(page: Page, nomenclature: str) -> bool:
    """
    Вводит номенклатуру и подтверждает Enter.
    Returns:
        True — найдена и выбрана; False — нет в базе (создание не делаем).
    """
    _paste_text(page, nomenclature)
    page.wait_for_timeout(NOMENCLATURE_INPUT_DELAY_MS)

    if _nomenclature_confirmed_missing(page):
        return False

    for _ in range(NOMENCLATURE_ENTERS):
        page.keyboard.press("Enter")
        page.wait_for_timeout(FIELD_DELAY_MS)
    # 1С догружает товар и переводит фокус — без паузы qty уходит в скрытый input
    page.wait_for_timeout(AFTER_NOMENCLATURE_SETTLE_MS)
    return True


def fill_quantity(page: Page, quantity: str) -> None:
    """Кликает «Количество» в текущей строке, вводит значение, Tab → цена."""
    click_cell(page, "Количество", x_ratio=0.2)
    _type_into_grid_cell(page, quantity, "ТоварыКоличество")
    page.keyboard.press("Tab")
    page.wait_for_timeout(FIELD_DELAY_MS)


def fill_price(page: Page, price: str) -> None:
    """Вводит цену в текущее поле (уже ТоварыЦена после Tab) или кликом по колонке."""
    inp = _grid_edit_input(page, "ТоварыЦена")
    if inp is None:
        click_cell(page, "Цена", x_ratio=0.5)
    page.keyboard.press("Control+A")
    page.keyboard.type(str(price).strip(), delay=25)
    page.wait_for_timeout(FIELD_DELAY_MS)
    # зафиксировать значение в ячейке
    page.keyboard.press("Enter")
    page.wait_for_timeout(FIELD_DELAY_MS)


def fill_product_row(
    page: Page,
    nomenclature: str,
    quantity: str,
    price: str,
    row_number: int,
) -> bool:
    """
    Добавляет строку и заполняет номенклатуру / количество / цену.
    Returns:
        True если строка заполнена, False если пропущена (номенклатуры нет).
    """
    global _skipped_products
    print(
        f"→ Строка {row_number}: {nomenclature!r} | qty={quantity} | price={price}"
    )
    click_add_button(page)
    if not fill_nomenclature(page, nomenclature):
        cancel_incomplete_row(page)
        item = (nomenclature, quantity, price)
        _skipped_products.append(item)
        print(
            f"⚠ Пропуск строки {row_number}: номенклатуры нет в 1С — "
            f"{nomenclature!r}, qty={quantity}, price={price} "
            f"(строку удаляю, в сумму не входит)"
        )
        page.wait_for_timeout(BETWEEN_ROWS_DELAY_MS)
        return False

    fill_quantity(page, quantity)
    fill_price(page, price)
    page.wait_for_timeout(BETWEEN_ROWS_DELAY_MS)
    print(f"✅ Строка {row_number} заполнена.")
    return True


def fill_product_rows(page: Page, products: list[tuple]) -> tuple[int, int]:
    """
    Заполняет переданные позиции подряд.
    Returns:
        (заполнено, пропущено)
    """
    filled = 0
    skipped = 0
    for i, (nomenclature, quantity, price) in enumerate(products, start=1):
        if fill_product_row(page, nomenclature, quantity, price, row_number=i):
            filled += 1
        else:
            skipped += 1
    print(f"✅ Готово: заполнено {filled}, пропущено {skipped}.")
    return filled, skipped


def run_fill_rows(products: list[tuple], limit: int = FILL_ROWS_LIMIT) -> list[tuple]:
    """
    Точка входа: CDP → страница 1С → первые limit строк.
    Returns:
        список пропущенных позиций
    """
    batch = list(products[:limit])
    if not batch:
        raise ValueError("Нет позиций для заполнения.")

    clear_skipped_products()
    pw, browser = connect_browser()
    try:
        page = find_one_c_page(browser)
        fill_product_rows(page, batch)
        return get_skipped_products()
    except PlaywrightTimeout as exc:
        raise TimeoutError(
            f"Таймаут при работе с 1С: {exc}"
        ) from exc
    finally:
        # Не закрываем браузер пользователя — только отключаемся.
        browser.close()
        pw.stop()


# Обратная совместимость
def run_fill_first_row(nomenclature: str, quantity: str, price: str) -> None:
    run_fill_rows([(nomenclature, quantity, price)], limit=1)
