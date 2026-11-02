"""
Tek seferlik Gmail SMTP CLI gönderici (Task Scheduler uyumlu).
Çalışır → gönderir → REPORT_EMAIL bildirimi → exit code ile çıkar.
"""

from __future__ import annotations

import logging
import smtplib
import sys

from mailer.config import LOG_FILE
from mailer.send import send_campaign, send_error_report_safe
from mailer.sessions import build_send_config


def setup_logging() -> None:
    """Konsol + dosya loglama."""
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


def main() -> int:
    """
    Exit codes:
      0 = tüm alıcılara başarı
      1 = yapılandırma / gönderim hatası
      2 = beklenmeyen hata
    """
    setup_logging()
    session_id = _parse_session_arg(sys.argv)
    logging.info(
        "Mail gönderimi başladı%s.",
        f" (session={session_id})" if session_id else "",
    )
    config = None

    try:
        config = build_send_config(session_id)
        logging.info("Alıcı sayısı: %s", len(config["recipients"]))
        logging.info("Rapor adresi: %s", config["report_email"])

        result = send_campaign(config)
        logging.info("Özet: %s", result["message"])
        return 0 if result["ok"] else 1

    except (ValueError, FileNotFoundError) as exc:
        logging.error("%s", exc)
        send_error_report_safe(config, "Yapılandırma hatası.", exc)
        return 1
    except smtplib.SMTPAuthenticationError as exc:
        logging.exception("Kimlik doğrulama başarısız.")
        send_error_report_safe(
            config,
            "SMTP kimlik doğrulama hatası (yanlış şifre / App Password).",
            exc,
        )
        return 1
    except smtplib.SMTPException as exc:
        logging.exception("SMTP hatası oluştu.")
        send_error_report_safe(config, "SMTP hatası.", exc)
        return 1
    except TimeoutError as exc:
        logging.exception("SMTP zaman aşımı (timeout).")
        send_error_report_safe(config, "Bağlantı zaman aşımı (timeout).", exc)
        return 1
    except OSError as exc:
        logging.exception("Ağ / bağlantı / dosya okuma hatası.")
        send_error_report_safe(
            config, "Ağ veya sistem hatası (internet kopması vb.).", exc
        )
        return 1
    except Exception as exc:
        logging.exception("Beklenmeyen hata.")
        send_error_report_safe(config, "Beklenmeyen hata.", exc)
        return 2
    finally:
        logging.info("Mail gönderimi sonlandı.")


if __name__ == "__main__":
    sys.exit(main())
