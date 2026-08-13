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


def mark_alarms_read():
    """Tüm alarmları okundu olarak işaretler."""
    with db_manager.get_session() as session:
        session.query(Alarm).filter(Alarm.okundu == 0).update({Alarm.okundu: 1})
        session.commit()
        return True


def mark_single_alarm_read(alarm_id):
    """Belirli bir alarmı okundu olarak işaretler."""
    with db_manager.get_session() as session:
        alarm = session.get(Alarm, alarm_id)
        if alarm:
            alarm.okundu = 1
            session.commit()
            return True
        return False
