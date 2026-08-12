"""
İşçi Takip Sistemi - Web Arayüzü (Modüler Flask Blueprint & ORM Mimarisi)
Flask + Flask-SocketIO tabanlı yönetim paneli
Kullanım: python web/app.py
Tarayıcı: http://localhost:5000
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()


# Windows terminal UTF-8 sorunu çözümü
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

import json
import time
import logging
import datetime
import threading
from functools import wraps
from typing import Optional, List, Dict, Any
from pathlib import Path

import cv2
import numpy as np
import yaml

from flask import (
    Flask, render_template, request, jsonify,
    Response, redirect, url_for,
    session, flash,
)
from flask_socketio import SocketIO
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

try:
    from flask_cors import CORS
    HAS_CORS = True
except ImportError:
    HAS_CORS = False

try:
    import ultralytics
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False

# ---------------------------------------------------------------------------
# Yol ayarları ve Core modülleri
# ---------------------------------------------------------------------------
BASE_DIR   = Path(__file__).parent.parent  # proje kökü
CORE_DIR   = BASE_DIR / 'core'
WEB_DIR    = Path(__file__).parent
DB_PATH    = BASE_DIR / 'isci_takip.db'
CONFIG_PATH = BASE_DIR / 'config.yaml'
PHOTOS_DIR  = WEB_DIR / 'static' / 'workers'

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass

for _p in [str(CORE_DIR), str(BASE_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sqlalchemy import select, delete, func, case, and_, or_, desc, String
from core.database.models import Worker, DurumKaydi, Alarm, User, Camera
from core.database.connection import db_manager
from core.camera_manager import CameraProcessor
from web.helpers import login_required, admin_required


try:
    from pg_sync import SenkronThread, veritabanlarini_temizle
    HAS_PG_SYNC = True
except ImportError:
    HAS_PG_SYNC = False
    SenkronThread = None
    veritabanlarini_temizle = None

# ---------------------------------------------------------------------------
# Loglama - UTF-8 handler + 5 MB RotatingFileHandler
# ---------------------------------------------------------------------------
import io as _io
from logging.handlers import RotatingFileHandler

LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

_log_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')

_stream_handler = logging.StreamHandler(
    _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    if hasattr(sys.stdout, 'buffer') else sys.stdout
)
_stream_handler.setFormatter(_log_formatter)

_file_handler = RotatingFileHandler(
    LOGS_DIR / 'web.log',
    maxBytes=5 * 1024 * 1024,
    backupCount=5,
    encoding='utf-8'
)
_file_handler.setFormatter(_log_formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[_stream_handler, _file_handler],
    force=True,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask & SocketIO
# ---------------------------------------------------------------------------
app = Flask(
    __name__,
    template_folder=str(WEB_DIR / 'templates'),
    static_folder=str(WEB_DIR / 'static'),
)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'isci-takip-secret-2024-xK9mP2')
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({'success': False, 'error': 'Yüklenen video dosyası çok büyük! (Maksimum 500 MB yükleyebilirsiniz.)'}), 413
app.config['SESSION_PERMANENT'] = False

from web.extensions import socketio, config, camera_processor, face_recognizer, last_status
import web.extensions as ext

if HAS_CORS:
    CORS(app)
socketio.init_app(app)

def start_camera(cam_id=0):
    """Kamerayı başlatan yardımcı fonksiyon (cameras.py ve dashboard.js tarafından çağrılabilir)."""
    cfg = dict(ext.config)
    cfg['camera_id'] = cam_id
    if ext.camera_processor is None:
        ext.camera_processor = CameraProcessor(
            camera_id=cam_id,
            config=cfg,
            db_path=str(DB_PATH),
            face_recognizer=ext.face_recognizer,
            socketio=socketio,
        )
    else:
        if ext.camera_processor.is_running:
            return True  # Zaten çalışıyor
        ext.camera_processor.camera_id = cam_id
        ext.camera_processor.cfg.update(cfg)
        ext.camera_processor.config.update(cfg)
    return ext.camera_processor.start_camera()


def stop_camera():
    """Kamerayı durduran yardımcı fonksiyon."""
    if ext.camera_processor is not None:
        ext.camera_processor.stop_camera()

# ---------------------------------------------------------------------------
# Modüler Blueprint Kayıtları
# ---------------------------------------------------------------------------
from web.routes.auth import auth_bp
from web.routes.dashboard import dashboard_bp
from web.routes.cameras import cameras_bp
from web.routes.workers import workers_bp
from web.routes.alarms import alarms_bp
from web.routes.reports import reports_bp
from web.routes.settings import settings_bp

app.register_blueprint(auth_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(cameras_bp)
app.register_blueprint(workers_bp)
app.register_blueprint(alarms_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(settings_bp)
logger.info("Modüler Flask Blueprint'leri başarıyla yüklendi ve kaydedildi.")

# ---------------------------------------------------------------------------
# Veritabanı İlklendirme (Code-First ORM)
# ---------------------------------------------------------------------------

def init_db():
    """Tüm ORM modellerini (Code-First) oluşturur ve varsayılan yöneticiyi ekler."""
    db_manager.init_db()
    try:
        with db_manager.get_session() as session_orm:
            admin_user = session_orm.scalars(select(User).where(User.kullanici_adi == 'admin')).first()
            if not admin_user:
                default_admin = User(
                    kullanici_adi='admin',
                    sifre_hash=generate_password_hash('admin123'),
                    ad_soyad='Sözleşmeli Yönetici',
                    rol='admin'
                )
                session_orm.add(default_admin)
                session_orm.commit()
                logger.info("Varsayılan admin kullanıcısı oluşturuldu (admin / admin123).")
            elif admin_user.rol != 'admin':
                admin_user.rol = 'admin'
                session_orm.commit()
        logger.info(f"ORM Veritabanı başlatıldı: {DB_PATH}")
    except Exception as e:
        logger.error(f"Veritabanı ilklendirme hatası: {e}")

# ---------------------------------------------------------------------------
# Yapılandırma
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    'camera_id': 0,
    'camera_width': 1280,
    'camera_height': 720,
    'camera_fps': 30,
    'istasyon_adi': 'auto',
    'roi_x1': 0.12,
    'roi_y1': 0.24,
    'roi_x2': 0.75,
    'roi_y2': 0.85,
    'save_interval': 1,
    'merkezi_db': {
        'aktif': os.getenv('POSTGRES_ENABLED', 'true').lower() in ('true', '1'),
        'host': os.getenv('POSTGRES_HOST', '192.168.30.222'),
        'port': int(os.getenv('POSTGRES_PORT', 5432)),
        'dbname': os.getenv('POSTGRES_DB', 'fabrika_takip'),
        'kullanici': os.getenv('POSTGRES_USER', 'takip_user'),
        'sifre': os.getenv('POSTGRES_PASSWORD', 'admin123'),
        'senkron_araligi_sn': int(os.getenv('POSTGRES_SYNC_INTERVAL', 5)),
        'local_retention_days': int(os.getenv('LOCAL_RETENTION_DAYS', 7)),
        'pg_retention_days': int(os.getenv('PG_RETENTION_DAYS', 30)),
    }
}


# Yapılandırma ve yardımcı fonksiyonlar dosyanın alt bölümündedir.


def generate_frames():
    """MJPEG akış üreteci (CameraProcessor pre-encoded JPEG buffer kullanır)."""
    dark_frame = _get_dark_frame()

    try:
        while True:
            if (
                ext.camera_processor is not None
                and ext.camera_processor.is_running
            ):
                jpeg_bytes = ext.camera_processor.get_current_jpeg()
                if jpeg_bytes is None:
                    # Görüntü henüz kodlanmadıysa ham frame alıp dene
                    raw_frame = ext.camera_processor.get_current_frame()
                    if raw_frame is not None:
                        if raw_frame.shape[1] > 640:
                            target_w = 640
                            target_h = int(640 * raw_frame.shape[0] / raw_frame.shape[1])
                            encode_frame = cv2.resize(raw_frame, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
                        else:
                            encode_frame = raw_frame
                        _, jpeg_buf = cv2.imencode('.jpg', encode_frame, [cv2.IMWRITE_JPEG_QUALITY, 55])
                        jpeg_bytes = jpeg_buf.tobytes()

                if jpeg_bytes is not None:
                    cur_st = ext.camera_processor.get_status()
                    ext.last_status.update(cur_st)
                    ext.last_status['running'] = True

                    yield (
                        b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n'
                    )
                    time.sleep(0.030)
                else:
                    yield (
                        b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' + dark_frame + b'\r\n'
                    )
                    time.sleep(0.050)
            else:
                ext.last_status['running'] = False
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + dark_frame + b'\r\n'
                )
                time.sleep(0.2)
    except (GeneratorExit, ConnectionResetError, BrokenPipeError, OSError):
        pass
    except Exception as e:
        logger.debug(f"Kamera akış üreteç sonlandı: {e}")


def _broadcast_status():
    """Her saniye durum güncellemesi yayınlar."""
    while True:
        try:
            st = _get_current_status()
            socketio.emit('status_update', st)
        except Exception:
            pass
        time.sleep(1.0)


def _get_current_status() -> dict:
    if ext.camera_processor is not None and ext.camera_processor.is_running:
        st = ext.camera_processor.get_current_status()
        ext.last_status.update(st)
        ext.last_status['running'] = True
    else:
        ext.last_status['running'] = False
        ext.last_status['durum'] = 'Kamera Kapalı'
        ext.last_status['status'] = 'Kamera Kapalı'
        ext.last_status['worker_name'] = ''
        ext.last_status['worker_confidence'] = 0.0
        ext.last_status['kisi_sayisi'] = 0
        ext.last_status['person_count'] = 0
        ext.last_status['fps'] = 0.0
    return ext.last_status


@app.context_processor
def inject_user():
    """Tüm şablonlara mevcut kullanıcı bilgisini aktarır."""
    if 'user_id' in session:
        return {
            'current_user': {
                'id': session.get('user_id'),
                'username': session.get('username'),
                'full_name': session.get('full_name'),
                'rol': session.get('role'),
            }
        }
    return {'current_user': None}

# ---------------------------------------------------------------------------
# Video Akış ve Kontrol API Rotaları
# ---------------------------------------------------------------------------

@app.route('/api/video_feed')
@app.route('/video_feed')
@login_required
def video_feed():
    return Response(
        generate_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@app.route('/api/cameras/is_local/<int:cam_id>')
@login_required
def api_is_local_camera(cam_id):
    """Bu kamera ID'si yerel makineye ait mi? Sadece istasyon adı eşleşmesine göre karar verilir."""
    try:
        from core.database.models import Camera
        with db_manager.get_session() as sess:
            cam = sess.get(Camera, cam_id)
            if not cam:
                return jsonify({'is_local': False})
            # Yalnızca istasyon adı eşleşmesi — IP adresi birden fazla ağ kartında çakışabilir
            local_station = (ext.config.get('station_name') or ext.config.get('istasyon_adi') or '').strip().lower()
            cam_station   = (cam.istasyon_adi or '').strip().lower()
            is_local = bool(local_station and cam_station and cam_station == local_station)
            return jsonify({'is_local': is_local, 'cam_id': cam_id, 'ip': cam.ip_adresi, 'station': cam.istasyon_adi})
    except Exception as e:
        logger.error(f"is_local_camera hatası: {e}")
        return jsonify({'is_local': False})


@app.route('/api/camera/status', methods=['GET'])
@app.route('/api/status', methods=['GET'])
@login_required
def api_status():
    return jsonify(_get_current_status())


@app.route('/api/system/info', methods=['GET'])
@app.route('/api/system_info', methods=['GET'])
@login_required
def api_system_info():
    try:
        import platform
        import psutil
        db_size_str = "0 MB"
        if DB_PATH.exists():
            bytes_size = DB_PATH.stat().st_size
            if bytes_size > 1024 * 1024:
                db_size_str = f"{bytes_size / (1024 * 1024):.2f} MB"
            else:
                db_size_str = f"{bytes_size / 1024:.1f} KB"

        cam_status = 'Aktif' if (camera_processor is not None and camera_processor.is_running) else 'Kapalı'
        cpu_pct = round(psutil.cpu_percent(interval=None), 1)
        ram_pct = round(psutil.virtual_memory().percent, 1)

        return jsonify({
            'success': True,
            'python_version': str(sys.version.split()[0]),
            'platform': f"{platform.system()} {platform.release()}",
            'db_size': db_size_str,
            'face_lib': 'YuNet + SFace (Deep Learning)',
            'camera_status': cam_status,
            'last_update': datetime.datetime.now().strftime('%H:%M:%S'),
            'cpu_usage': cpu_pct,
            'ram_usage': ram_pct,
            'opencv_version': str(cv2.__version__),
            'yolo_available': bool(HAS_YOLO),
        })
    except Exception as e:
        logger.error(f"System info error: {e}")
        return jsonify({
            'success': True,
            'python_version': str(sys.version.split()[0]),
            'platform': 'Windows',
            'db_size': 'N/A',
            'face_lib': 'YuNet + SFace',
            'camera_status': 'Kapalı',
            'last_update': datetime.datetime.now().strftime('%H:%M:%S'),
            'cpu_usage': 0,
            'ram_usage': 0,
        })


@app.route('/api/database/cleanup', methods=['POST'])
@admin_required
def api_database_cleanup():
    """Manuel veritabanı temizliği tetikler."""
    if veritabanlarini_temizle is None:
        return jsonify({'success': False, 'message': 'Temizleme modülü yüklü değil.'}), 500

    data = request.get_json() or {}
    merkezi_cfg = config.get('merkezi_db', {})
    local_retention = data.get('local_retention_days', merkezi_cfg.get('local_retention_days', 7))
    pg_retention = data.get('pg_retention_days', merkezi_cfg.get('pg_retention_days', 30))

    try:
        from pg_sync import pg_baglan
        engine = pg_baglan(merkezi_cfg)
        result = veritabanlarini_temizle(
            db_mgr=db_manager,
            engine=engine,
            local_retention_days=int(local_retention),
            pg_retention_days=int(pg_retention)
        )
        msg = f"Temizlik tamamlandı. Yerel SQLite: {result.get('local_deleted', 0)} kayıt, PostgreSQL: {result.get('pg_deleted', 0)} kayıt silindi."
        return jsonify({'success': True, 'message': msg, 'details': result})
    except Exception as e:
        logger.error(f"Manuel veritabanı temizleme hatası: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/camera/list', methods=['GET'])
@app.route('/api/cameras/scan', methods=['GET'])
@login_required
def api_scan_cameras():
    cam_list = scan_cameras()
    return jsonify({'cameras': cam_list, 'camera_list': cam_list})


UPLOAD_VIDEO_DIR = BASE_DIR / 'web' / 'static' / 'uploads' / 'videos'
UPLOAD_VIDEO_DIR.mkdir(parents=True, exist_ok=True)

@app.route('/api/video/upload', methods=['POST'])
@admin_required
def api_upload_video():
    if 'video' not in request.files:
        return jsonify({'success': False, 'error': 'Video dosyası bulunamadı.'}), 400
    file = request.files['video']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'Dosya seçilmedi.'}), 400
    
    ext = Path(file.filename).suffix.lower()
    if ext not in ['.mp4', '.avi', '.mov', '.mkv', '.webm']:
        return jsonify({'success': False, 'error': 'Desteklenmeyen video formatı! (.mp4, .avi, .mov, .mkv, .webm)'}), 400

    # Aynı isimde başka bir videonun önceden yüklenip yüklenmediğini kontrol et (şişmeyi önlemek için)
    safe_name = secure_filename(file.filename).lower()
    if UPLOAD_VIDEO_DIR.exists():
        for f in UPLOAD_VIDEO_DIR.glob('*'):
            if f.name.lower().endswith(f"_{safe_name}"):
                return jsonify({
                    'success': False, 
                    'error': f'"{file.filename}" isimli video zaten sistemde mevcut! Lütfen listeden seçin veya ismini değiştirip tekrar yükleyin.'
                }), 400

    filename = f"video_{int(time.time())}_{secure_filename(file.filename)}"
    save_path = UPLOAD_VIDEO_DIR / filename
    file.save(str(save_path))
    
    return jsonify({
        'success': True,
        'message': 'Video başarıyla yüklendi.',
        'video_path': str(save_path.resolve()),
        'filename': filename
    })


@app.route('/api/video/list', methods=['GET'])
@login_required
def api_list_videos():
    videos = []
    if UPLOAD_VIDEO_DIR.exists():
        for f in UPLOAD_VIDEO_DIR.glob('*'):
            if f.suffix.lower() in ['.mp4', '.avi', '.mov', '.mkv', '.webm']:
                videos.append({
                    'filename': f.name,
                    'path': str(f.resolve()),
                    'size_mb': round(f.stat().st_size / (1024 * 1024), 2)
                })
    return jsonify({'videos': videos})


@app.route('/api/video/delete', methods=['POST', 'DELETE'])
@admin_required
def api_delete_video():
    data = request.get_json() or {}
    filename = data.get('filename') or data.get('video_path')
    if not filename:
        return jsonify({'success': False, 'error': 'Silinecek video dosya adı belirtilmedi.'}), 400

    clean_filename = Path(filename).name
    target_path = UPLOAD_VIDEO_DIR / clean_filename

    if ext.camera_processor and ext.camera_processor.is_running:
        curr_source = str(getattr(ext.camera_processor, 'camera_id', ''))
        if clean_filename in curr_source:
            ext.camera_processor.stop_camera()

    if target_path.exists():
        try:
            target_path.unlink()
            logger.info(f"Video dosyası silindi: {target_path}")
            return jsonify({'success': True, 'message': 'Video başarıyla silindi.'})
        except Exception as e:
            logger.error(f"Video silme hatası: {e}")
            return jsonify({'success': False, 'error': f'Video silinirken hata oluştu: {str(e)}'}), 500
    else:
        return jsonify({'success': False, 'error': 'Video dosyası bulunamadı.'}), 404


@app.route('/api/camera/start', methods=['POST'])
@app.route('/api/cameras/start', methods=['POST'])
@app.route('/api/video/start', methods=['POST'])
@login_required
def api_start_camera():
    data = request.get_json() or {}
    source_type = data.get('source_type', 'camera')
    video_path = data.get('video_path')
    cam_id_raw = data.get('camera_id')

    if source_type == 'video' and video_path:
        target_source = video_path
    else:
        if cam_id_raw is None or cam_id_raw == '':
            target_source = config.get('camera_id', 0)
        else:
            try:
                target_source = int(cam_id_raw)
            except (ValueError, TypeError):
                target_source = str(cam_id_raw)

    from web.helpers import get_current_patron_id
    patron_id, is_super = get_current_patron_id()
    station_override = None
    if not is_super and patron_id:
        try:
            with db_manager.get_session() as session_check:
                u_check = session_check.get(User, patron_id)
                if u_check and u_check.istasyonlar:
                    stations_list = [s.strip() for s in u_check.istasyonlar.split(',') if s.strip()]
                    if stations_list:
                        station_override = stations_list[0]
        except Exception:
            pass

    cfg = dict(config)
    cfg['camera_id'] = target_source
    if station_override:
        cfg['station_name'] = station_override
        cfg['istasyon_adi'] = station_override

    if ext.camera_processor is None:
        ext.camera_processor = CameraProcessor(
            camera_id=target_source,
            config=cfg,
            db_path=str(DB_PATH),
            face_recognizer=ext.face_recognizer,
            socketio=socketio
        )
    else:
        if ext.camera_processor.is_running:
            ext.camera_processor.stop_camera()

        ext.camera_processor.camera_id = target_source
        ext.camera_processor.cfg.update(cfg)
        ext.camera_processor.config.update(cfg)
        if hasattr(ext.camera_processor, '_update_hostname'):
            ext.camera_processor._update_hostname()

    success = ext.camera_processor.start_camera()
    if success:
        label = "Video Dosyası" if source_type == 'video' else f"Kamera {target_source}"
        return jsonify({'success': True, 'message': f'{label} analizi başlatıldı.', 'camera_id': str(target_source)})
    else:
        return jsonify({'success': False, 'message': 'Kaynak başlatılamadı.'}), 400


@app.route('/api/camera/stop', methods=['POST'])
@app.route('/api/cameras/stop', methods=['POST'])
@login_required
def api_stop_camera():
    if ext.camera_processor is not None:
        ext.camera_processor.stop_camera()
    return jsonify({'success': True, 'message': 'Kamera durduruldu.'})


def load_config() -> dict:
    """config.yaml dosyasını okur, yoksa varsayılanı yazar."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            loaded = yaml.safe_load(f) or {}
        merged_merkezi = {**_DEFAULT_CONFIG.get('merkezi_db', {}), **(loaded.get('merkezi_db') or {})}
        ext.config = {**_DEFAULT_CONFIG, **loaded, 'merkezi_db': merged_merkezi}
    else:
        ext.config = dict(_DEFAULT_CONFIG)
        save_config(ext.config)
    return ext.config


def save_config(cfg: dict):
    """Yapılandırmayı config.yaml dosyasına kaydeder."""
    ext.config = cfg
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)
    logger.info("Yapılandırma kaydedildi.")

# ---------------------------------------------------------------------------
# Kamera tarama & Akış Üreteçleri
# ---------------------------------------------------------------------------

def scan_cameras(max_index: int = 5) -> list:
    """Kullanılabilir kameraları tarar ve cihaz detayları listesini döndürür."""
    try:
        return CameraProcessor.scan_cameras(max_index=max_index)
    except Exception as e:
        logger.debug(f"Kamera tarama hatası: {e}")
        return []


def _get_dark_frame() -> bytes:
    from web.helpers import _get_dark_frame as dark_fn
    return dark_fn()

# ---------------------------------------------------------------------------
# Başlatma
# ---------------------------------------------------------------------------

def _print_banner():
    try:
        banner = """
==========================================================
          ISCI TAKIP SISTEMI - Web Arayuzu (ORM)

  Tarayicida acin: http://localhost:5000
  Yerel ag:        http://0.0.0.0:5000

  Durdurmak icin: Ctrl+C
==========================================================
"""
        print(banner)
    except Exception:
        pass


def initialize():
    """Uygulama başlangıç işlemleri."""
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    (WEB_DIR / 'static').mkdir(parents=True, exist_ok=True)
    (WEB_DIR / 'templates').mkdir(parents=True, exist_ok=True)

    ext.config = load_config()
    logger.info("Yapılandırma yüklendi.")

    init_db()
    ext.face_recognizer = None

    try:
        logger.info("YOLO modelleri sunucu açılışında ön-yükleniyor (Sıfır Donma / Sıfır Gecikme)...")
        CameraProcessor.preload_models(ext.config)
    except Exception as e:
        logger.error(f"Modeller ön-yüklenirken hata: {e}")

    broadcast_thread = threading.Thread(
        target=_broadcast_status,
        name='BroadcastThread',
        daemon=True,
    )
    broadcast_thread.start()
    logger.info("Durum yayın iş parçacığı başlatıldı.")

    merkezi_db_cfg = ext.config.get("merkezi_db") or ext.config
    if HAS_PG_SYNC and SenkronThread:
        try:
            istasyon_adi = ext.config.get("station_name") or ext.config.get("istasyon_adi") or "Istasyon-1"
            if not istasyon_adi or str(istasyon_adi).strip().lower() == "auto":
                istasyon_adi = "Istasyon-1"
            senkron_thread = SenkronThread(
                db_mgr=db_manager,
                merkezi_db_cfg=merkezi_db_cfg,
                istasyon_adi=istasyon_adi,
            )
            senkron_thread.start()
            logger.info("Otomatik PostgreSQL senkronizasyon thread'i başlatıldı.")
        except Exception as e:
            logger.error(f"PostgreSQL senkronizasyon başlatılamadı: {e}")

    # Otomatik Kamera Başlatma (Varsayılan olarak kapalıdır, kullanıcı 'Kamerayı Başlat' dediğinde başlar)
    if ext.config.get("auto_start_camera", False):
        try:
            target_source = ext.config.get('camera_id', 0)
            cfg = dict(ext.config)
            ext.camera_processor = CameraProcessor(
                camera_id=target_source,
                config=cfg,
                db_path=str(DB_PATH),
                face_recognizer=ext.face_recognizer,
                socketio=socketio
            )
            if ext.camera_processor.start_camera():
                logger.info(f"Kamera (ID: {target_source}) sistem açılışında otomatik olarak başlatıldı.")
            else:
                logger.warning(f"Kamera (ID: {target_source}) sistem açılışında otomatik başlatılamadı.")
        except Exception as e:
            logger.error(f"Otomatik kamera başlatma hatası: {e}")


if __name__ == '__main__':
    initialize()
    _print_banner()
    socketio.run(
        app,
        host='0.0.0.0',
        port=5000,
        debug=False,
        allow_unsafe_werkzeug=True
    )