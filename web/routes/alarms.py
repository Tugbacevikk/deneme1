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
    return render_template('alarms.html')


@alarms_bp.route('/api/alarms', methods=['GET'])
@login_required
def api_alarms():
    alarms_list = get_alarms()
    return jsonify({'success': True, 'alarms': alarms_list})


@alarms_bp.route('/api/alarms/unread_count', methods=['GET'])
@login_required
def api_alarms_unread_count():
    count = get_unread_count()
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
    ok = mark_single_alarm_read(alarm_id)
    if ok:
        return jsonify({'success': True, 'unread_count': get_unread_count()})
    return jsonify({'success': False, 'message': 'Alarm bulunamadı.'}), 404
