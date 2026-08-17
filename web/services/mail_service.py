import smtplib
import os
import re
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText

EMAIL_RE = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')


def send_pdf_report(to_email: str, pdf_bytes: bytes, filename: str, subject: str, body: str):
    if not to_email or not isinstance(to_email, str):
        return False, "Lütfen bir e-posta adresi girin."
    
    to_email = to_email.strip()
    if not EMAIL_RE.match(to_email):
        return False, "Geçerli bir e-posta adresi girin (örn: ad@sirket.com)."

    cfg = {}
    try:
        import web.extensions as ext
        cfg = getattr(ext, 'config', {}) or {}
    except Exception:
        pass

    cfg_smtp = cfg.get('smtp') if isinstance(cfg.get('smtp'), dict) else {}

    host = os.getenv('SMTP_HOST') or os.getenv('SMTP_SERVER') or cfg_smtp.get('host') or cfg_smtp.get('server') or cfg.get('smtp_host') or 'smtp.gmail.com'
    port = int(os.getenv('SMTP_PORT') or cfg_smtp.get('port') or cfg.get('smtp_port') or 587)
    user = os.getenv('SMTP_USER') or os.getenv('SMTP_EMAIL') or cfg_smtp.get('user') or cfg_smtp.get('email') or cfg.get('smtp_user') or ''
    password = os.getenv('SMTP_PASSWORD') or cfg_smtp.get('password') or cfg.get('smtp_password') or ''
    sender = os.getenv('SMTP_FROM') or cfg_smtp.get('from') or cfg.get('smtp_from') or user

    if not host or not user or not password:
        return False, "SMTP ayarları yapılandırılmamış (Ayarlar sayfasından e-posta ve şifrenizi girin)."


    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    part = MIMEApplication(pdf_bytes, Name=filename)
    part['Content-Disposition'] = f'attachment; filename="{filename}"'
    msg.attach(part)

    try:
        if int(port) == 465:
            with smtplib.SMTP_SSL(host, int(port), timeout=12) as server:
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, int(port), timeout=12) as server:
                server.starttls()
                if user and password:
                    server.login(user, password)
                server.send_message(msg)
        return True, "Rapor e-posta ile başarıyla gönderildi."
    except smtplib.SMTPAuthenticationError:
        return False, "E-posta giriş hatası! Gmail kullanıyorsanız şifre yerine 16 haneli 'Uygulama Şifresi' (App Password) girilmesi gereklidir."
    except smtplib.SMTPRecipientsRefused:
        return False, "Bu e-posta adresi sunucu tarafından reddedildi."
    except Exception as e:
        err_msg = str(e)
        if "Network is unreachable" in err_msg or "101" in err_msg or "Timed out" in err_msg or "110" in err_msg:
            return False, "Raspberry Pi yerel fabrika ağında internet erişimi olmadığı için Gmail sunucusuna bağlanamıyor. Cihazın internet bağlantısını kontrol edin."
        return False, f"E-posta gönderilemedi: {err_msg}"
