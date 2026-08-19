"""
worker_service.py - Çalışan / İşçi Yönetim Servisi
"""
import logging
from sqlalchemy import select, func, or_
from core.database.models import Worker, Camera, DurumKaydi
from core.database.connection import db_manager

logger = logging.getLogger(__name__)


def _get_worker_session():
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


def get_all_workers(aktif_only=False):
    """Tüm çalışanları döndürür (aktif_only=True ise sadece aktifleri getirir)."""
    with _get_worker_session() as sess:
        stmt = select(Worker)
        if aktif_only:
            stmt = stmt.where(or_(Worker.aktif == 1, Worker.aktif.is_(None)))
        stmt = stmt.order_by(Worker.ad.asc(), Worker.soyad.asc())
        workers = sess.scalars(stmt).all()
        return [w.to_dict() for w in workers]


def get_all_stations():
    """Sistemdeki tüm benzersiz GERÇEK fabrika istasyon adlarını döndürür (video adları filtrelenmiştir)."""
    from web.helpers import get_all_system_stations
    stations = get_all_system_stations()
    if not stations:
        stations = ['Istasyon-1', 'Istasyon-2', 'Istasyon-3', 'Istasyon-4']
    import re
    def natural_key(text):
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
    return sorted(list(stations), key=natural_key)


def get_worker_by_id(worker_id):
    """ID'ye göre çalışan döndürür."""
    with _get_worker_session() as sess:
        w = sess.get(Worker, worker_id)
        return w.to_dict() if w else None


def create_worker(ad, soyad, sicil_no=None, departman=None, istasyon_adi=None, fotograf_yolu=None, patron_id=None):
    """Yeni çalışan kaydeder (hem merkezi PG hem yerel SQLite'a ekler)."""
    with _get_worker_session() as sess:
        if sicil_no:
            existing = sess.scalars(select(Worker).where(Worker.sicil_no == sicil_no)).first()
            if existing:
                return False, "Bu sicil numarası zaten kullanımda."

        if istasyon_adi:
            existing_station = sess.scalars(
                select(Worker).where(
                    func.lower(Worker.istasyon_adi) == istasyon_adi.strip().lower(),
                    Worker.aktif == 1
                )
            ).first()
            if existing_station:
                return False, f"'{istasyon_adi.strip()}' istasyonuna zaten '{existing_station.ad} {existing_station.soyad}' atanmış."

        new_worker = Worker(
            ad=ad,
            soyad=soyad,
            sicil_no=sicil_no,
            departman=departman,
            istasyon_adi=istasyon_adi.strip() if istasyon_adi else None,
            fotograf_yolu=fotograf_yolu,
            patron_id=patron_id,
            aktif=1
        )
        sess.add(new_worker)
        sess.commit()
        sess.refresh(new_worker)
        res_dict = new_worker.to_dict()

    try:
        with db_manager.get_session() as loc_sess:
            if sicil_no:
                loc_w = loc_sess.scalars(select(Worker).where(Worker.sicil_no == sicil_no)).first()
                if not loc_w:
                    w_loc = Worker(
                        ad=ad, soyad=soyad, sicil_no=sicil_no, departman=departman,
                        istasyon_adi=istasyon_adi.strip() if istasyon_adi else None,
                        fotograf_yolu=fotograf_yolu, patron_id=patron_id, aktif=1
                    )
                    loc_sess.add(w_loc)
                    loc_sess.commit()
    except Exception:
        pass

    return True, res_dict


def update_worker(worker_id, **kwargs):
    """Çalışan bilgilerini günceller."""
    with _get_worker_session() as sess:
        worker = sess.get(Worker, worker_id)
        if not worker:
            return False, "Çalışan bulunamadı."

        sicil_no = kwargs.get('sicil_no')
        if sicil_no and sicil_no != worker.sicil_no:
            existing = sess.scalars(
                select(Worker).where(Worker.sicil_no == sicil_no, Worker.id != worker_id)
            ).first()
            if existing:
                return False, "Bu sicil numarası başka bir çalışana ait."

        istasyon_adi = kwargs.get('istasyon_adi')
        if istasyon_adi and istasyon_adi.strip().lower() != (worker.istasyon_adi or "").strip().lower():
            existing_station = sess.scalars(
                select(Worker).where(
                    func.lower(Worker.istasyon_adi) == istasyon_adi.strip().lower(),
                    Worker.id != worker_id,
                    Worker.aktif == 1
                )
            ).first()
            if existing_station:
                return False, f"'{istasyon_adi.strip()}' istasyonuna zaten '{existing_station.ad} {existing_station.soyad}' atanmış."

        for key, value in kwargs.items():
            if hasattr(worker, key) and value is not None:
                if key == 'istasyon_adi' and isinstance(value, str):
                    value = value.strip()
                setattr(worker, key, value)

        sess.commit()
        sicil_check = worker.sicil_no

    try:
        with db_manager.get_session() as loc_sess:
            loc_w = loc_sess.scalars(select(Worker).where(Worker.sicil_no == sicil_check)).first()
            if loc_w:
                for key, value in kwargs.items():
                    if hasattr(loc_w, key) and value is not None:
                        if key == 'istasyon_adi' and isinstance(value, str):
                            value = value.strip()
                        setattr(loc_w, key, value)
                loc_sess.commit()
    except Exception:
        pass

    return True, "Çalışan güncellendi."


def delete_worker(worker_id):
    """Çalışanı veritabanından tamamen siler (PG ve SQLite senkronize)."""
    sicil_check = None
    ad_check = None
    soyad_check = None
    with _get_worker_session() as sess:
        worker = sess.get(Worker, worker_id)
        if worker:
            sicil_check = worker.sicil_no
            ad_check = worker.ad
            soyad_check = worker.soyad
            try:
                sess.delete(worker)
                sess.commit()
            except Exception:
                sess.rollback()
                worker.aktif = 0
                sess.commit()
        else:
            return False, "Çalışan bulunamadı."

    try:
        with db_manager.get_session() as loc_sess:
            loc_w = loc_sess.get(Worker, worker_id)
            if not loc_w and sicil_check:
                loc_w = loc_sess.scalars(select(Worker).where(Worker.sicil_no == sicil_check)).first()
            if not loc_w and ad_check:
                loc_w = loc_sess.scalars(select(Worker).where(Worker.ad == ad_check, Worker.soyad == soyad_check)).first()
            if loc_w:
                try:
                    loc_sess.delete(loc_w)
                    loc_sess.commit()
                except Exception:
                    loc_sess.rollback()
                    loc_w.aktif = 0
                    loc_sess.commit()
    except Exception:
        pass

    return True, "Çalışan başarıyla silindi."


def toggle_worker_aktif(worker_id):
    """Çalışanın aktiflik durumunu (1/0) değiştirir."""
    with _get_worker_session() as sess:
        worker = sess.get(Worker, worker_id)
        if not worker:
            return False, "Çalışan bulunamadı."
        worker.aktif = 0 if worker.aktif == 1 else 1
        new_status = worker.aktif
        sess.commit()
        sicil_check = worker.sicil_no

    try:
        with db_manager.get_session() as loc_sess:
            loc_w = loc_sess.scalars(select(Worker).where(Worker.sicil_no == sicil_check)).first()
            if loc_w:
                loc_w.aktif = new_status
                loc_sess.commit()
    except Exception:
        pass

    msg = "Çalışan aktif yapıldı." if new_status == 1 else "Çalışan pasif yapıldı."
    return True, msg

