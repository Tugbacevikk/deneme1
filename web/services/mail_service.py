import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText

def send_pdf_report(to_email: str, pdf_bytes: bytes, filename: str, subject: str, body: str):
    host = os.getenv('SMTP_HOST') or os.getenv('SMTP_SERVER')
    port = int(os.getenv('SMTP_PORT', 587))
    user = os.getenv('SMTP_USER') or os.getenv('SMTP_EMAIL')
    password = os.getenv('SMTP_PASSWORD')
    sender = os.getenv('SMTP_FROM') or user

    if not host or not user or not password:
        return False, "SMTP ayarları yapılandırılmamış (.env dosyasını kontrol edin)."

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
    except Exception as e:
        return False, f"E-posta gönderilemedi: {e}"
