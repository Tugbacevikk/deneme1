"""
worker_service.py - Çalışan / İşçi Yönetim Servisi
"""
import logging
from sqlalchemy import select, func
from core.database.models import Worker
from core.database.connection import db_manager

logger = logging.getLogger(__name__)


def get_all_workers(aktif_only=False):
    """Tüm çalışanları döndürür."""
    with db_manager.get_session() as session:
        stmt = select(Worker)
        if aktif_only:
            from sqlalchemy import or_
            stmt = stmt.where(or_(Worker.aktif == 1, Worker.aktif.is_(None)))
        stmt = stmt.order_by(Worker.ad.asc(), Worker.soyad.asc())
        workers = session.scalars(stmt).all()
        return [w.to_dict() for w in workers]


def create_worker(ad, soyad, sicil_no=None, departman=None, istasyon_adi=None, fotograf_yolu=None, patron_id=None):
    """Yeni çalışan kaydeder."""
    with db_manager.get_session() as session:
        if sicil_no:
            existing = session.scalars(select(Worker).where(Worker.sicil_no == sicil_no)).first()
            if existing:
                return False, "Bu sicil numarası zaten kullanımda."

        if istasyon_adi:
            existing_station = session.scalars(
                select(Worker).where(
                    func.lower(Worker.istasyon_adi) == istasyon_adi.strip().lower(),
                    Worker.aktif == 1
                )
            ).first()
            if existing_station:
                ad_soyad = f"{existing_station.ad} {existing_station.soyad}"
                return False, (
                    f"Bu istasyonda zaten aktif bir çalışan var: {ad_soyad}. "
                    "Önce onu pasif yapın veya farklı bir istasyon seçin."
                )

        new_worker = Worker(
            ad=ad,
            soyad=soyad,
            sicil_no=sicil_no,
            departman=departman,
            istasyon_adi=istasyon_adi,
            fotograf_yolu=fotograf_yolu,
            patron_id=patron_id
        )
        session.add(new_worker)
        session.commit()
        session.refresh(new_worker)
        return True, new_worker.to_dict()


def delete_worker(worker_id):
    """Çalışanı siler veya pasife alır."""
    with db_manager.get_session() as session:
        worker = session.get(Worker, worker_id)
        if not worker:
            return False, "Çalışan bulunamadı."
        session.delete(worker)
        session.commit()
        return True, "Çalışan silindi."


def update_worker(worker_id, data):
    """Çalışan bilgilerini günceller."""
    with db_manager.get_session() as session:
        worker = session.get(Worker, worker_id)
        if not worker:
            return False, "Çalışan bulunamadı."

        istasyon_adi = data.get('istasyon_adi')
        if istasyon_adi:
            existing_station = session.scalars(
                select(Worker).where(
                    func.lower(Worker.istasyon_adi) == istasyon_adi.strip().lower(),
                    Worker.aktif == 1,
                    Worker.id != worker_id
                )
            ).first()
            if existing_station:
                ad_soyad = f"{existing_station.ad} {existing_station.soyad}"
                return False, (
                    f"Bu istasyonda zaten aktif bir çalışan var: {ad_soyad}. "
                    "Önce onu pasif yapın veya farklı bir istasyon seçin."
                )

        for key in ['ad', 'soyad', 'sicil_no', 'departman', 'istasyon_adi', 'fotograf_yolu', 'patron_id', 'aktif']:
            if key in data and data[key] is not None:
                setattr(worker, key, data[key])

        session.commit()
        return True, worker.to_dict()


def toggle_worker_aktif(worker_id):
    """Çalışanı aktif ↔ pasif arasında geçiş yapar.
    Pasife alınırken istasyon ataması da temizlenir."""
    with db_manager.get_session() as session:
        worker = session.get(Worker, worker_id)
        if not worker:
            return False, "Çalışan bulunamadı."

        yeni_durum = 0 if worker.aktif == 1 else 1

        worker.aktif = yeni_durum
        # Pasife alınırken istasyonu serbest bırak
        if yeni_durum == 0:
            worker.istasyon_adi = None

        session.commit()
        durum_label = "aktif" if yeni_durum == 1 else "pasif"
        return True, f"{worker.ad} {worker.soyad} artık {durum_label}."

