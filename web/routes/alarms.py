"""
alarms.py - Alarm Rotaları (Blueprint)
"""
from flask import Blueprint, render_template, jsonify, session, redirect, url_for
from web.services.alarm_service import get_alarms, get_unread_count, mark_alarms_read
from web.helpers import login_required

alarms_bp = Blueprint('alarms', __name__)


@alarms_bp.route('/alarms')
@alarms_bp.route('/alarms_page')
@login_required
def alarms_page():
    import datetime
    from web.services.user_service import get_pending_users
    from web.helpers import get_current_patron_access
    
    patron_id, is_super, patron_stations = get_current_patron_access()
    stations_param = None if is_super else patron_stations

    alarms_list = []
    role = session.get('role') or session.get('rol')
    if role in ('admin', 'super_admin'):
        pending_users = get_pending_users()
        for u in pending_users:
            z_time = u.get('kayit_tarihi') or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            alarms_list.append({
                'id': f"pending_{u['id']}",
                'istasyon_adi': 'Sistem',
                'station': 'Sistem',
                'alarm_turu': 'Kayıt Başvurusu',
                'type': 'Kayıt Başvurusu',
                'aciklama': f"Yeni patron başvurdu: {u['ad_soyad']} ({u['firma_adi'] or 'Birim Belirtilmemiş'}) onay bekliyor.",
                'description': f"Yeni patron başvurdu: {u['ad_soyad']} ({u['firma_adi'] or 'Birim Belirtilmemiş'}) onay bekliyor.",
                'zaman': z_time,
                'created_at': z_time,
                'time': z_time,
                'okundu': 0,
                'read': False
            })
        
    real_alarms = get_alarms(limit=50, stations=stations_param)
    for a in real_alarms:
        a['read'] = (a.get('okundu') == 1)
        a['type'] = a.get('alarm_turu') or 'Alarm'
        a['station'] = a.get('istasyon_adi') or 'Genel'
        a['description'] = a.get('aciklama') or ''
        a['created_at'] = a.get('zaman') or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        a['time'] = a['created_at']
        alarms_list.append(a)

    return render_template('alarms.html', alarms=alarms_list)


@alarms_bp.route('/api/alarms', methods=['GET'])
@login_required
def api_alarms():
    import datetime
    from web.services.user_service import get_pending_users
    from web.helpers import get_current_patron_access
    
    patron_id, is_super, patron_stations = get_current_patron_access()
    stations_param = None if is_super else patron_stations

    alarms_list = []
    role = session.get('role') or session.get('rol')
    if role in ('admin', 'super_admin'):
        pending_users = get_pending_users()
        for u in pending_users:
            z_time = u.get('kayit_tarihi') or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            alarms_list.append({
                'id': f"pending_{u['id']}",
                'istasyon_adi': 'Sistem',
                'station': 'Sistem',
                'alarm_turu': 'Kayıt Başvurusu',
                'type': 'Kayıt Başvurusu',
                'aciklama': f"Yeni patron başvurdu: {u['ad_soyad']} ({u['firma_adi'] or 'Birim Belirtilmemiş'}) onay bekliyor.",
                'description': f"Yeni patron başvurdu: {u['ad_soyad']} ({u['firma_adi'] or 'Birim Belirtilmemiş'}) onay bekliyor.",
                'zaman': z_time,
                'created_at': z_time,
                'time': z_time,
                'okundu': 0,
                'read': False
            })
        
    real_alarms = get_alarms(limit=50, stations=stations_param)
    for a in real_alarms:
        a['read'] = (a.get('okundu') == 1)
        a['type'] = a.get('alarm_turu') or 'Alarm'
        a['station'] = a.get('istasyon_adi') or 'Genel'
        a['description'] = a.get('aciklama') or ''
        a['created_at'] = a.get('zaman') or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        a['time'] = a['created_at']
        alarms_list.append(a)

    return jsonify({'success': True, 'alarms': alarms_list})


@alarms_bp.route('/api/alarms/unread_count', methods=['GET'])
@login_required
def api_alarms_unread_count():
    from web.helpers import get_current_patron_access
    patron_id, is_super, patron_stations = get_current_patron_access()
    stations_param = None if is_super else patron_stations

    count = get_unread_count(stations=stations_param)
    return jsonify({'success': True, 'unread_count': count})


@alarms_bp.route('/api/alarms/mark_read', methods=['POST'])
@login_required
def api_alarms_mark_read():
    mark_alarms_read()
    return jsonify({'success': True, 'message': 'Tüm alarmlar okundu olarak işaretlendi.'})


@alarms_bp.route('/api/alarms/<int:alarm_id>/mark_read', methods=['POST'])
@login_required
def api_alarms_mark_single_read(alarm_id):
    from web.services.alarm_service import mark_single_alarm_read
    from web.helpers import get_current_patron_access
    patron_id, is_super, patron_stations = get_current_patron_access()
    stations_param = None if is_super else patron_stations

    ok = mark_single_alarm_read(alarm_id)
    if ok:
        return jsonify({'success': True, 'unread_count': get_unread_count(stations=stations_param)})
    return jsonify({'success': False, 'message': 'Alarm bulunamadı.'}), 404


@alarms_bp.route('/api/alarms/<int:alarm_id>/mark_unread', methods=['POST'])
@login_required
def api_alarms_mark_single_unread(alarm_id):
    from web.services.alarm_service import mark_single_alarm_unread
    from web.helpers import get_current_patron_access
    patron_id, is_super, patron_stations = get_current_patron_access()
    stations_param = None if is_super else patron_stations

    ok = mark_single_alarm_unread(alarm_id)
    if ok:
        return jsonify({'success': True, 'unread_count': get_unread_count(stations=stations_param)})
    return jsonify({'success': False, 'message': 'Alarm bulunamadı.'}), 404


@alarms_bp.route('/api/alarms/delete/<alarm_id>', methods=['DELETE', 'POST'])
@alarms_bp.route('/api/alarms/<alarm_id>/delete', methods=['DELETE', 'POST'])
@alarms_bp.route('/api/alarms/<alarm_id>', methods=['DELETE'])
@login_required
def api_delete_alarm(alarm_id):
    from web.services.alarm_service import delete_alarm
    from web.helpers import get_current_patron_access
    patron_id, is_super, patron_stations = get_current_patron_access()
    stations_param = None if is_super else patron_stations

    ok = delete_alarm(alarm_id)
    if ok:
        return jsonify({'success': True, 'message': 'Alarm silindi.', 'unread_count': get_unread_count(stations=stations_param)})
    return jsonify({'success': False, 'message': 'Alarm bulunamadı veya silinemedi.'}), 404
