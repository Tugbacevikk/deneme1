"""
alarm_service.py - Alarm ve İhlal Yönetim Servisi
"""
import logging
from sqlalchemy import select, func
from core.database.models import Alarm
from core.database.connection import db_manager

logger = logging.getLogger(__name__)


def get_alarms(limit=50, unread_only=False, stations=None):
    """Alarmları getirir (Hareketsizlik hariç, Telefon ve Sistem alarmları)."""
    with db_manager.get_session() as session:
        stmt = select(Alarm).where(Alarm.alarm_turu != 'HAREKETSİZLİK')
        if unread_only:
            stmt = stmt.where(Alarm.okundu == 0)
        if stations is not None:
            stmt = stmt.where(Alarm.istasyon_adi.in_(stations))
        stmt = stmt.order_by(Alarm.id.desc()).limit(limit)
        alarms = session.scalars(stmt).all()
        return [a.to_dict() for a in alarms]


def get_unread_count(stations=None):
    """Okunmamış alarm sayısını döndürür (Hareketsizlik hariç)."""
    with db_manager.get_session() as session:
        stmt = select(func.count(Alarm.id)).where(
            Alarm.okundu == 0,
            Alarm.alarm_turu != 'HAREKETSİZLİK'
        )
        if stations is not None:
            stmt = stmt.where(Alarm.istasyon_adi.in_(stations))
        count = session.scalar(stmt) or 0
        return count


def mark_alarms_read(stations=None):
    """Tüm alarmları (veya yetkili olunan istasyon alarmlarını) okundu olarak işaretler."""
    with db_manager.get_session() as session:
        query = session.query(Alarm).filter(Alarm.okundu == 0)
        if stations is not None:
            query = query.filter(Alarm.istasyon_adi.in_(stations))
        query.update({Alarm.okundu: 1}, synchronize_session=False)
        session.commit()
        return True


def mark_single_alarm_read(alarm_id, stations=None):
    """Belirli bir alarmı okundu olarak işaretler (istasyon yetkisi kontrolü ile)."""
    with db_manager.get_session() as session:
        alarm = session.get(Alarm, alarm_id)
        if alarm:
            if stations is not None and alarm.istasyon_adi and alarm.istasyon_adi not in stations:
                return False
            alarm.okundu = 1
            session.commit()
            return True
        return False


def mark_single_alarm_unread(alarm_id, stations=None):
    """Belirli bir alarmı okunmadı olarak işaretler (istasyon yetkisi kontrolü ile)."""
    with db_manager.get_session() as session:
        alarm = session.get(Alarm, alarm_id)
        if alarm:
            if stations is not None and alarm.istasyon_adi and alarm.istasyon_adi not in stations:
                return False
            alarm.okundu = 0
            session.commit()
            return True
        return False


def delete_alarm(alarm_id, stations=None):
    """Belirli bir alarmı siler (istasyon yetkisi kontrolü ile)."""
    if str(alarm_id).startswith('pending_'):
        return True
    try:
        alarm_id_int = int(alarm_id)
    except (ValueError, TypeError):
        return False

    with db_manager.get_session() as session:
        alarm = session.get(Alarm, alarm_id_int)
        if alarm:
            if stations is not None and alarm.istasyon_adi and alarm.istasyon_adi not in stations:
                return False
            session.delete(alarm)
            session.commit()
            return True
        return False
