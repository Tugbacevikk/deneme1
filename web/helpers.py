"""
helpers.py - Web Arayüzü Genel Yardımcı ve Yetkilendirme Fonksiyonları
"""
import sys
import logging
import datetime
from functools import wraps
from typing import Optional, List, Tuple
from flask import session, Response, redirect, url_for, request, jsonify
import cv2
import numpy as np

from sqlalchemy import select
from core.database.models import User, Camera
from core.database.connection import db_manager

logger = logging.getLogger(__name__)


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Yetkisiz erişim. Lütfen giriş yapın.'}), 401
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Yetkisiz erişim. Lütfen giriş yapın.'}), 401
            return redirect(url_for('auth.login'))
        
        role = session.get('role') or session.get('rol')
        if role not in ('admin', 'super_admin'):
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Bu işlem için yetkiniz yok.'}), 403
            return jsonify({'success': False, 'error': 'Bu işlem için yetkiniz yok.'}), 403
        return f(*args, **kwargs)
    return decorated_function


def get_current_patron_access() -> Tuple[Optional[int], bool, List[str]]:
    """
    Oturum açan kullanıcının (patron_id, is_super_admin, patron_stations_list) bilgisini döndürür.
    Süper Admin / Admin ise: (None, True, []) -> Tüm sistem yetkisi var
    Patron ise: (user_id, False, ['Istasyon-A', 'Istasyon-B']) -> Sadece kendi veya atanan istasyon verilerine erişebilir
    """
    user_id = session.get('user_id')
    if not user_id:
        return -99999, False, []
    role = session.get('role', 'operator')
    if role in ('super_admin', 'admin'):
        return None, True, []

    stations = []
    try:
        with db_manager.get_session() as session_orm:
            u = session_orm.get(User, user_id)
            if u and u.istasyonlar:
                stations = [s.strip() for s in u.istasyonlar.split(',') if s.strip()]
    except Exception as e:
        logger.debug(f"Patron erişim yetkisi okuma hatası: {e}")

    return user_id, False, stations


def get_current_patron_id() -> Tuple[Optional[int], bool]:
    p_id, is_super, _ = get_current_patron_access()
    return p_id, is_super


def is_local_ip(ip_str: str, cam_station: str = None) -> bool:
    """IP adresinin veya istasyon adının yerel makineye ait olup olmadığını kontrol eder."""
    if not ip_str:
        return True
    ip = ip_str.strip().lower()
    if ip in ('127.0.0.1', 'localhost', '0.0.0.0', '::1'):
        return True

    try:
        import socket
        hostname = socket.gethostname()
        local_ips = set(socket.gethostbyname_ex(hostname)[2])
        local_ips.add(socket.gethostbyname(hostname))
        if ip in local_ips:
            return True
    except Exception:
        pass

    try:
        from web.app import config
        st_name = config.get('station_name') or config.get('istasyon_adi')
        if cam_station and st_name and str(cam_station).strip().lower() == str(st_name).strip().lower():
            return True
    except Exception:
        pass

    return False


def is_camera_authorized(cam: Camera, user_id: Optional[int], is_super: bool, stations: List[str]) -> bool:
    """
    Sıkı İstasyon Bazlı Kamera Yetki Denetimi:
    - Super Admin / Admin -> TÜM KAMERALARA YETKİLİ
    - Patron -> Kameranın istasyon adı (örn: 'Istasyon-1') kullanıcının yetkili istasyonlar listesinde (User.istasyonlar) OLMAK ZORUNDADIR.
    """
    if is_super:
        return True
    if not cam or not cam.aktif:
        return False
    
    if stations and len(stations) > 0:
        return cam.istasyon_adi in stations

    return False


def _get_dark_frame() -> bytes:
    """'Kamera Başlatılmadı' yazılı koyu kare döndürür."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = (30, 30, 30)
    cv2.putText(
        frame, "Kamera Baslatilmadi", (120, 240),
        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (150, 150, 150), 2, cv2.LINE_AA,
    )
    _, jpeg = cv2.imencode('.jpg', frame)
    return jpeg.tobytes()


def _get_unauthorized_frame() -> Response:
    """'Yetkisiz Erişim' yazılı kırmızı uyarı karesi döndürür."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = (20, 20, 35)
    cv2.putText(
        frame, "YETKISIZ ERISIM", (160, 220),
        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (50, 50, 239), 2, cv2.LINE_AA,
    )
    cv2.putText(
        frame, "Bu kamerayi izleme yetkiniz yok", (120, 270),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 1, cv2.LINE_AA,
    )
    _, buffer = cv2.imencode('.jpg', frame)
    return Response(buffer.tobytes(), mimetype='image/jpeg')


def format_duration_tr(seconds: float) -> str:
    """Saniyeyi insan tarafından rahatça anlaşılır saat / dakika / saniye biçimine dönüştürür."""
    sec_int = int(round(seconds))
    if sec_int <= 0:
        return "0 dk"
    
    hours = sec_int // 3600
    remainder = sec_int % 3600
    minutes = remainder // 60
    secs = remainder % 60
    
    parts = []
    if hours > 0:
        parts.append(f"{hours} sa")
    if minutes > 0:
        parts.append(f"{minutes} dk")
    if secs > 0 and hours == 0:
        parts.append(f"{secs} sn")
    
    return " ".join(parts) if parts else "0 dk"


def _format_date_tr(date_str: str) -> str:
    if not date_str:
        return ''
    try:
        dt = datetime.datetime.strptime(date_str[:10], '%Y-%m-%d')
        return dt.strftime('%d.%m.%Y')
    except Exception:
        return date_str
