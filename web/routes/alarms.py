"""
alarms.py - Alarm Rotaları (Blueprint)
"""
from flask import Blueprint, render_template, jsonify, session, redirect, url_for
from web.services.alarm_service import get_alarms, get_unread_count, mark_alarms_read

alarms_bp = Blueprint('alarms', __name__)


@alarms_bp.route('/alarms')
@alarms_bp.route('/alarms_page')
def alarms_page():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    return render_template('alarms.html')


@alarms_bp.route('/api/alarms', methods=['GET'])
def api_alarms():
    alarms_list = get_alarms()
    return jsonify({'success': True, 'alarms': alarms_list})


@alarms_bp.route('/api/alarms/unread_count', methods=['GET'])
def api_alarms_unread_count():
    count = get_unread_count()
    return jsonify({'success': True, 'unread_count': count})


@alarms_bp.route('/api/alarms/mark_read', methods=['POST'])
def api_alarms_mark_read():
    mark_alarms_read()
    return jsonify({'success': True, 'message': 'Tüm alarmlar okundu olarak işaretlendi.'})
