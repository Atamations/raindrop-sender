"""
.env yapılandırma yükleme, doğrulama ve kaydetme.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


def _resolve_base_dir() -> Path:
    """Yazılabilir kök: .env, log, schedule (exe yanı veya proje kökü)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _resolve_resource_dir() -> Path:
    """UI vb. salt-okunur kaynaklar (PyInstaller _MEIPASS / _internal)."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent / "_internal"
    return Path(__file__).resolve().parent.parent


BASE_DIR = _resolve_base_dir()
RESOURCE_DIR = _resolve_resource_dir()
LOG_FILE = BASE_DIR / "mailer.log"
ENV_FILE = BASE_DIR / ".env"

DEFAULT_ATTACHMENT_PATH = ""

ConfigDict = dict[str, Any]


def parse_single_email(raw: str, field_name: str) -> str:
    """Tek bir e-posta adresini doğrular."""
    email = raw.strip().strip('"').strip("'")
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError(f"{field_name} geçersiz: {raw!r}")
    return email


def parse_recipients(raw_recipients: str) -> list[str]:
    """Virgülle ayrılmış alıcı adreslerini parse eder."""
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
            raise ValueError(f"Geçersiz e-posta adresi: {email!r}")
        seen.add(key)
        recipients.append(email)

    if not recipients:
        raise ValueError("RECIPIENT_EMAIL içinde geçerli adres bulunamadı.")

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
            raise FileNotFoundError(f"Ek dosya bulunamadı: {path}")

        paths.append(path)

    return paths


def paths_to_env_value(paths: list[str] | list[Path]) -> str:
    """Path listesini ATTACHMENT_PATH .env formatına çevirir."""
    return ";".join(str(p) for p in paths if str(p).strip())


def load_config(*, require_attachments_exist: bool = True) -> ConfigDict:
    """
    .env dosyasından ayarları yükler ve doğrular.

    Raises:
        ValueError / FileNotFoundError: Geçersiz yapılandırma.
    """
    load_dotenv(ENV_FILE, override=True)

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
        raise ValueError(f"Eksik .env değişkenleri: {', '.join(missing)}")

    port_raw = os.getenv("SMTP_PORT", "587").strip()
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ValueError(f"SMTP_PORT sayı olmalı, gelen: {port_raw!r}") from exc

    if port not in (587, 465):
        raise ValueError(f"Gmail için SMTP_PORT 587 veya 465 olmalı, gelen: {port}")

    recipients = parse_recipients(os.getenv("RECIPIENT_EMAIL", ""))
    report_email = parse_single_email(os.getenv("REPORT_EMAIL", ""), "REPORT_EMAIL")

    env_attachment = os.getenv("ATTACHMENT_PATH", "").strip()
    attachment_raw = env_attachment or DEFAULT_ATTACHMENT_PATH

    if require_attachments_exist:
        attachment_paths = resolve_attachment_paths(attachment_raw)
    else:
        attachment_paths = []
        for part in attachment_raw.split(";"):
            path_str = part.strip().strip('"').strip("'")
            if path_str:
                attachment_paths.append(Path(path_str))

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
        "attachment_raw": attachment_raw,
    }


def config_for_ui() -> dict[str, Any]:
    """
    UI için güvenli yapılandırma (şifre maskeli).
    Eksik .env durumunda boş form alanları döner.
    """
    load_dotenv(ENV_FILE, override=True)
    password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
    masked = ("*" * 12) if password else ""

    return {
        "gmail_address": os.getenv("GMAIL_ADDRESS", "").strip(),
        "app_password_set": bool(password),
        "app_password_masked": masked,
        "recipients": os.getenv("RECIPIENT_EMAIL", "").strip(),
        "report_email": os.getenv("REPORT_EMAIL", "").strip(),
        "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
        "smtp_port": os.getenv("SMTP_PORT", "587").strip(),
        "subject": os.getenv("EMAIL_SUBJECT", "").strip(),
        "body": os.getenv("EMAIL_BODY", "").strip(),
        "attachment_path": os.getenv("ATTACHMENT_PATH", "").strip(),
        "env_exists": ENV_FILE.is_file(),
    }


def _resolve_password(payload: dict[str, Any]) -> str:
    """Yeni şifre veya mevcut .env şifresi."""
    load_dotenv(ENV_FILE, override=True)
    current_password = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
    new_password = str(payload.get("app_password", "")).strip().replace(" ", "")
    if not new_password or set(new_password) <= {"*"}:
        return current_password
    return new_password


def save_account(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Yalnızca hesap alanlarını .env'e yazar (çoklu oturum modeli).
    Oturum içerik alanlarını zorlamaz; mevcut RECIPIENT/SUBJECT korunur.
    """
    load_dotenv(ENV_FILE, override=True)
    password_to_store = _resolve_password(payload)
    gmail = str(payload.get("gmail_address", "")).strip() or os.getenv(
        "GMAIL_ADDRESS", ""
    ).strip()
    report = str(payload.get("report_email", "")).strip() or os.getenv(
        "REPORT_EMAIL", ""
    ).strip()
    smtp_host = (
        str(payload.get("smtp_host", "")).strip()
        or os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
        or "smtp.gmail.com"
    )
    smtp_port = (
        str(payload.get("smtp_port", "")).strip()
        or os.getenv("SMTP_PORT", "587").strip()
        or "587"
    )

    if not gmail:
        raise ValueError("Gmail adresi gerekli.")
    if not report:
        raise ValueError("Hata raporu adresi (REPORT_EMAIL) gerekli.")
    if not password_to_store:
        raise ValueError("GMAIL_APP_PASSWORD gerekli (Uygulama Şifresi).")

    parse_single_email(gmail, "GMAIL_ADDRESS")
    parse_single_email(report, "REPORT_EMAIL")

    values = {
        "GMAIL_ADDRESS": gmail,
        "GMAIL_APP_PASSWORD": password_to_store,
        "RECIPIENT_EMAIL": os.getenv("RECIPIENT_EMAIL", "").strip(),
        "REPORT_EMAIL": report,
        "SMTP_HOST": smtp_host,
        "SMTP_PORT": smtp_port,
        "EMAIL_SUBJECT": os.getenv("EMAIL_SUBJECT", "").strip(),
        "EMAIL_BODY": os.getenv("EMAIL_BODY", "").strip(),
        "ATTACHMENT_PATH": os.getenv("ATTACHMENT_PATH", "").strip(),
    }
    _write_env(values)
    logging.info(".env hesap alanları kaydedildi.")
    return config_for_ui()


def save_config(payload: dict[str, Any]) -> dict[str, Any]:
    """
    UI'dan gelen alanları .env dosyasına yazar (tek-oturum / legacy).

    app_password boş veya sadece '*' ise mevcut şifre korunur.
    """
    password_to_store = _resolve_password(payload)

    attachments = payload.get("attachment_path", "")
    if isinstance(attachments, list):
        attachment_value = paths_to_env_value(attachments)
    else:
        attachment_value = str(attachments or "").strip()

    values = {
        "GMAIL_ADDRESS": str(payload.get("gmail_address", "")).strip(),
        "GMAIL_APP_PASSWORD": password_to_store,
        "RECIPIENT_EMAIL": str(payload.get("recipients", "")).strip(),
        "REPORT_EMAIL": str(payload.get("report_email", "")).strip(),
        "SMTP_HOST": str(payload.get("smtp_host", "smtp.gmail.com")).strip()
        or "smtp.gmail.com",
        "SMTP_PORT": str(payload.get("smtp_port", "587")).strip() or "587",
        "EMAIL_SUBJECT": str(payload.get("subject", "")).strip(),
        "EMAIL_BODY": str(payload.get("body", "")).strip(),
        "ATTACHMENT_PATH": attachment_value,
    }

    for key in ("GMAIL_ADDRESS", "RECIPIENT_EMAIL", "REPORT_EMAIL"):
        if not values[key]:
            raise ValueError(f"{key} boş olamaz.")
    if not values["GMAIL_APP_PASSWORD"]:
        raise ValueError("GMAIL_APP_PASSWORD gerekli (Uygulama Şifresi).")

    parse_recipients(values["RECIPIENT_EMAIL"])
    parse_single_email(values["REPORT_EMAIL"], "REPORT_EMAIL")
    parse_single_email(values["GMAIL_ADDRESS"], "GMAIL_ADDRESS")

    _write_env(values)
    logging.info(".env kaydedildi.")
    return config_for_ui()


def _write_env(values: dict[str, str]) -> None:
    lines = [
        "# Raindrop Mail Sender — otomatik yazıldı",
        f"GMAIL_ADDRESS={values['GMAIL_ADDRESS']}",
        f"GMAIL_APP_PASSWORD={values['GMAIL_APP_PASSWORD']}",
        f"RECIPIENT_EMAIL={values['RECIPIENT_EMAIL']}",
        f"REPORT_EMAIL={values['REPORT_EMAIL']}",
        f"SMTP_HOST={values['SMTP_HOST']}",
        f"SMTP_PORT={values['SMTP_PORT']}",
        f"EMAIL_SUBJECT={_escape_env(values['EMAIL_SUBJECT'])}",
        f"EMAIL_BODY={_escape_env(values['EMAIL_BODY'])}",
        f"ATTACHMENT_PATH={values['ATTACHMENT_PATH']}",
        "",
    ]
    ENV_FILE.write_text("\n".join(lines), encoding="utf-8")


def _escape_env(value: str) -> str:
    """Çok satırlı veya özel karakterli değerleri tırnaklar."""
    if "\n" in value or "#" in value or value.startswith(" ") or value.endswith(" "):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    return value


def read_log_tail(max_lines: int = 80) -> str:
    """mailer.log dosyasının son satırlarını döner."""
    if not LOG_FILE.is_file():
        return "Henüz log yok."
    try:
        text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"Log okunamadı: {exc}"
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])
