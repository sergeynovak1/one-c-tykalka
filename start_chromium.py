"""
Запускает Chromium Playwright с remote debugging.
Открой в нём 1С → документ «Реализация товаров», затем запусти main.py.
"""
import os
import subprocess
import sys
from pathlib import Path

# Стабильный путь к браузерам (не sandbox-кэш Cursor)
_ROOT = Path(__file__).resolve().parent
_BROWSERS_DIR = _ROOT / ".pw-browsers"
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(_BROWSERS_DIR)

from playwright.sync_api import sync_playwright

from config import CDP_URL, ONE_C_START_URL

PROFILE_DIR = _ROOT / ".chromium-1c-profile"


def _chromium_exe_from_playwright() -> Path:
    with sync_playwright() as pw:
        return Path(pw.chromium.executable_path)


def _ensure_chromium() -> Path:
    """Возвращает путь к chrome.exe; при отсутствии ставит через playwright install."""
    _BROWSERS_DIR.mkdir(parents=True, exist_ok=True)
    # Хвост от сорванной установки иногда блокирует повторный install
    lock = _BROWSERS_DIR / "__dirlock"
    if lock.exists():
        try:
            if lock.is_dir():
                lock.rmdir()
            else:
                lock.unlink()
        except OSError:
            pass

    exe = _chromium_exe_from_playwright()
    if exe.is_file():
        return exe

    print(f"Chromium не найден в {_BROWSERS_DIR}, ставлю...")
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(_BROWSERS_DIR)},
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"playwright install chromium завершился с кодом {result.returncode}"
        )

    exe = _chromium_exe_from_playwright()
    if not exe.is_file():
        raise FileNotFoundError(
            f"Chromium всё ещё не найден после установки: {exe}"
        )
    return exe


def main() -> None:
    port = CDP_URL.rsplit(":", 1)[-1]
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    exe = _ensure_chromium()
    args = [
        str(exe),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        ONE_C_START_URL,
    ]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Chromium запущен (CDP {CDP_URL}).")
    print(f"Бинарник: {exe}")
    print("1) Войди в 1С и открой «Реализация товаров».")
    print("2) Запусти: python main.py")
    print(f"Профиль: {PROFILE_DIR}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"❌ Не удалось запустить Chromium: {exc}", file=sys.stderr)
        sys.exit(1)
