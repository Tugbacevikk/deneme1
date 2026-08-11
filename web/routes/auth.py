"""
auth.py - Kullanıcı Oturum Açma / Kapatma Rotaları (Blueprint)
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import check_password_hash
from sqlalchemy import select
from core.database.models import User
from core.database.connection import db_manager
from web.services.user_service import get_all_users, get_patrons, create_user, delete_user, assign_worker_to_patron

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        kullanici_adi = (request.form.get('username') or request.form.get('kullanici_adi') or '').strip()
        sifre = (request.form.get('password') or request.form.get('sifre') or '')

        with db_manager.get_session() as db_session:
            user = db_session.scalars(select(User).where(User.kullanici_adi.ilike(kullanici_adi))).first()
            if not user:
                user = db_session.scalars(select(User).where(User.kullanici_adi == kullanici_adi)).first()

            if user and check_password_hash(user.sifre_hash, sifre):
                session['user_id'] = user.id
                session['kullanici_adi'] = user.kullanici_adi
                session['username'] = user.kullanici_adi
                session['ad_soyad'] = user.ad_soyad
                session['full_name'] = user.ad_soyad
                session['rol'] = user.rol
                session['role'] = user.rol
                flash(f'Hoş geldiniz, {user.ad_soyad}!', 'success')
                return redirect(url_for('dashboard.dashboard'))
            else:
                flash('Kullanıcı adı veya şifre hatalı.', 'danger')

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('Oturum kapatıldı.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/api/users', methods=['GET'])
@auth_bp.route('/api/users/list', methods=['GET'])
def api_users_list():
    users = get_all_users()
    return jsonify({'success': True, 'users': users})


@auth_bp.route('/api/patrons', methods=['GET'])
@auth_bp.route('/api/patrons/list', methods=['GET'])
def api_patrons_list():
    patrons = get_patrons()
    return jsonify({'success': True, 'patrons': patrons})


@auth_bp.route('/api/users', methods=['POST'])
@auth_bp.route('/api/users/add', methods=['POST'])
def api_users_add():
    data = request.get_json() or request.form
    kullanici_adi = data.get('kullanici_adi')
    sifre = data.get('sifre')
    ad_soyad = data.get('ad_soyad')
    rol = data.get('rol', 'operator')
    firma_adi = data.get('firma_adi')

    if not kullanici_adi or not sifre or not ad_soyad:
        return jsonify({'success': False, 'message': 'Eksik bilgi.'}), 400

    ok, res = create_user(kullanici_adi, sifre, ad_soyad, rol, firma_adi)
    if ok:
        return jsonify({'success': True, 'user': res})
    return jsonify({'success': False, 'message': res}), 400


@auth_bp.route('/api/users/<int:user_id>', methods=['DELETE', 'POST'])
@auth_bp.route('/api/users/<int:user_id>/delete', methods=['DELETE', 'POST'])
def api_users_delete(user_id):
    ok, msg = delete_user(user_id)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'message': msg}), 400


@auth_bp.route('/api/patrons/assign_worker', methods=['POST'])
def api_patrons_assign_worker():
    data = request.get_json() or request.form
    worker_id = data.get('worker_id')
    patron_id = data.get('patron_id')
    ok, msg = assign_worker_to_patron(worker_id, patron_id)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'message': msg}), 400
