"""
Uygulama içi zamanlama — Task Scheduler 'Edit Trigger' seviyesinde ayarlar.
Görev XML ile kaydedilir (tekrar, süre, expire, random delay, execution limit).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from typing import Any
from xml.dom import minidom

from mailer.config import BASE_DIR

TASK_NAME = "RaindropMailSender"
SCHEDULE_FILE = BASE_DIR / "schedule.json"
TASK_XML_FILE = BASE_DIR / ".task_raindrop.xml"
BAT_PATH = BASE_DIR / "run_mailer.bat"

WEEKDAY_XML = {
    "mon": "Monday",
    "tue": "Tuesday",
    "wed": "Wednesday",
    "thu": "Thursday",
    "fri": "Friday",
    "sat": "Saturday",
    "sun": "Sunday",
}
WEEKDAY_LABELS = {
    "mon": "Pzt",
    "tue": "Sal",
    "wed": "Çar",
    "thu": "Per",
    "fri": "Cum",
    "sat": "Cmt",
    "sun": "Paz",
}
FREQUENCIES = ("once", "daily", "weekly", "monthly")

# UI seçenekleri → ISO-8601 süre
DELAY_CHOICES = {
    "30 seconds": "PT30S",
    "1 minute": "PT1M",
    "15 minutes": "PT15M",
    "30 minutes": "PT30M",
    "1 hour": "PT1H",
    "4 hours": "PT4H",
    "8 hours": "PT8H",
}
REPEAT_EVERY_CHOICES = {
    "5 minutes": "PT5M",
    "10 minutes": "PT10M",
    "15 minutes": "PT15M",
    "20 minutes": "PT20M",
    "30 minutes": "PT30M",
    "1 hour": "PT1H",
}
REPEAT_FOR_CHOICES = {
    "1 hour": "PT1H",
    "8 hours": "PT8H",
    "12 hours": "PT12H",
    "1 day": "P1D",
    "indefinitely": "P3650D",
}
STOP_AFTER_CHOICES = {
    "1 hour": "PT1H",
    "2 hours": "PT2H",
    "4 hours": "PT4H",
    "8 hours": "PT8H",
    "12 hours": "PT12H",
    "1 day": "P1D",
    "3 days": "P3D",
}


def _default_schedule() -> dict[str, Any]:
    today = date.today().isoformat()
    return {
        "enabled": False,
        "frequency": "weekly",
        "time": "09:00",
        "start_date": today,
        "sync_timezones": False,
        "interval": 1,
        "weekdays": ["mon", "tue", "wed", "thu", "fri"],
        "month_day": 1,
        "delay_enabled": False,
        "delay_for": "1 hour",
        "repeat_enabled": False,
        "repeat_every": "20 minutes",
        "repeat_for": "8 hours",
        "repeat_stop_at_end": False,
        "stop_if_runs_longer_enabled": False,
        "stop_if_runs_longer": "3 days",
        "expire_enabled": False,
        "expire_date": today,
        "expire_time": "21:00",
    }


def load_schedule_prefs() -> dict[str, Any]:
    data = _default_schedule()
    if SCHEDULE_FILE.is_file():
        try:
            raw = json.loads(SCHEDULE_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data.update(raw)
        except (OSError, json.JSONDecodeError) as exc:
            logging.warning("schedule.json okunamadı: %s", exc)
    return _sanitize_prefs(data)


def _normalize_time(time_str: str) -> str:
    value = (time_str or "").strip()
    # 09:00 veya 09:00:00
    if re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", value):
        value = value[:5]
    if not re.fullmatch(r"\d{1,2}:\d{2}", value):
        raise ValueError("Saat HH:MM formatında olmalı.")
    hour_s, minute_s = value.split(":")
    hour, minute = int(hour_s), int(minute_s)
    if hour > 23 or minute > 59:
        raise ValueError("Geçersiz saat.")
    return f"{hour:02d}:{minute:02d}"


def _sanitize_prefs(raw: dict[str, Any]) -> dict[str, Any]:
    base = _default_schedule()
    freq = str(raw.get("frequency", "weekly")).lower()
    if freq not in FREQUENCIES:
        freq = "weekly"

    weekdays = raw.get("weekdays") or base["weekdays"]
    if not isinstance(weekdays, list):
        weekdays = base["weekdays"]
    weekdays = [str(d).lower()[:3] for d in weekdays if str(d).lower()[:3] in WEEKDAY_XML]
    if not weekdays and freq == "weekly":
        weekdays = list(base["weekdays"])

    def _int(key: str, lo: int, hi: int, default: int) -> int:
        try:
            return max(lo, min(hi, int(raw.get(key, default))))
        except (TypeError, ValueError):
            return default

    def _date(key: str) -> str:
        value = str(raw.get(key) or base[key]).strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return str(base[key])
        return value

    repeat_every = str(raw.get("repeat_every") or "30 minutes")
    if repeat_every not in REPEAT_EVERY_CHOICES:
        repeat_every = "30 minutes"

    delay_for = str(raw.get("delay_for") or "1 hour")
    if delay_for not in DELAY_CHOICES:
        delay_for = "1 hour"

    repeat_for = str(raw.get("repeat_for") or "8 hours")
    if repeat_for not in REPEAT_FOR_CHOICES:
        repeat_for = "8 hours"

    stop_longer = str(raw.get("stop_if_runs_longer") or "3 days")
    if stop_longer not in STOP_AFTER_CHOICES:
        stop_longer = "3 days"

    def _safe_time(key: str, fallback: str) -> str:
        """Bozuk saat değerinde varsayılana düş (UI açılışını çökertmesin)."""
        try:
            return _normalize_time(str(raw.get(key, fallback)))
        except ValueError:
            logging.warning("Geçersiz saat (%s=%r); varsayılan: %s", key, raw.get(key), fallback)
            return fallback

    return {
        "enabled": bool(raw.get("enabled")),
        "frequency": freq,
        "time": _safe_time("time", "09:00"),
        "start_date": _date("start_date"),
        "sync_timezones": bool(raw.get("sync_timezones")),
        "interval": _int("interval", 1, 365, 1),
        "weekdays": weekdays,
        "month_day": _int("month_day", 1, 31, 1),
        "delay_enabled": bool(raw.get("delay_enabled")),
        "delay_for": delay_for,
        "repeat_enabled": bool(raw.get("repeat_enabled")),
        "repeat_every": repeat_every,
        "repeat_for": repeat_for,
        "repeat_stop_at_end": bool(raw.get("repeat_stop_at_end")),
        "stop_if_runs_longer_enabled": bool(raw.get("stop_if_runs_longer_enabled")),
        "stop_if_runs_longer": stop_longer,
        "expire_enabled": bool(raw.get("expire_enabled")),
        "expire_date": _date("expire_date"),
        "expire_time": _safe_time("expire_time", "21:00"),
    }


def save_schedule_prefs(prefs: dict[str, Any]) -> None:
    clean = _sanitize_prefs(prefs)
    SCHEDULE_FILE.write_text(
        json.dumps(clean, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _boundary(date_iso: str, time_hm: str) -> str:
    return f"{date_iso}T{_normalize_time(time_hm)}:00"


def _to_iso_duration_minutes_label(label: str) -> str:
    if label in REPEAT_EVERY_CHOICES:
        return REPEAT_EVERY_CHOICES[label]
    match = re.fullmatch(r"(\d+)\s*minutes?", label.strip())
    if match:
        return f"PT{int(match.group(1))}M"
    match = re.fullmatch(r"(\d+)\s*hours?", label.strip())
    if match:
        return f"PT{int(match.group(1))}H"
    return "PT30M"


def _build_calendar_trigger(prefs: dict[str, Any]) -> ET.Element:
    ns = ""
    trigger = ET.Element("CalendarTrigger")

    start = _boundary(prefs["start_date"], prefs["time"])
    ET.SubElement(trigger, "StartBoundary").text = start
    ET.SubElement(trigger, "Enabled").text = "true"

    if prefs["expire_enabled"]:
        ET.SubElement(trigger, "EndBoundary").text = _boundary(
            prefs["expire_date"], prefs["expire_time"]
        )

    if prefs["delay_enabled"]:
        delay = DELAY_CHOICES.get(prefs["delay_for"], "PT1H")
        ET.SubElement(trigger, "RandomDelay").text = delay

    if prefs["repeat_enabled"]:
        rep = ET.SubElement(trigger, "Repetition")
        ET.SubElement(rep, "Interval").text = _to_iso_duration_minutes_label(
            prefs["repeat_every"]
        )
        ET.SubElement(rep, "Duration").text = REPEAT_FOR_CHOICES.get(
            prefs["repeat_for"], "PT8H"
        )
        ET.SubElement(rep, "StopAtDurationEnd").text = (
            "true" if prefs["repeat_stop_at_end"] else "false"
        )

    freq = prefs["frequency"]
    if freq == "once":
        # Tek sefer: ScheduleByDay yok; sadece StartBoundary yeterli + TimeTrigger benzeri
        # CalendarTrigger one-time: boş schedule + start — Windows OneTime kullanır
        pass
    elif freq == "daily":
        schedule = ET.SubElement(trigger, "ScheduleByDay")
        ET.SubElement(schedule, "DaysInterval").text = str(prefs["interval"])
    elif freq == "weekly":
        schedule = ET.SubElement(trigger, "ScheduleByWeek")
        ET.SubElement(schedule, "WeeksInterval").text = str(prefs["interval"])
        days = ET.SubElement(schedule, "DaysOfWeek")
        for key in prefs["weekdays"]:
            ET.SubElement(days, WEEKDAY_XML[key])
    elif freq == "monthly":
        schedule = ET.SubElement(trigger, "ScheduleByMonth")
        days = ET.SubElement(schedule, "DaysOfMonth")
        ET.SubElement(days, "Day").text = str(prefs["month_day"])
        months = ET.SubElement(schedule, "Months")
        for m in (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ):
            ET.SubElement(months, m)

    # One-time: TimeTrigger daha doğru
    if freq == "once":
        tt = ET.Element("TimeTrigger")
        ET.SubElement(tt, "StartBoundary").text = start
        ET.SubElement(tt, "Enabled").text = "true"
        if prefs["expire_enabled"]:
            ET.SubElement(tt, "EndBoundary").text = _boundary(
                prefs["expire_date"], prefs["expire_time"]
            )
        if prefs["delay_enabled"]:
            ET.SubElement(tt, "RandomDelay").text = DELAY_CHOICES.get(
                prefs["delay_for"], "PT1H"
            )
        if prefs["repeat_enabled"]:
            rep = ET.SubElement(tt, "Repetition")
            ET.SubElement(rep, "Interval").text = _to_iso_duration_minutes_label(
                prefs["repeat_every"]
            )
            ET.SubElement(rep, "Duration").text = REPEAT_FOR_CHOICES.get(
                prefs["repeat_for"], "PT8H"
            )
            ET.SubElement(rep, "StopAtDurationEnd").text = (
                "true" if prefs["repeat_stop_at_end"] else "false"
            )
        return tt

    _ = ns
    return trigger


def build_task_xml(prefs: dict[str, Any]) -> str:
    """Windows Task Scheduler 1.2 XML üretir."""
    if not BAT_PATH.is_file():
        raise FileNotFoundError(f"Çalıştırılacak dosya yok: {BAT_PATH}")

    clean = _sanitize_prefs(prefs)
    root = ET.Element(
        "Task",
        {
            "version": "1.2",
            "xmlns": "http://schemas.microsoft.com/windows/2004/02/mit/task",
        },
    )

    reg = ET.SubElement(root, "RegistrationInfo")
    ET.SubElement(reg, "Date").text = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    ET.SubElement(reg, "Author").text = "Raindrop Mail Sender"
    ET.SubElement(reg, "Description").text = "Raindrop otomatik e-posta gönderimi"

    triggers = ET.SubElement(root, "Triggers")
    triggers.append(_build_calendar_trigger(clean))

    principals = ET.SubElement(root, "Principals")
    principal = ET.SubElement(principals, "Principal", {"id": "Author"})
    ET.SubElement(principal, "LogonType").text = "InteractiveToken"
    ET.SubElement(principal, "RunLevel").text = "LeastPrivilege"

    settings = ET.SubElement(root, "Settings")
    ET.SubElement(settings, "MultipleInstancesPolicy").text = "IgnoreNew"
    ET.SubElement(settings, "DisallowStartIfOnBatteries").text = "false"
    ET.SubElement(settings, "StopIfGoingOnBatteries").text = "false"
    ET.SubElement(settings, "AllowHardTerminate").text = "true"
    ET.SubElement(settings, "StartWhenAvailable").text = "true"
    ET.SubElement(settings, "RunOnlyIfNetworkAvailable").text = "false"
    ET.SubElement(settings, "AllowStartOnDemand").text = "true"
    ET.SubElement(settings, "Enabled").text = "true" if clean["enabled"] else "false"
    ET.SubElement(settings, "Hidden").text = "false"
    ET.SubElement(settings, "RunOnlyIfIdle").text = "false"
    ET.SubElement(settings, "WakeToRun").text = "false"
    ET.SubElement(settings, "ExecutionTimeLimit").text = (
        STOP_AFTER_CHOICES.get(clean["stop_if_runs_longer"], "P3D")
        if clean["stop_if_runs_longer_enabled"]
        else "PT72H"
    )
    ET.SubElement(settings, "Priority").text = "7"

    actions = ET.SubElement(root, "Actions", {"Context": "Author"})
    exe = ET.SubElement(actions, "Exec")
    ET.SubElement(exe, "Command").text = str(BAT_PATH.resolve())
    ET.SubElement(exe, "WorkingDirectory").text = str(BASE_DIR.resolve())

    rough = ET.tostring(root, encoding="utf-8")
    parsed = minidom.parseString(rough)
    return parsed.toprettyxml(indent="  ")


def _run_schtasks(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["schtasks", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )


def is_task_registered() -> bool:
    return _run_schtasks(["/Query", "/TN", TASK_NAME]).returncode == 0


def delete_windows_task() -> None:
    if not is_task_registered():
        return
    result = _run_schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Zamanlanmış görev silinemedi: {detail}")
    logging.info("Windows görevi silindi: %s", TASK_NAME)


def create_windows_task(prefs: dict[str, Any]) -> None:
    """XML ile Task Scheduler görevi oluşturur/günceller."""
    xml_text = build_task_xml(prefs)
    # schtasks UTF-16 (BOM) ister
    TASK_XML_FILE.write_text(xml_text, encoding="utf-16")
    result = _run_schtasks(
        ["/Create", "/TN", TASK_NAME, "/XML", str(TASK_XML_FILE.resolve()), "/F"]
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            "Zamanlanmış görev oluşturulamadı. "
            f"Detay: {detail or 'bilinmeyen hata'}"
        )
    logging.info("Windows görevi XML ile ayarlandı: %s", TASK_NAME)


def _describe(prefs: dict[str, Any]) -> str:
    t = prefs["time"]
    freq = prefs["frequency"]
    parts: list[str] = []
    if freq == "once":
        parts.append(f"Tek sefer · {prefs['start_date']} {t}")
    elif freq == "daily":
        every = prefs["interval"]
        parts.append(f"Her {every} günde · {t}" if every > 1 else f"Her gün · {t}")
    elif freq == "weekly":
        days = ", ".join(WEEKDAY_LABELS[d] for d in prefs["weekdays"])
        every = prefs["interval"]
        prefix = f"Her {every} hafta" if every > 1 else "Her hafta"
        parts.append(f"{prefix} ({days}) · {t}")
    elif freq == "monthly":
        parts.append(f"Her ayın {prefs['month_day']}. günü · {t}")

    if prefs["repeat_enabled"]:
        parts.append(f"tekrar {prefs['repeat_every']} / {prefs['repeat_for']}")
    if prefs["expire_enabled"]:
        parts.append(f"bitiş {prefs['expire_date']} {prefs['expire_time']}")
    return " · ".join(parts)


def get_schedule_status() -> dict[str, Any]:
    prefs = load_schedule_prefs()
    registered = is_task_registered()
    active = bool(prefs.get("enabled")) and registered

    if active:
        message = f"Aktif — {_describe(prefs)} (PC açıkken)."
    elif prefs.get("enabled") and not registered:
        message = "Etkin seçili ama Windows görevi eksik — kaydet."
    else:
        message = "Kapalı — yalnızca elle gönderim."

    return {
        **prefs,
        "task_registered": registered,
        "active": active,
        "message": message,
        "task_name": TASK_NAME,
        "summary": _describe(prefs),
        "delay_choices": list(DELAY_CHOICES.keys()),
        "repeat_every_choices": list(REPEAT_EVERY_CHOICES.keys()),
        "repeat_for_choices": list(REPEAT_FOR_CHOICES.keys()),
        "stop_after_choices": list(STOP_AFTER_CHOICES.keys()),
    }


def apply_schedule(payload: dict[str, Any]) -> dict[str, Any]:
    prefs = _sanitize_prefs(payload or {})
    save_schedule_prefs(prefs)

    if prefs["enabled"]:
        create_windows_task(prefs)
    else:
        delete_windows_task()

    status = get_schedule_status()
    logging.info("Zamanlama uygulandı: %s", status["message"])
    return status
