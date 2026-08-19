"""
settings.py - Sistem Ayarları Rotaları (Blueprint)
"""
import yaml
from pathlib import Path
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from pg_sync import pg_baglan

from web.helpers import login_required, admin_required

settings_bp = Blueprint('settings', __name__)
BASE_DIR = Path(__file__).parent.parent.parent
CONFIG_PATH = BASE_DIR / 'config.yaml'


@settings_bp.route('/settings')
@login_required
def settings():
    import psutil, platform
    from web.services.worker_service import get_all_stations
    db_path = BASE_DIR / 'isci_takip.db'
    db_size_str = '—'
    if db_path.exists():
        size_mb = db_path.stat().st_size / (1024 * 1024)
        db_size_str = f"{size_mb:.1f} MB"

    sys_info = {
        'python_version': platform.python_version(),
        'platform': f"{platform.system()} {platform.release()}",
        'db_size': db_size_str,
        'last_update': 'Aktif (Canlı)'
    }
    all_stations = get_all_stations()
    return render_template('settings.html', system_info=sys_info, all_stations=all_stations)


@settings_bp.route('/user_management')
@settings_bp.route('/users_management')
@settings_bp.route('/user-management')
@login_required
def user_management():
    from web.services.user_service import get_pending_users, get_all_users
    from web.services.worker_service import get_all_workers, get_all_stations
    pending_users = get_pending_users()
    users = get_all_users()
    all_workers = get_all_workers()
    all_stations = get_all_stations()
    return render_template('user_management.html', pending_users=pending_users, users=users, all_workers=all_workers, all_stations=all_stations)




@settings_bp.route('/api/system/info', methods=['GET'])
@settings_bp.route('/api/system_info', methods=['GET'])
@login_required
def api_system_info():
    import psutil, platform
    import web.extensions as ext
    db_path = BASE_DIR / 'isci_takip.db'
    db_size_str = '—'
    if db_path.exists():
        size_mb = db_path.stat().st_size / (1024 * 1024)
        db_size_str = f"{size_mb:.1f} MB"

    cam_running = False
    if ext.camera_processor is not None and getattr(ext.camera_processor, 'is_running', False):
        cam_running = True

    cpu_val = psutil.cpu_percent()
    ram_val = psutil.virtual_memory().percent

    return jsonify({
        'success': True,
        'python_version': platform.python_version(),
        'platform': f"{platform.system()} {platform.release()}",
        'db_size': db_size_str,
        'face_lib': 'YOLOv8 (ARM CM5 Hızlandırmalı)',
        'camera_status': 'Aktif (Çalışıyor)' if cam_running else 'Kapalı',
        'last_update': 'Aktif (Canlı)',
        'cpu_usage': round(cpu_val, 1),
        'ram_usage': round(ram_val, 1)
    })



@settings_bp.route('/api/settings/save', methods=['POST'])
@admin_required
def api_settings_save():
    data = request.get_json() or {}
    try:
        cfg = {}
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = yaml.safe_load(f) or {}

        cfg.update(data)

        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.safe_dump(cfg, f, allow_unicode=True)

        import web.extensions as ext
        ext.config = cfg

        if ext.camera_processor is not None:
            if hasattr(ext.camera_processor, 'update_config'):
                ext.camera_processor.update_config(cfg)
            elif hasattr(ext.camera_processor, 'cfg'):
                ext.camera_processor.cfg.update(cfg)

        return jsonify({'success': True, 'message': 'Ayarlar başarıyla kaydedildi.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@settings_bp.route('/api/camera/apply_settings', methods=['POST'])
@admin_required
def api_camera_apply_settings():
    data = request.get_json() or {}
    allowed_keys = ['brightness', 'contrast', 'saturation', 'flip_h', 'flip_v',
                    'roi_x1', 'roi_y1', 'roi_x2', 'roi_y2',
                    'hareket_esik_orani', 'inaktif_kare_limiti',
                    'motion_threshold', 'inactive_frame_limit', 'calibration_mode']
    updates = {k: v for k, v in data.items() if k in allowed_keys}

    cfg = {}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
    cfg.update(updates)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.safe_dump(cfg, f, allow_unicode=True)

    import web.extensions as ext
    ext.config = cfg

    if ext.camera_processor is not None:
        ext.camera_processor.cfg.update(updates)

    return jsonify({'success': True, 'message': 'Ayarlar canlı olarak uygulandı.'})


@settings_bp.route('/api/settings/test_db', methods=['POST'])
@admin_required
def api_settings_test_db():
    data = request.get_json() or {}
    engine = pg_baglan(data)
    if engine:
        engine.dispose()
        return jsonify({'success': True, 'message': 'PostgreSQL veritabanı bağlantısı başarılı!'})
    return jsonify({'success': False, 'message': 'Veritabanına bağlanılamadı.'}), 400


@settings_bp.route('/api/settings/test_smtp', methods=['POST'])
@admin_required
def api_settings_test_smtp():
    import smtplib
    data = request.get_json() or {}
    host = data.get('smtp_host', 'smtp.gmail.com')
    port = int(data.get('smtp_port', 587))
    user = data.get('smtp_user', '').strip()
    password = data.get('smtp_password', '').strip()

    if not host or not user or not password:
        return jsonify({'success': False, 'message': 'Lütfen SMTP Sunucu, Kullanıcı ve Şifre alanlarını doldurun.'}), 400

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=10) as server:
                server.login(user, password)
        else:
            with smtplib.SMTP(host, port, timeout=10) as server:
                server.starttls()
                server.login(user, password)
        return jsonify({'success': True, 'message': 'SMTP E-posta sunucu bağlantısı başarılı!'})
    except Exception as e:
        err_str = str(e)
        if '535' in err_str or 'BadCredentials' in err_str or 'Username and Password not accepted' in err_str:
            user_msg = "SMTP Giriş Başarısız: E-posta adresi veya 16 haneli Gmail Uygulama Şifresi hatalı. Lütfen kontrol edin."
        elif '101' in err_str or 'Network is unreachable' in err_str or 'timed out' in err_str or 'timeout' in err_str:
            user_msg = "E-posta Sunucusuna Erişilemedi: İnternet bağlantınızı veya SMTP port ayarlarınızı (587/465) kontrol edin."
        else:
            user_msg = f"SMTP Bağlantı Hatası: {err_str}"
        return jsonify({'success': False, 'message': user_msg}), 400



@settings_bp.route('/api/settings/cleanup_db', methods=['POST'])
@admin_required
def api_settings_cleanup_db():
    from core.database.connection import db_manager
    data = request.get_json() or {}
    days = int(data.get('days', 30))
    deleted_count = db_manager.cleanup_old_records(days=days)
    
    if days <= 0:
        msg = f'Tüm geçmiş durum ve sistem kayıtları ({deleted_count} adet) başarıyla sıfırlandı ve temizlendi.'
    elif deleted_count > 0:
        msg = f'{days} günden eski {deleted_count} adet durum ve sistem kaydı başarıyla temizlendi.'
    else:
        msg = f'Sistemdeki kayıtlar henüz yeni (dün/bugün) olduğu için {days} günden eski silinecek kayıt bulunamadı (0 kayıt).'

    return jsonify({'success': True, 'message': msg, 'count': deleted_count})


@settings_bp.route('/api/settings/theme', methods=['POST'])
@login_required
def api_settings_theme():
    data = request.get_json() or {}
    theme = data.get('theme', 'dark')
    session['theme'] = theme
    return jsonify({'success': True, 'theme': theme})


@settings_bp.route('/api/system/shutdown', methods=['POST'])
@admin_required
def api_system_shutdown():
    import sys, subprocess
    try:
        if sys.platform.startswith('linux'):
            try:
                subprocess.Popen(['sudo', 'systemctl', 'poweroff'])
            except Exception:
                try:
                    subprocess.Popen(['sudo', 'shutdown', '-h', 'now'])
                except Exception:
                    subprocess.Popen(['sudo', 'poweroff'])
            return jsonify({'success': True, 'message': 'Raspberry Pi sistemi güvenli bir şekilde kapatılıyor. Yeşil ışık söndükten sonra fişi çekebilirsiniz.'})
        else:
            return jsonify({'success': False, 'message': 'Sadece Raspberry Pi (Linux) üzerinde çalışır.'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'Kapatma hatası: {e}'}), 500
