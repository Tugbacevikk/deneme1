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
    from web.services.user_service import get_pending_users
    from web.services.worker_service import get_all_workers
    pending_users = get_pending_users()
    all_workers = get_all_workers()
    return render_template('settings.html', pending_users=pending_users, all_workers=all_workers)


@settings_bp.route('/api/system/info', methods=['GET'])
@settings_bp.route('/api/system_info', methods=['GET'])
@login_required
def api_system_info():
    import psutil, platform
    return jsonify({
        'success': True,
        'system': {
            'os': platform.system(),
            'release': platform.release(),
            'cpu_usage': psutil.cpu_percent(),
            'ram_usage': psutil.virtual_memory().percent
        }
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

        if 'merkezi_db' in data:
            cfg['merkezi_db'] = data['merkezi_db']

        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.safe_dump(cfg, f, allow_unicode=True)

        import web.extensions as ext
        ext.config = cfg

        return jsonify({'success': True, 'message': 'Ayarlar başarıyla kaydedildi.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@settings_bp.route('/api/settings/test_db', methods=['POST'])
@admin_required
def api_settings_test_db():
    data = request.get_json() or {}
    engine = pg_baglan(data)
    if engine:
        engine.dispose()
        return jsonify({'success': True, 'message': 'PostgreSQL veritabanı bağlantısı başarılı!'})
    return jsonify({'success': False, 'message': 'Veritabanına bağlanılamadı.'}), 400


@settings_bp.route('/api/settings/theme', methods=['POST'])
@login_required
def api_settings_theme():
    data = request.get_json() or {}
    theme = data.get('theme', 'dark')
    session['theme'] = theme
    return jsonify({'success': True, 'theme': theme})
