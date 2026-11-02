# Raindrop Mail Sender

**Atamation** — Gmail SMTP mail gönderici · **v2.1.0**

Çerçevesiz masaüstü UI + **çoklu oturum** + Task Scheduler otomasyonu.

## v2.1.0

- Sol menü: birden fazla oturum / kampanya
- Her oturum kendi alıcıları, içeriği ve zamanlaması
- Oturum kartından otomasyonu Başlat / Durdur
- Gönder kilidi bug'ı düzeltildi (doğrulama hatasında UI kilitlenmiyor)
- Task Scheduler: `RaindropMail_<session_id>`

## Hızlı başlangıç (exe)

1. [Releases](https://github.com/Atamations/raindrop-sender/releases) → **v2.1.0**
2. Zip'i aç, `.env.example` → `.env` (Gmail + App Password + rapor maili)
3. `RaindropMailSender.exe` çalıştır
4. Sol menüden oturum ekle, zamanlamayı kaydet

## Geliştirici

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python ui_app.py
```

Exe: `build_exe.bat`

## Lisans

© Atamation
