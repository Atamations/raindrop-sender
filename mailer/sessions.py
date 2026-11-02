"""
Çoklu oturum (kampanya) modeli.

Her oturum: alıcılar + içerik + kendi zamanlaması + ayrı Task Scheduler görevi.
Hesap (Gmail) paylaşımlı .env'de kalır — sunucu/multitask için hazır ayrım.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import string
from datetime import datetime
from pathlib import Path
from typing import Any

from mailer.config import (
    BASE_DIR,
    config_for_ui,
    load_config,
    parse_recipients,
    parse_single_email,
    resolve_attachment_paths,
    save_account,
)
from mailer.schedule import (
    _default_schedule,
    _describe,
    _sanitize_prefs,
    apply_schedule_for_session,
    get_schedule_status_for_session,
    load_schedule_prefs,
)

SESSIONS_DIR = BASE_DIR / "sessions"
INDEX_FILE = SESSIONS_DIR / "index.json"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _new_id() -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "s_" + "".join(secrets.choice(alphabet) for _ in range(10))


def _session_path(session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id)
    return SESSIONS_DIR / f"{safe}.json"


def _ensure_store() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.is_file():
        INDEX_FILE.write_text(
            json.dumps({"active_id": None, "order": []}, indent=2) + "\n",
            encoding="utf-8",
        )


def _read_index() -> dict[str, Any]:
    _ensure_store()
    try:
        # PowerShell/Windows bazen BOM yazar
        data = json.loads(INDEX_FILE.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            data.setdefault("active_id", None)
            data.setdefault("order", [])
            data.setdefault("legacy_migrated", False)
            return data
    except (OSError, json.JSONDecodeError) as exc:
        logging.warning("sessions index okunamadı: %s", exc)
    return {"active_id": None, "order": [], "legacy_migrated": False}


def _write_index(data: dict[str, Any]) -> None:
    _ensure_store()
    INDEX_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _blank_session(name: str = "Yeni oturum") -> dict[str, Any]:
    sid = _new_id()
    return {
        "id": sid,
        "name": name.strip() or "Yeni oturum",
        "recipients": "",
        "subject": "",
        "body": "",
        "attachment_path": "",
        "report_email": "",
        "schedule": _default_schedule(),
        "created_at": _now(),
        "updated_at": _now(),
    }


def _read_session(session_id: str) -> dict[str, Any] | None:
    path = _session_path(session_id)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or not raw.get("id"):
        return None
    raw.setdefault("schedule", _default_schedule())
    raw["schedule"] = _sanitize_prefs(raw.get("schedule") or {})
    return raw


def _write_session(session: dict[str, Any]) -> None:
    _ensure_store()
    session = dict(session)
    session["updated_at"] = _now()
    session["schedule"] = _sanitize_prefs(session.get("schedule") or {})
    path = _session_path(str(session["id"]))
    path.write_text(
        json.dumps(session, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _session_summary(session: dict[str, Any]) -> dict[str, Any]:
    """Sol menü kartı için özet."""
    sched = _sanitize_prefs(session.get("schedule") or {})
    status = get_schedule_status_for_session(sched, str(session["id"]))
    recipients = str(session.get("recipients") or "").strip()
    count = 0
    if recipients:
        try:
            count = len(parse_recipients(recipients))
        except ValueError:
            count = max(1, recipients.count(",") + 1) if "@" in recipients else 0

    return {
        "id": session["id"],
        "name": session.get("name") or "Oturum",
        "recipients_preview": recipients[:80],
        "recipient_count": count,
        "subject": str(session.get("subject") or "")[:60],
        "schedule_enabled": bool(sched.get("enabled")),
        "schedule_active": bool(status.get("active")),
        "schedule_summary": status.get("summary") or _describe(sched),
        "schedule_message": status.get("message") or "",
        "task_name": status.get("task_name") or "",
        "updated_at": session.get("updated_at") or "",
    }


def migrate_legacy_if_needed() -> None:
    """
    Eski tek-.env / schedule.json kurulumunu yalnızca bir kez ilk oturuma taşır.
    Kullanıcı tüm oturumları sildiyse boş liste korunur (yeniden üretmez).
    """
    _ensure_store()
    index = _read_index()
    if index.get("order") or index.get("legacy_migrated"):
        return

    # Diskte zaten oturum dosyası varsa sadece bayrağı işaretle
    existing_files = list(SESSIONS_DIR.glob("s_*.json"))
    if existing_files:
        order = [p.stem for p in sorted(existing_files)]
        index["order"] = order
        index["active_id"] = order[0]
        index["legacy_migrated"] = True
        _write_index(index)
        return

    account = config_for_ui()
    legacy_sched = (
        load_schedule_prefs()
        if (BASE_DIR / "schedule.json").is_file()
        else _default_schedule()
    )

    has_mail = bool(
        account.get("recipients") or account.get("subject") or account.get("body")
    )
    # İlk kurulumda .env yoksa boş bırak — kullanıcı + ile ekler
    if not (has_mail or account.get("env_exists")):
        index["legacy_migrated"] = True
        index["active_id"] = None
        index["order"] = []
        _write_index(index)
        return

    session = _blank_session("Varsayılan oturum")
    session["recipients"] = account.get("recipients") or ""
    session["subject"] = account.get("subject") or ""
    session["body"] = account.get("body") or ""
    session["attachment_path"] = account.get("attachment_path") or ""
    session["report_email"] = ""
    session["schedule"] = legacy_sched
    if legacy_sched.get("enabled"):
        session["schedule"] = {**legacy_sched, "enabled": True}

    _write_session(session)
    _write_index(
        {
            "active_id": session["id"],
            "order": [session["id"]],
            "legacy_migrated": True,
        }
    )
    logging.info("İlk oturum oluşturuldu: %s", session["id"])


def list_sessions() -> dict[str, Any]:
    migrate_legacy_if_needed()
    index = _read_index()
    items: list[dict[str, Any]] = []
    order = list(index.get("order") or [])
    seen: set[str] = set()

    for sid in order:
        session = _read_session(str(sid))
        if session:
            items.append(_session_summary(session))
            seen.add(str(sid))

    # Orphan dosyalar
    for path in sorted(SESSIONS_DIR.glob("s_*.json")):
        sid = path.stem
        if sid in seen:
            continue
        session = _read_session(sid)
        if session:
            items.append(_session_summary(session))
            order.append(sid)

    if order != index.get("order"):
        index["order"] = order
        _write_index(index)

    active_id = index.get("active_id")
    if active_id and not any(i["id"] == active_id for i in items):
        active_id = items[0]["id"] if items else None
        index["active_id"] = active_id
        _write_index(index)
    if not active_id and items:
        active_id = items[0]["id"]
        index["active_id"] = active_id
        _write_index(index)

    return {
        "ok": True,
        "active_id": active_id,
        "sessions": items,
        "account": config_for_ui(),
    }


def get_session(session_id: str) -> dict[str, Any]:
    migrate_legacy_if_needed()
    session = _read_session(session_id)
    if not session:
        return {"ok": False, "message": f"Oturum bulunamadı: {session_id}"}

    sched = get_schedule_status_for_session(
        session.get("schedule") or {},
        str(session["id"]),
    )
    return {
        "ok": True,
        "session": session,
        "schedule": sched,
        "account": config_for_ui(),
        "summary": _session_summary(session),
        "sessions": [],  # çağıran doldurabilir
    }


def set_active_session(session_id: str) -> dict[str, Any]:
    session = _read_session(session_id)
    if not session:
        return {"ok": False, "message": "Oturum bulunamadı."}
    index = _read_index()
    index["active_id"] = session_id
    if session_id not in index.get("order", []):
        index.setdefault("order", []).append(session_id)
    _write_index(index)
    payload = get_session(session_id)
    payload["sessions"] = list_sessions()["sessions"]
    return payload


def create_session(name: str | None = None) -> dict[str, Any]:
    migrate_legacy_if_needed()
    session = _blank_session(name or f"Oturum {datetime.now().strftime('%H:%M')}")
    _write_session(session)
    index = _read_index()
    index.setdefault("order", []).append(session["id"])
    index["active_id"] = session["id"]
    index["legacy_migrated"] = True
    _write_index(index)
    logging.info("Yeni oturum: %s (%s)", session["name"], session["id"])
    return get_session(session["id"]) | {"sessions": list_sessions()["sessions"]}


def delete_session(session_id: str) -> dict[str, Any]:
    session = _read_session(session_id)
    if not session:
        return {"ok": False, "message": "Oturum bulunamadı."}

    # Windows görevini kapat
    try:
        apply_schedule_for_session(
            {**(session.get("schedule") or {}), "enabled": False},
            session_id=str(session_id),
            session_name=str(session.get("name") or ""),
        )
    except Exception:
        logging.exception("Oturum görevi silinirken uyarı.")

    path = _session_path(session_id)
    if path.is_file():
        path.unlink()

    index = _read_index()
    index["order"] = [x for x in index.get("order", []) if x != session_id]
    if index.get("active_id") == session_id:
        index["active_id"] = index["order"][0] if index["order"] else None
    # Boş kalsın — otomatik Varsayılan üretme
    index["legacy_migrated"] = True
    _write_index(index)

    listed = list_sessions()
    if not listed.get("sessions"):
        return {
            "ok": True,
            "message": "Tüm oturumlar silindi.",
            "session": None,
            "schedule": None,
            "summary": None,
            "account": listed.get("account"),
            "sessions": [],
            "active_id": None,
        }

    active = listed.get("active_id")
    result = get_session(str(active)) if active else listed
    result["ok"] = True
    result["message"] = "Oturum silindi."
    result["sessions"] = listed["sessions"]
    return result


def save_session_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    UI kaydı: oturum alanları + zamanlama + (opsiyonel) hesap.
    Exception fırlatmaz; {ok, message, ...} döner.
    """
    try:
        session_id = str(payload.get("id") or "").strip()
        if not session_id:
            return {"ok": False, "message": "Oturum id eksik.", "field": "id"}

        existing = _read_session(session_id)
        if not existing:
            return {"ok": False, "message": "Oturum bulunamadı.", "field": "id"}

        name = str(payload.get("name") or existing.get("name") or "Oturum").strip()
        recipients = str(payload.get("recipients") or "").strip()
        report = str(payload.get("report_email") or "").strip()

        account_ui = config_for_ui()
        effective_report = report or str(account_ui.get("report_email") or "").strip()
        if not effective_report:
            return {
                "ok": False,
                "message": "Hata raporu adresi gerekli (oturum veya Hesap sekmesi).",
                "field": "reportEmail",
            }

        # Hesap alanları geldiyse .env güncelle
        if any(
            k in payload
            for k in (
                "gmail_address",
                "app_password",
                "smtp_port",
                "smtp_host",
                "account_report_email",
            )
        ):
            try:
                save_account(
                    {
                        "gmail_address": payload.get("gmail_address"),
                        "app_password": payload.get("app_password"),
                        "report_email": payload.get("account_report_email")
                        or effective_report,
                        "smtp_host": payload.get("smtp_host", "smtp.gmail.com"),
                        "smtp_port": payload.get("smtp_port", "587"),
                    }
                )
            except Exception as exc:
                msg = str(exc)
                field = "gmailAddress"
                if "REPORT" in msg.upper() or "rapor" in msg.lower():
                    field = "reportEmail"
                elif "PASSWORD" in msg.upper() or "şifre" in msg.lower():
                    field = "appPassword"
                return {"ok": False, "message": msg, "field": field}

        if recipients:
            try:
                parse_recipients(recipients)
            except ValueError as exc:
                return {"ok": False, "message": str(exc), "field": "recipients"}

        if report:
            try:
                parse_single_email(report, "REPORT_EMAIL")
            except ValueError as exc:
                return {"ok": False, "message": str(exc), "field": "reportEmail"}

        schedule_raw = payload.get("schedule")
        if not isinstance(schedule_raw, dict):
            schedule_raw = existing.get("schedule") or _default_schedule()

        session = {
            **existing,
            "name": name,
            "recipients": recipients,
            "subject": str(payload.get("subject") or "").strip(),
            "body": str(payload.get("body") or ""),
            "attachment_path": str(payload.get("attachment_path") or "").strip(),
            "report_email": report,
            "schedule": _sanitize_prefs(schedule_raw),
        }

        apply_sched = bool(payload.get("apply_schedule", True))
        if apply_sched:
            try:
                sched_status = apply_schedule_for_session(
                    session["schedule"],
                    session_id=session_id,
                    session_name=name,
                )
            except Exception as exc:
                logging.exception("Zamanlama uygulanamadı.")
                return {
                    "ok": False,
                    "message": f"Oturum kaydedilemedi (zamanlama): {exc}",
                    "field": "schedule",
                }
            session["schedule"] = {
                **session["schedule"],
                "enabled": bool(sched_status.get("enabled")),
            }
        else:
            # Gönderim öncesi hızlı kayıt — TS'ye dokunma; enabled bayrağını
            # mevcut oturumdan koru (formda Etkin açıkken görevsiz "aktif" yazma).
            preserved = _sanitize_prefs(existing.get("schedule") or {})
            session["schedule"] = {
                **session["schedule"],
                "enabled": bool(preserved.get("enabled")),
            }
            sched_status = get_schedule_status_for_session(
                session["schedule"], session_id
            )

        _write_session(session)

        index = _read_index()
        index["active_id"] = session_id
        _write_index(index)

        result = get_session(session_id)
        result["ok"] = True
        result["message"] = "Oturum kaydedildi."
        result["sessions"] = list_sessions()["sessions"]
        return result
    except Exception as exc:
        logging.exception("save_session_payload hata")
        return {"ok": False, "message": str(exc)}


def set_session_automation(session_id: str, enabled: bool) -> dict[str, Any]:
    """Sol menüden otomasyonu aç/kapa (içeriğe girmeden)."""
    session = _read_session(session_id)
    if not session:
        return {"ok": False, "message": "Oturum bulunamadı."}

    sched = _sanitize_prefs(session.get("schedule") or {})
    sched["enabled"] = bool(enabled)
    try:
        status = apply_schedule_for_session(
            sched,
            session_id=session_id,
            session_name=str(session.get("name") or ""),
        )
    except Exception as exc:
        return {"ok": False, "message": str(exc)}

    session["schedule"] = {**sched, "enabled": bool(status.get("enabled"))}
    _write_session(session)
    result = get_session(session_id)
    result["ok"] = True
    result["message"] = "Otomasyon güncellendi." if enabled else "Otomasyon durduruldu."
    result["sessions"] = list_sessions()["sessions"]
    return result


def build_send_config(session_id: str | None = None) -> dict[str, Any]:
    """
    SMTP gönderimi için birleşik config.
    Oturum alanları + .env hesabı.
    """
    migrate_legacy_if_needed()
    if not session_id:
        index = _read_index()
        session_id = index.get("active_id")

    if not session_id:
        return load_config(require_attachments_exist=True)

    session = _read_session(str(session_id))
    if not session:
        raise ValueError(f"Oturum bulunamadı: {session_id}")

    # Hesap zorunlu alanlar
    base = load_config(require_attachments_exist=False)

    recipients_raw = str(session.get("recipients") or "").strip()
    if not recipients_raw:
        raise ValueError("Bu oturumda alıcı yok.")
    recipients = parse_recipients(recipients_raw)

    report = str(session.get("report_email") or "").strip() or str(base["report_email"])
    parse_single_email(report, "REPORT_EMAIL")

    attachment_raw = str(session.get("attachment_path") or "").strip()
    attachments = resolve_attachment_paths(attachment_raw) if attachment_raw else []

    return {
        **base,
        "recipients": recipients,
        "report_email": report,
        "subject": str(session.get("subject") or "").strip(),
        "body": str(session.get("body") or ""),
        "attachment_paths": attachments,
        "attachment_raw": attachment_raw,
        "session_id": session_id,
        "session_name": session.get("name") or "",
    }


def rename_session(session_id: str, name: str) -> dict[str, Any]:
    session = _read_session(session_id)
    if not session:
        return {"ok": False, "message": "Oturum bulunamadı."}
    session["name"] = (name or "").strip() or session.get("name") or "Oturum"
    _write_session(session)
    # Görev açıklamasını güncelle (etkinse)
    if session.get("schedule", {}).get("enabled"):
        try:
            apply_schedule_for_session(
                session["schedule"],
                session_id=session_id,
                session_name=session["name"],
            )
        except Exception:
            logging.exception("İsim güncellemesinde görev yenileme uyarısı.")
    result = get_session(session_id)
    result["ok"] = True
    result["sessions"] = list_sessions()["sessions"]
    return result
