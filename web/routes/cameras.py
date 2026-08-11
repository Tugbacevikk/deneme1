"""
cameras.py - Kamera ve Video Analiz Rotaları (Blueprint)
Orijinal app.py içerisindeki yetkilendirme ve proxy mantığını 1:1 korur.
"""
import logging
from flask import Blueprint, render_template, request, jsonify, session, Response, redirect, url_for
from sqlalchemy import select
from core.database.models import Camera
from core.database.connection import db_manager
from web.helpers import (
    get_current_patron_access, is_camera_authorized,
    _get_dark_frame, _get_unauthorized_frame,
)

cameras_bp = Blueprint('cameras', __name__)
logger = logging.getLogger(__name__)


def _get_app_globals():
    import web.app as app_module
    return app_module


@cameras_bp.route('/cameras')
def cameras():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    app_mod = _get_app_globals()
    cams = app_mod.scan_cameras()
    return render_template('cameras.html', cameras=cams, config=app_mod.config)


@cameras_bp.route('/live-cameras')
@cameras_bp.route('/live_cameras')
def live_cameras():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    patron_id, is_super, stations = get_current_patron_access()
    try:
        from core.database.models import User
        with db_manager.get_session() as session_orm:
            users = session_orm.scalars(select(User).where(User.rol == 'patron')).all()
            patrons = [u.to_dict() for u in users]
    except Exception:
        patrons = []
    return render_template('live_cameras.html', is_admin=is_super, patrons=patrons)


@cameras_bp.route('/api/cameras/manage', methods=['GET'])
def api_cameras_list():
    patron_id, is_super, stations = get_current_patron_access()
    user_id = session.get('user_id')
    try:
        with db_manager.get_session() as session_orm:
            all_cams = session_orm.scalars(select(Camera).where(Camera.aktif == 1).order_by(Camera.id.asc())).all()
            allowed_cams = [c for c in all_cams if is_camera_authorized(c, user_id, is_super, stations)]
            return jsonify({'success': True, 'cameras': [c.to_dict() for c in allowed_cams]})
    except Exception as e:
        logger.error(f"Kamera listesi getirme hatası: {e}")
        return jsonify({'success': False, 'cameras': []})


@cameras_bp.route('/api/proxy_feed/<int:cam_id>')
def api_proxy_feed(cam_id):
    """Kamera yayınını sıkı yetki kontrolünden geçirerek sunar."""
    app_mod = _get_app_globals()
    patron_id, is_super, stations = get_current_patron_access()
    user_id = session.get('user_id')
    try:
        with db_manager.get_session() as session_orm:
            cam = session_orm.get(Camera, cam_id)
            if not cam or not cam.aktif:
                return Response(_get_dark_frame(), mimetype='image/jpeg')

            # Sıkı Yetki Kontrolü
            if not is_camera_authorized(cam, user_id, is_super, stations):
                return _get_unauthorized_frame(), 403

            # Yerel İstasyon Tespiti: SADECE istasyon adı ile karşılaştır.
            # IP tabanlı tespit kullanılmaz çünkü bu bilgisayar birden fazla
            # ağ kartına sahip olabilir (192.168.30.168 de bu PC'de tanımlı).
            local_station = (app_mod.config.get('station_name') or app_mod.config.get('istasyon_adi') or '').strip().lower()
            cam_station   = (cam.istasyon_adi or '').strip().lower()
            is_this_local = bool(local_station and cam_station and cam_station == local_station)

            if is_this_local:
                if app_mod.camera_processor is None or not getattr(app_mod.camera_processor, 'is_running', False):
                    return Response(_get_dark_frame(), mimetype='image/jpeg')
                return app_mod.video_feed()

            # Hızlı Soket Kontrolü (Uzak Pi Çevrimdışıysa Sunucuyu Asla Kitlemez)
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.4)
            is_online = (sock.connect_ex((ip, 5000)) == 0)
            sock.close()

            if not is_online:
                return Response(_get_dark_frame(), mimetype='image/jpeg')

            target_url = f"http://{ip}:5000/api/video_feed"
            import urllib.request

            def generate_proxy_stream():
                try:
                    req = urllib.request.urlopen(target_url, timeout=2)
                    while True:
                        chunk = req.read(4096)
                        if not chunk:
                            break
                        yield chunk
                except Exception as ex:
                    logger.debug(f"Proxy akış okuma hatası ({ip}): {ex}")
                    yield (
                        b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' + _get_dark_frame() + b'\r\n'
                    )

            return Response(generate_proxy_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')
    except Exception as e:
        logger.error(f"Proxy feed hatası: {e}")
        return Response(_get_dark_frame(), mimetype='image/jpeg')


@cameras_bp.route('/api/cameras/manage', methods=['POST'])
def api_cameras_add():
    if session.get('role') not in ('admin', 'super_admin'):
        return jsonify({'success': False, 'message': 'Yönetici yetkisi gereklidir.'}), 403

    data = request.get_json() or {}
    istasyon_adi = (data.get('istasyon_adi') or '').strip()
    ip_adresi = (data.get('ip_adresi') or '').strip()

    if not istasyon_adi or not ip_adresi:
        return jsonify({'success': False, 'message': 'İstasyon adı ve IP adresi gereklidir.'}), 400

    try:
        with db_manager.get_session() as session_orm:
            new_cam = Camera(
                istasyon_adi=istasyon_adi,
                ip_adresi=ip_adresi,
                patron_id=None,
                patron_adi=None,
                aktif=1
            )
            session_orm.add(new_cam)
            session_orm.commit()
            return jsonify({'success': True, 'message': f'"{istasyon_adi}" kamerasını/istasyonunu başarıyla eklendi.', 'camera': new_cam.to_dict()})
    except Exception as e:
        logger.error(f"Kamera ekleme hatası: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@cameras_bp.route('/api/cameras/manage/<int:cam_id>', methods=['DELETE', 'POST'])
def api_cameras_delete(cam_id):
    if session.get('role') not in ('admin', 'super_admin'):
        return jsonify({'success': False, 'message': 'Yönetici yetkisi gereklidir.'}), 403

    try:
        with db_manager.get_session() as session_orm:
            cam = session_orm.get(Camera, cam_id)
            if not cam:
                return jsonify({'success': False, 'message': 'Kamera bulunamadı.'}), 404
            session_orm.delete(cam)
            session_orm.commit()
            return jsonify({'success': True, 'message': 'Kamera başarıyla silindi.'})
    except Exception as e:
        logger.error(f"Kamera silme hatası: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
