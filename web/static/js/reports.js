// web/static/js/reports.js
// Raporlar (Reports) sayfası için ayrıştırılmış JavaScript iş mantığı dosyası.

let allRecords = [];
let workerStatsData = [];
let currentPage = 1;
let pageSize = 20;
let activityChartInst = null;
let summaryChartInst = null;
let workerChartInst = null;
let wdDonutChartInst = null;

// Tarihleri varsayılan olarak bugün yap (Saatiz, sadece YYYY-MM-DD)
function initDates() {
    const elStart = document.getElementById('filter-start');
    const elEnd   = document.getElementById('filter-end');
    if (!elStart || !elEnd) return;
    const allChip = document.querySelector('.btn-chip[data-preset="all"]');
    if (allChip && allChip.classList.contains('active')) return;

    const now = new Date();
    const pad = n => String(n).padStart(2, '0');
    const todayStr = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}`;
    if (!elStart.value && !elEnd.value && !document.querySelector('.btn-chip.active')) {
        elStart.value = todayStr;
        elEnd.value = todayStr;
    }
}

function applyDatePreset(preset) {
    const elStart = document.getElementById('filter-start');
    const elEnd   = document.getElementById('filter-end');
    if (!elStart || !elEnd) return;
    const now = new Date();
    const pad = n => String(n).padStart(2, '0');
    const fmt = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;

    let start = fmt(now);
    let end   = fmt(now);

    if (preset === 'today') {
        start = fmt(now);
        end   = fmt(now);
    } else if (preset === 'week') {
        const day = now.getDay() === 0 ? 7 : now.getDay(); // Pazartesi=1 kabul
        const monday = new Date(now);
        monday.setDate(now.getDate() - (day - 1));
        start = fmt(monday);
        end   = fmt(now);
    } else if (preset === 'month') {
        start = fmt(new Date(now.getFullYear(), now.getMonth(), 1));
        end   = fmt(now);
    } else if (preset === 'all') {
        start = ''; // boş = filtre yok, backend'de tüm kayıtlar dönsün
        end   = '';
    }

    elStart.value = start;
    elEnd.value   = end;

    document.querySelectorAll('.btn-chip').forEach(b => b.classList.remove('active'));
    const targetChip = document.querySelector(`.btn-chip[data-preset="${preset}"]`);
    if (targetChip) targetChip.classList.add('active');

    fetchAll();
}

function buildParams() {
    initDates();
    const elStart   = document.getElementById('filter-start');
    const elEnd     = document.getElementById('filter-end');
    const elStation = document.getElementById('filter-station');
    const elWorker  = document.getElementById('filter-worker');

    const start   = elStart ? elStart.value : '';
    const end     = elEnd ? elEnd.value : '';
    const station = elStation ? elStation.value : '';
    const worker  = elWorker ? elWorker.value : '';

    const p = new URLSearchParams();
    if (start)   p.set('start', start);
    if (end)     p.set('end', end);
    if (station) p.set('istasyon', station);
    if (worker)  p.set('worker', worker);
    return p.toString();
}

function fetchSummary(params) {
    fetch('/api/reports/summary?' + params)
        .then(r => r.json())
        .then(data => {
            const active   = data.aktif_kayit   || 0;
            const inactive = data.inaktif_kayit || 0;
            const alarms   = data.aktif_alarm   || 0;
            const rate     = data.aktif_oran    || 0;

            if (document.getElementById('sum-active')) document.getElementById('sum-active').textContent   = active.toLocaleString('tr-TR') + ' kayıt';
            if (document.getElementById('sum-inactive')) document.getElementById('sum-inactive').textContent = inactive.toLocaleString('tr-TR') + ' kayıt';
            if (document.getElementById('sum-rate')) document.getElementById('sum-rate').textContent     = '%' + rate;
            if (document.getElementById('sum-alarms')) document.getElementById('sum-alarms').textContent   = alarms.toLocaleString('tr-TR');

            if (summaryChartInst) {
                summaryChartInst.data.datasets[0].data = [active, inactive, alarms];
                summaryChartInst.update();
            }
        })
        .catch(err => console.error(err));
}

function fetchWorkerStats(params) {
    const tbody = document.getElementById('worker-stats-tbody');
    if (tbody) {
        tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding:20px; color:var(--text-secondary);"><i class="fa-solid fa-spinner fa-spin"></i> Veriler yükleniyor...</td></tr>`;
    }
    fetch('/api/reports/worker_stats?' + params)
        .then(r => r.json())
        .then(data => {
            workerStatsData = data.workers || data.data || [];
            currentPage = 1;
            renderWorkerStatsTable(workerStatsData);
            if (typeof updateWorkerChart === 'function') {
                updateWorkerChart(workerStatsData);
            }

            let totalActiveSec = 0;
            let totalInactiveSec = 0;
            workerStatsData.forEach(w => {
                totalActiveSec += (w.aktif_sure_sec || (w.aktif_kayit || 0) * 5);
                totalInactiveSec += (w.inaktif_sure_sec || (w.inaktif_kayit || 0) * 5);
            });

            if (document.getElementById('sum-active-time')) document.getElementById('sum-active-time').textContent = formatSec(totalActiveSec);
            if (document.getElementById('sum-inactive-time')) document.getElementById('sum-inactive-time').textContent = formatSec(totalInactiveSec);
        })
        .catch(err => {
            console.error("Worker stats fetch error:", err);
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding:20px; color:var(--red);">Veri yükleme hatası oluştu.</td></tr>`;
            }
        });
}

function formatSec(seconds) {
    if (!seconds || seconds <= 0) return '0 dk';
    const secInt = Math.round(seconds);
    const hrs = Math.floor(secInt / 3600);
    const rem = secInt % 3600;
    const mins = Math.floor(rem / 60);
    const secs = rem % 60;

    let parts = [];
    if (hrs > 0) parts.push(`${hrs} sa`);
    if (mins > 0) parts.push(`${mins} dk`);
    if (secs > 0 && hrs === 0) parts.push(`${secs} sn`);

    return parts.length ? parts.join(' ') : '0 dk';
}

function renderWorkerStatsTable(workers) {
    const tbody = document.getElementById('worker-stats-tbody');
    const totalRecords = workers ? workers.length : 0;

    if (!totalRecords) {
        tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding:20px; color:var(--text-secondary);">Kayıtlı çalışma verisi bulunamadı.</td></tr>`;
        updatePaginationControls(0, 0, 0, 1, 1);
        return;
    }

    const totalPages = Math.ceil(totalRecords / pageSize) || 1;
    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    const startIdx = (currentPage - 1) * pageSize;
    const endIdx = Math.min(startIdx + pageSize, totalRecords);
    const pageWorkers = workers.slice(startIdx, endIdx);

    tbody.innerHTML = pageWorkers.map(w => {
        const aktFmt = w.aktif_sure_fmt || formatSec((w.aktif_kayit || 0) * 5);
        const kynkFmt = w.kaynak_sure_fmt || formatSec(w.kaynak_sure_sec || (w.kaynak_kayit || 0) * 5);
        const inaktFmt = w.inaktif_sure_fmt || formatSec((w.inaktif_kayit || 0) * 5);
        const telFmt = w.telefon_sure_fmt || formatSec(w.telefon_sure_sec || 0);
        const rateVal = w.verimlilik_orani !== undefined ? w.verimlilik_orani : (w.aktif_oran !== undefined ? w.aktif_oran : 0);
        const stName = w.istasyon_adi || 'İstasyon-1';
        const isVideo = stName.startsWith('VIDEO:');
        const cleanStName = isVideo ? stName.replace('VIDEO: ', '') : stName;
        const stHtml = isVideo 
            ? `<span style="display:inline-flex; align-items:center; gap:6px; color:#06B6D4; font-weight:700; max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="Video Analiz Raporu: ${cleanStName}"><i class="fa-solid fa-file-video" style="flex-shrink:0;"></i><span style="overflow:hidden; text-overflow:ellipsis;">${cleanStName}</span></span>` 
            : `<span style="display:inline-flex; align-items:center; gap:6px; max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${stName}"><i class="fa-solid fa-industry" style="margin-right:2px; flex-shrink:0;"></i><span style="overflow:hidden; text-overflow:ellipsis;">${stName}</span></span>`;

        const workerHtml = `<span style="display:inline-flex; align-items:center; gap:6px; max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${w.worker_adi}"><i class="fa-solid fa-user-tie" style="color:var(--text-secondary); margin-right:2px; flex-shrink:0;"></i><span style="overflow:hidden; text-overflow:ellipsis;">${w.worker_adi}</span></span>`;

        return `
        <tr style="cursor:pointer;" 
            data-wid="${w.worker_id || ''}" 
            data-wname="${w.worker_adi || ''}" 
            data-date="${w.tarih || ''}" 
            data-station="${stName}" 
            onclick="openWorkerDetailFromBtn(this)" 
            title="${stName} - ${w.worker_adi} (${w.tarih_fmt || w.tarih}) detaylı grafik ve analizi için tıklayın">
            <td style="font-weight:600; color:var(--text-primary);"><i class="fa-regular fa-calendar" style="color:var(--accent); margin-right:6px;"></i>${w.tarih_fmt || w.tarih}</td>
            <td style="font-weight:700;">${stHtml}</td>
            <td style="font-weight:600;">${workerHtml}</td>
            <td style="font-size:13px; color:var(--text-secondary);">${w.ilk_gorulme || '—'}</td>
            <td style="font-size:13px; color:var(--text-secondary);">${w.son_gorulme || '—'}</td>
            <td style="font-weight:700; color:var(--green);">${aktFmt}</td>
            <td style="font-weight:700; color:#06B6D4;"><i class="fa-solid fa-fire-flame-curved" style="margin-right:4px;"></i>${kynkFmt}</td>
            <td style="color:var(--red);">${inaktFmt}</td>
            <td style="color:var(--orange); font-weight:700;"><i class="fa-solid fa-mobile-screen-button" style="margin-right:4px;"></i>${telFmt}</td>
            <td><span class="status-badge ${rateVal >= 70 ? 'aktif' : 'inaktif'}">%${rateVal}</span></td>
            <td>
                <button class="btn btn-outline" style="padding:4px 10px; font-size:12px; display:inline-flex; align-items:center; gap:6px;" onclick="event.stopPropagation(); openWorkerDetailFromBtn(this.closest('tr'))">
                    <i class="fa-solid fa-chart-pie"></i> Detaylı Analiz & Grafik
                </button>
            </td>
        </tr>
    `;

    }).join('');

    updatePaginationControls(startIdx + 1, endIdx, totalRecords, currentPage, totalPages);
}

function updatePaginationControls(from, to, total, page, totalPages) {
    const elRange = document.getElementById('pagination-range-text');
    const elNum = document.getElementById('pagination-page-num');
    const btnPrev = document.getElementById('btn-page-prev');
    const btnNext = document.getElementById('btn-page-next');

    if (elRange) elRange.textContent = total > 0 ? `${from} - ${to} / ${total}` : '0 - 0 / 0';
    if (elNum) elNum.textContent = `Sayfa ${page} / ${totalPages}`;
    if (btnPrev) btnPrev.disabled = (page <= 1);
    if (btnNext) btnNext.disabled = (page >= totalPages);
}

function goToPrevPage() {
    if (currentPage > 1) {
        currentPage--;
        renderWorkerStatsTable(workerStatsData);
    }
}

function goToNextPage() {
    const totalPages = Math.ceil(workerStatsData.length / pageSize) || 1;
    if (currentPage < totalPages) {
        currentPage++;
        renderWorkerStatsTable(workerStatsData);
    }
}

function changePageSize(val) {
    pageSize = parseInt(val) || 20;
    currentPage = 1;
    renderWorkerStatsTable(workerStatsData);
}

function openWorkerDetailFromBtn(el) {
    if (!el) return;
    const wid = el.getAttribute('data-wid') || '';
    const wname = el.getAttribute('data-wname') || '';
    const date = el.getAttribute('data-date') || '';
    const station = el.getAttribute('data-station') || '';
    openWorkerDetailModal(wid, wname, date, station);
}

function openWorkerDetailModal(workerId, workerName, rowDate, stationName) {
    let start = document.getElementById('filter-start').value;
    let end   = document.getElementById('filter-end').value;

    if (rowDate) {
        start = rowDate;
        end   = rowDate;
    }

    const params = new URLSearchParams();
    if (workerId && workerId !== 'None') params.set('worker_id', workerId);
    if (workerName) params.set('worker_name', workerName);
    if (stationName) params.set('istasyon', stationName);
    if (start) params.set('start', start);
    if (end) params.set('end', end);

    window.location.href = '/reports/worker_detail_page?' + params.toString();
}

function closeWorkerDetailModal() {
    document.getElementById('worker-detail-modal').style.display = 'none';
}

function renderWdDonutChart(aktifMin, inaktifMin, telefonMin) {
    const ctx = document.getElementById('wdDonutChart').getContext('2d');
    if (wdDonutChartInst) wdDonutChartInst.destroy();

    wdDonutChartInst = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Aktif Çalışma (Dk)', 'Hareketsiz Süre (Dk)', 'Telefon Kullanımı (Dk)'],
            datasets: [{
                data: [aktifMin, inaktifMin, telefonMin],
                backgroundColor: ['#10B981', '#EF4444', '#F59E0B'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom', labels: { boxWidth: 12 } }
            },
            cutout: '65%'
        }
    });
}

function fetchAll() {
    const params = buildParams();
    fetchSummary(params);
    fetchWorkerStats(params);
}

// Global click event delegation for preset chips
document.addEventListener('click', function(e) {
    const chip = e.target.closest('.btn-chip');
    if (chip && chip.dataset.preset) {
        applyDatePreset(chip.dataset.preset);
    }
});

const btnFilter = document.getElementById('btn-filter');
if (btnFilter) {
    btnFilter.addEventListener('click', () => {
        document.querySelectorAll('.btn-chip').forEach(b => b.classList.remove('active'));
        fetchAll();
    });
}

const btnResetFilter = document.getElementById('btn-reset-filter');
if (btnResetFilter) {
    btnResetFilter.addEventListener('click', () => {
        const elWorker = document.getElementById('filter-worker');
        const elStation = document.getElementById('filter-station');
        if (elWorker) elWorker.value = '';
        if (elStation) elStation.value = '';
        applyDatePreset('today');
    });
}

// CSV İndir
const btnCsv = document.getElementById('btn-csv');
if (btnCsv) {
    btnCsv.addEventListener('click', () => {
        if (!workerStatsData.length) {
            showToast('İndirilecek veri bulunamadı', 'warning');
            return;
        }

        let csv = "\uFEFF=== ÇALIŞAN GÜNLÜK MESAİ VE ÇALIŞMA SÜRELERİ ÖZETİ ===\n";
        csv += "Tarih,Çalışan Adı,Vardiya Başı (İlk Görülme),Vardiya Bitişi (Son Görülme),Aktif Çalışma Süresi,Hareketsiz Süre,Verimlilik Oranı (%)\n";
        workerStatsData.forEach(w => {
            csv += `"${w.tarih_fmt || w.tarih}","${w.worker_adi}","${w.ilk_gorulme}","${w.son_gorulme}","${w.aktif_sure_fmt}","${w.inaktif_sure_fmt}","%${w.aktif_oran}"\n`;
        });

        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `calisan_calisma_saatleri_raporu_${new Date().toISOString().split('T')[0]}.csv`;
        a.click();
        showToast('Çalışan çalışma saatleri raporu CSV olarak indirildi!', 'success');
    });
}

// PDF İndir
const btnPdf = document.getElementById('btn-pdf');
if (btnPdf) {
    btnPdf.addEventListener('click', () => {
        const params = buildParams();
        window.open('/api/reports/export_pdf?' + params, '_blank');
    });
}

function isValidEmail(email) {
    const re = /^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/;
    return re.test(email);
}

const KNOWN_DOMAINS = [
    'gmail.com', 'googlemail.com',
    'hotmail.com', 'outlook.com', 'live.com', 'msn.com',
    'yahoo.com', 'yahoo.com.tr', 'ymail.com'
];

function levenshtein(a, b) {
    const dp = Array.from({length: a.length + 1}, (_, i) => [i, ...Array(b.length).fill(0)]);
    for (let j = 0; j <= b.length; j++) dp[0][j] = j;
    for (let i = 1; i <= a.length; i++) {
        for (let j = 1; j <= b.length; j++) {
            dp[i][j] = a[i-1] === b[j-1]
                ? dp[i-1][j-1]
                : 1 + Math.min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1]);
        }
    }
    return dp[a.length][b.length];
}

function checkDomainTypo(email) {
    const parts = email.split('@');
    if (parts.length !== 2) return null;
    const domain = parts[1].toLowerCase();
    if (KNOWN_DOMAINS.includes(domain)) return null;
    for (const known of KNOWN_DOMAINS) {
        if (levenshtein(domain, known) <= 2 && domain !== known) {
            return known;
        }
    }
    return null;
}

function parseEmailList(raw) {
    return raw.split(/[,;\n]+/).map(s => s.trim()).filter(s => s.length > 0);
}

const mailInputEl = document.getElementById('mail-input');
if (mailInputEl) {
    mailInputEl.addEventListener('input', () => {
        const errorEl = document.getElementById('mail-input-error');
        if (errorEl) errorEl.style.display = 'none';
        mailInputEl.classList.remove('input-error');
    });
}

let fetchedMailUsers = [];
let activeMailTab = 'all';

function openMailPanel() {
    const modal = document.getElementById('mail-panel-modal');
    if (modal) modal.style.display = 'flex';
    fetchMailUsers();
}

function closeMailPanel(event) {
    if (!event || event.target.id === 'mail-panel-modal' || event.target.closest('.modal-close') || event.target.closest('.btn-secondary')) {
        const modal = document.getElementById('mail-panel-modal');
        if (modal) modal.style.display = 'none';
        const errorEl = document.getElementById('mail-input-error');
        if (errorEl) errorEl.style.display = 'none';
    }
}

function fetchMailUsers() {
    const previewEl = document.getElementById('all-recipients-preview');
    const checklistEl = document.getElementById('recipient-checklist');
    if (previewEl) previewEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Kullanıcılar yükleniyor...';

    fetch('/api/users/with_email')
        .then(r => r.json())
        .then(data => {
            fetchedMailUsers = (data && data.users) ? data.users : [];
            if (!fetchedMailUsers.length) {
                if (previewEl) previewEl.innerHTML = '<span style="color:var(--text-muted);">Sistemde e-postası tanımlı onaylı kullanıcı bulunamadı.</span>';
                if (checklistEl) checklistEl.innerHTML = '<span style="color:var(--text-muted); font-size:13px;">E-postası olan kullanıcı bulunamadı.</span>';
                return;
            }

            if (previewEl) {
                previewEl.innerHTML = fetchedMailUsers.map(u => 
                    `<div style="margin-bottom:4px;"><strong>${u.ad_soyad}</strong> (${u.rol}) — <span style="color:var(--accent);">${u.email}</span></div>`
                ).join('');
            }

            if (checklistEl) {
                checklistEl.innerHTML = fetchedMailUsers.map(u => `
                    <label style="display:flex; align-items:center; gap:8px; font-size:13px; cursor:pointer; padding:6px 10px; border:1px solid var(--border-color); border-radius:6px; background:var(--bg-card);">
                        <input type="checkbox" name="recipient-cb" value="${u.email}" checked style="accent-color:var(--accent);">
                        <span><strong>${u.ad_soyad}</strong> (${u.rol}) — ${u.email}</span>
                    </label>
                `).join('');
            }
        })
        .catch(err => {
            if (previewEl) previewEl.innerHTML = '<span style="color:#DC2626;">Kullanıcı listesi yüklenemedi.</span>';
        });
}

// Tab Switching
const mailModalTabs = document.querySelector('.modal-tabs');
if (mailModalTabs) {
    mailModalTabs.addEventListener('click', function(e) {
        const tabBtn = e.target.closest('.modal-tab');
        if (tabBtn && tabBtn.dataset.tab) {
            activeMailTab = tabBtn.dataset.tab;
            document.querySelectorAll('.modal-tab').forEach(b => {
                b.classList.remove('active');
                b.style.borderBottom = 'none';
                b.style.color = 'var(--text-secondary)';
            });
            tabBtn.classList.add('active');
            tabBtn.style.borderBottom = '2px solid var(--accent)';
            tabBtn.style.color = 'var(--accent)';

            document.querySelectorAll('.tab-panel').forEach(p => p.style.display = 'none');
            const activePanel = document.getElementById('tab-' + activeMailTab);
            if (activePanel) activePanel.style.display = 'block';

            const errorEl = document.getElementById('mail-input-error');
            if (errorEl) errorEl.style.display = 'none';
        }
    });
}

const btnOpenMailPanel = document.getElementById('btn-open-mail-panel');
if (btnOpenMailPanel) {
    btnOpenMailPanel.addEventListener('click', openMailPanel);
}

// Mail Gönder
const btnMailSend = document.getElementById('btn-mail-send');
if (btnMailSend) {
    btnMailSend.addEventListener('click', async () => {
        if (btnMailSend.disabled) return;

        const mailInput = document.getElementById('mail-input');
        const errorEl = document.getElementById('mail-input-error');

        if (errorEl) errorEl.style.display = 'none';
        if (mailInput) mailInput.classList.remove('input-error');

        let emails = [];
        if (activeMailTab === 'all') {
            emails = fetchedMailUsers.map(u => u.email).filter(Boolean);
        } else if (activeMailTab === 'select') {
            emails = Array.from(document.querySelectorAll('input[name="recipient-cb"]:checked'))
                .map(cb => cb.value).filter(Boolean);
        } else if (activeMailTab === 'manual') {
            const rawVal = mailInput ? mailInput.value.trim() : '';
            emails = parseEmailList(rawVal);
        }

        if (emails.length === 0) {
            if (errorEl) {
                errorEl.textContent = 'Lütfen en az bir e-posta adresi girin veya seçin.';
                errorEl.style.display = 'block';
            }
            if (activeMailTab === 'manual' && mailInput) {
                mailInput.classList.add('input-error');
                mailInput.focus();
            }
            return;
        }

        const invalidOnes = emails.filter(e => !isValidEmail(e));
        if (invalidOnes.length > 0) {
            if (errorEl) {
                errorEl.textContent = `Geçersiz adres(ler): ${invalidOnes.join(', ')}`;
                errorEl.style.display = 'block';
            }
            if (activeMailTab === 'manual' && mailInput) {
                mailInput.classList.add('input-error');
                mailInput.focus();
            }
            return;
        }

        for (const addr of emails) {
            const suggestion = checkDomainTypo(addr);
            if (suggestion) {
                if (errorEl) {
                    errorEl.textContent = `"${addr}" adresinde hata olabilir — "${addr.split('@')[0]}@${suggestion}" mi demek istediniz?`;
                    errorEl.style.display = 'block';
                }
                if (activeMailTab === 'manual' && mailInput) {
                    mailInput.classList.add('input-error');
                    mailInput.focus();
                }
                return;
            }
        }

        if (emails.length > 20) {
            if (errorEl) {
                errorEl.textContent = 'Tek seferde en fazla 20 adrese gönderebilirsiniz.';
                errorEl.style.display = 'block';
            }
            return;
        }

        btnMailSend.disabled = true;
        const elStart = document.getElementById('filter-start') ? document.getElementById('filter-start').value : '';
        const elEnd = document.getElementById('filter-end') ? document.getElementById('filter-end').value : '';
        const elStation = document.getElementById('filter-station') ? document.getElementById('filter-station').value : '';
        const elWorker = document.getElementById('filter-worker') ? document.getElementById('filter-worker').value : '';
        try {
            const res = await fetch('/api/reports/email_pdf', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({emails, start: elStart, end: elEnd, istasyon: elStation, worker: elWorker})
            });
            const result = await res.json();
            if (result && Array.isArray(result.results)) {
                const successCount = result.results.filter(r => r.success).length;
                const failCount = result.results.length - successCount;
                showToast(`${successCount} adrese gönderildi${failCount > 0 ? `, ${failCount} adrese gönderilemedi` : ''}`, failCount > 0 ? 'error' : 'success');
                if (result.success) closeMailPanel();
            } else {
                showToast(result.message || 'E-posta gönderildi', result.success ? 'success' : 'error');
                if (result.success) closeMailPanel();
            }
        } catch (e) {
            showToast('Sunucu bağlantı hatası', 'error');
        } finally {
            btnMailSend.disabled = false;
        }
    });
}



function loadStationOptions() {
    const sel = document.getElementById('filter-station');
    if (!sel || sel.tagName !== 'SELECT') return;
    fetch('/api/cameras/stations')
        .then(r => r.json())
        .then(data => {
            if (data && data.stations && data.stations.length > 0) {
                const currentVal = sel.value;
                sel.innerHTML = '<option value="">Tüm İstasyonlar</option>';
                data.stations.forEach(st => {
                    const opt = document.createElement('option');
                    opt.value = st;
                    opt.textContent = st;
                    if (st === currentVal) opt.selected = true;
                    sel.appendChild(opt);
                });
            }
        })
        .catch(() => {});
}

function initReportsPage() {
    if (window._reportsPageInitialized) return;
    window._reportsPageInitialized = true;
    loadStationOptions();
    applyDatePreset('today');
}

document.addEventListener('DOMContentLoaded', initReportsPage);
if (document.readyState === 'interactive' || document.readyState === 'complete') {
    initReportsPage();
}

