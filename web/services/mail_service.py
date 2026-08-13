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

    # .env veya config.yaml üzerinden SMTP oku
    cfg_smtp = {}
    try:
        import web.extensions as ext
        cfg_smtp = (ext.config or {}).get('smtp', {})
    except Exception:
        pass

    host = os.getenv('SMTP_HOST') or os.getenv('SMTP_SERVER') or cfg_smtp.get('host') or cfg_smtp.get('server')
    port = int(os.getenv('SMTP_PORT') or cfg_smtp.get('port') or 587)
    user = os.getenv('SMTP_USER') or os.getenv('SMTP_EMAIL') or cfg_smtp.get('user') or cfg_smtp.get('email')
    password = os.getenv('SMTP_PASSWORD') or cfg_smtp.get('password')
    sender = os.getenv('SMTP_FROM') or cfg_smtp.get('from') or user

    if not host or not user or not password:
        return False, "SMTP ayarları yapılandırılmamış (.env veya config.yaml dosyasını kontrol edin)."


    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    part = MIMEApplication(pdf_bytes, Name=filename)
    part['Content-Disposition'] = f'attachment; filename="{filename}"'
    msg.attach(part)

    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        return True, "Rapor e-posta ile gönderildi."
    except smtplib.SMTPRecipientsRefused:
        return False, "Bu e-posta adresi sunucu tarafından reddedildi, adresi kontrol edin."
    except Exception as e:
        return False, f"E-posta gönderilemedi: {e}"
