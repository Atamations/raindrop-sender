# Raindrop Sender

**Atamation** — Gmail SMTP ile tek seferlik e-posta gönderici.

Görev Zamanlayıcısı (Task Scheduler) ile çalıştırılabilir: ek dosya desteği, çoklu alıcı ve her çalıştırmada durum raporu maili.

## Özellikler

- `.env` üzerinden yapılandırma (şifreler kodda tutulmaz)
- Birden fazla alıcıya ayrı mail
- İsteğe bağlı dosya eki
- `REPORT_EMAIL` adresine başarı / hata özeti
- Konsol + `mailer.log` kaydı

## Gereksinimler

- Python 3.10+
- Gmail hesabı + [Google App Password](https://myaccount.google.com/apppasswords)

## Kurulum

```bash
git clone https://github.com/Atamations/raindrop-sender.git
cd raindrop-sender
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Credential’ları nereye yazmalısınız?

1. Şablonu kopyalayın:

```bash
copy .env.example .env
```

2. `.env` dosyasını düzenleyin:

| Değişken | Ne yazmalısınız |
|----------|-----------------|
| `GMAIL_ADDRESS` | Gönderen Gmail adresiniz |
| `GMAIL_APP_PASSWORD` | Google Uygulama Şifresi (16 hane; normal şifre değil) |
| `RECIPIENT_EMAIL` | Alıcı(lar), virgülle ayırın |
| `REPORT_EMAIL` | Durum raporunun geleceği sizin mailiniz |
| `SMTP_HOST` / `SMTP_PORT` | Varsayılan Gmail: `smtp.gmail.com` / `587` |
| `EMAIL_SUBJECT` / `EMAIL_BODY` | Mail konusu ve gövdesi |
| `ATTACHMENT_PATH` | İsteğe bağlı ek dosya yolu(ları); boş bırakılabilir |

3. Çalıştırın:

```bash
python main.py
```

veya Windows’ta:

```bash
run_mailer.bat
```

## Güvenlik

- Gerçek `.env` dosyası Git’e **dahil edilmez**.
- App Password’ü kimseyle paylaşmayın; sızdıysa Google hesabından iptal edip yenisini alın.
- Bu repo yalnızca şablon (`.env.example`) içerir; kişisel mail/şifre bulunmaz.

## Windows Görev Zamanlayıcısı

1. Görev Zamanlayıcısı → Temel Görev Oluştur
2. Tetikleyici: istediğiniz saat / günlük
3. Eylem: `run_mailer.bat` veya `python main.py` (çalışma dizini proje klasörü olsun)

## Lisans

© Atamation — kişisel / portföy kullanımı.
