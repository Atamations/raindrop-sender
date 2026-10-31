"""Durum / hata rapor maili gövde metinleri."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


def format_success_report(
    config: dict[str, Any],
    ok_recipients: list[str],
) -> str:
    """Başarı bildirimi gövdesi."""
    attachments = config.get("attachment_paths", [])
    attachment_lines = "yok"
    if isinstance(attachments, list) and attachments:
        attachment_lines = ", ".join(
            path.name if isinstance(path, Path) else Path(str(path)).name
            for path in attachments
        )

    return (
        "Mailler başarıyla gönderildi.\n\n"
        f"Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Konu: {config.get('subject', '')}\n"
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
