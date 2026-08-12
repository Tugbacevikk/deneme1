"""
reports.py - Raporlama ve Analiz Rotaları (Blueprint)
Orijinal app.py içerisindeki tüm ORM sorgularını ve rapor hesaplama algoritmalarını 1:1 korur.
"""
import datetime
import logging
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from sqlalchemy import select, func, case, and_, or_, desc, String
from core.database.models import DurumKaydi, Worker, Alarm, User
from core.database.connection import db_manager
from web.helpers import (
    get_current_patron_access, get_current_patron_id,
    format_duration_tr, _format_date_tr,
    login_required,
)
from web.services.report_service import (
    _calculate_worker_durations, _build_orm_filters, _get_reports_db_context,
)

reports_bp = Blueprint('reports', __name__)
logger = logging.getLogger(__name__)


def _get_app_config():
    from web.app import config
    return config


@reports_bp.route('/reports')
@login_required
def reports():
    stations_set = {'Istasyon-1', 'Istasyon-2', 'Istasyon-3', 'Istasyon-4'}
    try:
        with db_manager.get_session() as session_orm:
            stmt = select(DurumKaydi.istasyon_adi).where(DurumKaydi.istasyon_adi.isnot(None)).distinct()
            for s in session_orm.scalars(stmt).all():
                if s and not s.startswith('VIDEO:') and not s.startswith('LAPTOP-') and not s.startswith('DESKTOP-'):
                    stations_set.add(s.strip())
            for s in session_orm.scalars(select(Worker.istasyon_adi).where(Worker.istasyon_adi.isnot(None)).distinct()).all():
                if s and not s.startswith('VIDEO:'):
                    stations_set.add(s.strip())
    except Exception:
        pass
    stations = sorted(list(stations_set))
    return render_template('reports.html', stations=stations)


@reports_bp.route('/worker_analysis')
@reports_bp.route('/reports/worker_detail_page')
@login_required
def worker_detail_page():
    return render_template('worker_detail_page.html')


@reports_bp.route('/api/reports/summary', methods=['GET'])
@login_required
def api_reports_summary():
    """Özet rapor istatistiklerini ORM ile hesaplar."""
    start    = request.args.get('start', '')
    end      = request.args.get('end', '')
    istasyon = request.args.get('istasyon', '')
    worker   = request.args.get('worker', '')

    config = _get_app_config()
    save_interval = config.get('save_interval', 5)
    patron_id, is_super = get_current_patron_id()

    try:
        with _get_reports_db_context(config) as (session_orm, model_cls):
            filters = _build_orm_filters(start, end, istasyon, worker=worker, patron_id=patron_id, model_cls=model_cls)


            # Toplam Aktif Kayıt Sayısı
            stmt_aktif = select(func.count(model_cls.id)).where(model_cls.durum.like('AKT%'))
            # Toplam Kaynak Kayıt Sayısı
            stmt_kaynak = select(func.count(model_cls.id)).where(model_cls.durum.like('%KAYNAK%'))
            # Toplam İnaktif Kayıt Sayısı
            stmt_inaktif = select(func.count(model_cls.id)).where(model_cls.durum.like('%NAKT%'))

            if filters:
                stmt_aktif = stmt_aktif.where(and_(*filters))
                stmt_kaynak = stmt_kaynak.where(and_(*filters))
                stmt_inaktif = stmt_inaktif.where(and_(*filters))

            aktif_cnt = session_orm.scalar(stmt_aktif) or 0
            kaynak_cnt = session_orm.scalar(stmt_kaynak) or 0
            inaktif_cnt = session_orm.scalar(stmt_inaktif) or 0

            # Toplam Alarm
            with db_manager.get_session() as local_session:
                stmt_alarm = select(func.count(Alarm.id))
                alarm_filters = []
                alarm_zaman_expr = func.cast(Alarm.zaman, String)
                if start: alarm_filters.append(func.substr(alarm_zaman_expr, 1, 10) >= start)
                if end: alarm_filters.append(func.substr(alarm_zaman_expr, 1, 10) <= end)
                if istasyon: alarm_filters.append(Alarm.istasyon_adi == istasyon)
                if alarm_filters:
                    stmt_alarm = stmt_alarm.where(and_(*alarm_filters))
                toplam_alarm = local_session.scalar(stmt_alarm) or 0
                
                stmt_workers = select(func.count(Worker.id)).where(Worker.aktif == 1)
                if patron_id is not None:
                    stmt_workers = stmt_workers.where(Worker.patron_id == patron_id)
                toplam_calisan = local_session.scalar(stmt_workers) or 0

        aktif_sure_dk = round((aktif_cnt * save_interval) / 60.0, 1)
        kaynak_sure_dk = round((kaynak_cnt * save_interval) / 60.0, 1)
        inaktif_sure_dk = round((inaktif_cnt * save_interval) / 60.0, 1)
        toplam_sure_dk = aktif_sure_dk + kaynak_sure_dk + inaktif_sure_dk
        verimlilik = round(((aktif_sure_dk + kaynak_sure_dk) / toplam_sure_dk * 100), 1) if toplam_sure_dk > 0 else 0.0

        return jsonify({
            'toplam_calisan': toplam_calisan,
            'aktif_sure_dk': aktif_sure_dk,
            'kaynak_sure_dk': kaynak_sure_dk,
            'inaktif_sure_dk': inaktif_sure_dk,
            'verimlilik_orani': verimlilik,
            'toplam_alarm': toplam_alarm,
            'aktif_kayit': aktif_cnt,
            'kaynak_kayit': kaynak_cnt,
            'inaktif_kayit': inaktif_cnt,
            'aktif_alarm': toplam_alarm,
            'aktif_oran': verimlilik,
            'alarm_count': toplam_alarm,
        })
    except Exception as e:
        logger.error(f"Özet rapor hatası (ORM): {e}")
        return jsonify({'error': str(e)}), 500


@reports_bp.route('/api/reports/chart_data', methods=['GET'])
@reports_bp.route('/api/reports/hourly', methods=['GET'])
@login_required
def api_reports_hourly():
    """Saatlik aktif/inaktif dağılımını 24 saatlik eksiksiz etiketlerle ORM ile döndürür."""
    start    = request.args.get('start', request.args.get('date', datetime.date.today().isoformat()))
    end      = request.args.get('end', '')
    istasyon = request.args.get('istasyon', '')
    patron_id, is_super = get_current_patron_id()
    config = _get_app_config()

    hourly_map = {f"{h:02d}:00": {"aktif": 0, "inaktif": 0} for h in range(24)}

    try:
        with _get_reports_db_context(config) as (session_orm, model_cls):
            filters = _build_orm_filters(start, end, istasyon, patron_id=patron_id, model_cls=model_cls)
            zaman_str_expr = func.cast(model_cls.zaman, String)
            saat_col = func.substr(zaman_str_expr, 12, 2)

            stmt = select(
                saat_col.label('saat'),
                func.sum(case((model_cls.durum.like('AKT%'), 1), else_=0)).label('aktif'),
                func.sum(case((model_cls.durum.like('%NAKT%'), 1), else_=0)).label('inaktif')
            )
            if filters:
                stmt = stmt.where(and_(*filters))

            stmt = stmt.group_by(saat_col).order_by(saat_col)
            rows = session_orm.execute(stmt).all()

            save_interval = config.get('save_interval', 5)
            for r in rows:
                if r.saat and str(r.saat).isdigit():
                    hour_key = f"{int(r.saat):02d}:00"
                    if hour_key in hourly_map:
                        hourly_map[hour_key]["aktif"] = round(((r.aktif or 0) * save_interval) / 60.0, 1)
                        hourly_map[hour_key]["inaktif"] = round(((r.inaktif or 0) * save_interval) / 60.0, 1)

        labels  = list(hourly_map.keys())
        aktif   = [hourly_map[k]["aktif"] for k in labels]
        inaktif = [hourly_map[k]["inaktif"] for k in labels]

        return jsonify({'labels': labels, 'aktif': aktif, 'inaktif': inaktif})
    except Exception as e:
        logger.error(f"Grafik verisi hatası (ORM): {e}")
        labels = [f"{h:02d}:00" for h in range(24)]
        return jsonify({'labels': labels, 'aktif': [0]*24, 'inaktif': [0]*24, 'error': str(e)})


@reports_bp.route('/api/reports/data', methods=['GET'])
@reports_bp.route('/api/reports/worker_stats', methods=['GET'])
@login_required
def api_reports_worker_stats():
    """Çalışanların günlük bazda çalışma süreleri ve detaylarını ORM ile döndürür."""
    start    = request.args.get('start', '')
    end      = request.args.get('end', '')
    istasyon = request.args.get('istasyon', '')
    worker   = request.args.get('worker', '')
    patron_id, is_super = get_current_patron_id()
    config = _get_app_config()

    try:
        from web.services.report_service import get_worker_stats_rows
        workers_data = get_worker_stats_rows(start, end, istasyon, worker, patron_id, config)
        return jsonify({'workers': workers_data, 'data': workers_data})
    except Exception as e:
        logger.error(f"Worker stats API hatası: {e}")
        return jsonify({'workers': [], 'data': [], 'error': str(e)})


def _get_pdf_font():
    """Türkçe karakterleri (ç, ğ, ı, ö, ş, ü) destekleyen TrueType fontu yükler."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import os

    font_name = 'TR-Font'
    font_bold = 'TR-Font-Bold'

    try:
        pdfmetrics.getFont(font_name)
        pdfmetrics.getFont(font_bold)
        return font_name, font_bold
    except Exception:
        pass

    font_paths = [
        # Windows
        (os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'arial.ttf'),
         os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'arialbd.ttf')),
        (os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'segoeui.ttf'),
         os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'segoeuib.ttf')),
        (os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'tahoma.ttf'),
         os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'tahomabd.ttf')),
        # Linux
        ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
         '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
        ('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
         '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf'),
        # macOS
        ('/Library/Fonts/Arial.ttf', '/Library/Fonts/Arial Bold.ttf'),
        ('/System/Library/Fonts/Supplemental/Arial.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf'),
    ]

    for regular_path, bold_path in font_paths:
        if os.path.exists(regular_path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, regular_path))
                if os.path.exists(bold_path):
                    pdfmetrics.registerFont(TTFont(font_bold, bold_path))
                else:
                    pdfmetrics.registerFont(TTFont(font_bold, regular_path))
                return font_name, font_bold
            except Exception:
                pass

    return 'Helvetica', 'Helvetica-Bold'


def _generate_report_pdf(start='', end='', istasyon='', worker='', patron_id=None) -> bytes:
    """Rapor verilerini PDF (bytes) formatında üretir."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    import io

    from web.services.report_service import get_worker_stats_rows
    rows = get_worker_stats_rows(start, end, istasyon, worker, patron_id)

    font_name, font_bold = _get_pdf_font()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1*cm, rightMargin=1*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TRTitle', parent=styles['Title'], fontName=font_bold, fontSize=16, leading=20, alignment=1)
    norm_style = ParagraphStyle('TRNormal', parent=styles['Normal'], fontName=font_name, fontSize=9, leading=13)
    hdr_style = ParagraphStyle('TRHdr', parent=styles['Normal'], fontName=font_bold, fontSize=8, leading=10, textColor=colors.white, alignment=1)
    cell_style = ParagraphStyle('TRCell', parent=styles['Normal'], fontName=font_name, fontSize=8, leading=10)
    cell_center = ParagraphStyle('TRCellCenter', parent=styles['Normal'], fontName=font_name, fontSize=8, leading=10, alignment=1)

    elements = []
    elements.append(Paragraph("Çalışan Çalışma Saatleri Raporu", title_style))
    elements.append(Spacer(1, 0.3*cm))

    tarih_araligi = f"{start or 'Tüm Zamanlar'} — {end or 'Tüm Zamanlar'}"
    elements.append(Paragraph(f"<b>Tarih Aralığı:</b> {tarih_araligi}", norm_style))
    if istasyon:
        elements.append(Paragraph(f"<b>İstasyon:</b> {istasyon}", norm_style))
    if worker:
        elements.append(Paragraph(f"<b>Çalışan Filtresi:</b> {worker}", norm_style))
    elements.append(Spacer(1, 0.4*cm))

    headers = ['Tarih', 'Çalışan', 'İstasyon', 'Vardiya Başı', 'Vardiya Bitişi', 'Aktif Süre', 'Hareketsiz Süre', 'Verimlilik']
    hdr_row = [Paragraph(f"<b>{h}</b>", hdr_style) for h in headers]
    table_data = [hdr_row]

    for r in rows:
        table_data.append([
            Paragraph(r.get('tarih_fmt', r.get('tarih', '')), cell_center),
            Paragraph(r.get('worker_adi', ''), cell_style),
            Paragraph(r.get('istasyon_adi', ''), cell_center),
            Paragraph(r.get('ilk_gorulme', ''), cell_center),
            Paragraph(r.get('son_gorulme', ''), cell_center),
            Paragraph(r.get('aktif_sure_fmt', ''), cell_center),
            Paragraph(r.get('inaktif_sure_fmt', ''), cell_center),
            Paragraph(f"%{r.get('aktif_oran', 0)}", cell_center)
        ])

    col_widths = [2.2*cm, 3.2*cm, 2.3*cm, 3.0*cm, 3.0*cm, 2.0*cm, 2.2*cm, 1.6*cm]
    t = Table(table_data, repeatRows=1, colWidths=col_widths)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1F2937')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#D1D5DB')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F9FAFB')]),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


@reports_bp.route('/api/reports/export_pdf', methods=['GET'])
@login_required
def api_reports_export_pdf():
    import io
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    istasyon = request.args.get('istasyon', '')
    worker = request.args.get('worker', '')
    patron_id, is_super = get_current_patron_id()

    pdf_bytes = _generate_report_pdf(start, end, istasyon, worker, patron_id)
    buffer = io.BytesIO(pdf_bytes)

    from flask import send_file
    filename = f"calisan_raporu_{start or 'tum'}_{end or 'zamanlar'}.pdf"
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=filename)


@reports_bp.route('/api/reports/email_pdf', methods=['POST'])
@login_required
def api_reports_email_pdf():
    data = request.get_json() or {}
    to_email = data.get('email', '').strip()
    if not to_email or '@' not in to_email:
        return jsonify({'success': False, 'message': 'Geçerli bir e-posta adresi girin.'}), 400

    start = data.get('start', '')
    end = data.get('end', '')
    istasyon = data.get('istasyon', '')
    worker = data.get('worker', '')
    patron_id, is_super = get_current_patron_id()

    pdf_bytes = _generate_report_pdf(start, end, istasyon, worker, patron_id)
    filename = f"calisan_raporu_{start or 'tum'}_{end or 'zamanlar'}.pdf"
    tarih_araligi = f"{start or 'başlangıç'} — {end or 'bitiş'}"

    from web.services.mail_service import send_pdf_report
    ok, msg = send_pdf_report(
        to_email, pdf_bytes, filename,
        subject=f"Çalışan Raporu ({tarih_araligi})",
        body=f"Ekte {tarih_araligi} tarih aralığına ait çalışan raporu yer almaktadır."
    )
    return jsonify({'success': ok, 'message': msg}), (200 if ok else 500)




@reports_bp.route('/api/reports/worker_detail', methods=['GET'])
@login_required
def api_reports_worker_detail():
    """Belirli bir çalışanın detaylı zaman, grafik ve durum kayıtlarını ORM ile döndürür."""
    worker_id   = request.args.get('worker_id')
    worker_name = request.args.get('worker_name', '')
    istasyon    = request.args.get('istasyon', '')
    start       = request.args.get('start', '')
    end         = request.args.get('end', '')

    config = _get_app_config()
    save_interval = config.get('save_interval', 5)

    try:
        with _get_reports_db_context(config) as (session_orm, model_cls):
            # 1. Worker Bilgilerini Oku
            worker_obj = None
            with db_manager.get_session() as local_session:
                if worker_id and str(worker_id).isdigit() and int(worker_id) > 0:
                    worker_obj = local_session.get(Worker, int(worker_id))
                if not worker_obj and worker_name:
                    stmt_w = select(Worker).where(or_(
                        Worker.ad.like(f"%{worker_name}%"),
                        Worker.soyad.like(f"%{worker_name}%")
                    ))
                    worker_obj = local_session.scalars(stmt_w).first()
                if not worker_obj and istasyon:
                    stmt_w = select(Worker).where(Worker.istasyon_adi == istasyon, Worker.aktif == 1)
                    worker_obj = local_session.scalars(stmt_w).first()

            patron_id, is_super = get_current_patron_id()
            if not is_super and patron_id:
                has_access = False
                with db_manager.get_session() as local_session:
                    u = local_session.get(User, patron_id)
                    assigned_stations = [s.strip() for s in (u.istasyonlar or '').split(',') if s.strip()]
                    if worker_obj and worker_obj.patron_id == patron_id:
                        has_access = True
                    elif istasyon and istasyon in assigned_stations:
                        has_access = True
                    elif worker_obj and worker_obj.istasyon_adi in assigned_stations:
                        has_access = True

                if not has_access:
                    return jsonify({'success': False, 'message': 'Bu çalışanın raporlarını görüntüleme yetkiniz yoktur.'}), 403

            full_name = f"{worker_obj.ad} {worker_obj.soyad}".strip() if worker_obj else (worker_name or 'Bilinmeyen Çalışan')
            sicil_no  = worker_obj.sicil_no if worker_obj and worker_obj.sicil_no else 'EMP-001'
            departman = worker_obj.departman if worker_obj and worker_obj.departman else 'Üretim'
            photo_url = f"/static/workers/{worker_obj.id}.jpg" if worker_obj else None

            w_id_target = worker_obj.id if worker_obj else worker_id

            if not istasyon and worker_obj and worker_obj.istasyon_adi:
                istasyon = worker_obj.istasyon_adi

            filters_k = _build_orm_filters(start, end, istasyon=istasyon, patron_id=patron_id, model_cls=model_cls)

            if istasyon and istasyon.startswith('VIDEO:'):
                pass
            elif w_id_target and str(w_id_target).isdigit() and int(w_id_target) > 0:
                filters_k.append(or_(
                    model_cls.worker_id == int(w_id_target),
                    model_cls.worker_adi == full_name
                ))
            elif full_name and full_name != 'Atanmamış Çalışan' and not full_name.startswith('Video:'):
                filters_k.append(model_cls.worker_adi == full_name)

            stmt_k = select(model_cls).where(and_(*filters_k)).order_by(model_cls.zaman.asc())
            kayitlar = session_orm.scalars(stmt_k).all()

            dur_info = _calculate_worker_durations(
                session_orm,
                worker_id=w_id_target,
                worker_name=full_name,
                start_date=start,
                end_date=end,
                istasyon=istasyon,
                save_interval=save_interval,
                model_cls=model_cls
            )

        aktif_sec = dur_info['aktif_sec']
        kaynak_sec = dur_info.get('kaynak_sec', 0)
        inaktif_sec = dur_info['inaktif_sec']
        telefon_sec = dur_info['telefon_sec']
        toplam_sec = dur_info['toplam_sec'] or (aktif_sec + kaynak_sec + inaktif_sec + telefon_sec)

        telefon_cnt = sum(1 for k in kayitlar if 'TELEFON' in (k.durum or '').upper())
        kaynak_cnt = sum(1 for k in kayitlar if 'KAYNAK' in (k.durum or '').upper())

        recent_records = []
        if kayitlar:
            current_block = None
            for i, k in enumerate(kayitlar):
                z_str = str(k.zaman).replace('T', ' ')[:19]
                dur_lbl = k.durum or 'Bilinmiyor'
                ist_lbl = k.istasyon_adi or 'İstasyon 1'

                try:
                    if isinstance(k.zaman, datetime.datetime):
                        z_dt = k.zaman
                    else:
                        z_dt = datetime.datetime.strptime(z_str, '%Y-%m-%d %H:%M:%S')
                except Exception:
                    z_dt = datetime.datetime.now()

                is_gap_too_large = False
                if i < len(kayitlar) - 1:
                    next_k = kayitlar[i + 1]
                    try:
                        if isinstance(next_k.zaman, datetime.datetime):
                            next_dt = next_k.zaman
                        else:
                            next_dt = datetime.datetime.strptime(str(next_k.zaman).replace('T', ' ')[:19], '%Y-%m-%d %H:%M:%S')
                        gap = int((next_dt - z_dt).total_seconds())
                        is_gap_too_large = (gap > 20)
                        dur_sec = save_interval if is_gap_too_large else (gap if (0 < gap <= 20) else save_interval)
                    except Exception:
                        dur_sec = save_interval
                else:
                    dur_sec = save_interval

                if current_block is None:
                    current_block = {
                        'start_str': z_str,
                        'end_str': z_str,
                        'durum': dur_lbl,
                        'istasyon_adi': ist_lbl,
                        'sure_sec': dur_sec
                    }
                elif current_block['durum'] == dur_lbl and current_block['istasyon_adi'] == ist_lbl and not is_gap_too_large:
                    current_block['end_str'] = z_str
                    current_block['sure_sec'] += dur_sec
                else:
                    t1 = current_block['start_str'][11:16] if len(current_block['start_str']) >= 16 else current_block['start_str']
                    t2 = current_block['end_str'][11:16] if len(current_block['end_str']) >= 16 else current_block['end_str']
                    range_str = f"{t1} - {t2}" if t1 != t2 else t1
                    recent_records.append({
                        'zaman_araligi': range_str,
                        'baslangic': current_block['start_str'],
                        'bitis': current_block['end_str'],
                        'sure_sec': current_block['sure_sec'],
                        'sure_fmt': format_duration_tr(current_block['sure_sec']),
                        'istasyon_adi': current_block['istasyon_adi'],
                        'durum': current_block['durum']
                    })
                    current_block = {
                        'start_str': z_str,
                        'end_str': z_str,
                        'durum': dur_lbl,
                        'istasyon_adi': ist_lbl,
                        'sure_sec': dur_sec
                    }

            if current_block:
                t1 = current_block['start_str'][11:16] if len(current_block['start_str']) >= 16 else current_block['start_str']
                t2 = current_block['end_str'][11:16] if len(current_block['end_str']) >= 16 else current_block['end_str']
                range_str = f"{t1} - {t2}" if t1 != t2 else t1
                recent_records.append({
                    'zaman_araligi': range_str,
                    'baslangic': current_block['start_str'],
                    'bitis': current_block['end_str'],
                    'sure_sec': current_block['sure_sec'],
                    'sure_fmt': format_duration_tr(current_block['sure_sec']),
                    'istasyon_adi': current_block['istasyon_adi'],
                    'durum': current_block['durum']
                })
            recent_records = list(reversed(recent_records))[:100]

        hourly_aktif = [0] * 24
        hourly_kaynak = [0] * 24
        hourly_inaktif = [0] * 24
        hourly_telefon = [0] * 24

        for k in kayitlar:
            try:
                if isinstance(k.zaman, datetime.datetime):
                    h = k.zaman.hour
                else:
                    h = int(str(k.zaman)[11:13])
                st = (k.durum or '').upper()
                if 'TELEFON' in st:
                    hourly_telefon[h] += save_interval
                elif 'KAYNAK' in st:
                    hourly_kaynak[h] += save_interval
                elif 'İNAKTİF' in st or 'INAKTIF' in st or 'NAKT' in st:
                    hourly_inaktif[h] += save_interval
                elif st.startswith('AKT'):
                    hourly_aktif[h] += save_interval
            except Exception:
                pass

        total_calc = max(toplam_sec, 1)
        aktif_pct = round((aktif_sec / total_calc * 100), 1)
        kaynak_pct = round((kaynak_sec / total_calc * 100), 1)
        inaktif_pct = round((inaktif_sec / total_calc * 100), 1)
        telefon_pct = round((telefon_sec / total_calc * 100), 1)

        uretim_sec = aktif_sec + kaynak_sec
        verimlilik_orani = round((uretim_sec / total_calc * 100), 1) if total_calc > 0 else 0.0

        return jsonify({
            'worker_name': full_name,
            'sicil_no': sicil_no,
            'departman': departman,
            'istasyon_adi': istasyon or (worker_obj.istasyon_adi if worker_obj and worker_obj.istasyon_adi else '') or config.get('station_name', 'İstasyon-1'),
            'photo_url': photo_url,
            'aktif_fmt': format_duration_tr(aktif_sec),
            'aktif_pct': aktif_pct,
            'aktif_sec': aktif_sec,
            'kaynak_fmt': format_duration_tr(kaynak_sec),
            'kaynak_count': kaynak_cnt,
            'kaynak_pct': kaynak_pct,
            'kaynak_sec': kaynak_sec,
            'inaktif_fmt': format_duration_tr(inaktif_sec),
            'inaktif_pct': inaktif_pct,
            'inaktif_sec': inaktif_sec,
            'telefon_fmt': format_duration_tr(telefon_sec),
            'telefon_count': telefon_cnt,
            'telefon_sec': telefon_sec,
            'telefon_pct': telefon_pct,
            'verimlilik_orani': verimlilik_orani,
            'recent_records': recent_records,
            'hourly_labels': [f"{h:02d}:00" for h in range(24)],
            'hourly_aktif_min': [round(s / 60.0, 1) for s in hourly_aktif],
            'hourly_kaynak_min': [round(s / 60.0, 1) for s in hourly_kaynak],
            'hourly_inaktif_min': [round(s / 60.0, 1) for s in hourly_inaktif],
            'hourly_telefon_min': [round(s / 60.0, 1) for s in hourly_telefon]
        })
    except Exception as e:
        logger.error(f"Çalışan detay hatası (ORM): {e}")
        return jsonify({'error': str(e)})


@reports_bp.route('/api/cameras/stations', methods=['GET'])
@login_required
def api_camera_stations():
    try:
        stations_set = {'Istasyon-1', 'Istasyon-2', 'Istasyon-3', 'Istasyon-4'}
        with db_manager.get_session() as session_orm:
            stmt = select(DurumKaydi.istasyon_adi).where(DurumKaydi.istasyon_adi.isnot(None)).distinct()
            db_stations = session_orm.scalars(stmt).all()
            for s in db_stations:
                if s and not s.startswith('VIDEO:') and not s.startswith('LAPTOP-') and not s.startswith('DESKTOP-'):
                    stations_set.add(s)
            
            w_stations = session_orm.scalars(select(Worker.istasyon_adi).where(Worker.istasyon_adi.isnot(None)).distinct()).all()
            for s in w_stations:
                if s and not s.startswith('VIDEO:'):
                    stations_set.add(s)

        sorted_list = sorted(list(stations_set))
        return jsonify({'stations': sorted_list, 'success': True})
    except Exception as e:
        return jsonify({'stations': ['Istasyon-1', 'Istasyon-2', 'Istasyon-3', 'Istasyon-4'], 'success': False})
