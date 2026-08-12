"""
user_service.py - Kullanıcı, Patron ve Yetki Yönetim Servisi
"""
import logging
from flask import session
from sqlalchemy import select, func
from werkzeug.security import generate_password_hash
from core.database.models import User, Worker
from core.database.connection import db_manager

logger = logging.getLogger(__name__)


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


def create_user(kullanici_adi, sifre, ad_soyad, rol='operator', firma_adi=None, istasyonlar=None, durum='onaylandi'):
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
            istasyonlar=istasyonlar,
            durum=durum
        )
        session.add(new_user)
        if durum == 'bekliyor':
            from core.database.models import Alarm
            new_alarm = Alarm(
                istasyon_adi="Sistem",
                alarm_turu="Kayıt Başvurusu",
                aciklama=f"Yeni patron başvurdu: {ad_soyad} ({kullanici_adi}) onay bekliyor.",
                okundu=0
            )
            session.add(new_alarm)
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
    """Çalışanı bir patrona atar ve işçinin istasyonunu patronun yetki listesine ekler."""
    with db_manager.get_session() as session:
        worker = session.get(Worker, worker_id)
        if not worker:
            return False, "Çalışan bulunamadı."
        worker.patron_id = patron_id
        
        if worker.istasyon_adi and worker.istasyon_adi.strip() and patron_id:
            user = session.get(User, patron_id)
            if user:
                current_stations = [s.strip() for s in user.istasyonlar.split(',') if s.strip()] if user.istasyonlar else []
                new_station = worker.istasyon_adi.strip()
                if new_station not in current_stations:
                    current_stations.append(new_station)
                    user.istasyonlar = ", ".join(current_stations)
                    
        session.commit()
        return True, "Çalışan patrona atandı."


def get_pending_users():
    """Durumu 'bekliyor' olan kullanıcıları döndürür."""
    with db_manager.get_session() as session:
        users = session.scalars(select(User).where(User.durum == 'bekliyor').order_by(User.id.desc())).all()
        return [u.to_dict() for u in users]


def approve_user(user_id, worker_ids):
    """Kullanıcıyı onaylar ve seçilen çalışanların istasyonlarını atar."""
    with db_manager.get_session() as session:
        user = session.get(User, user_id)
        if not user:
            return False, "Kullanıcı bulunamadı."
        
        user.durum = 'onaylandi'
        stations = set()
        for w_id in worker_ids:
            worker = session.get(Worker, w_id)
            if worker:
                worker.patron_id = user_id
                if worker.istasyon_adi and worker.istasyon_adi.strip():
                    stations.add(worker.istasyon_adi.strip())
        
        user.istasyonlar = ", ".join(stations) if stations else None
        session.commit()
        return True, f"Kullanıcı onaylandı. {len(worker_ids)} çalışan ve {len(stations)} istasyon atandı."


def reject_user(user_id):
    """Kullanıcı başvurusunu reddeder."""
    with db_manager.get_session() as session:
        user = session.get(User, user_id)
        if not user:
            return False, "Kullanıcı bulunamadı."
        user.durum = 'reddedildi'
        session.commit()
        return True, "Kullanıcı reddedildi."


def get_pending_count():
    """durum='bekliyor' olan User sayısını döndürür."""
    with db_manager.get_session() as session:
        return session.scalar(select(func.count(User.id)).where(User.durum == 'bekliyor')) or 0
