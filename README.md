# Raindrop Mail Sender

**Atamation** — Gmail SMTP mail gönderici · **v2.0.1**

Çerçevesiz masaüstü UI (pywebview) + Task Scheduler seviyesinde zamanlama + tek seferlik CLI.

## v2.0.1 Öne çıkanlar

- Resmi Raindrop uygulama ikonu (exe + pencere + kısayol)
- Çerçevesiz masaüstü arayüz + sürüklenebilir title bar
- Hesap / Zamanlama / Aktivite sekmeleri
- Edit Trigger tarzı zamanlama (bir kez, günlük, haftalık, aylık + gelişmiş tekrar/bitiş)
- Çoklu alıcı, ek dosya, yalnızca hata durumunda `REPORT_EMAIL` bildirimi
- `RaindropMailSender.exe` paketi (PyInstaller)

## Hızlı başlangıç (exe)

1. [Releases](https://github.com/Atamations/raindrop-sender/releases) sayfasından **v2.0.1** paketini indirin
2. Klasörde `.env.example` → `.env` kopyalayın ve doldurun
3. `RaindropMailSender.exe` çalıştırın  
   veya masaüstü kısayolunu kullanın

Otomatik gönderim: UI → **Zamanlama** → ayarla → **Ayarları kaydet**  
(PC açıkken çalışır; Windows görevini uygulama kurar.)

## Geliştirici kurulumu

```bash
git clone https://github.com/Atamations/raindrop-sender.git
cd raindrop-sender
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python ui_app.py
```

CLI / Task Scheduler:

```bash
python main.py
# veya
python ui_app.py --send
# veya
run_mailer.bat
```

Exe derleme:

```bash
build_exe.bat
```

## `.env` alanları

| Değişken | Açıklama |
|----------|----------|
| `GMAIL_ADDRESS` | Gönderen Gmail |
| `GMAIL_APP_PASSWORD` | Google Uygulama Şifresi |
| `RECIPIENT_EMAIL` | Alıcı(lar), virgülle |
| `REPORT_EMAIL` | Yalnızca hata raporu adresi |
| `EMAIL_SUBJECT` / `EMAIL_BODY` | Konu / gövde |
| `ATTACHMENT_PATH` | Ekler (`;` ile ayır) |
| `SMTP_HOST` / `SMTP_PORT` | Varsayılan Gmail `587` |

## Güvenlik

- `.env` Git’e girmez
- App Password paylaşmayın

## Lisans

© Atamation — kişisel / portföy kullanımı.
