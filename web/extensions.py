"""
web/extensions.py - Ortak uzantılar ve global durum değişkenleri.
İmport döngülerini (circular imports) önlemek amacıyla tasarlanmıştır.
"""
from flask_socketio import SocketIO
import datetime

# Ortak Flask-SocketIO nesnesi
socketio = SocketIO(async_mode='threading', cors_allowed_origins='*')

# Global Yapılandırma ve Durum Nesneleri
config = {}
camera_processor = None
face_recognizer = None

last_status = {
    'durum': 'Kamera Başlatılmadı',
    'renk': '#888888',
    'fps': 0.0,
    'kisi_sayisi': 0,
    'istasyon': 'N/A',
    'zaman': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'running': False,
    'worker_name': '',
    'worker_confidence': 0.0,
    'phone_detected': False,
    'camera_id': '',
}
