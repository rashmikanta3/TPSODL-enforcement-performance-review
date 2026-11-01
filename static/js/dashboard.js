// Executive Dashboard & Visual Analytics for TPSODL Enforcement Portal
// Completely Universal, Public, and Unrestricted across all Circles

let charts = {};

// Helper to reliably access circle filter element regardless of whether circleFilter or dashCircleSelect is queried
function getCircleFilterEl() {
    return document.getElementById('circleFilter') || document.getElementById('dashCircleSelect');
}

function getCircleFilterValue() {
    const el = getCircleFilterEl();
    return el ? el.value : '';
}

// Intercept getElementById to ensure seamless compatibility with both id names
if (typeof document !== 'undefined') {
    const _origGetElementById = document.getElementById.bind(document);
    document.getElementById = function(id) {
        if (id === 'dashCircleSelect') {
            return _origGetElementById('circleFilter') || _origGetElementById('dashCircleSelect');
        }
        if (id === 'circleFilter') {
            return _origGetElementById('circleFilter') || _origGetElementById('dashCircleSelect');
        }
        return _origGetElementById(id);
    };
}

document.addEventListener('DOMContentLoaded', () => {
    const today = new Date().toISOString().split('T')[0];
    const fromEl = document.getElementById('dashFromDate');
    const toEl = document.getElementById('dashToDate');
    if (fromEl) fromEl.value = today;
    if (toEl) toEl.value = today;

    // Ensure circle filter is enabled and unlocked for ALL users and guests
    const cEl = getCircleFilterEl();
    if (cEl) {
        cEl.disabled = false;
        cEl.removeAttribute('disabled');
        // Default to ALL CIRCLES
        if (!cEl.value) {
            cEl.value = '';
        }
    }

    // Load initial data
    refreshDashboard();
});

async function refreshDashboard() {
    const fromDate = document.getElementById('dashFromDate').value;
    const toDate = document.getElementById('dashToDate').value;
    const circle = getCircleFilterValue();

    // Ensure circle filter remains unlocked
    const cEl = getCircleFilterEl();
    if (cEl) {
        cEl.disabled = false;
    }

    setButtonLoading('btnRefreshDash', true);
    try {
        await Promise.all([
            loadKPIs(fromDate, toDate, circle),
            loadCharts(fromDate, toDate, circle),
            loadDailyOperationsStatus(toDate, circle),
            loadSquadPerformance(fromDate, toDate, circle)
        ]);
        showToast("Dashboard analytics refreshed!");
    } catch(err) {
        console.error("Dashboard error:", err);
        showToast("Failed to refresh some dashboard components", "danger");
    } finally {
        setButtonLoading('btnRefreshDash', false, '<i class="fa-solid fa-arrows-rotate me-1"></i> Apply Filter');
    }
}

// 1. KPI Cards
async function loadKPIs(fromDate, toDate, circle) {
    let url = `/api/analytics/kpis?from_date=${fromDate}&to_date=${toDate}`;
    if (circle) url += `&circle=${encodeURIComponent(circle)}`;

    const res = await fetch(url);
    const data = await res.json();

    const loadBookedEl = document.getElementById('kpiLoadBooked');
    if (loadBookedEl) loadBookedEl.innerText = `${Number(data.total_load_kw || 0).toLocaleString('en-IN')} kW`;

    const collEl = document.getElementById('kpiCollection');
    if (collEl) collEl.innerText = `₹ ${Number(data.total_collection_amount || 0).toLocaleString('en-IN')}`;

    const mrEl = document.getElementById('kpiMRCount');
    if (mrEl) mrEl.innerText = Number(data.total_mr_count || 0).toLocaleString('en-IN');

    const theftEl = document.getElementById('kpiTheftCount');
    if (theftEl) theftEl.innerText = Number(data.total_theft_cases || 0).toLocaleString('en-IN');

    const dcCountEl = document.getElementById('kpiDCCount');
    if (dcCountEl) dcCountEl.innerText = Number(data.total_dc_count || 0).toLocaleString('en-IN');

    const dcAmtEl = document.getElementById('kpiDCAmount');
    if (dcAmtEl) dcAmtEl.innerText = `₹ ${Number(data.total_dc_amount || 0).toLocaleString('en-IN')}`;
}

// 2. Charts
async function loadCharts(fromDate, toDate, circle) {
    let url = `/api/analytics/charts?from_date=${fromDate}&to_date=${toDate}`;
    if (circle) url += `&circle=${encodeURIComponent(circle)}`;

    const res = await fetch(url);
    const data = await res.json();

    if (data.circle_load) renderCircleLoadChart(data.circle_load);
    if (data.team_load) renderTeamLoadChart(data.team_load);
    if (data.circle_collection) renderCircleCollectionChart(data.circle_collection);
    if (data.team_collection) renderTeamCollectionChart(data.team_collection);
    if (data.circle_dc && data.team_dc) renderDCChart(data.circle_dc, data.team_dc);
}

function renderCircleLoadChart(d) {
    const canvas = document.getElementById('chartCircleLoad');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (charts.circleLoad) charts.circleLoad.destroy();

    charts.circleLoad = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: d.labels || [],
            datasets: [
                { label: 'Hooking (kW)', data: d.hooking || [], backgroundColor: '#dc2626' },
                { label: 'Meter Tamper (kW)', data: d.meter_tamper || [], backgroundColor: '#ea580c' },
                { label: 'Bypass (kW)', data: d.bypass || [], backgroundColor: '#ca8a04' },
                { label: 'Misuse (kW)', data: d.misuse || [], backgroundColor: '#64748b' }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { stacked: true },
                y: { stacked: true, beginAtZero: true, title: { display: true, text: 'Booked Load (kW)' } }
            }
        }
    });
}

function renderTeamLoadChart(d) {
    const canvas = document.getElementById('chartTeamLoad');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (charts.teamLoad) charts.teamLoad.destroy();

    charts.teamLoad = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: d.labels || [],
            datasets: [
                { label: 'Hooking (kW)', data: d.hooking || [], backgroundColor: '#dc2626' },
                { label: 'Meter Tamper (kW)', data: d.meter_tamper || [], backgroundColor: '#ea580c' },
                { label: 'Bypass (kW)', data: d.bypass || [], backgroundColor: '#ca8a04' },
                { label: 'Misuse (kW)', data: d.misuse || [], backgroundColor: '#64748b' }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { stacked: true },
                y: { stacked: true, beginAtZero: true, title: { display: true, text: 'Booked Load (kW)' } }
            }
        }
    });
}

function renderCircleCollectionChart(d) {
    const canvas = document.getElementById('chartCircleColl');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (charts.circleColl) charts.circleColl.destroy();

    charts.circleColl = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: d.labels || [],
            datasets: [{
                label: 'Collection (₹)',
                data: d.amounts || [],
                backgroundColor: '#16a34a'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, title: { display: true, text: 'Amount in ₹' } }
            }
        }
    });
}

function renderTeamCollectionChart(d) {
    const canvas = document.getElementById('chartTeamColl');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (charts.teamColl) charts.teamColl.destroy();

    charts.teamColl = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: d.labels || [],
            datasets: [{
                label: 'Collection (₹)',
                data: d.amounts || [],
                backgroundColor: '#0d9488'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, title: { display: true, text: 'Amount in ₹' } }
            }
        }
    });
}

function renderDCChart(cData, tData) {
    const canvas = document.getElementById('chartDC');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (charts.dcChart) charts.dcChart.destroy();

    charts.dcChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: cData.labels || [],
            datasets: [
                {
                    label: 'DC Count',
                    data: cData.counts || [],
                    backgroundColor: '#7c3aed',
                    yAxisID: 'y'
                },
                {
                    label: 'Amount Pending (₹)',
                    data: cData.amounts || [],
                    backgroundColor: '#f59e0b',
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    beginAtZero: true,
                    title: { display: true, text: 'Number of Disconnections' }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    beginAtZero: true,
                    grid: { drawOnChartArea: false },
                    title: { display: true, text: 'Pending Amount (₹)' }
                }
            }
        }
    });
}

// 3. Daily Operations Status
async function loadDailyOperationsStatus(opDate, circle) {
    let url = `/api/analytics/daily-operations-status?op_date=${opDate}`;
    if (circle) url += `&circle=${encodeURIComponent(circle)}`;

    const res = await fetch(url);
    const data = await res.json();

    // Update mini status summary counters
    const c = data.counts || {};
    const cntActiveTLEl = document.getElementById('cntActiveTL');
    if (cntActiveTLEl) cntActiveTLEl.innerText = c.INDEPENDENT_WITH_TL || 0;

    const cntActiveCollEl = document.getElementById('cntActiveColl');
    if (cntActiveCollEl) cntActiveCollEl.innerText = c.INDEPENDENT_WITHOUT_TL_COLLECTION || 0;

    const cntMergedEl = document.getElementById('cntMerged');
    if (cntMergedEl) cntMergedEl.innerText = c.MERGED || 0;

    const cntOfficeDutyEl = document.getElementById('cntOfficeDuty');
    if (cntOfficeDutyEl) cntOfficeDutyEl.innerText = c.OFFICE_DUTY_NO_VEHICLE || 0;

    const cntNonOpEl = document.getElementById('cntNonOp');
    if (cntNonOpEl) cntNonOpEl.innerText = c.NON_OPERATIONAL || 0;

    const tbody = document.getElementById('dailyOpsStatusBody');
    if (!tbody) return;

    if (!data.rows || !data.rows.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-3">No squad operations recorded for this date</td></tr>';
        return;
    }

    tbody.innerHTML = data.rows.map(r => {
        let badgeClass = 'badge-unreported';
        let badgeText = r.mode;
        if (r.mode === 'INDEPENDENT_WITH_TL') {
            badgeClass = 'badge-independent-tl';
            badgeText = 'Independent with TL';
        } else if (r.mode === 'INDEPENDENT_WITHOUT_TL_COLLECTION') {
            badgeClass = 'badge-independent-coll';
            badgeText = 'Collection Only (No TL)';
        } else if (r.mode === 'MERGED') {
            badgeClass = 'badge-merged';
            badgeText = `Merged`;
        } else if (r.mode === 'OFFICE_DUTY_NO_VEHICLE') {
            badgeClass = 'bg-secondary text-white';
            badgeText = 'Office Duty (No Vehicle)';
        } else if (r.mode === 'NON_OPERATIONAL') {
            badgeClass = 'badge-non-op';
            badgeText = 'Non-Operational';
        }

        const officeTag = (r.is_office || r.is_office_team || !r.has_vehicle)
            ? '<span class="badge bg-secondary-subtle text-secondary ms-1">Office (No Veh)</span>'
            : '';

        return `
            <tr>
                <td class="text-center">${r.sl_no}</td>
                <td class="fw-bold">${r.team_name} ${officeTag} <span class="badge bg-light text-secondary ms-1">${r.circle}</span></td>
                <td>${r.operated_by_tl}</td>
                <td><span class="badge ${badgeClass} px-2 py-1">${badgeText}</span></td>
                <td>${r.merged_with_team}</td>
                <td class="small text-muted">${r.remarks}</td>
            </tr>
        `;
    }).join('');
}

// 4. Squad Performance Table
async function loadSquadPerformance(fromDate, toDate, circle) {
    let url = `/api/analytics/squad-performance?from_date=${fromDate}&to_date=${toDate}`;
    if (circle) url += `&circle=${encodeURIComponent(circle)}`;

    const res = await fetch(url);
    const data = await res.json();

    const tbody = document.getElementById('squadPerformanceBody');
    if (!tbody) return;

    if (!data.rows || !data.rows.length) {
        tbody.innerHTML = '<tr><td colspan="9" class="text-center text-muted py-3">No performance data found</td></tr>';
        return;
    }

    tbody.innerHTML = data.rows.map(r => {
        let modeDisplay = (r.operation_mode || '').replace(/_/g, ' ');
        if (r.merged_status) {
            modeDisplay = `<span class="badge badge-merged">${r.merged_status}</span>`;
        } else if (r.is_office || r.operation_mode === 'OFFICE_DUTY_NO_VEHICLE') {
            modeDisplay = `<span class="badge bg-secondary text-white">Office Duty (No Vehicle)</span>`;
        }

        const officeTag = (r.is_office || r.is_office_team || !r.has_vehicle)
            ? '<span class="badge bg-secondary-subtle text-secondary ms-1">Office (No Veh)</span>'
            : '';

        return `
            <tr>
                <td class="fw-bold">${r.team_name} ${officeTag}</td>
                <td>${r.permanent_tl}</td>
                <td>${modeDisplay}</td>
                <td class="text-end fw-bold text-primary">${r.load_booked_kw} kW</td>
                <td class="text-end fw-bold text-success">₹ ${Number(r.amount_collected).toLocaleString('en-IN')}</td>
                <td class="text-center">${r.dc_count}</td>
                <td class="text-end">₹ ${Number(r.dc_amount).toLocaleString('en-IN')}</td>
                <td class="text-center">${r.km_run} KM</td>
                <td class="small text-muted">${r.remarks}</td>
            </tr>
        `;
    }).join('');
}

// 5. Image Export and WhatsApp Sharing
function downloadCardAsImage(cardId, filename) {
    const card = document.getElementById(cardId);
    if (!card) return;

    if (typeof html2canvas !== 'undefined') {
        html2canvas(card, { scale: 2 }).then(canvas => {
            const link = document.createElement('a');
            link.download = `${filename}_${Date.now()}.png`;
            link.href = canvas.toDataURL('image/png');
            link.click();
            showToast("Chart exported as image!");
        });
    } else {
        alert("html2canvas library is loading, please try again in a second");
    }
}

function shareCardWhatsApp(cardId, title) {
    const fromDate = document.getElementById('dashFromDate').value;
    const toDate = document.getElementById('dashToDate').value;
    const circle = getCircleFilterValue() || 'ALL CIRCLES';

    const kpiLoad = document.getElementById('kpiLoadBooked') ? document.getElementById('kpiLoadBooked').innerText : '-';
    const kpiColl = document.getElementById('kpiCollection') ? document.getElementById('kpiCollection').innerText : '-';
    const kpiTheft = document.getElementById('kpiTheftCount') ? document.getElementById('kpiTheftCount').innerText : '-';
    const kpiDC = document.getElementById('kpiDCCount') ? document.getElementById('kpiDCCount').innerText : '-';

    const summaryText = `*TPSODL Enforcement & Squad Operations Report*\n` +
        `📅 *Period:* ${fromDate} to ${toDate}\n` +
        `📍 *Circle:* ${circle}\n` +
        `📊 *Category:* ${title}\n` +
        `------------------------------------\n` +
        `⚡ *Load Booked:* ${kpiLoad}\n` +
        `💰 *Collections:* ${kpiColl}\n` +
        `🔍 *Theft Cases:* ${kpiTheft}\n` +
        `✂️ *Disconnections:* ${kpiDC}\n` +
        `------------------------------------\n` +
        `_Generated via TPSODL MIS Portal_`;

    // Download image first
    downloadCardAsImage(cardId, title.replace(/\s+/g, '_'));

    // Copy text to clipboard
    navigator.clipboard.writeText(summaryText).then(() => {
        showToast("Summary copied to clipboard! Opening WhatsApp...");
        setTimeout(() => {
            const waUrl = `https://api.whatsapp.com/send?text=${encodeURIComponent(summaryText)}`;
            window.open(waUrl, '_blank');
        }, 800);
    }).catch(() => {
        const waUrl = `https://api.whatsapp.com/send?text=${encodeURIComponent(summaryText)}`;
        window.open(waUrl, '_blank');
    });
}

function exportDashLoadBookings(format) {
    const fromDate = document.getElementById('dashFromDate').value;
    const toDate = document.getElementById('dashToDate').value;
    const circle = getCircleFilterValue();
    let url = `/api/reports/load-bookings/${format}?`;
    if (circle) url += `circle=${encodeURIComponent(circle)}&`;
    if (fromDate) url += `from_date=${fromDate}&`;
    if (toDate) url += `to_date=${toDate}&`;
    window.open(url, '_blank');
    showToast(`Downloading Load Bookings Register (${format.toUpperCase()})...`);
}
