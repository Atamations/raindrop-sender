# Raindrop Mail Sender

**Atamation** — Gmail SMTP · **v2.1.2**

Çerçevesiz UI · çoklu oturum · Task Scheduler otomasyonu.

## v2.1.2
- Tekrar aralığı min. **5 dakika** (Windows TS uyumu)
- Tüm oturumlar silinince liste **boş kalır** (otomatik Varsayılan yok)
- Gönderim UI kilidi yok (arka plan SMTP)
- Saat: HH:MM + **Şimdi Başla**
- `run_mailer.bat` / exe fallback

## Exe
[Releases](https://github.com/Atamations/raindrop-sender/releases) → **v2.1.2**

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python ui_app.py
```

Exe: `build_exe.bat`

© Atamation
