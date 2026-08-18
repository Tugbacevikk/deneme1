/*
 * dashboard.js - Dashboard (Ana Ekran) JavaScript Mantığı
 */

function showToast(message, type = 'info') {
    if (window.showToast) {
        window.showToast(message, type);
    } else {
        alert(message);
    }
}

function fetchKPIs() {
    fetch('/api/reports/summary')
        .then(r => r.json())
        .then(data => {
            const alarmCount = (data.alarm_count !== undefined ? data.alarm_count : (data.alarms || 0));
            if (document.getElementById('kpi-alarm-val')) document.getElementById('kpi-alarm-val').textContent = alarmCount;

            const total = (data.active || 0) + (data.inactive || 0);
            const pct = total > 0 ? Math.round((data.active || 0) / total * 100) : 0;
            if (document.getElementById('kpi-fps-sub')) document.getElementById('kpi-fps-sub').textContent = `Aktif: ${pct}%`;
        })
        .catch(() => {});
}

function fetchAlarmBadge() {
    fetch('/api/alarms/unread_count')
        .then(r => r.json())
        .then(data => {
            const c = data.count || data.unread_count || 0;
            const badge = document.getElementById('alarm-count-badge');
            if (badge) { badge.style.display = c > 0 ? 'inline-flex' : 'none'; badge.textContent = c; }
            if (document.getElementById('kpi-alarm-val')) document.getElementById('kpi-alarm-val').textContent = c;
        }).catch(() => {});
}

function fetchQuickAlarms() {
    fetch('/api/alarms?limit=3')
        .then(r => r.json())
        .then(data => {
            const list = document.getElementById('quick-alarm-list');
            if (!list) return;
            const alarms = data.alarms || (Array.isArray(data) ? data : []);
            if (!alarms.length) {
                list.innerHTML = `
                    <div class="quick-alarm-empty" style="padding:15px; text-align:center; color:var(--text-secondary);">
                        <i class="fa-solid fa-check-circle" style="color:var(--green); margin-right:6px;"></i>
                        <span>Henüz alarm kaydı bulunmuyor</span>
                    </div>`;
                return;
            }
            list.innerHTML = alarms.map(a => {
                const atype = (a.alarm_turu || a.type || 'Alarm');
                const isPhone = atype.toLowerCase().includes('telefon');
                const desc = a.aciklama || a.station || a.istasyon_adi || 'Alarm Kaydı';
                const timeStr = a.zaman || a.time || '—';
                return `
                <div class="quick-alarm-item quick-alarm-item--${isPhone ? 'red' : 'orange'}" style="padding:8px 12px; margin-bottom:6px; border-radius:8px; background:var(--bg-secondary); display:flex; align-items:center; justify-content:space-between;">
                    <div style="display:flex; align-items:center; gap:8px;">
                        <i class="fa-solid ${isPhone ? 'fa-phone' : 'fa-triangle-exclamation'}" style="color:${isPhone ? 'var(--red)' : 'var(--orange)'}"></i>
                        <div>
                            <strong style="font-size:12px; display:block;">${atype}</strong>
                            <small style="font-size:11px; color:var(--text-secondary);">${desc}</small>
                        </div>
                    </div>
                    <span style="font-size:11px; color:var(--text-secondary);">${timeStr}</span>
                </div>
            `}).join('');
        }).catch(() => {});
}

function loadUploadedVideos(selectPath = null) {
    return fetch('/api/video/list?t=' + Date.now())
        .then(r => r.json())
        .then(data => {
            const select = document.getElementById('select-uploaded-video');
            if (!select) return;
            const currentVal = select.value;
            if (data.videos && data.videos.length) {
                select.innerHTML = '<option value="">Yüklenen Videolar...</option>' + 
                    data.videos.map(v => `<option value="${v.path}">${v.filename} (${v.size_mb} MB)</option>`).join('');
                
                const target = selectPath || currentVal;
                if (target) {
                    select.value = target;
                    if (!select.value) {
                        const fname = String(target).split('/').pop().split('\\').pop();
                        for (let i = 0; i < select.options.length; i++) {
                            if (select.options[i].value && select.options[i].value.includes(fname)) {
                                select.selectedIndex = i;
                                break;
                            }
                        }
                    }
                }
                if (!select.value && select.options.length > 1) {
                    select.selectedIndex = select.options.length - 1;
                }
            } else {
                select.innerHTML = '<option value="">Yüklenen Video Yok</option>';
            }
        }).catch(() => {});
}

function pollCameraStatus() {
    fetch('/api/camera/status')
        .then(r => r.json())
        .then(data => {
            if (!data) return;

            const feed = document.getElementById('camera-feed');
            const overlay = document.getElementById('camera-overlay');

            if (data.running || data.is_running) {
                if (overlay) overlay.style.display = 'none';
                if (feed) {
                    feed.style.display = 'block';
                    if (!feed.src || !feed.src.includes('/api/video_feed')) {
                        feed.src = '/api/video_feed?' + Date.now();
                    }
                }
            } else {
                if (overlay && feed && feed.src.includes('/api/video_feed')) {
                    feed.src = '';
                    feed.style.display = 'none';
                    overlay.style.display = 'flex';
                }
            }

            if (data.fps !== undefined) {
                if (document.getElementById('kpi-fps-val')) document.getElementById('kpi-fps-val').textContent = parseFloat(data.fps).toFixed(1);
                if (document.getElementById('ms-fps')) document.getElementById('ms-fps').textContent = parseFloat(data.fps).toFixed(1);
            }

            const pCnt = data.kisi_sayisi !== undefined ? data.kisi_sayisi : (data.person_count !== undefined ? data.person_count : (data.worker_name ? 1 : 0));
            if (document.getElementById('ms-kisi')) document.getElementById('ms-kisi').textContent = pCnt;

            const stationName = data.istasyon || data.station || '—';
            if (document.getElementById('ms-station')) document.getElementById('ms-station').textContent = stationName;

            const curDurum = data.durum || data.status;
            if (curDurum) {
                const statusText = document.getElementById('status-text-big');
                if (statusText) statusText.textContent = curDurum;

                const statusCircle = document.getElementById('status-circle');
                const statusIcon = document.getElementById('status-circle-icon');
                if (statusCircle) {
                    const st = curDurum.toLowerCase();
                    statusCircle.className = 'status-circle status-circle--' +
                        (st.includes('aktif') || st.includes('active') || st.includes('çalışıyor') ? 'active' :
                         st.includes('alarm') || st.includes('telefon') || st.includes('inaktif') ? 'alarm' : 'idle');
                    if (statusIcon) {
                        if (st.includes('aktif') || st.includes('active') || st.includes('çalışıyor')) {
                            statusIcon.className = 'fa-solid fa-person-walking';
                        } else if (st.includes('telefon') || st.includes('alarm')) {
                            statusIcon.className = 'fa-solid fa-phone';
                        } else {
                            statusIcon.className = 'fa-solid fa-person';
                        }
                    }
                }
            }

            const updateElem = document.getElementById('last-update-time');
            if (updateElem) {
                updateElem.textContent = data.zaman || data.last_update || new Date().toLocaleTimeString('tr-TR');
            }
        }).catch(() => {});
}

function loadCameraSelect() {
    fetch('/api/camera/list')
        .then(r => r.json())
        .then(data => {
            const select = document.getElementById('cam-select');
            if (!select) return;
            const cams = data.cameras || data.camera_list || [];
            if (cams.length > 0) {
                const currentVal = select.value;
                select.innerHTML = cams.map(c => 
                    `<option value="${c.id}" ${c.id == currentVal ? 'selected' : ''}>${c.name || ('Kamera ' + c.id)}</option>`
                ).join('');
            } else {
                select.innerHTML = '<option value="0">Kamera 0 (Varsayılan WebCam)</option>';
            }
        })
        .catch(() => {
            const select = document.getElementById('cam-select');
            if (select) select.innerHTML = '<option value="0">Kamera 0 (Varsayılan WebCam)</option>';
        });
}

document.addEventListener('DOMContentLoaded', () => {
    fetchKPIs();
    setInterval(fetchKPIs, 30000);
    fetchAlarmBadge();
    fetchQuickAlarms();
    loadCameraSelect();
    loadUploadedVideos();
    pollCameraStatus();
    setInterval(pollCameraStatus, 2000);

    const tabCam = document.getElementById('tab-mode-camera');
    const tabVid = document.getElementById('tab-mode-video');
    const groupCam = document.getElementById('ctrl-group-camera');
    const groupVid = document.getElementById('ctrl-group-video');

    if (tabCam && tabVid) {
        tabCam.addEventListener('click', () => {
            tabCam.style.background = 'var(--card-bg, #fff)';
            tabCam.style.color = 'var(--text-primary, #0f172a)';
            tabCam.style.border = '1px solid var(--border-color, #cbd5e1)';
            tabVid.style.background = 'transparent';
            tabVid.style.color = 'var(--text-secondary, #64748b)';
            tabVid.style.border = 'none';

            if (groupCam) groupCam.style.display = 'flex';
            if (groupVid) groupVid.style.display = 'none';

            // Kamera yayını sıfırla
            const feed = document.getElementById('camera-feed');
            if (feed) { feed.src = ''; feed.style.display = 'none'; }
            const ov = document.getElementById('camera-overlay');
            if (ov) ov.style.display = 'flex';
            fetch('/api/camera/stop', { method: 'POST' }).catch(() => {});
        });

        tabVid.addEventListener('click', () => {
            tabVid.style.background = 'var(--card-bg, #fff)';
            tabVid.style.color = 'var(--text-primary, #0f172a)';
            tabVid.style.border = '1px solid var(--border-color, #cbd5e1)';
            tabCam.style.background = 'transparent';
            tabCam.style.color = 'var(--text-secondary, #64748b)';
            tabCam.style.border = 'none';

            if (groupCam) groupCam.style.display = 'none';
            if (groupVid) groupVid.style.display = 'flex';

            // Video yayını sıfırla ve listeyi çek
            const feed = document.getElementById('camera-feed');
            if (feed) { feed.src = ''; feed.style.display = 'none'; }
            const ov = document.getElementById('camera-overlay');
            if (ov) ov.style.display = 'flex';
            fetch('/api/camera/stop', { method: 'POST' }).catch(() => {});
            loadUploadedVideos();
        });
    }

    if (document.getElementById('btn-choose-video')) {
        document.getElementById('btn-choose-video').addEventListener('click', () => {
            document.getElementById('input-video-file').click();
        });
    }

    if (document.getElementById('input-video-file')) {
        document.getElementById('input-video-file').addEventListener('change', function() {
            if (!this.files || !this.files[0]) return;
            const file = this.files[0];
            const formData = new FormData();
            formData.append('video', file);

            const btnChoose = document.getElementById('btn-choose-video');
            btnChoose.disabled = true;
            btnChoose.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Yükleniyor...';

            fetch('/api/video/upload', { method: 'POST', body: formData })
            .then(r => r.json().catch(() => ({ success: false, error: 'Sunucu yanıtı okunamadı' })))
            .then(data => {
                if (data.success) {
                    showToast('Video başarıyla yüklendi!', 'success');
                    loadUploadedVideos(data.video_path || data.filename);
                } else {
                    showToast(data.error || data.message || 'Video yüklenemedi', 'error');
                }
            })
            .catch(e => showToast('Yükleme hatası: ' + e, 'error'))
            .finally(() => {
                btnChoose.disabled = false;
                btnChoose.innerHTML = '<i class="fa-solid fa-upload" style="color:var(--accent);"></i> Video Yükle';
                this.value = '';
            });
        });
    }

    if (document.getElementById('btn-start')) {
        document.getElementById('btn-start').addEventListener('click', function() {
            if (this.dataset.loading === 'true') return;
            this.dataset.loading = 'true';
            const camSelect = document.getElementById('cam-select');
            const camId = camSelect ? camSelect.value : 0;
            this.disabled = true;
            this.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Başlatılıyor...';
            fetch('/api/camera/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ camera_id: parseInt(camId) })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success || data.status === 'ok') {
                    showToast('Kamera başarıyla başlatıldı!', 'success');
                    const ov = document.getElementById('camera-overlay');
                    if (ov) ov.style.display = 'none';
                    const feed = document.getElementById('camera-feed');
                    if (feed) {
                        feed.style.display = 'block';
                        setTimeout(() => {
                            feed.src = '/api/video_feed?' + Date.now();
                        }, 350);
                    }
                } else {
                    showToast(data.message || 'Kamera başlatılamadı', 'error');
                }
            })
            .catch(err => console.error('Camera start error:', err))
            .finally(() => {
                this.disabled = false;
                this.dataset.loading = 'false';
                this.innerHTML = '<i class="fa-solid fa-circle-play"></i> Başlat';
            });
        });
    }

    if (document.getElementById('btn-stop')) {
        document.getElementById('btn-stop').addEventListener('click', function() {
            this.disabled = true;
            this.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Durduruluyor...';
            const feed = document.getElementById('camera-feed');
            if (feed) {
                feed.src = '';
                feed.style.display = 'none';
            }
            const ov = document.getElementById('camera-overlay');
            if (ov) ov.style.display = 'flex';

            fetch('/api/camera/stop', { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                showToast('Kamera durduruldu.', 'info');
            })
            .catch(err => console.error('Camera stop error:', err))
            .finally(() => {
                this.disabled = false;
                this.innerHTML = '<i class="fa-solid fa-circle-stop"></i> Durdur';
            });
        });
    }

    if (document.getElementById('btn-start-video')) {
        document.getElementById('btn-start-video').addEventListener('click', function() {
            if (this.dataset.loading === 'true') return;
            const select = document.getElementById('select-uploaded-video');
            const videoPath = select ? select.value : '';
            if (!videoPath) {
                showToast('Lütfen analiz edilecek bir video seçin.', 'warning');
                return;
            }
            this.dataset.loading = 'true';
            this.disabled = true;
            this.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Başlatılıyor...';
            fetch('/api/camera/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_type: 'video', video_path: videoPath })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showToast('Video analizi başarıyla başlatıldı!', 'success');
                    const ov = document.getElementById('camera-overlay');
                    if (ov) ov.style.display = 'none';
                    const feed = document.getElementById('camera-feed');
                    if (feed) {
                        feed.style.display = 'block';
                        setTimeout(() => {
                            feed.src = '/api/video_feed?' + Date.now();
                        }, 350);
                    }
                } else {
                    showToast(data.message || 'Video analizi başlatılamadı', 'error');
                }
            })
            .catch(err => {
                console.error('Video start error:', err);
                showToast('Hata: ' + err, 'error');
            })
            .finally(() => {
                this.disabled = false;
                this.dataset.loading = 'false';
                this.innerHTML = '<i class="fa-solid fa-robot"></i> Videoyu Analiz Et';
            });
        });
    }

    if (document.getElementById('btn-stop-video')) {
        document.getElementById('btn-stop-video').addEventListener('click', function() {
            this.disabled = true;
            this.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Durduruluyor...';
            const feed = document.getElementById('camera-feed');
            if (feed) {
                feed.src = '';
                feed.style.display = 'none';
            }
            const ov = document.getElementById('camera-overlay');
            if (ov) ov.style.display = 'flex';

            fetch('/api/camera/stop', { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                showToast('Video analizi durduruldu.', 'info');
            })
            .catch(err => console.error('Video stop error:', err))
            .finally(() => {
                this.disabled = false;
                this.innerHTML = '<i class="fa-solid fa-circle-stop"></i> Durdur';
            });
        });
    }

    if (document.getElementById('btn-delete-video')) {
        document.getElementById('btn-delete-video').addEventListener('click', async function() {
            const select = document.getElementById('select-uploaded-video');
            const videoPath = select ? select.value : '';
            if (!videoPath) {
                showToast('Lütfen silinecek bir video seçin.', 'warning');
                return;
            }
            const ok = await showConfirm('Bu videoyu silmek istediğinize emin misiniz?', { title: 'Video Sil', okText: 'Sil' });
            if (!ok) return;

            this.disabled = true;
            fetch('/api/video/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ video_path: videoPath })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showToast('Video başarıyla silindi.', 'success');
                    loadUploadedVideos();
                } else {
                    showToast(data.error || 'Video silinemedi', 'error');
                }
            })
            .catch(err => console.error('Video delete error:', err))
            .finally(() => {
                this.disabled = false;
            });
        });
    }
});
