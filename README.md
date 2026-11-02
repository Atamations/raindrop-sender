# Raindrop Mail Sender

**Atamation** — Gmail SMTP mail gönderici · **v2.0.2**

Çerçevesiz masaüstü UI (pywebview) + Task Scheduler seviyesinde zamanlama + tek seferlik CLI.

## v2.0.2 Öne çıkanlar

- Geçersiz ikon dosyasından kaynaklanan açılış çökmesi düzeltildi
- Windows uyumlu çok-boyutlu Raindrop `.ico`
- Çerçevesiz UI + sürüklenebilir title bar
- Zamanlama / çoklu alıcı / hata-only rapor / exe paketi

## Hızlı başlangıç (exe)

1. [Releases](https://github.com/Atamations/raindrop-sender/releases) → **v2.0.2**
2. Zip'i aç, `.env.example` → `.env`
3. `RaindropMailSender.exe` çalıştır

## Geliştirici

```bash
git clone https://github.com/Atamations/raindrop-sender.git
cd raindrop-sender
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python ui_app.py
```

Exe: `build_exe.bat`

## Lisans

© Atamation
