"""
İşçi Takip Sistemi - Veritabanı Yöneticisi (DatabaseManager)
SQLAlchemy 2.0 ORM Engine ve Session Yönetimi
"""

import os
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from .models import Base

logger = logging.getLogger(__name__)

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Sadece SQLite veritabanlarında Foreign Key, WAL modu ve synchronous=NORMAL ayarlarını aktif eder."""
    try:
        mod = getattr(type(dbapi_connection), '__module__', '')
        if mod.startswith(('sqlite3', '_sqlite3')) or 'sqlite' in mod.lower():
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()
    except Exception as e:
        logger.warning(f"SQLite PRAGMA ayarlari uygulanamadi: {e}")

BASE_DIR = Path(__file__).parent.parent.parent
DEFAULT_DB_PATH = BASE_DIR / 'isci_takip.db'


class DatabaseManager:
    """
    Code-First ORM veritabanı motorunu (engine) ve oturumlarını (session)
    yöneten sınıf yapısı.
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = str(DEFAULT_DB_PATH)
        
        # Absolute path format for SQLite engine
        db_path_obj = Path(db_path).resolve()
        self.db_url = f"sqlite:///{db_path_obj}"
        
        self.engine = create_engine(
            self.db_url,
            connect_args={"check_same_thread": False, "timeout": 30},
            echo=False
        )
        self.SessionFactory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.init_db()

    def init_db(self):
        """Code-First: Tüm veritabanı tablolarını ORM sınıflarından otomatik oluşturur ve eksik sütunları tamamlar."""
        try:
            Base.metadata.create_all(self.engine)
            logger.info(f"Code-First ORM veritabanı başlatıldı: {self.db_url}")
            self._auto_migrate_columns()
        except Exception as e:
            logger.error(f"Veritabanı başlatma hatası: {e}")

    def _auto_migrate_columns(self):
        """Eski veritabanı dosyalarında eksik kalmış olabilecek sütunları otomatik tespit eder ve güvenle ekler."""
        try:
            inspector = inspect(self.engine)
            if 'users' in inspector.get_table_names():
                columns = [c['name'] for c in inspector.get_columns('users')]
                with self.engine.begin() as conn:
                    if 'email' not in columns:
                        conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(150)"))
                        logger.info("Auto-migration: 'users' tablosuna 'email' sutunu eklendi.")
                    if 'durum' not in columns:
                        conn.execute(text("ALTER TABLE users ADD COLUMN durum VARCHAR(20) DEFAULT 'bekliyor'"))
                        logger.info("Auto-migration: 'users' tablosuna 'durum' sutunu eklendi.")
                    if 'firma_adi' not in columns:
                        conn.execute(text("ALTER TABLE users ADD COLUMN firma_adi VARCHAR(150)"))
                        logger.info("Auto-migration: 'users' tablosuna 'firma_adi' sutunu eklendi.")
                    if 'istasyonlar' not in columns:
                        conn.execute(text("ALTER TABLE users ADD COLUMN istasyonlar VARCHAR(255)"))
                        logger.info("Auto-migration: 'users' tablosuna 'istasyonlar' sutunu eklendi.")
            
            if 'workers' in inspector.get_table_names():
                w_columns = [c['name'] for c in inspector.get_columns('workers')]
                with self.engine.begin() as conn:
                    if 'patron_id' not in w_columns:
                        conn.execute(text("ALTER TABLE workers ADD COLUMN patron_id INTEGER REFERENCES users(id)"))
                        logger.info("Auto-migration: 'workers' tablosuna 'patron_id' sutunu eklendi.")
        except Exception as e:
            logger.warning(f"Auto-migration kontrolu sirasinda hata: {e}")

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Güvenli ORM Oturumu (Session) sağlayan bağlam yöneticisi."""
        session: Session = self.SessionFactory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"ORM Oturum Hatası (Rollback yapıldı): {e}")
            raise
        finally:
            session.close()


    def cleanup_old_records(self, days: int = 30) -> int:
        """30 günden (veya belirtilen gün sayısından) eski ham DurumKaydi loglarını temizler."""
        import datetime
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self.engine.begin() as conn:
                res = conn.execute(
                    text("DELETE FROM durum_kayitlari WHERE zaman < :cutoff"),
                    {"cutoff": cutoff_str}
                )
                deleted_count = res.rowcount
                logger.info(f"DB Temizlik: {days} günden eski {deleted_count} adet DurumKaydi temizlendi.")
                return deleted_count
        except Exception as e:
            logger.error(f"DB Temizlik Hatası: {e}")
            return 0


# Proje genelinde kullanılacak varsayılan veritabanı yöneticisi örneği
db_manager = DatabaseManager()
