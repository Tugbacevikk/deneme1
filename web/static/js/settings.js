// web/static/js/settings.js
// Sistem Ayarları (Settings) sayfası için ayrıştırılmış JavaScript iş mantığı dosyası.

// ── General Settings Save ─────────────────────────────────────
const btnSaveGen = document.getElementById('btn-save-general');
if (btnSaveGen) {
    btnSaveGen.addEventListener('click', function() {
        const payload = {
            station_name: document.getElementById('s-station-name').value
        };
        saveSettings(payload, this, 'Genel ayarlar kaydedildi');
    });
}

// ── Generic Save Helper ───────────────────────────────────────
function saveSettings(payload, btn, successMsg) {
    const origHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Kaydediliyor...';

    fetch('/api/settings/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(r => r.json())
    .then(data => {
        if (data.success || data.status === 'ok') {
            showToast(successMsg, 'success');
        } else {
            showToast(data.message || 'Kayıt hatası', 'error');
        }
    })
    .catch(() => showToast('Sunucu bağlantı hatası', 'error'))
    .finally(() => {
        btn.disabled = false;
        btn.innerHTML = origHTML;
    });
}

// ── System Info Fetcher ───────────────────────────────────────
function fetchSystemInfo() {
    fetch('/api/system/info')
        .then(r => r.json())
        .then(data => {
            if (!data) return;
            if (document.getElementById('si-python')) document.getElementById('si-python').textContent = data.python_version || '—';
            if (document.getElementById('si-platform')) document.getElementById('si-platform').textContent = data.platform || '—';
            if (document.getElementById('si-db-size')) document.getElementById('si-db-size').textContent = data.db_size || '—';

            const faceElem = document.getElementById('si-face-lib');
            if (faceElem) {
                faceElem.innerHTML = `<span class="badge badge--success">${data.face_lib || 'YuNet + SFace'}</span>`;
            }

            const camElem = document.getElementById('si-camera-status');
            if (camElem) {
                const isActive = data.camera_status === 'Aktif';
                camElem.innerHTML = `<span class="badge ${isActive ? 'badge--success' : 'badge--outline'}">${data.camera_status || 'Kapalı'}</span>`;
            }

            if (document.getElementById('si-last-update')) document.getElementById('si-last-update').textContent = data.last_update || '—';

            // CPU
            const cpuVal = data.cpu_usage !== undefined ? data.cpu_usage : 0;
            const cpuBar = document.getElementById('si-cpu-bar');
            if (cpuBar) cpuBar.style.width = cpuVal + '%';
            const cpuText = document.getElementById('si-cpu-text');
            if (cpuText) cpuText.textContent = cpuVal + '%';

            // RAM
            const ramVal = data.ram_usage !== undefined ? data.ram_usage : 0;
            const ramBar = document.getElementById('si-ram-bar');
            if (ramBar) ramBar.style.width = ramVal + '%';
            const ramText = document.getElementById('si-ram-text');
            if (ramText) ramText.textContent = ramVal + '%';
        })
        .catch(err => console.error('System info fetch error:', err));
}

const btnRefreshSys = document.getElementById('btn-refresh-sysinfo');
if (btnRefreshSys) {
    btnRefreshSys.addEventListener('click', function() {
        this.disabled = true;
        fetchSystemInfo();
        setTimeout(() => { this.disabled = false; }, 1000);
    });
}

fetchSystemInfo();
setInterval(fetchSystemInfo, 5000);

// ── Kullanıcı Yönetimi (Admin Only) ───────────────────────────
function loadUsers() {
    const tbody = document.getElementById('users-table-tbody');
    if (!tbody) return;

    fetch('/api/users/list')
        .then(r => {
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        })
        .then(data => {
            const users = Array.isArray(data) ? data : (data.users || data.data || []);
            if (!users.length) {
                tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:15px; color:var(--text-secondary);">Kullanıcı bulunamadı.</td></tr>';
                return;
            }

            tbody.innerHTML = users.map(u => {
                const isSuper = u.rol === 'admin' || u.rol === 'super_admin';
                const isPatron = u.rol === 'patron';
                const roleBadgeClass = isSuper ? 'aktif' : (isPatron ? 'inaktif' : 'tolerans');
                const roleLabel = isSuper ? 'Süper Admin' : (isPatron ? 'Patron' : 'Operatör');
                const stStr = u.istasyonlar || (isSuper ? 'Tüm Fabrika' : 'Atanmadı');

                let statusBadge = '';
                if (u.durum === 'bekliyor') {
                    statusBadge = `<span class="status-badge yok" style="background:#FEF3C7; color:#D97706; border:1px solid #FDE68A;">Bekliyor</span>`;
                } else if (u.durum === 'reddedildi') {
                    statusBadge = `<span class="status-badge inaktif">Reddedildi</span>`;
                } else {
                    statusBadge = `<span class="status-badge aktif">Onaylandı</span>`;
                }

                let approveRejectBtns = '';
                if (u.durum === 'bekliyor') {
                    approveRejectBtns = `
                        <button class="btn btn-success" style="padding:4px 8px; font-size:12px; margin-right:4px;"
                            onclick="approveUser(${u.id})">
                            <i class="fa-solid fa-user-check"></i> Onayla
                        </button>
                        <button class="btn btn-danger" style="padding:4px 8px; font-size:12px; margin-right:4px; background:#e11d48; border-color:#e11d48; color:#fff;"
                            onclick="rejectUser(${u.id})">
                            <i class="fa-solid fa-user-xmark"></i> Reddet
                        </button>
                    `;
                }                let editBtn = '';
                if (u.kullanici_adi !== 'admin') {
                    const editButtonHtml = u.durum === 'onaylandi' ? `
                           <button class="btn btn--outline btn--sm" style="padding:4px 8px;font-size:12px;"
                               data-uid="${u.id}"
                               data-uname="${(u.kullanici_adi||'').replace(/"/g,'&quot;')}"
                               data-ufull="${(u.ad_soyad||'').replace(/"/g,'&quot;')}"
                               data-urol="${u.rol}"
                               data-ust="${(u.istasyonlar||'').replace(/"/g,'&quot;')}"
                               onclick="editUserFromBtn(this)">
                               <i class="fa-solid fa-pen"></i> Düzenle
                           </button>
                    ` : '';

                    editBtn = `<div style="display:flex;gap:6px;align-items:center;">
                           ${approveRejectBtns}
                           ${editButtonHtml}
                           <button class="btn btn-danger" style="padding:4px 8px;font-size:12px;"
                               onclick="deleteUser(${u.id},'${u.kullanici_adi}')">
                               <i class="fa-solid fa-trash"></i> Sil
                           </button>
                       </div>`;
                } else {
                    editBtn = '<span style="font-size:11px;color:var(--text-muted);">Ana Sistem Hesabı</span>';
                }
                return `
                    <tr>
                        <td style="font-weight:700;">${u.kullanici_adi}</td>
                        <td>${u.ad_soyad || '—'}</td>
                        <td>${u.firma_adi || 'Fabrika'}</td>
                        <td><span class="badge badge--outline" style="font-size:11px;"><i class="fa-solid fa-industry"></i> ${stStr}</span></td>
                        <td><span class="status-badge ${roleBadgeClass}">${roleLabel}</span></td>
                        <td>${statusBadge}</td>
                        <td>${editBtn}</td>
                    </tr>
                `;
            }).join('');
        })
        .catch(err => {
            console.error('Kullanıcı yükleme hatası:', err);
            tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; padding:15px; color:var(--red);">Kullanıcı listesi yüklenemedi. (Yönetici girişi gereklidir)</td></tr>';
        });
}

function addUserSubmit(e) {
    e.preventDefault();
    const username = document.getElementById('u-username').value.trim();
    const fullname = document.getElementById('u-fullname').value.trim();
    const password = document.getElementById('u-password').value;
    const role     = document.getElementById('u-role').value;

    // Collect checked station checkboxes → comma-separated string
    const checked = Array.from(document.querySelectorAll('input[name="u-station-cb"]:checked')).map(cb => cb.value);
    const stations = checked.join(', ');
    const hiddenStations = document.getElementById('u-stations');
    if (hiddenStations) hiddenStations.value = stations;

    if (!username || !fullname || !password) {
        showToast('Kullanıcı adı, ad soyad ve şifre zorunludur.', 'error');
        return;
    }

    fetch('/api/users/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            kullanici_adi: username,
            username: username,
            ad_soyad: fullname,
            fullname: fullname,
            firma_adi: 'Fabrika',
            company: 'Fabrika',
            sifre: password,
            password: password,
            rol: role,
            role: role,
            istasyonlar: stations,
            stations: stations
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast(data.message || 'Kullanıcı başarıyla eklendi', 'success');
            document.getElementById('form-add-user').reset();
            // Uncheck all checkboxes after reset
            document.querySelectorAll('input[name="u-station-cb"]').forEach(cb => cb.checked = false);
            loadUsers();
        } else {
            showToast(data.message || data.error || 'Hata oluştu', 'error');
        }
    })
    .catch(err => showToast('Bağlantı hatası: ' + err.message, 'error'));
}

const formAddUser = document.getElementById('form-add-user');
if (formAddUser) {
    formAddUser.addEventListener('submit', addUserSubmit);
}

function deleteUser(btn, username) {
    let id = null;
    if (btn && typeof btn === 'object' && btn.dataset) {
        id = btn.dataset.id;
        username = btn.dataset.name;
    } else {
        id = btn;
    }
    if (!confirm(`${username} kullanıcısını silmek istediğinizden emin misiniz?`)) return;

    fetch(`/api/users/${id}/delete`, { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast(data.message || 'Kullanıcı silindi', 'success');
                loadUsers();
            } else {
                showToast(data.message || data.error || 'Silme hatası', 'error');
            }
        });
}

// ── Kullanıcı Düzenle ──────────────────────────────────────────
// Reads data-* attributes from button to avoid string escaping in template literals
function editUserFromBtn(btn) {
    editUser(
        btn.dataset.uid,
        btn.dataset.uname,
        btn.dataset.ufull,
        btn.dataset.urol,
        btn.dataset.ust
    );
}

function editUser(id, username, fullname, rol, istasyonlar) {
    document.getElementById('edit-user-id').value = id;
    document.getElementById('edit-username').value = username;
    document.getElementById('edit-fullname').value = fullname;
    document.getElementById('edit-role').value = rol;
    document.getElementById('edit-password').value = '';

    // Mevcut istasyonları parse edip checkbox'ları işaretle
    const assigned = istasyonlar ? istasyonlar.split(',').map(s => s.trim()).filter(Boolean) : [];
    document.querySelectorAll('input[name="edit-station-cb"]').forEach(cb => {
        cb.checked = assigned.includes(cb.value);
        // Seçili olanları görsel olarak vurgula
        const lbl = cb.closest('label');
        if (cb.checked) {
            lbl.style.background = 'var(--accent-light, #e0e7ff)';
            lbl.style.borderColor = 'var(--accent)';
            lbl.style.color = 'var(--accent)';
            lbl.style.fontWeight = '600';
        } else {
            lbl.style.background = 'var(--bg-card)';
            lbl.style.borderColor = 'var(--border-color)';
            lbl.style.color = '';
            lbl.style.fontWeight = '';
        }
    });

    // Checkbox değişince görsel güncelle
    document.querySelectorAll('input[name="edit-station-cb"]').forEach(cb => {
        cb.onchange = function() {
            const lbl = this.closest('label');
            if (this.checked) {
                lbl.style.background = 'var(--accent-light, #e0e7ff)';
                lbl.style.borderColor = 'var(--accent)';
                lbl.style.color = 'var(--accent)';
                lbl.style.fontWeight = '600';
            } else {
                lbl.style.background = 'var(--bg-card)';
                lbl.style.borderColor = 'var(--border-color)';
                lbl.style.color = '';
                lbl.style.fontWeight = '';
            }
        };
    });

    document.getElementById('modal-edit-user').style.display = 'flex';
}

function closeEditUserModal(event) {
    if (!event || event.target.id === 'modal-edit-user' || event.target.closest('.modal-close') || event.target.closest('.btn-secondary')) {
        document.getElementById('modal-edit-user').style.display = 'none';
    }
}

function saveEditUser() {
    const id       = document.getElementById('edit-user-id').value;
    const fullname = document.getElementById('edit-fullname').value.trim();
    const role     = document.getElementById('edit-role').value;
    const password = document.getElementById('edit-password').value;

    const checkedStations = Array.from(document.querySelectorAll('input[name="edit-station-cb"]:checked'))
        .map(cb => cb.value);
    const stations = checkedStations.join(', ');

    if (!fullname) {
        showToast('Ad Soyad boş bırakılamaz.', 'error');
        return;
    }

    const btn = document.getElementById('btn-save-edit-user');
    const origHTML = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Kaydediliyor...';

    fetch(`/api/users/${id}/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            ad_soyad: fullname,
            rol: role,
            sifre: password,
            istasyonlar: stations,
            stations: stations
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showToast(data.message || 'Kullanıcı güncellendi', 'success');
            document.getElementById('modal-edit-user').style.display = 'none';
            loadUsers();
        } else {
            showToast(data.message || 'Güncelleme hatası', 'error');
        }
    })
    .catch(err => showToast('Sunucu hatası: ' + err.message, 'error'))
    .finally(() => {
        btn.disabled = false;
        btn.innerHTML = origHTML;
    });
}

function approveUser(id) {
    if (!confirm('Bu kullanıcı başvurusunu onaylamak istediğinizden emin misiniz?')) return;
    fetch(`/api/users/${id}/approve`, {
        method: 'POST',
        headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast(data.message || 'Kullanıcı onaylandı', 'success');
                loadUsers();
            } else {
                showToast(data.message || 'Hata oluştu', 'error');
            }
        })
        .catch(() => showToast('Bağlantı hatası', 'error'));
}

function rejectUser(id) {
    if (!confirm('Bu kullanıcı başvurusunu reddetmek istediğinizden emin misiniz?')) return;
    fetch(`/api/users/${id}/reject`, {
        method: 'POST',
        headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                showToast(data.message || 'Kullanıcı reddedildi', 'success');
                loadUsers();
            } else {
                showToast(data.message || 'Hata oluştu', 'error');
            }
        })
        .catch(() => showToast('Bağlantı hatası', 'error'));
}

document.addEventListener('DOMContentLoaded', () => {
    loadUsers();
});
