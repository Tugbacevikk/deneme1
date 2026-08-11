"""
user_service.py - Kullanıcı, Patron ve Yetki Yönetim Servisi
"""
import logging
from flask import session
from sqlalchemy import select
from werkzeug.security import generate_password_hash
from core.database.models import User, Worker
from core.database.connection import db_manager

logger = logging.getLogger(__name__)


def get_current_patron_access():
    """Oturum açan kullanıcının patron erişim yetkisini döndürür."""
    user_id = session.get('user_id')
    if not user_id:
        return None, True, []
    role = session.get('role') or session.get('rol', 'admin')
    if role in ('super_admin', 'admin', 'operator'):
        return None, True, []

    stations = []
    try:
        with db_manager.get_session() as session_orm:
            u = session_orm.get(User, user_id)
            if u and u.istasyonlar:
                stations = [s.strip() for s in u.istasyonlar.split(',') if s.strip()]
    except Exception:
        pass

    return user_id, False, stations


def get_all_users():
    """Tüm kullanıcıları döndürür."""
    with db_manager.get_session() as session:
        users = session.scalars(select(User).order_by(User.id.desc())).all()
        return [u.to_dict() for u in users]


def get_patrons():
    """Sadece 'patron' rolündeki kullanıcıları döndürür."""
    with db_manager.get_session() as session:
        patrons = session.scalars(select(User).where(User.rol == 'patron').order_by(User.ad_soyad.asc())).all()
        return [p.to_dict() for p in patrons]


def create_user(kullanici_adi, sifre, ad_soyad, rol='operator', firma_adi=None, istasyonlar=None):
    """Yeni kullanıcı oluşturur."""
    with db_manager.get_session() as session:
        existing = session.scalars(select(User).where(User.kullanici_adi == kullanici_adi)).first()
        if existing:
            return False, "Bu kullanıcı adı zaten mevcut."
        
        new_user = User(
            kullanici_adi=kullanici_adi,
            sifre_hash=generate_password_hash(sifre),
            ad_soyad=ad_soyad,
            rol=rol,
            firma_adi=firma_adi,
            istasyonlar=istasyonlar
        )
        session.add(new_user)
        session.commit()
        session.refresh(new_user)
        return True, new_user.to_dict()


def delete_user(user_id):
    """Kullanıcıyı siler."""
    with db_manager.get_session() as session:
        user = session.get(User, user_id)
        if not user:
            return False, "Kullanıcı bulunamadı."
        session.delete(user)
        session.commit()
        return True, "Kullanıcı silindi."


def assign_worker_to_patron(worker_id, patron_id):
    """Çalışanı bir patrona atar."""
    with db_manager.get_session() as session:
        worker = session.get(Worker, worker_id)
        if not worker:
            return False, "Çalışan bulunamadı."
        worker.patron_id = patron_id
        session.commit()
        return True, "Çalışan patrona atandı."
