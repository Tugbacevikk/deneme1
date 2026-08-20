"""
auth.py - Kullanıcı Oturum Açma / Kapatma Rotaları (Blueprint)
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import select
from core.database.models import User
from core.database.connection import db_manager
from web.services.user_service import get_all_users, get_patrons, create_user, delete_user, assign_worker_to_patron, approve_user, reject_user

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 200
    if request.method == 'POST':
        kullanici_adi = (request.form.get('username') or request.form.get('kullanici_adi') or '').strip()
        sifre = (request.form.get('password') or request.form.get('sifre') or '')

        from web.services.user_service import _get_user_session
        with _get_user_session() as db_session:
            user = db_session.scalars(select(User).where(User.kullanici_adi.ilike(kullanici_adi))).first()
            if not user:
                user = db_session.scalars(select(User).where(User.kullanici_adi == kullanici_adi)).first()

            if user and check_password_hash(user.sifre_hash, sifre):
                if user.durum == 'bekliyor':
                    flash('Hesabınız henüz onaylanmadı.', 'warning')
                    return render_template('login.html')
                elif user.durum == 'reddedildi':
                    flash('Başvurunuz reddedildi.', 'danger')
                    return render_template('login.html')

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


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        ad_soyad = (request.form.get('ad_soyad') or '').strip()
        username = (request.form.get('username') or '').strip()
        firma_adi = (request.form.get('firma_adi') or '').strip()
        email = (request.form.get('email') or '').strip()
        password = request.form.get('password') or ''
        password_confirm = request.form.get('password_confirm') or ''

        if not ad_soyad or not username or not password or not firma_adi or not email:
            flash('Lütfen tüm zorunlu alanları doldurun.', 'danger')
            return render_template('register.html')

        from web.routes.reports import EMAIL_RE
        if not email or not EMAIL_RE.match(email):
            flash('Geçerli bir e-posta adresi girin.', 'danger')
            return render_template('register.html')

        if password != password_confirm:
            flash('Şifreler eşleşmiyor.', 'danger')
            return render_template('register.html')

        with db_manager.get_session() as session_orm:
            existing_email = session_orm.scalars(select(User).where(User.email == email)).first()
            if existing_email:
                flash('Bu e-posta adresi zaten kayıtlı.', 'danger')
                return render_template('register.html')

        ok, res = create_user(
            kullanici_adi=username,
            sifre=password,
            ad_soyad=ad_soyad,
            email=email,
            rol='patron',
            firma_adi=firma_adi,
            istasyonlar=None,
            durum='bekliyor'
        )
        if ok:
            from web.extensions import socketio
            from web.services.user_service import get_pending_count
            from web.services.alarm_service import get_unread_count
            socketio.emit('new_pending_user', {'count': get_pending_count(), 'ad_soyad': ad_soyad})
            socketio.emit('alarm_update', {'unread_count': get_unread_count()})
            flash('Kaydınız alındı, onay bekleniyor.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash(res, 'danger')

    return render_template('register.html')


from web.helpers import login_required, admin_required


@auth_bp.route('/api/users', methods=['GET'])
@auth_bp.route('/api/users/list', methods=['GET'])
@login_required
def api_users_list():
    users = get_all_users()
    return jsonify({'success': True, 'users': users})


@auth_bp.route('/api/patrons', methods=['GET'])
@auth_bp.route('/api/patrons/list', methods=['GET'])
@login_required
def api_patrons_list():
    patrons = get_patrons()
    return jsonify({'success': True, 'patrons': patrons})


@auth_bp.route('/api/users', methods=['POST'])
@auth_bp.route('/api/users/add', methods=['POST'])
@admin_required
def api_users_add():
    data = request.get_json(silent=True) or request.form
    kullanici_adi = (data.get('kullanici_adi') or data.get('username') or '').strip()
    sifre = data.get('sifre') or data.get('password') or ''
    ad_soyad = (data.get('ad_soyad') or data.get('fullname') or '').strip()
    rol = data.get('rol') or data.get('role') or 'patron'
    firma_adi = (data.get('firma_adi') or data.get('company') or 'Fabrika').strip()
    istasyonlar = data.get('istasyonlar') or data.get('stations') or ''
    email = (data.get('email') or '').strip() or None

    if not kullanici_adi or not sifre or not ad_soyad:
        return jsonify({'success': False, 'message': 'Kullanıcı adı, şifre ve ad soyad zorunludur.'}), 400

    ok, res = create_user(
        kullanici_adi=kullanici_adi,
        sifre=sifre,
        ad_soyad=ad_soyad,
        rol=rol,
        firma_adi=firma_adi,
        istasyonlar=istasyonlar,
        email=email
    )
    if ok:
        return jsonify({'success': True, 'message': 'Kullanıcı başarıyla eklendi.', 'user': res})
    return jsonify({'success': False, 'message': str(res)}), 400


@auth_bp.route('/api/users/<int:user_id>', methods=['DELETE', 'POST'])
@auth_bp.route('/api/users/<int:user_id>/delete', methods=['DELETE', 'POST'])
@admin_required
def api_users_delete(user_id):
    ok, msg = delete_user(user_id)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'message': msg}), 400


@auth_bp.route('/api/patrons/assign_worker', methods=['POST'])
@admin_required
def api_patrons_assign_worker():
    data = request.get_json() or request.form
    worker_id = data.get('worker_id')
    patron_id = data.get('patron_id')
    ok, msg = assign_worker_to_patron(worker_id, patron_id)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'message': msg}), 400


@auth_bp.route('/api/users/<int:user_id>/approve', methods=['POST'])
@admin_required
def api_users_approve(user_id):
    data = request.get_json(silent=True) or {}
    raw_workers = data.get('workers') or request.form.getlist('workers') or []
    raw_stations = data.get('stations') or request.form.getlist('stations') or []
    
    ok, msg = approve_user(user_id, worker_ids=raw_workers, station_names=raw_stations)
    if not ok:
        if request.is_json or 'application/json' in request.headers.get('Accept', ''):
            return jsonify({'success': False, 'message': msg}), 400
        flash(msg, 'danger')
        return redirect(url_for('settings.user_management'))

    from web.services.user_service import get_pending_count
    if request.is_json or 'application/json' in request.headers.get('Accept', ''):
        return jsonify({'success': True, 'message': msg, 'pending_count': get_pending_count()})
    
    flash(msg, 'success')
    return redirect(url_for('settings.user_management'))



@auth_bp.route('/api/users/<int:user_id>/reject', methods=['POST'])
@admin_required
def api_users_reject(user_id):
    ok, msg = reject_user(user_id)
    if not ok:
        if request.is_json or 'application/json' in request.headers.get('Accept', ''):
            return jsonify({'success': False, 'message': msg}), 404
        flash(msg, 'danger')
        return redirect(url_for('settings.settings'))

    from web.services.user_service import get_pending_count
    if request.is_json or 'application/json' in request.headers.get('Accept', ''):
        return jsonify({'success': True, 'message': msg, 'pending_count': get_pending_count()})
    
    flash(msg, 'info')
    return redirect(url_for('settings.settings'))


@auth_bp.route('/api/users/pending_count', methods=['GET'])
@admin_required
def api_users_pending_count():
    from web.services.user_service import get_pending_count
    return jsonify({'success': True, 'count': get_pending_count()})


@auth_bp.route('/api/users/pending_notifications', methods=['GET'])
@admin_required
def api_users_pending_notifications():
    from web.services.user_service import get_pending_users
    users = get_pending_users()
    formatted = []
    for u in users:
        formatted.append({
            'id': u['id'],
            'ad_soyad': u['ad_soyad'],
            'firma_adi': u['firma_adi'],
            'kayit_tarihi': u['kayit_tarihi']
        })
    return jsonify({
        'success': True,
        'count': len(users),
        'notifications': formatted
    })


@auth_bp.route('/api/users/<int:user_id>/update', methods=['POST', 'PUT'])
@admin_required
def api_users_update(user_id):
    from web.services.user_service import update_user_admin
    data = request.get_json() or request.form
    ad_soyad = data.get('ad_soyad') or data.get('fullname')
    rol = data.get('rol') or data.get('role')
    sifre = data.get('sifre') or data.get('password')
    istasyonlar = data.get('istasyonlar') or data.get('stations')
    email = data.get('email')

    if not ad_soyad or not rol:
        return jsonify({'success': False, 'message': 'Ad Soyad ve Rol alanları zorunludur.'}), 400

    ok, msg = update_user_admin(user_id, ad_soyad=ad_soyad, rol=rol, istasyonlar=istasyonlar, email=email, sifre=sifre)
    if ok:
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'message': msg}), 404


@auth_bp.route('/api/users/with_email', methods=['GET'])
@auth_bp.route('/api/users/mail_recipients', methods=['GET'])
@login_required
def api_users_with_email():
    from web.services.user_service import _get_user_session
    with _get_user_session() as db_session:
        stmt = select(User).where(
            User.durum == 'onaylandi',
            User.email != None,
            User.email != ''
        )
        users = db_session.scalars(stmt).all()
        result = [
            {
                'id': u.id,
                'ad_soyad': u.ad_soyad,
                'email': u.email.strip(),
                'rol': u.rol
            }
            for u in users if u.email and u.email.strip()
        ]
        return jsonify({'success': True, 'users': result})


@auth_bp.route('/profile', methods=['GET'])
@login_required
def profile():
    from web.services.user_service import get_user_by_id
    user_id = session.get('user_id')
    user_data = get_user_by_id(user_id)
    if not user_data:
        # Fallback to session data if user lookup is temporarily unavailable
        user_data = {
            'id': user_id,
            'kullanici_adi': session.get('username') or session.get('kullanici_adi') or 'Kullanıcı',
            'ad_soyad': session.get('full_name') or session.get('ad_soyad') or session.get('username') or 'Kullanıcı',
            'rol': session.get('role') or session.get('rol') or 'patron',
            'email': session.get('email', ''),
            'firma_adi': session.get('firma_adi', 'Fabrika'),
            'istasyonlar': session.get('istasyonlar', 'Tüm Fabrika')
        }
    return render_template('profile.html', user=user_data)


@auth_bp.route('/api/profile/change_password', methods=['POST'])
@login_required
def api_profile_change_password():
    from web.services.user_service import change_own_password
    user_id = session.get('user_id')
    data = request.get_json() or request.form
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    new_password_confirm = data.get('new_password_confirm', '')

    if not current_password or not new_password or not new_password_confirm:
        return jsonify({'success': False, 'message': 'Tüm alanları doldurunuz.'}), 400

    if new_password != new_password_confirm:
        return jsonify({'success': False, 'message': 'Yeni şifreler eşleşmiyor.'}), 400

    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'Yeni şifre en az 6 karakter olmalıdır.'}), 400

    ok, msg = change_own_password(user_id, current_password, new_password)
    if ok:
        from web.extensions import socketio
        from web.services.alarm_service import get_unread_count
        socketio.emit('alarm_update', {'unread_count': get_unread_count()})
        return jsonify({'success': True, 'message': msg})
    return jsonify({'success': False, 'message': msg}), 400


@auth_bp.route('/api/profile/update_email', methods=['POST'])
@login_required
def api_profile_update_email():
    from web.services.user_service import update_own_email
    user_id = session.get('user_id')
    data = request.get_json() or request.form
    new_email = data.get('email', '').strip()
    ok, msg = update_own_email(user_id, new_email)
    return jsonify({'success': ok, 'message': msg}), (200 if ok else 400)
