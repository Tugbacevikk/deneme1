"""
report_service.py - Raporlama ve Analiz Mantığı Servisi
Orijinal app.py içerisindeki tüm hassas süre hesaplama ve ORM filtreleme algoritmasını içerir.
"""
import logging
import datetime
from contextlib import contextmanager
from sqlalchemy import select, func, and_, or_, String
from core.database.models import DurumKaydi, Worker, User
from core.database.connection import db_manager

logger = logging.getLogger(__name__)


def _calculate_worker_durations(session_orm, worker_id=None, worker_name='', start_date='', end_date='', istasyon='', save_interval=5, model_cls=DurumKaydi):
    """
    Belirli bir çalışan, istasyon ve tarih aralığı için ham durum kayıtlarını inceleyerek 
    kesintisiz aktif, inaktif ve telefon sürelerini tam olarak hesaplar.
    """
    zaman_str_expr = func.cast(model_cls.zaman, String)
    filters = []
    if start_date:
        filters.append(func.substr(zaman_str_expr, 1, 10) >= start_date)
    if end_date:
        filters.append(func.substr(zaman_str_expr, 1, 10) <= end_date)

    if istasyon:
        filters.append(model_cls.istasyon_adi == istasyon)

    if istasyon and istasyon.startswith('VIDEO:'):
        pass
    elif worker_id and str(worker_id).isdigit() and int(worker_id) > 0:
        filters.append(or_(
            model_cls.worker_id == int(worker_id),
            model_cls.worker_adi == worker_name
        ))
    elif worker_name and worker_name != 'Atanmamış Çalışan' and not worker_name.startswith('Video:'):
        filters.append(model_cls.worker_adi == worker_name)

    stmt = select(model_cls).where(and_(*filters)).order_by(model_cls.zaman.asc())
    kayitlar = session_orm.scalars(stmt).all()

    aktif_sec = 0
    kaynak_sec = 0
    inaktif_sec = 0
    telefon_sec = 0

    num_kayitlar = len(kayitlar)
    for i in range(num_kayitlar):
        k = kayitlar[i]
        st = (k.durum or '').upper()
        is_kaynak = 'KAYNAK' in st
        is_telefon = 'TELEFON' in st
        is_inaktif = 'İNAKTİF' in st or 'INAKTIF' in st or 'NAKT' in st
        is_aktif = st.startswith('AKT')

        if is_telefon:
            cat = 'TELEFON'
        elif is_kaynak:
            cat = 'KAYNAK'
        elif is_inaktif:
            cat = 'INAKTIF'
        elif is_aktif:
            cat = 'AKTIF'
        else:
            cat = 'INAKTIF'

        try:
            if isinstance(k.zaman, datetime.datetime):
                z_dt = k.zaman
            else:
                z_dt = datetime.datetime.strptime(str(k.zaman).replace('T', ' ')[:19], '%Y-%m-%d %H:%M:%S')
        except Exception:
            z_dt = datetime.datetime.now()

        if i < num_kayitlar - 1:
            next_k = kayitlar[i + 1]
            try:
                if isinstance(next_k.zaman, datetime.datetime):
                    next_dt = next_k.zaman
                else:
                    next_dt = datetime.datetime.strptime(str(next_k.zaman).replace('T', ' ')[:19], '%Y-%m-%d %H:%M:%S')
            except Exception:
                next_dt = z_dt

            gap = (next_dt - z_dt).total_seconds()
            dur = int(gap) if 0 < gap <= 15 else save_interval
        else:
            dur = save_interval

        if cat == 'KAYNAK':
            kaynak_sec += dur
        elif cat == 'AKTIF':
            aktif_sec += dur
        elif cat == 'INAKTIF':
            inaktif_sec += dur
        elif cat == 'TELEFON':
            telefon_sec += dur

    toplam_sec = aktif_sec + kaynak_sec + inaktif_sec + telefon_sec

    return {
        'aktif_sec': aktif_sec,
        'kaynak_sec': kaynak_sec,
        'inaktif_sec': inaktif_sec,
        'telefon_sec': telefon_sec,
        'toplam_sec': toplam_sec,
        'kayitlar_count': len(kayitlar)
    }


def _build_orm_filters(start: str, end: str, istasyon: str, only_registered: bool = False, patron_id: int = None, model_cls=DurumKaydi):
    """Tarih, istasyon, patron_id ve atanmış istasyon filtrelerini ORM koşul listesi olarak oluşturur."""
    filters = []
    zaman_str_expr = func.cast(model_cls.zaman, String)
    if start:
        filters.append(func.substr(zaman_str_expr, 1, 10) >= start)
    if end:
        filters.append(func.substr(zaman_str_expr, 1, 10) <= end)
    if istasyon:
        if 'VIDEO:' in istasyon.upper() or istasyon.endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
            filters.append(model_cls.istasyon_adi.like(f"%{istasyon}%"))
        else:
            filters.append(model_cls.istasyon_adi == istasyon)

    if patron_id is not None:
        stations = []
        patron_worker_ids = []
        try:
            with db_manager.get_session() as local_session:
                u = local_session.get(User, patron_id)
                if u and u.istasyonlar:
                    stations = [s.strip() for s in u.istasyonlar.split(',') if s.strip()]

                cond_w = [Worker.patron_id == patron_id]
                if stations:
                    cond_w.append(Worker.istasyon_adi.in_(stations))

                patron_worker_ids = local_session.scalars(select(Worker.id).where(or_(*cond_w))).all()
        except Exception:
            pass

        patron_conds = []
        if stations:
            patron_conds.append(model_cls.istasyon_adi.in_(stations))
        if patron_worker_ids:
            patron_conds.append(model_cls.worker_id.in_(patron_worker_ids))

        if patron_conds:
            filters.append(or_(*patron_conds))
        else:
            filters.append(model_cls.worker_id == -1)

    return filters


@contextmanager
def _get_reports_db_context(config=None):
    """
    Eğer PostgreSQL (merkezi_db) aktif ve erişilebilir ise PostgreSQL ORM Session ve CentralDurumKaydiModel döner.
    Aksi takdirde yerel SQLite db_manager session ve DurumKaydi döner.
    """
    merkezi_cfg = (config or {}).get('merkezi_db', {})
    is_pg_active = merkezi_cfg.get('aktif', True) if isinstance(merkezi_cfg, dict) else False

    if is_pg_active:
        try:
            from pg_sync import pg_baglan, CentralDurumKaydiModel, pg_baglantiyi_kapat
            engine = pg_baglan(merkezi_cfg)
            if engine:
                from sqlalchemy.orm import Session
                session = Session(engine)
                try:
                    yield session, CentralDurumKaydiModel
                except Exception as query_exc:
                    logger.warning(f"PostgreSQL sorgu hatası ({query_exc}), yerel SQLite veritabanına geçiliyor.")
                    session.close()
                    pg_baglantiyi_kapat(engine)
                    with db_manager.get_session() as fallback_session:
                        yield fallback_session, DurumKaydi
                    return
                finally:
                    try:
                        session.close()
                        pg_baglantiyi_kapat(engine)
                    except Exception:
                        pass
                return
        except Exception as e:
            logger.warning(f"PostgreSQL rapor bağlantısı başarısız, yerel SQLite'a geçiliyor: {e}")

    with db_manager.get_session() as session:
        yield session, DurumKaydi
