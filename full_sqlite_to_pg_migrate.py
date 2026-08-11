"""
full_sqlite_to_pg_migrate.py - SQLite'tan PostgreSQL'e Eksiksiz Veri Taşıma Scripti
"""
import os
import sys
import logging
from pathlib import Path
from sqlalchemy import create_engine, text, select
from sqlalchemy.orm import Session
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
load_dotenv(BASE_DIR / '.env')

from core.database.connection import DatabaseManager
from core.database.models import (
    Base, User, Worker, DurumKaydi, Alarm, TespitKaydi, GunlukOzet, Camera
)
from pg_sync import pg_baglan, CentralDurumKaydiModel

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)


def migrate_all():
    db_path = BASE_DIR / 'isci_takip.db'
    if not db_path.exists():
        logger.error(f"SQLite veritabanı bulunamadı: {db_path}")
        return

    db_mgr = DatabaseManager(str(db_path))
    import yaml
    config_path = BASE_DIR / 'config.yaml'
    cfg = {}
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}

    merkezi_cfg = cfg.get("merkezi_db", {})
    pg_engine = pg_baglan(merkezi_cfg)

    if not pg_engine:
        logger.error("PostgreSQL motoru oluşturulamadı.")
        return

    logger.info("Şemalar doğrulanıyor...")
    Base.metadata.create_all(pg_engine)

    # Modeller dizisi (Sıra önemli: FK bağımlılıklarına dikkat)
    models_to_migrate = [
        ("Users", User),
        ("Workers", Worker),
        ("DurumKayitlari", DurumKaydi),
        ("Alarmlar", Alarm),
        ("TespitKayitlari", TespitKaydi),
        ("GunlukOzetler", GunlukOzet),
        ("Cameras", Camera),
    ]

    with db_mgr.get_session() as sqlite_session:
        with Session(pg_engine) as pg_session:
            for model_name, model_cls in models_to_migrate:
                try:
                    records = sqlite_session.scalars(select(model_cls)).all()
                    if not records:
                        logger.info(f"{model_name}: SQLite'ta veri yok, atlanıyor.")
                        continue

                    count = 0
                    for item in records:
                        # SQLite nesnesinin alanlarını al
                        data = {col.name: getattr(item, col.name) for col in item.__table__.columns}
                        
                        # Mevcut kaydı kontrol et (ID ile)
                        existing = pg_session.get(model_cls, data['id'])
                        if not existing:
                            new_obj = model_cls(**data)
                            pg_session.add(new_obj)
                            count += 1
                    
                    pg_session.commit()
                    logger.info(f"{model_name}: {count} adet yeni kayıt PostgreSQL'e aktarıldı. (Toplam SQLite: {len(records)})")
                except Exception as e:
                    pg_session.rollback()
                    logger.error(f"{model_name} aktarım hatası: {e}")

            # Sequence (Autoincrement ID) güncellemesi
            with pg_engine.connect() as conn:
                for model_name, model_cls in models_to_migrate:
                    table_name = model_cls.__tablename__
                    try:
                        conn.execute(text(
                            f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), COALESCE(max(id), 1)) FROM {table_name};"
                        ))
                        conn.commit()
                    except Exception as e:
                        logger.debug(f"{table_name} sequence güncelleme: {e}")

    logger.info("SQLite -> PostgreSQL veri aktarımı ve senkronizasyonu tamamlandı!")


if __name__ == '__main__':
    migrate_all()
