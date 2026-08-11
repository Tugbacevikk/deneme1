"""
alarm_service.py - Alarm ve İhlal Yönetim Servisi
"""
import logging
from sqlalchemy import select, func
from core.database.models import Alarm
from core.database.connection import db_manager

logger = logging.getLogger(__name__)


def get_alarms(limit=50, unread_only=False):
    """Alarmları getirir."""
    with db_manager.get_session() as session:
        stmt = select(Alarm)
        if unread_only:
            stmt = stmt.where(Alarm.okundu == 0)
        stmt = stmt.order_by(Alarm.id.desc()).limit(limit)
        alarms = session.scalars(stmt).all()
        return [a.to_dict() for a in alarms]


def get_unread_count():
    """Okunmamış alarm sayısını döndürür."""
    with db_manager.get_session() as session:
        stmt = select(func.count(Alarm.id)).where(Alarm.okundu == 0)
        count = session.scalar(stmt) or 0
        return count


def mark_alarms_read():
    """Tüm alarmları okundu olarak işaretler."""
    with db_manager.get_session() as session:
        session.query(Alarm).filter(Alarm.okundu == 0).update({Alarm.okundu: 1})
        session.commit()
        return True
