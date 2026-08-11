"""
web/routes package init
"""
from web.routes.auth import auth_bp
from web.routes.dashboard import dashboard_bp
from web.routes.cameras import cameras_bp
from web.routes.workers import workers_bp
from web.routes.alarms import alarms_bp
from web.routes.reports import reports_bp
from web.routes.settings import settings_bp

__all__ = [
    'auth_bp',
    'dashboard_bp',
    'cameras_bp',
    'workers_bp',
    'alarms_bp',
    'reports_bp',
    'settings_bp'
]
