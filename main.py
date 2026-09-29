"""
Tek seferlik Gmail SMTP e-posta gönderici (ek dosya + durum raporu destekli).
Çalışır → gönderir → REPORT_EMAIL'e bildirim → loglar → exit code ile çıkar.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import smtplib
import ssl
import sys
import traceback
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "mailer.log"
ENV_FILE = BASE_DIR / ".env"

# .env'de ATTACHMENT_PATH yoksa / boşsa bu yol(lar) kullanılır.
# Birden fazla dosya için noktalı virgül (;) ile ayır.
# Boş bırakırsan ek olmadan sadece metin mail gider.
# Örnek: r"C:\Users\USER\Documents\rapor.pdf;C:\Users\USER\Desktop\foto.png"
DEFAULT_ATTACHMENT_PATH = ""

ConfigDict = dict[str, str | int | list[str] | list[Path]]


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
    )


def parse_single_email(raw: str, field_name: str) -> str:
    """Tek bir e-posta adresini doğrular."""
    email = raw.strip().strip('"').strip("'")
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        logging.error("%s geçersiz: %r", field_name, raw)
        raise SystemExit(1)
    return email


def parse_recipients(raw_recipients: str) -> list[str]:
    """
    Virgülle ayrılmış alıcı adreslerini parse eder.

    Örnek: mail1@domain.com, mail2@domain.com
    """
    recipients: list[str] = []
    seen: set[str] = set()

    for part in raw_recipients.split(","):
        email = part.strip().strip('"').strip("'")
        if not email:
            continue
        key = email.lower()
        if key in seen:
            continue
        if "@" not in email or "." not in email.split("@")[-1]:
            logging.error("Geçersiz e-posta adresi: %r", email)
            raise SystemExit(1)
        seen.add(key)
        recipients.append(email)

    if not recipients:
        logging.error("RECIPIENT_EMAIL içinde geçerli adres bulunamadı.")
        raise SystemExit(1)

    return recipients


def resolve_attachment_paths(raw_paths: str) -> list[Path]:
    """Tek veya birden fazla ek dosya yolunu çözümler (; ile ayrılır)."""
    if not raw_paths.strip():
        return []

    paths: list[Path] = []
    for part in raw_paths.split(";"):
        path_str = part.strip().strip('"').strip("'")
        if not path_str:
            continue

        path = Path(path_str).expanduser()
        if not path.is_absolute():
            path = (BASE_DIR / path).resolve()
        else:
            path = path.resolve()

        if not path.is_file():
            logging.error("Ek dosya bulunamadı: %s", path)
            raise SystemExit(1)

        paths.append(path)

    return paths


def load_config() -> ConfigDict:
    """
    .env dosyasından ayarları yükler ve doğrular.

    Raises:
        SystemExit: Zorunlu değişken eksikse veya değerler geçersizse.
    """
    load_dotenv(ENV_FILE)

    required = (
        "GMAIL_ADDRESS",
        "GMAIL_APP_PASSWORD",
        "RECIPIENT_EMAIL",
        "REPORT_EMAIL",
        "EMAIL_SUBJECT",
        "EMAIL_BODY",
    )
    missing = [key for key in required if not os.getenv(key, "").strip()]
    if missing:
        logging.error("Eksik .env değişkenleri: %s", ", ".join(missing))
        raise SystemExit(1)

    port_raw = os.getenv("SMTP_PORT", "587").strip()
    try:
        port = int(port_raw)
    except ValueError:
        logging.error("SMTP_PORT sayı olmalı, gelen: %r", port_raw)
        raise SystemExit(1)

    if port not in (587, 465):
        logging.error("Gmail için SMTP_PORT 587 veya 465 olmalı, gelen: %s", port)
        raise SystemExit(1)

    recipients = parse_recipients(os.getenv("RECIPIENT_EMAIL", ""))
    report_email = parse_single_email(
        os.getenv("REPORT_EMAIL", ""),
        "REPORT_EMAIL",
    )

    env_attachment = os.getenv("ATTACHMENT_PATH", "").strip()
    attachment_raw = env_attachment or DEFAULT_ATTACHMENT_PATH
    attachment_paths = resolve_attachment_paths(attachment_raw)

    app_password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")

    return {
        "gmail_address": os.getenv("GMAIL_ADDRESS", "").strip(),
        "app_password": app_password,
        "recipients": recipients,
        "report_email": report_email,
        "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
        "smtp_port": port,
        "subject": os.getenv("EMAIL_SUBJECT", "").strip(),
        "body": os.getenv("EMAIL_BODY", "").strip(),
        "attachment_paths": attachment_paths,
    }


def attach_file(message: EmailMessage, file_path: Path) -> None:
    """Dosyayı e-postaya ekler (EmailMessage.add_attachment)."""
    mime_type, _ = mimetypes.guess_type(file_path.name)
    if mime_type is None:
        maintype, subtype = "application", "octet-stream"
    else:
        maintype, subtype = mime_type.split("/", 1)

    with file_path.open("rb") as handle:
        data = handle.read()

    message.add_attachment(
        data,
        maintype=maintype,
        subtype=subtype,
        filename=file_path.name,
    )
    logging.info(
        "Ek eklendi: %s (%s/%s, %s bayt)",
        file_path.name,
        maintype,
        subtype,
        len(data),
    )


def build_message(config: ConfigDict, recipient: str) -> EmailMessage:
    """Ana içerik mailini tek alıcı için oluşturur."""
    msg = EmailMessage()
    msg["From"] = str(config["gmail_address"])
    msg["To"] = recipient
    msg["Subject"] = str(config["subject"])
    msg.set_content(str(config["body"]))

    attachments = config.get("attachment_paths", [])
    if isinstance(attachments, list):
        for path in attachments:
            if isinstance(path, Path):
                attach_file(msg, path)

    return msg


def build_report_message(
    config: ConfigDict,
    *,
    success: bool,
    body: str,
) -> EmailMessage:
    """REPORT_EMAIL için kısa durum / hata raporu oluşturur (eksiz)."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if success:
        subject = f"[Mailer] Başarı raporu — {stamp}"
    else:
        subject = f"[Mailer] HATA RAPORU — {stamp}"

    msg = EmailMessage()
    msg["From"] = str(config["gmail_address"])
    msg["To"] = str(config["report_email"])
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def open_smtp(config: ConfigDict) -> smtplib.SMTP | smtplib.SMTP_SSL:
    """SMTP oturumu açar ve giriş yapar (587 STARTTLS / 465 SSL)."""
    host = str(config["smtp_host"])
    port = int(config["smtp_port"])  # type: ignore[arg-type]
    user = str(config["gmail_address"])
    password = str(config["app_password"])
    context = ssl.create_default_context()

    if port == 465:
        server: smtplib.SMTP | smtplib.SMTP_SSL = smtplib.SMTP_SSL(
            host, port, context=context, timeout=30
        )
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()

    server.login(user, password)
    return server


def close_smtp(server: smtplib.SMTP | smtplib.SMTP_SSL) -> None:
    """SMTP bağlantısını güvenli kapatır."""
    try:
        server.quit()
    except Exception:
        logging.debug("SMTP kapatılırken uyarı oluştu.", exc_info=True)


def format_success_report(
    config: ConfigDict,
    ok_recipients: list[str],
) -> str:
    """Başarı bildirimi gövdesi."""
    attachments = config.get("attachment_paths", [])
    attachment_lines = "yok"
    if isinstance(attachments, list) and attachments:
        attachment_lines = ", ".join(
            path.name for path in attachments if isinstance(path, Path)
        )

    return (
        "Mailler başarıyla gönderildi.\n\n"
        f"Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Konu: {config['subject']}\n"
        f"Alıcı sayısı: {len(ok_recipients)}\n"
        f"Alıcılar:\n- " + "\n- ".join(ok_recipients) + "\n"
        f"Ekler: {attachment_lines}\n"
    )


def format_error_report(
    *,
    title: str,
    detail: str,
    ok_recipients: list[str] | None = None,
    failed: list[tuple[str, str]] | None = None,
) -> str:
    """Hata bildirimi gövdesi."""
    lines = [
        "HATA RAPORU",
        "",
        f"Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Özet: {title}",
        "",
        "Detay:",
        detail.strip() or "(detay yok)",
    ]
    if ok_recipients:
        lines.extend(["", "Başarılı alıcılar:", *("- " + e for e in ok_recipients)])
    if failed:
        lines.append("")
        lines.append("Başarısız alıcılar:")
        for email, err in failed:
            lines.append(f"- {email}: {err}")
    lines.append("")
    lines.append("Tam log için mailer.log dosyasına bakabilirsin.")
    return "\n".join(lines)


def send_report(
    config: ConfigDict,
    *,
    success: bool,
    body: str,
    server: smtplib.SMTP | smtplib.SMTP_SSL | None = None,
) -> bool:
    """
    REPORT_EMAIL adresine durum maili gönderir.

    Mevcut SMTP oturumu verilirse onu kullanır; yoksa yeni oturum açar.
    Rapor gönderilemezse ana akışı çökertmez; False döner.
    """
    report_to = str(config["report_email"])
    owns_server = server is None
    try:
        if server is None:
            server = open_smtp(config)
        assert server is not None
        message = build_report_message(config, success=success, body=body)
        server.send_message(message)
        logging.info("Durum raporu gönderildi: %s", report_to)
        return True
    except Exception:
        logging.exception(
            "REPORT_EMAIL adresine durum raporu gönderilemedi: %s",
            report_to,
        )
        return False
    finally:
        if owns_server and server is not None:
            close_smtp(server)


def send_to_all_recipients(
    config: ConfigDict,
) -> tuple[list[str], list[tuple[str, str]]]:
    """
    Her alıcıya bağımsız e-posta gönderir; ardından REPORT_EMAIL'e özet yollar.

    Returns:
        (başarılı_alıcılar, [(başarısız_alıcı, hata_mesajı), ...])
    """
    recipients = config["recipients"]
    if not isinstance(recipients, list) or not recipients:
        logging.error("Gönderilecek alıcı yok.")
        raise SystemExit(1)

    email_list = [r for r in recipients if isinstance(r, str)]
    ok_recipients: list[str] = []
    failed: list[tuple[str, str]] = []

    server = open_smtp(config)
    try:
        for recipient in email_list:
            try:
                message = build_message(config, recipient)
                server.send_message(message)
                ok_recipients.append(recipient)
                logging.info("Gönderildi: %s", recipient)
            except smtplib.SMTPException as exc:
                failed.append((recipient, str(exc)))
                logging.exception("Bu alıcıya gönderilemedi: %s", recipient)

        if failed:
            report_body = format_error_report(
                title="Bazı veya tüm ana alıcılara gönderim başarısız.",
                detail=(
                    f"{len(ok_recipients)} başarılı, {len(failed)} başarısız."
                ),
                ok_recipients=ok_recipients,
                failed=failed,
            )
            send_report(config, success=False, body=report_body, server=server)
        else:
            report_body = format_success_report(config, ok_recipients)
            send_report(config, success=True, body=report_body, server=server)
    finally:
        close_smtp(server)

    return ok_recipients, failed


def main() -> int:
    """
    Ana akış. Task Scheduler için anlamlı exit code döner:
      0 = tüm alıcılara başarı (+ rapor denendi)
      1 = yapılandırma / kısmi veya tam gönderim hatası
      2 = beklenmeyen hata
    """
    setup_logging()
    logging.info("Mail gönderimi başladı.")
    config: ConfigDict | None = None

    try:
        config = load_config()
        recipients = config["recipients"]
        assert isinstance(recipients, list)
        logging.info("Alıcı sayısı: %s", len(recipients))
        logging.info("Rapor adresi: %s", config["report_email"])

        ok_recipients, failed = send_to_all_recipients(config)

        attachments = config.get("attachment_paths", [])
        attachment_note = ""
        if isinstance(attachments, list) and attachments:
            names = ", ".join(
                path.name for path in attachments if isinstance(path, Path)
            )
            attachment_note = f" | ekler={names}"

        logging.info(
            "Özet: %s başarılı, %s başarısız%s",
            len(ok_recipients),
            len(failed),
            attachment_note,
        )

        if failed or not ok_recipients:
            return 1
        return 0

    except SystemExit as exc:
        code = int(exc.code) if isinstance(exc.code, int) else 1
        # Yapılandırma hatasında SMTP bilgisi eksik olabilir; rapor deneme.
        if config is not None:
            send_report(
                config,
                success=False,
                body=format_error_report(
                    title="Script yapılandırma veya kontrollü hata ile durdu.",
                    detail=f"Exit code: {code}",
                ),
            )
        return code

    except smtplib.SMTPAuthenticationError as exc:
        logging.exception(
            "Kimlik doğrulama başarısız. Uygulama Şifresi ve 2AD'yi kontrol et."
        )
        if config is not None:
            send_report(
                config,
                success=False,
                body=format_error_report(
                    title="SMTP kimlik doğrulama hatası (yanlış şifre / App Password).",
                    detail=str(exc),
                ),
            )
        return 1

    except smtplib.SMTPException as exc:
        logging.exception("SMTP hatası oluştu.")
        if config is not None:
            send_report(
                config,
                success=False,
                body=format_error_report(
                    title="SMTP hatası.",
                    detail=f"{exc}\n\n{traceback.format_exc()}",
                ),
            )
        return 1

    except TimeoutError as exc:
        logging.exception("SMTP zaman aşımı (timeout).")
        if config is not None:
            send_report(
                config,
                success=False,
                body=format_error_report(
                    title="Bağlantı zaman aşımı (timeout).",
                    detail=f"{exc}\n\n{traceback.format_exc()}",
                ),
            )
        return 1

    except OSError as exc:
        logging.exception("Ağ / bağlantı / dosya okuma hatası.")
        if config is not None:
            send_report(
                config,
                success=False,
                body=format_error_report(
                    title="Ağ veya sistem hatası (internet kopması vb.).",
                    detail=f"{exc}\n\n{traceback.format_exc()}",
                ),
            )
        return 1

    except Exception as exc:
        logging.exception("Beklenmeyen hata.")
        if config is not None:
            send_report(
                config,
                success=False,
                body=format_error_report(
                    title="Beklenmeyen hata.",
                    detail=f"{exc}\n\n{traceback.format_exc()}",
                ),
            )
        return 2

    finally:
        logging.info("Mail gönderimi sonlandı.")


if __name__ == "__main__":
    sys.exit(main())
