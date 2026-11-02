"""
Raindrop Mail Sender — masaüstü UI (pywebview, çerçevesiz pencere).

Kullanım:
  python ui_app.py
  python ui_app.py --send [--session ID]
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Any

import webview

from mailer.config import LOG_FILE, RESOURCE_DIR, read_log_tail
from mailer.send import send_campaign, send_error_report_safe
from mailer.sessions import (
    build_send_config,
    create_session,
    delete_session,
    get_session,
    list_sessions,
    rename_session,
    save_session_payload,
    set_active_session,
    set_session_automation,
)

UI_DIR = RESOURCE_DIR / "ui"
INDEX_HTML = UI_DIR / "index.html"
ICON_PATH = RESOURCE_DIR / "assets" / "raindrop.ico"
if not ICON_PATH.is_file():
    from mailer.config import BASE_DIR

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


def _parse_session_arg(argv: list[str]) -> str | None:
    for i, arg in enumerate(argv):
        if arg == "--session" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--session="):
            return arg.split("=", 1)[1]
    return None


def run_send_once(session_id: str | None = None) -> int:
    """Task Scheduler / --send için CLI gönderim."""
    import smtplib

    setup_logging()
    logging.info(
        "Mail gönderimi başladı (--send%s).",
        f" session={session_id}" if session_id else "",
    )
    config = None
    try:
        config = build_send_config(session_id)
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
    """pywebview JavaScript köprüsü — hata fırlatmak yerine {ok:false} döner."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._window: webview.Window | None = None
        self._send_lock = threading.Lock()
        self._send_job: dict[str, Any] = {
            "busy": False,
            "phase": "idle",
            "message": "",
            "result": None,
        }

    def set_window(self, window: webview.Window) -> None:
        self._window = window

    def get_send_job(self) -> dict[str, Any]:
        """UI yoklaması — gönderim arka planda; bu çağrı bloklamaz."""
        with self._send_lock:
            return {
                "busy": bool(self._send_job.get("busy")),
                "phase": str(self._send_job.get("phase") or "idle"),
                "message": str(self._send_job.get("message") or ""),
                "result": self._send_job.get("result"),
            }

    def _set_send_job(self, **kwargs: Any) -> None:
        with self._send_lock:
            self._send_job.update(kwargs)

    def start_send(self, session_id: str = "") -> dict[str, Any]:
        """
        SMTP'yi arka plan thread'inde başlatır; hemen döner.
        UI donmasın diye send_mail senkron kullanılmamalı.
        """
        with self._send_lock:
            if self._send_job.get("busy"):
                return {
                    "ok": False,
                    "started": False,
                    "message": "Zaten bir gönderim sürüyor.",
                }
            self._send_job = {
                "busy": True,
                "phase": "starting",
                "message": "Gönderim kuyruğa alındı…",
                "result": None,
            }

        def worker() -> None:
            config = None
            try:
                self._set_send_job(phase="config", message="Yapılandırma okunuyor…")
                config = build_send_config(session_id or None)
                self._set_send_job(
                    phase="smtp",
                    message=f"SMTP bağlanıyor ({config.get('session_name') or 'oturum'})…",
                )
                logging.info(
                    "UI arka plan gönderim (session=%s).",
                    config.get("session_id") or "-",
                )
                result = send_campaign(config)
                logging.info("UI gönderim özeti: %s", result["message"])
                self._set_send_job(
                    busy=False,
                    phase="done",
                    message=str(result.get("message") or "Bitti"),
                    result=result,
                )
            except Exception as exc:
                logging.exception("UI arka plan gönderimi başarısız.")
                send_error_report_safe(config, "UI üzerinden gönderim hatası.", exc)
                fail = {
                    "ok": False,
                    "ok_count": 0,
                    "fail_count": 1,
                    "ok_recipients": [],
                    "failed": [],
                    "message": str(exc),
                }
                self._set_send_job(
                    busy=False,
                    phase="error",
                    message=str(exc),
                    result=fail,
                )

        threading.Thread(target=worker, name="raindrop-send", daemon=True).start()
        return {
            "ok": True,
            "started": True,
            "message": "Gönderim başladı — UI kilitlenmez.",
        }

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

    def list_sessions(self) -> dict[str, Any]:
        try:
            return list_sessions()
        except Exception as exc:
            logging.exception("list_sessions")
            return {"ok": False, "message": str(exc), "sessions": []}

    def get_session(self, session_id: str) -> dict[str, Any]:
        try:
            return get_session(str(session_id or ""))
        except Exception as exc:
            logging.exception("get_session")
            return {"ok": False, "message": str(exc)}

    def select_session(self, session_id: str) -> dict[str, Any]:
        try:
            return set_active_session(str(session_id or ""))
        except Exception as exc:
            logging.exception("select_session")
            return {"ok": False, "message": str(exc)}

    def create_session(self, name: str = "") -> dict[str, Any]:
        with self._lock:
            try:
                return create_session(name or None)
            except Exception as exc:
                logging.exception("create_session")
                return {"ok": False, "message": str(exc)}

    def delete_session(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            try:
                return delete_session(str(session_id or ""))
            except Exception as exc:
                logging.exception("delete_session")
                return {"ok": False, "message": str(exc)}

    def rename_session(self, session_id: str, name: str) -> dict[str, Any]:
        with self._lock:
            try:
                return rename_session(str(session_id or ""), str(name or ""))
            except Exception as exc:
                logging.exception("rename_session")
                return {"ok": False, "message": str(exc)}

    def set_session_automation(self, session_id: str, enabled: bool) -> dict[str, Any]:
        with self._lock:
            try:
                return set_session_automation(str(session_id or ""), bool(enabled))
            except Exception as exc:
                logging.exception("set_session_automation")
                return {"ok": False, "message": str(exc)}

    def save_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            try:
                return save_session_payload(payload or {})
            except Exception as exc:
                logging.exception("save_session")
                return {"ok": False, "message": str(exc)}

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

    def send_mail(self, session_id: str = "") -> dict[str, Any]:
        """Gönderim — asla unhandled raise etmez (UI kilidi önleme)."""
        with self._lock:
            config = None
            try:
                config = build_send_config(session_id or None)
                logging.info(
                    "UI gönderim başladı (session=%s).",
                    config.get("session_id") or "-",
                )
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
        width=1440,
        height=920,
        min_size=(1100, 740),
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


def main() -> int:
    if "--send" in sys.argv:
        return run_send_once(_parse_session_arg(sys.argv))
    return run_ui()


if __name__ == "__main__":
    sys.exit(main())
