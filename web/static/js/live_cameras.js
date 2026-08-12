// web/static/js/live_cameras.js
// Canlı Kameralar sayfası için ayrıştırılmış JavaScript iş mantığı dosyası.

function fetchManagedCameras() {
    const grid = document.getElementById('camera-grid');
    fetch('/api/cameras/manage')
        .then(r => r.json())
        .then(res => {
            if (!res.cameras || res.cameras.length === 0) {
                grid.innerHTML = `
                    <div style="grid-column: 1 / -1; text-align:center; padding:48px 24px; background:#fff; border:1px dashed #CBD5E1; border-radius:12px; color:#64748B;">
                        <i class="fa-solid fa-video-slash" style="font-size:36px; color:#94A3B8; margin-bottom:12px;"></i>
                        <h4 style="margin:0 0 6px 0; color:#1E293B;">Henüz Kamera Eklenmemiş</h4>
                        <p style="margin:0; font-size:13px;">${IS_ADMIN ? 'Yukarıdaki "Yeni Kamera Ekle" butonuna basarak Raspberry Pi 5 IP adresi ekleyebilirsiniz.' : 'Size atanmış aktif bir kamera bulunmamaktadır.'}</p>
                    </div>
                `;
                return;
            }

            renderCameraGrid(res.cameras);
        })
        .catch(err => {
            console.error(err);
            grid.innerHTML = `<div style="grid-column:1/-1; padding:20px; color:#EF4444; background:#FEF2F2; border-radius:8px;">Kameralar yüklenirken hata oluştu.</div>`;
        });
}

function renderCameraGrid(cameras) {
    const grid = document.getElementById('camera-grid');
    grid.innerHTML = '';

    cameras.forEach(cam => {
        const card = document.createElement('div');
        card.id = `cam-card-${cam.id}`;
        card.style.cssText = 'background:#ffffff; border:1px solid #E2E8F0; border-radius:12px; overflow:hidden; box-shadow:0 2px 6px rgba(0,0,0,0.04); display:flex; flex-direction:column; transition:transform 0.2s, box-shadow 0.2s;';

        card.innerHTML = `
            <div style="padding:12px 16px; background:#F8FAFC; border-bottom:1px solid #E2E8F0; display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <h3 style="margin:0; font-size:15px; font-weight:600; color:#1E293B; display:flex; align-items:center; gap:6px;">
                        <span style="width:8px; height:8px; background:#10B981; border-radius:50%; display:inline-block; animation:pulse 1.5s infinite;"></span>
                        <span>${cam.istasyon_adi}</span>
                    </h3>
                    <span style="font-size:11px; color:#64748B;">IP: ${cam.ip_adresi}</span>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                    <button onclick="toggleZoomCard(${cam.id})" title="Büyüt / Tam Ekran" style="background:#fff; border:1px solid #CBD5E1; width:30px; height:30px; border-radius:6px; color:#475569; cursor:pointer; display:inline-flex; align-items:center; justify-content:center;">
                        <i class="fa-solid fa-expand"></i>
                    </button>
                    ${IS_ADMIN ? `
                    <button onclick="deleteManagedCamera(${cam.id})" title="Kamerayı Sil" style="background:#FEF2F2; border:1px solid #FCA5A5; width:30px; height:30px; border-radius:6px; color:#EF4444; cursor:pointer; display:inline-flex; align-items:center; justify-content:center;">
                        <i class="fa-solid fa-trash-can"></i>
                    </button>
                    ` : ''}
                </div>
            </div>

            <div id="feed-wrap-${cam.id}" style="position:relative; width:100%; height:240px; background:#000; overflow:hidden; display:flex; align-items:center; justify-content:center;">
                <div style="color:#94A3B8; display:flex; flex-direction:column; align-items:center; gap:8px;">
                    <i class="fa-solid fa-spinner fa-spin" style="font-size:24px;"></i>
                    <span style="font-size:12px;">Bağlanıyor...</span>
                </div>
            </div>

            <div style="padding:12px 16px; background:#fff; border-top:1px solid #E2E8F0; display:flex; justify-content:space-between; align-items:center;">
                <div style="display:flex; align-items:center; gap:6px;">
                    <i class="fa-solid fa-shield-halved" style="color:#10B981; font-size:13px;"></i>
                    <span style="font-size:12px; font-weight:600; color:#334155;">Yapay Zeka Analizi Aktif</span>
                </div>
                <span style="font-size:11px; color:#94A3B8;">${cam.kayit_tarihi.split(' ')[0]}</span>
            </div>
        `;

        grid.appendChild(card);

        // Yerel mi yoksa uzak mı? Backend'den sor, doğru URL'yi yükle
        fetch(`/api/cameras/is_local/${cam.id}`)
            .then(r => r.json())
            .then(res => {
                const wrap = document.getElementById(`feed-wrap-${cam.id}`);
                if (!wrap) return;

                let streamUrl;
                if (res.is_local) {
                    // Yerel kameranın durumunu kontrol et
                    fetch('/api/camera/status')
                        .then(statusRes => statusRes.json())
                        .then(statusData => {
                            if (statusData.running) {
                                streamUrl = '/api/video_feed';
                                wrap.innerHTML = `<img src="${streamUrl}" alt="${cam.istasyon_adi}" style="width:100%;height:100%;object-fit:contain;" onerror="this.onerror=null;setTimeout(()=>{this.src='${streamUrl}?t='+Date.now();},2000);">`;
                            } else {
                                wrap.innerHTML = `
                                    <div style="color:#94A3B8; display:flex; flex-direction:column; align-items:center; gap:8px;">
                                        <i class="fa-solid fa-video-slash" style="font-size:28px;"></i>
                                        <span style="font-size:12px;">Kamera Başlatılmadı</span>
                                    </div>
                                `;
                            }
                        })
                        .catch(() => {
                            wrap.innerHTML = `
                                <div style="color:#94A3B8; display:flex; flex-direction:column; align-items:center; gap:8px;">
                                    <i class="fa-solid fa-video-slash" style="font-size:28px;"></i>
                                    <span style="font-size:12px;">Bağlantı Hatası</span>
                                </div>
                            `;
                        });
                } else {
                    // Uzak kamera: proxy üzerinden
                    streamUrl = `/api/proxy_feed/${cam.id}`;
                    wrap.innerHTML = `<img src="${streamUrl}" alt="${cam.istasyon_adi}" style="width:100%;height:100%;object-fit:contain;" onerror="this.onerror=null;setTimeout(()=>{this.src='${streamUrl}?t='+Date.now();},2000);">`;
                }
            })
            .catch(() => {
                const wrap = document.getElementById(`feed-wrap-${cam.id}`);
                if (wrap) {
                    const streamUrl = `/api/proxy_feed/${cam.id}`;
                    wrap.innerHTML = `<img src="${streamUrl}" alt="${cam.istasyon_adi}" style="width:100%;height:100%;object-fit:contain;">`;
                }
            });
    });
}

function toggleZoomCard(id) {
    const card = document.getElementById(`cam-card-${id}`);
    if (!card) return;
    const feedWrap = document.getElementById(`feed-wrap-${id}`) || card.querySelector('div[style*="height"]') || card.querySelector('div');
    if (card.classList.contains('zoomed')) {
        card.classList.remove('zoomed');
        card.style.position = 'static';
        card.style.zIndex = '1';
        if (feedWrap) feedWrap.style.height = '240px';
    } else {
        card.classList.add('zoomed');
        card.style.position = 'fixed';
        card.style.top = '20px';
        card.style.left = '20px';
        card.style.width = 'calc(100% - 40px)';
        card.style.height = 'calc(100% - 40px)';
        card.style.zIndex = '10000';
        if (feedWrap) feedWrap.style.height = 'calc(100% - 100px)';
    }
}

async function deleteManagedCamera(id) {
    const ok = await showConfirm('Bu kamerayı silmek istediğinizden emin misiniz?', { title: 'Kamera Sil', okText: 'Sil' });
    if (!ok) return;
    fetch(`/api/cameras/manage/${id}`, { method: 'DELETE' })
        .then(r => r.json())
        .then(res => {
            if (res.success) {
                showToast(res.message || 'Kamera silindi.', 'success');
                fetchManagedCameras();
            } else {
                showToast(res.message || 'Silme hatası.', 'error');
            }
        })
        .catch(err => {
            showToast('Bağlantı hatası.', 'error');
        });
}

// Modal Control
document.addEventListener('DOMContentLoaded', () => {
    fetchManagedCameras();

    const btnAddModal = document.getElementById('btn-add-cam-modal');
    const modal = document.getElementById('modal-add-cam');
    const btnClose = document.getElementById('btn-close-modal');
    const btnCancel = document.getElementById('btn-cancel-modal');
    const formAdd = document.getElementById('form-add-camera');

    function loadSystemStations() {
        fetch('/api/cameras/stations')
            .then(r => r.json())
            .then(data => {
                if (data.stations && data.stations.length > 0) {
                    const sel = document.getElementById('cam-station-name');
                    if (!sel) return;
                    sel.innerHTML = '<option value="">-- İstasyon Seçiniz --</option>';
                    data.stations.forEach(s => {
                        sel.innerHTML += `<option value="${s}">${s}</option>`;
                    });
                }
            }).catch(() => {});
    }

    if (btnAddModal && modal) {
        btnAddModal.addEventListener('click', () => {
            loadSystemStations();
            modal.style.display = 'flex';
        });
        btnClose && btnClose.addEventListener('click', () => modal.style.display = 'none');
        btnCancel && btnCancel.addEventListener('click', () => modal.style.display = 'none');
    }

    if (formAdd) {
        formAdd.addEventListener('submit', (e) => {
            e.preventDefault();
            const data = {
                istasyon_adi: document.getElementById('cam-station-name').value.trim(),
                ip_adresi: document.getElementById('cam-ip-address').value.trim()
            };

            fetch('/api/cameras/manage', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(res => {
                if (res.success) {
                    showToast(res.message || 'Kamera eklendi.', 'success');
                    modal.style.display = 'none';
                    formAdd.reset();
                    fetchManagedCameras();
                } else {
                    showToast(res.message || 'Kamera eklenemedi.', 'error');
                }
            })
            .catch(err => {
                showToast('Bağlantı hatası.', 'error');
            });
        });
    }
});
