// web/static/js/reports.js
// Raporlar (Reports) sayfası için ayrıştırılmış JavaScript iş mantığı dosyası.

let allRecords = [];
let workerStatsData = [];
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
    if (!workers.length) {
        tbody.innerHTML = `<tr><td colspan="11" style="text-align:center; padding:20px; color:var(--text-secondary);">Kayıtlı çalışma verisi bulunamadı.</td></tr>`;
        return;
    }

    tbody.innerHTML = workers.map(w => {
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

// Mail Gönder
const btnMailSend = document.getElementById('btn-mail-send');
if (btnMailSend) {
    btnMailSend.addEventListener('click', async () => {
        const mailInput = document.getElementById('mail-input');
        const email = mailInput ? mailInput.value.trim() : '';
        if (!email) { showToast('E-posta adresi girin', 'error'); return; }
        btnMailSend.disabled = true;
        const elStart = document.getElementById('filter-start').value;
        const elEnd = document.getElementById('filter-end').value;
        const elStation = document.getElementById('filter-station').value;
        const elWorker = document.getElementById('filter-worker').value;
        try {
            const res = await fetch('/api/reports/email_pdf', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, start: elStart, end: elEnd, istasyon: elStation, worker: elWorker})
            });
            const result = await res.json();
            showToast(result.message, result.success ? 'success' : 'error');
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

