"""
camera_service.py - Kamera ve İstasyon Yönetim Servisi
"""
import logging
from sqlalchemy import select
from core.database.models import Camera
from core.database.connection import db_manager

logger = logging.getLogger(__name__)


def _get_camera_session():
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


def get_all_cameras():
    """Tüm kameraları/istasyonları döndürür."""
    with _get_camera_session() as sess:
        cameras = sess.scalars(select(Camera).where(Camera.aktif == 1).order_by(Camera.id.asc())).all()
        return [c.to_dict() for c in cameras]


def add_camera(istasyon_adi, ip_adresi, patron_id=None, patron_adi=None):
    """Yeni kamera ekler (hem merkezi PG hem yerel SQLite'a ekler)."""
    with _get_camera_session() as sess:
        new_cam = Camera(
            istasyon_adi=istasyon_adi,
            ip_adresi=ip_adresi,
            patron_id=patron_id,
            patron_adi=patron_adi,
            aktif=1
        )
        sess.add(new_cam)
        sess.commit()
        sess.refresh(new_cam)
        res_dict = new_cam.to_dict()

    try:
        with db_manager.get_session() as loc_sess:
            loc_cam = Camera(
                istasyon_adi=istasyon_adi,
                ip_adresi=ip_adresi,
                patron_id=patron_id,
                patron_adi=patron_adi,
                aktif=1
            )
            loc_sess.add(loc_cam)
            loc_sess.commit()
    except Exception:
        pass

    return True, res_dict


def delete_camera(cam_id):
    """Kamerayı siler."""
    with _get_camera_session() as sess:
        cam = sess.get(Camera, cam_id)
        if not cam:
            return False, "Kamera bulunamadı."
        st_name = cam.istasyon_adi
        sess.delete(cam)
        sess.commit()

    try:
        with db_manager.get_session() as loc_sess:
            loc_c = loc_sess.scalars(select(Camera).where(Camera.istasyon_adi == st_name)).first()
            if loc_c:
                loc_sess.delete(loc_c)
                loc_sess.commit()
    except Exception:
        pass

    return True, "Kamera silindi."
