"""Raindrop Mail Sender — paylaşılan SMTP motoru."""

from mailer.config import BASE_DIR, LOG_FILE, load_config, save_config
from mailer.send import send_campaign

__all__ = [
    "BASE_DIR",
    "LOG_FILE",
    "load_config",
    "save_config",
    "send_campaign",
]
