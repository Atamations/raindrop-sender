"""
Gmail SMTP gönderimi: çoklu alıcı, ekler, REPORT_EMAIL durumu.
"""

from __future__ import annotations

import logging
import mimetypes
import smtplib
import ssl
import traceback
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from mailer.report import format_error_report


def attach_file(message: EmailMessage, file_path: Path) -> None:
    """Dosyayı e-postaya ekler."""
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


def build_message(config: dict[str, Any], recipient: str) -> EmailMessage:
    """Ana içerik mailini tek alıcı için oluşturur."""
    msg = EmailMessage()
    msg["From"] = str(config["gmail_address"])
    msg["To"] = recipient
    msg["Subject"] = str(config["subject"])
    msg.set_content(str(config["body"]))

    attachments = config.get("attachment_paths", [])
    if isinstance(attachments, list):
        for path in attachments:
            p = path if isinstance(path, Path) else Path(str(path))
            attach_file(msg, p)

    return msg


def build_report_message(
    config: dict[str, Any],
    *,
    success: bool,
    body: str,
) -> EmailMessage:
    """REPORT_EMAIL için kısa durum / hata raporu (eksiz)."""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject = (
        f"[Mailer] Başarı raporu — {stamp}"
        if success
        else f"[Mailer] HATA RAPORU — {stamp}"
    )

    msg = EmailMessage()
    msg["From"] = str(config["gmail_address"])
    msg["To"] = str(config["report_email"])
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


def open_smtp(config: dict[str, Any]) -> smtplib.SMTP | smtplib.SMTP_SSL:
    """SMTP oturumu açar (587 STARTTLS / 465 SSL)."""
    host = str(config["smtp_host"])
    port = int(config["smtp_port"])
    user = str(config["gmail_address"])
    password = str(config["app_password"])
    context = ssl.create_default_context()

    if port == 465:
        server: smtplib.SMTP | smtplib.SMTP_SSL = smtplib.SMTP_SSL(
            host, port, context=context, timeout=20
        )
    else:
        server = smtplib.SMTP(host, port, timeout=20)
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


def send_report(
    config: dict[str, Any],
    *,
    success: bool,
    body: str,
    server: smtplib.SMTP | smtplib.SMTP_SSL | None = None,
) -> bool:
    """REPORT_EMAIL adresine durum maili gönderir."""
    report_to = str(config["report_email"])
    owns_server = server is None
    active = server
    try:
        if active is None:
            active = open_smtp(config)
        message = build_report_message(config, success=success, body=body)
        active.send_message(message)
        logging.info("Durum raporu gönderildi: %s", report_to)
        return True
    except Exception:
        logging.exception(
            "REPORT_EMAIL adresine durum raporu gönderilemedi: %s",
            report_to,
        )
        return False
    finally:
        if owns_server and active is not None:
            close_smtp(active)


def send_campaign(config: dict[str, Any]) -> dict[str, Any]:
    """
    Her alıcıya bağımsız e-posta gönderir.
    Yalnızca sorun olursa REPORT_EMAIL'e hata raporu yollar.
    Başarılar mailer.log + UI aktivite panelinde tutulur.

    Returns:
        ok, failed, message özet sözlüğü.
    """
    recipients = config.get("recipients") or []
    if not recipients:
        raise ValueError("Gönderilecek alıcı yok.")

    email_list = [str(r) for r in recipients]
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
                detail=f"{len(ok_recipients)} başarılı, {len(failed)} başarısız.",
                ok_recipients=ok_recipients,
                failed=failed,
            )
            send_report(config, success=False, body=report_body, server=server)
        else:
            logging.info(
                "Tüm alıcılara başarıyla gönderildi; başarı raporu maili gönderilmedi."
            )
    finally:
        close_smtp(server)

    success = bool(ok_recipients) and not failed
    return {
        "ok": success,
        "ok_count": len(ok_recipients),
        "fail_count": len(failed),
        "ok_recipients": ok_recipients,
        "failed": [{"email": e, "error": err} for e, err in failed],
        "message": (
            f"{len(ok_recipients)} başarılı, {len(failed)} başarısız"
            if failed
            else f"Mailler başarıyla gönderildi ({len(ok_recipients)} alıcı)."
        ),
    }


def send_error_report_safe(config: dict[str, Any] | None, title: str, exc: BaseException) -> None:
    """Kritik hatalarda mümkünse REPORT_EMAIL'e bildirim dener."""
    if config is None:
        return
    send_report(
        config,
        success=False,
        body=format_error_report(
            title=title,
            detail=f"{exc}\n\n{traceback.format_exc()}",
        ),
    )
