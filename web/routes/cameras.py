"""
cameras.py - Kamera ve Video Analiz Rotaları (Blueprint)
Orijinal app.py içerisindeki yetkilendirme ve proxy mantığını 1:1 korur.
"""
import logging
from flask import Blueprint, render_template, request, jsonify, session, Response, redirect, url_for
from sqlalchemy import select
from core.database.models import Camera
from core.database.connection import db_manager
from web.services.camera_service import _get_camera_session
from web.helpers import (
    get_current_patron_access, is_camera_authorized,
    _get_dark_frame, _get_unauthorized_frame,
    login_required, admin_required, get_all_system_stations,
)

cameras_bp = Blueprint('cameras', __name__)
logger = logging.getLogger(__name__)

import web.extensions as ext

# Rota tanımları
@cameras_bp.route('/cameras')
@login_required
def cameras():
    from web.app import scan_cameras
    cams = scan_cameras()
    return render_template('cameras.html', cameras=cams, config=ext.config)


@cameras_bp.route('/live-cameras')
@cameras_bp.route('/live_cameras')
@login_required
def live_cameras():
    patron_id, is_super, patron_stations = get_current_patron_access()
    try:
        from core.database.models import User
        with _get_camera_session() as session_orm:
            users = session_orm.scalars(select(User).where(User.rol == 'patron')).all()
            patrons = [u.to_dict() for u in users]
    except Exception:
        patrons = []
    all_stations = get_all_system_stations()
    return render_template('live_cameras.html', is_admin=is_super, patrons=patrons, stations=all_stations)


@cameras_bp.route('/api/cameras/manage', methods=['GET'])
@login_required
def api_cameras_list():
    patron_id, is_super, stations = get_current_patron_access()
    user_id = session.get('user_id')
    try:
        with _get_camera_session() as session_orm:
            all_cams = session_orm.scalars(select(Camera).where(Camera.aktif == 1).order_by(Camera.id.asc())).all()
            allowed_cams = [c for c in all_cams if is_camera_authorized(c, user_id, is_super, stations)]
            return jsonify({'success': True, 'cameras': [c.to_dict() for c in allowed_cams]})
    except Exception as e:
        logger.error(f"Kamera listesi getirme hatası: {e}")
        return jsonify({'success': False, 'cameras': []})


@cameras_bp.route('/api/cameras/stations')
@login_required
def api_cameras_stations():
    from web.services.worker_service import get_all_stations
    stations = get_all_stations()
    return jsonify({'success': True, 'stations': stations})






@cameras_bp.route('/api/proxy_feed/<int:cam_id>')
@login_required
def api_proxy_feed(cam_id):
    """Kamera yayınını sıkı yetki kontrolünden geçirerek sunar."""
    patron_id, is_super, stations = get_current_patron_access()
    user_id = session.get('user_id')
    try:
        with _get_camera_session() as session_orm:
            cam = session_orm.get(Camera, cam_id)
            if not cam or not cam.aktif:
                return Response(_get_dark_frame(), mimetype='image/jpeg')

            # Sıkı Yetki Kontrolü
            if not is_camera_authorized(cam, user_id, is_super, stations):
                return _get_unauthorized_frame(), 403

            # Yerel İstasyon Tespiti: İstasyon adı veya IP adresi eşleşmesi
            local_station = (ext.config.get('station_name') or ext.config.get('istasyon_adi') or '').strip().lower()
            cam_station   = (cam.istasyon_adi or '').strip().lower()
            cam_ip        = (cam.ip_adresi or '').strip()

            from web.helpers import get_local_system_ips
            local_ips = get_local_system_ips()
            is_this_local = bool((local_station and cam_station and cam_station == local_station) or (cam_ip in local_ips))

            if is_this_local:
                if ext.camera_processor is None or not getattr(ext.camera_processor, 'is_running', False):
                    return Response(_get_dark_frame(), mimetype='image/jpeg')
                from web.app import video_feed
                return video_feed()

            # Hızlı Soket Kontrolü
            import socket
            ip = (cam.ip_adresi or '').strip()
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
@admin_required
def api_cameras_add():
    data = request.get_json() or {}
    istasyon_adi = (data.get('istasyon_adi') or '').strip()
    ip_adresi = (data.get('ip_adresi') or '').strip()

    if not istasyon_adi or not ip_adresi:
        return jsonify({'success': False, 'message': 'İstasyon adı ve IP adresi gereklidir.'}), 400

    try:
        with _get_camera_session() as session_orm:
            new_cam = Camera(
                istasyon_adi=istasyon_adi,
                ip_adresi=ip_adresi,
                patron_id=None,
                patron_adi=None,
                aktif=1
            )
            session_orm.add(new_cam)
            session_orm.commit()
            res_dict = new_cam.to_dict()

        try:
            with db_manager.get_session() as loc_sess:
                loc_cam = Camera(
                    istasyon_adi=istasyon_adi,
                    ip_adresi=ip_adresi,
                    patron_id=None,
                    patron_adi=None,
                    aktif=1
                )
                loc_sess.add(loc_cam)
                loc_sess.commit()
        except Exception:
            pass

        return jsonify({'success': True, 'message': f'"{istasyon_adi}" kamerasını/istasyonunu başarıyla eklendi.', 'camera': res_dict})
    except Exception as e:
        logger.error(f"Kamera ekleme hatası: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@cameras_bp.route('/api/cameras/manage/<int:cam_id>', methods=['DELETE', 'POST'])
@admin_required
def api_cameras_delete(cam_id):
    try:
        st_name = None
        with _get_camera_session() as session_orm:
            cam = session_orm.get(Camera, cam_id)
            if not cam:
                return jsonify({'success': False, 'message': 'Kamera bulunamadı.'}), 404
            st_name = cam.istasyon_adi
            session_orm.delete(cam)
            session_orm.commit()

        try:
            with db_manager.get_session() as loc_sess:
                loc_c = loc_sess.scalars(select(Camera).where(Camera.istasyon_adi == st_name)).first()
                if loc_c:
                    loc_sess.delete(loc_c)
                    loc_sess.commit()
        except Exception:
            pass

        return jsonify({'success': True, 'message': 'Kamera başarıyla silindi.'})
    except Exception as e:
        logger.error(f"Kamera silme hatası: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
