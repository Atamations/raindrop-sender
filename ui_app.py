"""
Raindrop Mail Sender — masaüstü UI (pywebview, çerçevesiz pencere).

Kullanım:
  python ui_app.py          → UI
  python ui_app.py --send   → tek seferlik CLI gönderim (Task Scheduler)
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Any

import webview

from mailer.config import (
    BASE_DIR,
    LOG_FILE,
    RESOURCE_DIR,
    config_for_ui,
    load_config,
    read_log_tail,
    save_config,
)
from mailer.schedule import apply_schedule, get_schedule_status
from mailer.send import send_campaign, send_error_report_safe

UI_DIR = RESOURCE_DIR / "ui"
INDEX_HTML = UI_DIR / "index.html"
ICON_PATH = RESOURCE_DIR / "assets" / "raindrop.ico"
if not ICON_PATH.is_file():
    ICON_PATH = BASE_DIR / "assets" / "raindrop.ico"


def setup_logging() -> None:
    """UI / CLI oturumu için dosya + konsol log."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )


def run_send_once() -> int:
    """Task Scheduler / --send için CLI gönderim."""
    import smtplib

    setup_logging()
    logging.info("Mail gönderimi başladı (--send).")
    config = None
    try:
        config = load_config()
        result = send_campaign(config)
        logging.info("Özet: %s", result["message"])
        return 0 if result["ok"] else 1
    except (ValueError, FileNotFoundError) as exc:
        logging.error("%s", exc)
        send_error_report_safe(config, "Yapılandırma hatası.", exc)
        return 1
    except smtplib.SMTPException as exc:
        logging.exception("SMTP hatası.")
        send_error_report_safe(config, "SMTP hatası.", exc)
        return 1
    except Exception as exc:
        logging.exception("Beklenmeyen hata.")
        send_error_report_safe(config, "Beklenmeyen hata.", exc)
        return 2
    finally:
        logging.info("Mail gönderimi sonlandı.")


class MailApi:
    """pywebview JavaScript köprüsü."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._window: webview.Window | None = None

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    def minimize(self) -> None:
        if self._window is not None:
            self._window.minimize()

    def close_window(self) -> None:
        """Frameless X — destroy; CLR teardown gürültüsünü yut."""
        if self._window is None:
            return
        try:
            self._window.destroy()
        except Exception:
            logging.debug("Pencere kapatılırken uyarı.", exc_info=True)
        finally:
            self._window = None

    def get_config(self) -> dict[str, Any]:
        return config_for_ui()

    def save_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            try:
                return save_config(payload or {})
            except Exception as exc:
                logging.exception("Ayar kaydı başarısız.")
                raise RuntimeError(str(exc)) from exc

    def get_log_tail(self) -> str:
        return read_log_tail(100)

    def pick_attachments(self) -> list[str]:
        if self._window is None:
            return []
        result = self._window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=("All files (*.*)",),
        )
        if not result:
            return []
        return [str(p) for p in result]

    def get_schedule(self) -> dict[str, Any]:
        return get_schedule_status()

    def save_schedule(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            try:
                return apply_schedule(payload or {})
            except Exception as exc:
                logging.exception("Zamanlama kaydı başarısız.")
                raise RuntimeError(str(exc)) from exc

    def send_mail(self) -> dict[str, Any]:
        with self._lock:
            config = None
            try:
                config = load_config(require_attachments_exist=True)
                logging.info("UI üzerinden gönderim başladı.")
                result = send_campaign(config)
                logging.info("UI gönderim özeti: %s", result["message"])
                return result
            except Exception as exc:
                logging.exception("UI gönderimi başarısız.")
                send_error_report_safe(config, "UI üzerinden gönderim hatası.", exc)
                return {
                    "ok": False,
                    "ok_count": 0,
                    "fail_count": 1,
                    "ok_recipients": [],
                    "failed": [],
                    "message": str(exc),
                }


def run_ui() -> int:
    setup_logging()

    if not INDEX_HTML.is_file():
        logging.error("UI dosyası bulunamadı: %s", INDEX_HTML)
        return 1

    api = MailApi()
    window = webview.create_window(
        title="Raindrop Mail Sender",
        url=Path(INDEX_HTML).as_uri(),
        js_api=api,
        width=1320,
        height=900,
        min_size=(1040, 720),
        background_color="#0b1220",
        text_select=True,
        frameless=True,
        easy_drag=False,
        shadow=True,
    )
    api.set_window(window)

    logging.info("UI başlatılıyor…")
    logging.info("UI dosyası: %s", INDEX_HTML)
    logging.info("İkon: %s (var=%s)", ICON_PATH, ICON_PATH.is_file())

    # Geçersiz .ico WinForms/CLR'yi öldürür (catch edilemez). Önce ICO imzasını doğrula.
    icon_arg: str | None = None
    if ICON_PATH.is_file() and _ico_looks_valid(ICON_PATH):
        icon_arg = str(ICON_PATH)
    elif ICON_PATH.is_file():
        logging.warning("İkon geçersiz görünüyor, ikonsuz başlatılıyor: %s", ICON_PATH)

    try:
        if icon_arg:
            webview.start(debug=False, icon=icon_arg)
        else:
            webview.start(debug=False)
    except Exception:
        logging.exception("UI başlatma hatası; ikonsuz yeniden deneniyor.")
        webview.start(debug=False)
    return 0


def _ico_looks_valid(path: Path) -> bool:
    """Windows ICONDIR imzası: reserved=0, type=1 (icon), count>0."""
    try:
        header = path.read_bytes()[:6]
    except OSError:
        return False
    if len(header) < 6:
        return False
    reserved = header[0] | (header[1] << 8)
    img_type = header[2] | (header[3] << 8)
    count = header[4] | (header[5] << 8)
    return reserved == 0 and img_type == 1 and count > 0


def main() -> int:
    if "--send" in sys.argv:
        return run_send_once()
    return run_ui()


if __name__ == "__main__":
    sys.exit(main())
