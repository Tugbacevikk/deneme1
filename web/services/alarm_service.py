"""
alarm_service.py - Alarm ve İhlal Yönetim Servisi
"""
import os
import logging
from contextlib import contextmanager
from sqlalchemy import select, func
from core.database.models import Alarm
from core.database.connection import db_manager

logger = logging.getLogger(__name__)


@contextmanager
def _get_alarm_db_context():
    """
    Eğer PostgreSQL (merkezi veritabanı) aktif ve erişilebilir ise PostgreSQL ORM Session kullanır.
    Aksi takdirde yerel SQLite db_manager session'ına geçer.
    """
    try:
        import web.extensions as ext
        config = getattr(ext, 'config', {}) or {}
    except Exception:
        config = {}

    merkezi_cfg = config.get('merkezi_db') or {}
    pg_host = os.getenv('POSTGRES_HOST') or merkezi_cfg.get('host') or config.get('pg_host')

    if pg_host:
        try:
            from pg_sync import pg_baglan, pg_baglantiyi_kapat
            engine = pg_baglan(merkezi_cfg if merkezi_cfg else config)
            if engine:
                from sqlalchemy.orm import Session
                session = Session(engine)
                try:
                    yield session
                    return
                except Exception as ex:
                    logger.warning(f"PostgreSQL alarm sorgu hatası ({ex}), yerel SQLite veritabanına geçiliyor.")
                    try:
                        session.close()
                        pg_baglantiyi_kapat(engine)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"PostgreSQL alarm bağlantısı kurulamadı ({e}), yerel SQLite kullanılıyor.")

    with db_manager.get_session() as session:
        yield session


def get_alarms(limit=50, unread_only=False, stations=None):
    """Alarmları getirir (Hareketsizlik hariç, Telefon ve Sistem alarmları)."""
    with _get_alarm_db_context() as session:
        stmt = select(Alarm).where(Alarm.alarm_turu != 'HAREKETSİZLİK')
        if unread_only:
            stmt = stmt.where(Alarm.okundu == 0)
        if stations:
            has_all = any(
                s.strip().lower() in ['tüm fabrika', 'tum fabrika', 'hepsi', 'tüm istasyonlar', 'tum istasyonlar']
                for s in stations
            )
            if not has_all:
                stmt = stmt.where(or_(
                    Alarm.istasyon_adi.in_(stations),
                    Alarm.istasyon_adi.in_(['Sistem', 'Genel', 'System', 'General']),
                    Alarm.istasyon_adi.is_(None)
                ))
        stmt = stmt.order_by(Alarm.id.desc()).limit(limit)
        alarms = session.scalars(stmt).all()
        return [a.to_dict() for a in alarms]


def get_unread_count(stations=None):
    """Okunmamış alarm sayısını döndürür (Hareketsizlik hariç)."""
    with _get_alarm_db_context() as session:
        stmt = select(func.count(Alarm.id)).where(
            Alarm.okundu == 0,
            Alarm.alarm_turu != 'HAREKETSİZLİK'
        )
        if stations:
            has_all = any(
                s.strip().lower() in ['tüm fabrika', 'tum fabrika', 'hepsi', 'tüm istasyonlar', 'tum istasyonlar']
                for s in stations
            )
            if not has_all:
                stmt = stmt.where(or_(
                    Alarm.istasyon_adi.in_(stations),
                    Alarm.istasyon_adi.in_(['Sistem', 'Genel', 'System', 'General']),
                    Alarm.istasyon_adi.is_(None)
                ))
        count = session.scalar(stmt) or 0
        return count


def mark_alarms_read(stations=None):
    """Tüm alarmları (veya yetkili olunan istasyon alarmlarını) okundu olarak işaretler."""
    with _get_alarm_db_context() as session:
        query = session.query(Alarm).filter(Alarm.okundu == 0)
        if stations is not None:
            query = query.filter(Alarm.istasyon_adi.in_(stations))
        query.update({Alarm.okundu: 1}, synchronize_session=False)
        session.commit()
        return True


def mark_single_alarm_read(alarm_id, stations=None):
    """Belirli bir alarmı okundu olarak işaretler (istasyon yetkisi kontrolü ile)."""
    with _get_alarm_db_context() as session:
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
    with _get_alarm_db_context() as session:
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

    with _get_alarm_db_context() as session:
        alarm = session.get(Alarm, alarm_id_int)
        if alarm:
            if stations is not None and alarm.istasyon_adi and alarm.istasyon_adi not in stations:
                return False
            session.delete(alarm)
            session.commit()
            return True
        return False

