"""
dashboard.py - Ana Sayfa ve Dashboard Rotaları (Blueprint)
"""
from flask import Blueprint, render_template, session, redirect, url_for
from web.helpers import login_required

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    return redirect(url_for('dashboard.dashboard'))


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')
