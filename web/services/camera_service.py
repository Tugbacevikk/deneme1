"""
camera_service.py - Kamera ve İstasyon Yönetim Servisi
"""
import logging
from sqlalchemy import select
from core.database.models import Camera
from core.database.connection import db_manager

logger = logging.getLogger(__name__)


def get_all_cameras():
    """Tüm kameraları/istasyonları döndürür."""
    with db_manager.get_session() as session:
        cameras = session.scalars(select(Camera).where(Camera.aktif == 1).order_by(Camera.id.asc())).all()
        return [c.to_dict() for c in cameras]


def add_camera(istasyon_adi, ip_adresi, patron_id=None, patron_adi=None):
    """Yeni kamera ekler."""
    with db_manager.get_session() as session:
        new_cam = Camera(
            istasyon_adi=istasyon_adi,
            ip_adresi=ip_adresi,
            patron_id=patron_id,
            patron_adi=patron_adi,
            aktif=1
        )
        session.add(new_cam)
        session.commit()
        session.refresh(new_cam)
        return True, new_cam.to_dict()


def delete_camera(cam_id):
    """Kamerayı siler."""
    with db_manager.get_session() as session:
        cam = session.get(Camera, cam_id)
        if not cam:
            return False, "Kamera bulunamadı."
        session.delete(cam)
        session.commit()
        return True, "Kamera silindi."
