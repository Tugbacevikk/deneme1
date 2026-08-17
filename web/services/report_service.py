"""
report_service.py - Raporlama ve Analiz Mantığı Servisi
Orijinal app.py içerisindeki tüm hassas süre hesaplama ve ORM filtreleme algoritmasını içerir.
"""
import logging
import datetime
from contextlib import contextmanager
from sqlalchemy import select, func, and_, or_, String
from core.database.models import DurumKaydi, Worker, User, GunlukOzet
from core.database.connection import db_manager

logger = logging.getLogger(__name__)


def _calculate_worker_durations(session_orm, worker_id=None, worker_name='', start_date='', end_date='', istasyon='', save_interval=5, model_cls=DurumKaydi):
    """
    Belirli bir çalışan, istasyon ve tarih aralığı için ham durum kayıtlarını inceleyerek 
    kesintisiz aktif, inaktif, kaynak ve telefon sürelerini tam kesinlikle hesaplar.
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
        'kayitlar_count': num_kayitlar
    }


def _normalize_date_str(d_str: str) -> str:
    """DD.MM.YYYY veya YYYY-MM-DD tarihini YYYY-MM-DD formatına dönüştürür."""
    if not d_str:
        return ''
    d_str = str(d_str).strip()
    if '.' in d_str:
        parts = d_str.split('.')
        if len(parts) == 3 and len(parts[2]) == 4:
            return f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
    return d_str


def _build_orm_filters(start: str, end: str, istasyon: str, worker: str = '', only_registered: bool = False, patron_id: int = None, model_cls=DurumKaydi):
    """Tarih, istasyon, çalışan, patron_id ve atanmış istasyon filtrelerini ORM koşul listesi olarak oluşturur."""
    filters = []
    start_clean = _normalize_date_str(start)
    end_clean = _normalize_date_str(end)

    zaman_str_expr = func.cast(model_cls.zaman, String)
    if start_clean:
        filters.append(func.substr(zaman_str_expr, 1, 10) >= start_clean)
    if end_clean:
        filters.append(func.substr(zaman_str_expr, 1, 10) <= end_clean)
    if istasyon:
        if 'VIDEO:' in istasyon.upper() or istasyon.endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm')):
            filters.append(model_cls.istasyon_adi.like(f"%{istasyon}%"))
        else:
            filters.append(or_(
                model_cls.istasyon_adi == istasyon,
                model_cls.istasyon_adi.like(f"%{istasyon}%")
            ))

    if worker:
        w_query = worker.strip().lower()
        w_ids = []
        w_stations = []
        try:
            with db_manager.get_session() as local_sess:
                w_all = local_sess.scalars(select(Worker)).all()
                for w in w_all:
                    w_full = f"{w.ad} {w.soyad}".strip().lower()
                    w_sicil = (w.sicil_no or '').lower()
                    if w_query in w_full or w_query in (w.ad or '').lower() or w_query in (w.soyad or '').lower() or w_query in w_sicil or str(w.id) == w_query:
                        w_ids.append(w.id)
                        if w.istasyon_adi:
                            w_stations.append(w.istasyon_adi.strip())
        except Exception:
            pass

        w_conds = [model_cls.worker_adi.ilike(f"%{worker}%")]
        if str(worker).isdigit():
            w_conds.append(model_cls.worker_id == int(worker))
        if w_ids:
            w_conds.append(model_cls.worker_id.in_(w_ids))
        if w_stations:
            w_conds.append(model_cls.istasyon_adi.in_(w_stations))

        filters.append(or_(*w_conds))


    if patron_id is not None:
        stations = []
        patron_worker_ids = []
        try:
            with db_manager.get_session() as local_session:
                u = local_session.get(User, patron_id)
                if u and u.istasyonlar:
                    stations = [s.strip() for s in u.istasyonlar.split(',') if s.strip()]

                cond_w = []
                if stations:
                    cond_w.append(Worker.istasyon_adi.in_(stations))

                patron_worker_ids = local_session.scalars(select(Worker.id).where(or_(*cond_w))).all() if cond_w else []
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
                    with db_manager.get_session() as fallback_session:
                        yield fallback_session, DurumKaydi
                    return
                finally:
                    try:
                        session.close()
                    except Exception:
                        pass
                return
        except Exception as e:
            logger.warning(f"PostgreSQL rapor bağlantısı başarısız, yerel SQLite'a geçiliyor: {e}")

    with db_manager.get_session() as session:
        yield session, DurumKaydi


def get_worker_stats_rows(start='', end='', istasyon='', worker='', patron_id=None, config=None):
    """
    api_reports_worker_stats ve PDF çıktısı için ortak çalışan istatistik satırlarını üretir.
    """
    if config is None:
        try:
            from web.routes.reports import _get_app_config
            config = _get_app_config()
        except Exception:
            config = {}
    save_interval = config.get('save_interval', 5)

    from web.helpers import format_duration_tr, _format_date_tr
    from sqlalchemy import case, desc

    workers_data = []
    try:
        with _get_reports_db_context(config) as (session_orm, model_cls):
            filters = _build_orm_filters(start, end, istasyon, worker=worker, patron_id=patron_id, model_cls=model_cls)

            default_st = config.get('station_name') or config.get('istasyon_adi') or 'Istasyon-1'
            if not default_st or default_st in ['auto', 'auto (Otomatik Bilgisayar Adı)'] or default_st.startswith('LAPTOP-') or default_st.startswith('DESKTOP-'):
                default_st = 'Istasyon-1'

            station_worker_map = {}
            try:
                with db_manager.get_session() as local_sess:
                    # Aktif ve pasif TÜM çalışanları istasyona göre haritala (Aktifler öncelikli)
                    w_all = local_sess.scalars(select(Worker).order_by(Worker.aktif.desc(), Worker.id.desc())).all()
                    for w in w_all:
                        if w.istasyon_adi and w.istasyon_adi.strip():
                            st_key = w.istasyon_adi.strip()
                            if st_key not in station_worker_map:
                                station_worker_map[st_key] = (w.id, f"{w.ad} {w.soyad}".strip())
            except Exception:
                pass

            zaman_str_expr = func.cast(model_cls.zaman, String)
            tarih_col = func.substr(zaman_str_expr, 1, 10)
            istasyon_col = func.coalesce(model_cls.istasyon_adi, default_st)

            stmt = select(
                tarih_col.label('tarih'),
                istasyon_col.label('istasyon_adi'),
                func.count(model_cls.id).label('toplam_kayit'),
                func.sum(case((model_cls.durum.like('AKT%'), 1), else_=0)).label('aktif_kayit'),
                func.sum(case((model_cls.durum.like('%KAYNAK%'), 1), else_=0)).label('kaynak_kayit'),
                func.sum(case((model_cls.durum.like('%TELEFON%'), 1), else_=0)).label('telefon_kayit'),
                func.sum(case((and_(model_cls.durum.like('%NAKT%'), ~model_cls.durum.like('%TELEFON%')), 1), else_=0)).label('inaktif_kayit'),
                func.min(model_cls.zaman).label('ilk_gorulme'),
                func.max(model_cls.zaman).label('son_gorulme')
            )
            if filters:
                stmt = stmt.where(and_(*filters))
            stmt = stmt.group_by(tarih_col, istasyon_col).order_by(desc('tarih'), desc('toplam_kayit'))
            rows = session_orm.execute(stmt).all()

            # Eğer PostgreSQL ortamından 0 kayıt geldiyse yerel SQLite veritabanından çek (Yedekleme garantisi)
            if not rows and model_cls != DurumKaydi:
                try:
                    with db_manager.get_session() as local_sess:
                        filters_l = _build_orm_filters(start, end, istasyon, worker=worker, patron_id=patron_id, model_cls=DurumKaydi)
                        z_str_l = func.cast(DurumKaydi.zaman, String)
                        tarih_col_l = func.substr(z_str_l, 1, 10)
                        ist_col_l = func.coalesce(DurumKaydi.istasyon_adi, default_st)
                        stmt_l = select(
                            tarih_col_l.label('tarih'),
                            ist_col_l.label('istasyon_adi'),
                            func.count(DurumKaydi.id).label('toplam_kayit'),
                            func.sum(case((DurumKaydi.durum.like('AKT%'), 1), else_=0)).label('aktif_kayit'),
                            func.sum(case((DurumKaydi.durum.like('%KAYNAK%'), 1), else_=0)).label('kaynak_kayit'),
                            func.sum(case((DurumKaydi.durum.like('%TELEFON%'), 1), else_=0)).label('telefon_kayit'),
                            func.sum(case((and_(DurumKaydi.durum.like('%NAKT%'), ~DurumKaydi.durum.like('%TELEFON%')), 1), else_=0)).label('inaktif_kayit'),
                            func.min(DurumKaydi.zaman).label('ilk_gorulme'),
                            func.max(DurumKaydi.zaman).label('son_gorulme')
                        )

                        if filters_l:
                            stmt_l = stmt_l.where(and_(*filters_l))
                        stmt_l = stmt_l.group_by(tarih_col_l, ist_col_l).order_by(desc('tarih'), desc('toplam_kayit'))
                        rows = local_sess.execute(stmt_l).all()
                        session_orm = local_sess
                        model_cls = DurumKaydi
                except Exception as ex_l:
                    logger.debug(f"SQLite yedek sorgu hatası: {ex_l}")

            for r in rows:
                st_name = r.istasyon_adi
                if not st_name or st_name.lower() == 'auto' or st_name.startswith('LAPTOP-') or st_name.startswith('DESKTOP-'):
                    st_name = default_st

                w_tuple = station_worker_map.get(st_name)
                w_id = w_tuple[0] if w_tuple else None
                if st_name and st_name.startswith('VIDEO:'):
                    clean_vid_name = st_name.replace('VIDEO: ', '').strip()
                    w_name = f"Video: {clean_vid_name}"
                else:
                    w_name = w_tuple[1] if w_tuple else None

                # Eğer istasyon haritasında çalışan bulunamadıysa DurumKaydi veya GunlukOzet'teki kaydedilmiş adı sorgula
                if not w_name or w_name in ['Atanmamış Çalışan', 'Bilinmeyen Çalışan']:
                    try:
                        rec_w = session_orm.scalars(
                            select(model_cls.worker_adi).where(
                                model_cls.istasyon_adi == st_name,
                                model_cls.worker_adi.isnot(None),
                                model_cls.worker_adi != '',
                                model_cls.worker_adi != 'Atanmamış Çalışan',
                                model_cls.worker_adi != 'Bilinmeyen Çalışan'
                            ).limit(1)
                        ).first()
                        if rec_w:
                            w_name = rec_w
                    except Exception:
                        pass

                if not w_name:
                    w_name = 'Atanmamış Çalışan'
                tarih_val = r.tarih or ''
                toplam = r.toplam_kayit or 0

                dur_info = _calculate_worker_durations(
                    session_orm,
                    worker_id=w_id,
                    worker_name=w_name if w_id else '',
                    start_date=tarih_val,
                    end_date=tarih_val,
                    istasyon=st_name,
                    save_interval=save_interval,
                    model_cls=model_cls
                )

                aktif_sec = dur_info['aktif_sec']
                kaynak_sec = dur_info.get('kaynak_sec', 0)
                inaktif_sec = dur_info['inaktif_sec']
                telefon_sec = dur_info['telefon_sec']
                toplam_sec = dur_info['toplam_sec'] or (toplam * save_interval)

                aktif_min = round(aktif_sec / 60.0, 1)
                kaynak_min = round(kaynak_sec / 60.0, 1)
                inaktif_min = round(inaktif_sec / 60.0, 1)

                uretim_sec = aktif_sec + kaynak_sec
                rate = round((uretim_sec / toplam_sec * 100), 1) if toplam_sec > 0 else 0.0

                ilk_raw = str(r.ilk_gorulme) if r.ilk_gorulme else ''
                son_raw = str(r.son_gorulme) if r.son_gorulme else ''
                ilk_str = ilk_raw.replace('T', ' ')[:19] if ilk_raw else '—'
                son_str = son_raw.replace('T', ' ')[:19] if son_raw else '—'

                aktif_fmt = format_duration_tr(aktif_sec)
                kaynak_fmt = format_duration_tr(kaynak_sec)
                inaktif_fmt = format_duration_tr(inaktif_sec)
                telefon_fmt = format_duration_tr(telefon_sec)

                workers_data.append({
                    'tarih': tarih_val,
                    'tarih_fmt': _format_date_tr(tarih_val),
                    'istasyon_adi': st_name,
                    'worker_id': w_id,
                    'worker_adi': w_name,
                    'toplam_kayit': toplam,
                    'toplam_sure_sec': toplam_sec,
                    'toplam_sure_min': round(toplam_sec / 60.0, 1),
                    'aktif_kayit': r.aktif_kayit or 0,
                    'aktif_sure_sec': aktif_sec,
                    'aktif_sure_min': aktif_min,
                    'aktif_sure_fmt': aktif_fmt,
                    'aktif_saat': round(aktif_min / 60.0, 2),
                    'kaynak_kayit': getattr(r, 'kaynak_kayit', 0) or 0,
                    'kaynak_sure_sec': kaynak_sec,
                    'kaynak_sure_min': kaynak_min,
                    'kaynak_sure_fmt': kaynak_fmt,
                    'kaynak_saat': round(kaynak_min / 60.0, 2),
                    'inaktif_kayit': r.inaktif_kayit or 0,
                    'inaktif_sure_sec': inaktif_sec,
                    'inaktif_sure_min': inaktif_min,
                    'inaktif_sure_fmt': inaktif_fmt,
                    'inaktif_saat': round(inaktif_min / 60.0, 2),
                    'telefon_sure_sec': telefon_sec,
                    'telefon_sure_fmt': telefon_fmt,
                    'aktif_oran': rate,
                    'verimlilik_orani': rate,
                    'ilk_gorulme': ilk_str,
                    'son_gorulme': son_str
                })
    except Exception as e:
        logger.error(f"get_worker_stats_rows hatası: {e}")
    return workers_data

