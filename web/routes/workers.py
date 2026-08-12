"""
workers.py - Çalışan Rotaları (Blueprint)
"""
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from web.services.worker_service import get_all_workers, create_worker, delete_worker, update_worker

from web.helpers import login_required

workers_bp = Blueprint('workers', __name__)


@workers_bp.route('/workers')
@workers_bp.route('/workers_page')
@login_required
def workers_page():
    workers = get_all_workers()
    return render_template('workers.html', workers=workers)


@workers_bp.route('/api/workers', methods=['GET'])
@login_required
def api_workers_list():
    workers = get_all_workers()
    return jsonify({'success': True, 'workers': workers})


@workers_bp.route('/api/workers/register', methods=['POST'])
@workers_bp.route('/api/workers', methods=['POST'])
@login_required
def api_workers_add():
    data = request.get_json() or request.form
    ad = data.get('ad')
    soyad = data.get('soyad')
    sicil_no = data.get('sicil_no')
    departman = data.get('departman')
    istasyon_adi = data.get('istasyon_adi')
    patron_id = data.get('patron_id')

    if not ad or not soyad:
        return jsonify({'success': False, 'message': 'Ad ve soyad zorunludur.'}), 400

    ok, res = create_worker(ad, soyad, sicil_no, departman, istasyon_adi, patron_id=patron_id)
    if ok:
        return jsonify({'success': True, 'worker': res})
    return jsonify({'success': False, 'message': res}), 400


@workers_bp.route('/api/workers/<int:worker_id>/delete', methods=['POST', 'DELETE'])
@workers_bp.route('/api/workers/<int:worker_id>', methods=['DELETE'])
@login_required
def api_workers_delete(worker_id):
    ok, msg = delete_worker(worker_id)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'message': msg}), 400


@workers_bp.route('/api/workers/<int:worker_id>/update', methods=['POST', 'PUT'])
@workers_bp.route('/api/workers/<int:worker_id>', methods=['PUT'])
@login_required
def api_workers_update(worker_id):
    data = request.get_json() or request.form
    ok, res = update_worker(worker_id, data)
    if ok:
        return jsonify({'success': True, 'worker': res})
    return jsonify({'success': False, 'message': res}), 400
