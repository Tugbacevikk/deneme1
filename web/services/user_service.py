"""
user_service.py - Kullanıcı, Patron ve Yetki Yönetim Servisi
"""
import logging
from flask import session
from sqlalchemy import select, func
from werkzeug.security import generate_password_hash
from core.database.models import User, Worker, Alarm
from core.database.connection import db_manager

logger = logging.getLogger(__name__)


def _get_user_session():
    """Merkezi PostgreSQL var ise PostgreSQL Session, yoksa yerel SQLite Session döndürür."""
    try:
        from pg_sync import pg_baglan
        from sqlalchemy.orm import Session
        engine = pg_baglan()
        if engine:
            return Session(engine)
    except Exception:
        pass
    return db_manager.get_session()


def get_all_users():
    """Tüm kullanıcıları döndürür."""
    with _get_user_session() as sess:
        users = sess.scalars(select(User).order_by(User.id.desc())).all()
        return [u.to_dict() for u in users]


def get_patrons():
    """Sadece 'patron' rolündeki kullanıcıları döndürür."""
    with _get_user_session() as sess:
        patrons = sess.scalars(select(User).where(User.rol == 'patron').order_by(User.ad_soyad.asc())).all()
        return [p.to_dict() for p in patrons]


def create_user(kullanici_adi, sifre, ad_soyad, rol='operator', firma_adi=None, istasyonlar=None, durum='onaylandi', email=None):
    """Yeni kullanıcı oluşturur (hem merkezi PG hem yerel SQLite'a ekler)."""
    with _get_user_session() as sess:
        existing = sess.scalars(select(User).where(User.kullanici_adi == kullanici_adi)).first()
        if existing:
            return False, "Bu kullanıcı adı zaten mevcut."
        
        new_user = User(
            kullanici_adi=kullanici_adi,
            sifre_hash=generate_password_hash(sifre),
            ad_soyad=ad_soyad,
            email=email,
            rol=rol,
            firma_adi=firma_adi,
            istasyonlar=istasyonlar,
            durum=durum
        )
        sess.add(new_user)
        sess.commit()
        
        if durum == 'bekliyor':
            try:
                new_alarm = Alarm(
                    istasyon_adi="Sistem",
                    alarm_turu="Kayıt Başvurusu",
                    aciklama=f"Yeni patron başvurdu: {ad_soyad} ({kullanici_adi}) onay bekliyor.",
                    okundu=0
                )
                sess.add(new_alarm)
                sess.commit()
            except Exception as alarm_err:
                sess.rollback()
                logger.warning(f"Kayıt başvurusu alarm bildirimi oluşturulamadı: {alarm_err}")
                
        sess.refresh(new_user)
        result_dict = new_user.to_dict()

    # Ayrıca yerel SQLite'a da yaz (yedeklilik için)
    try:
        with db_manager.get_session() as loc_sess:
            loc_exist = loc_sess.scalars(select(User).where(User.kullanici_adi == kullanici_adi)).first()
            if not loc_exist:
                u_loc = User(
                    kullanici_adi=kullanici_adi,
                    sifre_hash=generate_password_hash(sifre),
                    ad_soyad=ad_soyad,
                    email=email,
                    rol=rol,
                    firma_adi=firma_adi,
                    istasyonlar=istasyonlar,
                    durum=durum
                )
                loc_sess.add(u_loc)
                loc_sess.commit()
    except Exception:
        pass

    return True, result_dict


def delete_user(user_id):
    """Kullanıcıyı siler (hem merkezi PG hem yerel SQLite'tan siler)."""
    k_adi = None
    with _get_user_session() as sess:
        user = sess.get(User, user_id)
        if user:
            k_adi = user.kullanici_adi
            if user.rol in ('admin', 'super_admin'):
                return False, "Admin hesapları silinemez."
            sess.delete(user)
            sess.commit()

    try:
        with db_manager.get_session() as loc_sess:
            loc_user = loc_sess.get(User, user_id)
            if not loc_user and k_adi:
                loc_user = loc_sess.scalars(select(User).where(User.kullanici_adi == k_adi)).first()
            if loc_user and loc_user.rol not in ('admin', 'super_admin'):
                loc_sess.delete(loc_user)
                loc_sess.commit()
    except Exception:
        pass

    return True, "Kullanıcı başarıyla silindi."


def assign_worker_to_patron(worker_id, patron_id):
    """Çalışanı bir patrona atar ve işçinin istasyonunu patronun yetki listesine ekler."""
    with _get_user_session() as sess:
        worker = sess.get(Worker, worker_id)
        if not worker:
            return False, "Çalışan bulunamadı."
        worker.patron_id = patron_id
        
        if worker.istasyon_adi and worker.istasyon_adi.strip() and patron_id:
            user = sess.get(User, patron_id)
            if user:
                current_stations = [s.strip() for s in user.istasyonlar.split(',') if s.strip()] if user.istasyonlar else []
                new_station = worker.istasyon_adi.strip()
                if new_station not in current_stations:
                    current_stations.append(new_station)
                    user.istasyonlar = ", ".join(current_stations)
                    
        sess.commit()
        return True, "Çalışan patrona atandı."


def get_pending_users():
    """Durumu 'bekliyor' olan kullanıcıları döndürür."""
    with _get_user_session() as sess:
        users = sess.scalars(select(User).where(User.durum == 'bekliyor').order_by(User.id.desc())).all()
        return [u.to_dict() for u in users]


def approve_user(user_id, worker_ids=None, station_names=None):
    """Kullanıcıyı onaylar ve seçilen çalışanları veya istasyonları atar."""
    with _get_user_session() as sess:
        user = sess.get(User, user_id)
        if not user:
            return False, "Kullanıcı bulunamadı."
        
        user.durum = 'onaylandi'
        stations = set()
        
        if worker_ids:
            for w_id in worker_ids:
                if isinstance(w_id, int) or (isinstance(w_id, str) and w_id.isdigit()):
                    worker = sess.get(Worker, int(w_id))
                    if worker:
                        worker.patron_id = user_id
                        if worker.istasyon_adi and worker.istasyon_adi.strip():
                            stations.add(worker.istasyon_adi.strip())
                elif isinstance(w_id, str) and w_id.strip():
                    stations.add(w_id.strip())

        if station_names:
            for st in station_names:
                if st and isinstance(st, str) and st.strip():
                    stations.add(st.strip())
        
        if stations:
            workers_on_stations = sess.scalars(select(Worker).where(Worker.istasyon_adi.in_(list(stations)))).all()
            for w in workers_on_stations:
                w.patron_id = user_id

        user.istasyonlar = ", ".join(sorted(list(stations))) if stations else "Tüm Fabrika"
        sess.commit()
        k_adi = user.kullanici_adi
        new_durum = user.durum
        new_ist = user.istasyonlar

    # Ayrıca yerel SQLite'ı da güncelle
    try:
        with db_manager.get_session() as loc_sess:
            loc_u = loc_sess.scalars(select(User).where(User.kullanici_adi == k_adi)).first()
            if loc_u:
                loc_u.durum = new_durum
                loc_u.istasyonlar = new_ist
                loc_sess.commit()
    except Exception:
        pass

    return True, f"Kullanıcı onaylandı. {len(stations)} istasyon atandı."


def reject_user(user_id):
    """Kullanıcı başvurusunu reddeder."""
    with _get_user_session() as sess:
        user = sess.get(User, user_id)
        if not user:
            return False, "Kullanıcı bulunamadı."
        user.durum = 'reddedildi'
        sess.commit()
        k_adi = user.kullanici_adi

    try:
        with db_manager.get_session() as loc_sess:
            loc_u = loc_sess.scalars(select(User).where(User.kullanici_adi == k_adi)).first()
            if loc_u:
                loc_u.durum = 'reddedildi'
                loc_sess.commit()
    except Exception:
        pass

    return True, "Kullanıcı reddedildi."


def get_user_by_id(user_id):
    """Kullanıcıyı ID ile arar (PostgreSQL + yerel SQLite uyumlu)."""
    with _get_user_session() as sess:
        u = sess.get(User, user_id)
        if u:
            return u.to_dict()
    try:
        with db_manager.get_session() as loc_sess:
            u = loc_sess.get(User, user_id)
            if u:
                return u.to_dict()
    except Exception:
        pass
    return None


def update_user_admin(user_id, ad_soyad, rol, istasyonlar=None, email=None, sifre=None):
    """Admin tarafından kullanıcı yetki ve profili güncellenir (PG + SQLite uyumlu)."""
    with _get_user_session() as sess:
        user = sess.get(User, user_id)
        if not user:
            try:
                with db_manager.get_session() as loc_sess:
                    user_loc = loc_sess.get(User, user_id)
                    if user_loc:
                        user_loc.ad_soyad = ad_soyad
                        user_loc.rol = rol
                        user_loc.istasyonlar = istasyonlar
                        if email is not None:
                            user_loc.email = email.strip() if email else ''
                        if sifre and sifre.strip():
                            user_loc.sifre_hash = generate_password_hash(sifre)
                        loc_sess.commit()
                        return True, "Kullanıcı bilgileri başarıyla güncellendi."
            except Exception:
                pass
            return False, "Kullanıcı bulunamadı."
        
        k_adi = user.kullanici_adi
        user.ad_soyad = ad_soyad
        user.rol = rol
        user.istasyonlar = istasyonlar
        if email is not None:
            user.email = email.strip() if email else ''
        if sifre and sifre.strip():
            user.sifre_hash = generate_password_hash(sifre)

        try:
            with db_manager.get_session() as loc_sess:
                loc_u = loc_sess.scalars(
                    select(User).where(or_(User.id == user_id, User.kullanici_adi == k_adi))
                ).first()
                if loc_u:
                    loc_u.ad_soyad = ad_soyad
                    loc_u.rol = rol
                    loc_u.istasyonlar = istasyonlar
                    if email is not None:
                        loc_u.email = email.strip() if email else ''
                    if sifre and sifre.strip():
                        loc_u.sifre_hash = user.sifre_hash
                    loc_sess.commit()
        except Exception:
            pass

        sess.commit()
        return True, "Kullanıcı bilgileri başarıyla güncellendi."


def get_pending_count():
    """durum='bekliyor' olan User sayısını döndürür."""
    with _get_user_session() as sess:
        return sess.scalar(select(func.count(User.id)).where(User.durum == 'bekliyor')) or 0


def change_own_password(user_id, current_password, new_password):
    """Kullanıcının kendi şifresini değiştirir (PG + SQLite uyumlu)."""
    from werkzeug.security import check_password_hash
    with _get_user_session() as sess:
        user = sess.get(User, user_id)
        if not user:
            try:
                with db_manager.get_session() as loc_sess:
                    user_loc = loc_sess.get(User, user_id)
                    if user_loc:
                        if not check_password_hash(user_loc.sifre_hash, current_password):
                            return False, "Mevcut şifre hatalı."
                        user_loc.sifre_hash = generate_password_hash(new_password)
                        loc_sess.commit()
                        return True, "Şifreniz başarıyla güncellendi."
            except Exception:
                pass
            return False, "Kullanıcı bulunamadı."
        if not check_password_hash(user.sifre_hash, current_password):
            return False, "Mevcut şifre hatalı."
        user.sifre_hash = generate_password_hash(new_password)
        try:
            with db_manager.get_session() as loc_sess:
                loc_u = loc_sess.scalars(select(User).where(User.id == user_id)).first()
                if loc_u:
                    loc_u.sifre_hash = user.sifre_hash
                    loc_sess.commit()
        except Exception:
            pass
        sess.commit()
        try:
            with db_manager.get_session() as alm_sess:
                new_alarm = Alarm(
                    istasyon_adi="Sistem",
                    alarm_turu="Şifre Değişikliği",
                    aciklama=f"{user.ad_soyad} ({user.kullanici_adi}) kendi şifresini değiştirdi.",
                    okundu=0
                )
                alm_sess.add(new_alarm)
                alm_sess.commit()
        except Exception:
            pass
        return True, "Şifreniz başarıyla güncellendi."


def update_own_email(user_id: int, new_email: str):
    import re
    EMAIL_RE = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')
    if not new_email or not EMAIL_RE.match(new_email.strip()):
        return False, "Geçerli bir e-posta adresi girin."
    with _get_user_session() as sess:
        existing = sess.scalars(
            select(User).where(User.email == new_email.strip(), User.id != user_id)
        ).first()
        if existing:
            return False, "Bu e-posta adresi başka bir hesap tarafından kullanılıyor."
        user = sess.get(User, user_id)
        if not user:
            try:
                with db_manager.get_session() as loc_sess:
                    loc_u = loc_sess.get(User, user_id)
                    if loc_u:
                        loc_u.email = new_email.strip()
                        loc_sess.commit()
                        return True, "E-posta adresi güncellendi."
            except Exception:
                pass
            return False, "Kullanıcı bulunamadı."
        user.email = new_email.strip()
        try:
            with db_manager.get_session() as loc_sess:
                loc_u = loc_sess.scalars(select(User).where(User.id == user_id)).first()
                if loc_u:
                    loc_u.email = new_email.strip()
                    loc_sess.commit()
        except Exception:
            pass
        sess.commit()
    return True, "E-posta adresi güncellendi."
