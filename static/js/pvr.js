// PVR Upload & AI Quality Check – Frontend Controller
// Depends on app.js (showToast, setButtonLoading, getCurrentUser, populateOperationalCircleSelect, getUserAuthorizedCircles)

const PVR_API = '/api/pvr';
let pvrCurrentPage = 1;
const PVR_PAGE_SIZE = 20;
let pvrCurrentDetailId = null;

function escHtml(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

function authHeaders() {
    const user = getCurrentUser();
    if (!user) return {};
    return {
        'x-username': user.username || '',
        'x-user-role': user.role || '',
        'x-user-circle': user.circle || '',
        'x-user-team-id': user.team_id ? String(user.team_id) : '',
        'x-user-can-edit': user.can_edit ? 'true' : 'false',
    };
}

function authHeadersJson() {
    return { ...authHeaders(), 'Content-Type': 'application/json' };
}

// ─── TL Code Lookup ──────────────────────────────────────────────────
function setupTlLookup() {
    const inp = document.getElementById('pvrTlCode');
    const nameField = document.getElementById('pvrTlName');
    if (!inp || !nameField) return;

    let debounce = null;
    inp.addEventListener('input', () => {
        clearTimeout(debounce);
        const code = inp.value.trim();
        if (code.length < 3) { nameField.value = ''; return; }
        debounce = setTimeout(() => lookupTl(code), 400);
    });
    inp.addEventListener('blur', () => {
        const code = inp.value.trim();
        if (code.length >= 3) lookupTl(code);
    });
}

async function lookupTl(code) {
    const nameField = document.getElementById('pvrTlName');
    try {
        const resp = await fetch(`${PVR_API}/team-lead?code=${encodeURIComponent(code)}`, { headers: authHeaders() });
        if (resp.ok) {
            const data = await resp.json();
            nameField.value = data.name || '';
            nameField.classList.remove('is-invalid');
            nameField.classList.add('is-valid');
        } else {
            nameField.value = '';
            nameField.classList.remove('is-valid');
            nameField.classList.add('is-invalid');
        }
    } catch (e) {
        nameField.value = '';
    }
}

// ─── Upload Form ─────────────────────────────────────────────────────
function setupUploadForm() {
    const form = document.getElementById('pvrUploadForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const circle = document.getElementById('pvrCircle').value;
        const tlCode = document.getElementById('pvrTlCode').value.trim();
        const reportDate = document.getElementById('pvrReportDate').value;
        const fileInput = document.getElementById('pvrFile');

        if (!circle || !tlCode || !reportDate || !fileInput.files.length) {
            showToast('Please fill all required fields and select a PDF file.', 'warning');
            return;
        }

        const file = fileInput.files[0];
        if (file.size > 15 * 1024 * 1024) {
            showToast('File exceeds 15 MB limit.', 'danger');
            return;
        }

        setButtonLoading('btnPvrUpload', true);

        const fd = new FormData();
        fd.append('circle', circle);
        fd.append('tl_code', tlCode);
        fd.append('report_date', reportDate);
        fd.append('file', file);

        try {
            const resp = await fetch(`${PVR_API}/upload`, {
                method: 'POST',
                headers: authHeaders(),
                body: fd,
            });
            const data = await resp.json();
            if (resp.ok) {
                showToast(data.message || 'PVR uploaded!', 'success');
                pvrCurrentDetailId = data.id;
                showAiResultCard(data.id);
                form.reset();
                document.getElementById('pvrTlName').value = '';
                loadRecentPvrs();
            } else {
                showToast(data.detail || 'Upload failed', 'danger');
            }
        } catch (err) {
            showToast('Network error: ' + err.message, 'danger');
        } finally {
            setButtonLoading('btnPvrUpload', false, '<i class="fa-solid fa-upload me-1"></i> Upload & Evaluate');
        }
    });
}

// ─── AI Result Card ──────────────────────────────────────────────────
function showAiResultCard(recordId) {
    const card = document.getElementById('aiResultCard');
    const spinner = document.getElementById('aiPendingSpinner');
    const content = document.getElementById('aiResultContent');
    const badge = document.getElementById('aiStatusBadge');

    card.style.display = 'block';
    spinner.style.display = 'block';
    content.style.display = 'none';
    badge.textContent = 'PENDING';
    badge.className = 'badge bg-warning text-dark';

    pollAiStatus(recordId, 0);
}

async function pollAiStatus(recordId, attempt) {
    if (attempt > 60) {
        document.getElementById('aiPendingSpinner').innerHTML = '<p class="text-danger">AI evaluation timed out. Try re-evaluating.</p>';
        return;
    }

    try {
        const resp = await fetch(`${PVR_API}/${recordId}`, { headers: authHeaders() });
        if (!resp.ok) return;
        const data = await resp.json();

        if (data.ai_status === 'DONE') {
            renderAiResult(data);
            return;
        }
        if (data.ai_status === 'FAILED') {
            renderAiFailed(data);
            return;
        }
    } catch (e) { /* retry */ }

    setTimeout(() => pollAiStatus(recordId, attempt + 1), 3000);
}

function renderAiResult(data) {
    const spinner = document.getElementById('aiPendingSpinner');
    const content = document.getElementById('aiResultContent');
    const badge = document.getElementById('aiStatusBadge');
    const header = document.getElementById('aiResultHeader');

    spinner.style.display = 'none';
    content.style.display = 'block';

    badge.textContent = 'DONE';
    badge.className = 'badge bg-success';

    const score = data.ai_score ?? 0;
    document.getElementById('aiScoreDisplay').textContent = score;

    const verdictBadge = document.getElementById('aiVerdictBadge');
    const verdict = data.ai_verdict || 'UNKNOWN';
    verdictBadge.textContent = verdict;
    if (verdict === 'GOOD') {
        verdictBadge.className = 'badge fs-5 px-3 py-2 bg-success';
        header.className = 'card-header py-2 d-flex justify-content-between align-items-center bg-success text-white';
    } else if (verdict === 'AVERAGE') {
        verdictBadge.className = 'badge fs-5 px-3 py-2 bg-warning text-dark';
        header.className = 'card-header py-2 d-flex justify-content-between align-items-center bg-warning text-dark';
    } else {
        verdictBadge.className = 'badge fs-5 px-3 py-2 bg-danger';
        header.className = 'card-header py-2 d-flex justify-content-between align-items-center bg-danger text-white';
    }

    document.getElementById('aiSummaryText').textContent = data.ai_summary || 'N/A';

    // Findings
    const tbody = document.getElementById('aiFindingsBody');
    tbody.innerHTML = '';
    const findings = (data.ai_findings && data.ai_findings.findings) ? data.ai_findings.findings : [];
    findings.forEach(f => {
        const statusClass = f.status === 'PASS' ? 'text-success' : f.status === 'FAIL' ? 'text-danger' : 'text-warning';
        const icon = f.status === 'PASS' ? 'fa-circle-check' : f.status === 'FAIL' ? 'fa-circle-xmark' : 'fa-circle-half-stroke';
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td class="fw-semibold">${escHtml(f.item)}</td>
            <td class="${statusClass} fw-bold"><i class="fa-solid ${icon} me-1"></i>${escHtml(f.status)}</td>
            <td>${escHtml(f.remark)}</td>
        `;
        tbody.appendChild(tr);
    });

    // Suggestions
    const sugSection = document.getElementById('aiSuggestionsSection');
    const sugList = document.getElementById('aiSuggestionsList');
    const suggestions = (data.ai_findings && data.ai_findings.suggestions) ? data.ai_findings.suggestions : [];
    if (suggestions.length > 0) {
        sugSection.style.display = 'block';
        sugList.innerHTML = '';
        suggestions.forEach(s => {
            const li = document.createElement('li');
            li.textContent = s;
            sugList.appendChild(li);
        });
    } else {
        sugSection.style.display = 'none';
    }
}

function renderAiFailed(data) {
    const spinner = document.getElementById('aiPendingSpinner');
    const badge = document.getElementById('aiStatusBadge');
    const header = document.getElementById('aiResultHeader');

    spinner.innerHTML = `
        <div class="text-danger">
            <i class="fa-solid fa-triangle-exclamation fs-1 mb-2"></i>
            <p class="fw-bold">AI Evaluation Failed</p>
            <p class="text-muted small">${escHtml(data.ai_summary || 'Unknown error')}</p>
        </div>
    `;
    badge.textContent = 'FAILED';
    badge.className = 'badge bg-danger';
    header.className = 'card-header py-2 d-flex justify-content-between align-items-center bg-danger text-white';
}

// ─── Recent PVRs Table ───────────────────────────────────────────────
async function loadRecentPvrs() {
    const tbody = document.getElementById('pvrTableBody');
    tbody.innerHTML = '<tr><td colspan="8" class="text-center py-3"><div class="spinner-border spinner-border-sm"></div> Loading...</td></tr>';

    const circle = document.getElementById('pvrCircle') ? document.getElementById('pvrCircle').value : '';
    const tlFilter = document.getElementById('pvrSearchTl') ? document.getElementById('pvrSearchTl').value.trim() : '';

    let url = `${PVR_API}/list?page=${pvrCurrentPage}&limit=${PVR_PAGE_SIZE}`;
    if (circle && circle !== 'ALL') url += `&circle=${encodeURIComponent(circle)}`;
    if (tlFilter) url += `&tl_code=${encodeURIComponent(tlFilter)}`;

    try {
        const resp = await fetch(url, { headers: authHeaders() });
        if (!resp.ok) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-danger py-3">Failed to load records</td></tr>';
            return;
        }
        const data = await resp.json();
        const items = data.items || [];

        if (items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted py-3">No PVR reports found</td></tr>';
        } else {
            tbody.innerHTML = '';
            items.forEach(r => {
                const scoreHtml = r.ai_score !== null && r.ai_score !== undefined
                    ? `<span class="fw-bold">${r.ai_score}/10</span>` : '—';
                let verdictHtml = '—';
                if (r.ai_verdict === 'GOOD') verdictHtml = '<span class="badge bg-success">GOOD</span>';
                else if (r.ai_verdict === 'AVERAGE') verdictHtml = '<span class="badge bg-warning text-dark">AVERAGE</span>';
                else if (r.ai_verdict === 'POOR') verdictHtml = '<span class="badge bg-danger">POOR</span>';

                let statusHtml = '<span class="badge bg-secondary">PENDING</span>';
                if (r.ai_status === 'PROCESSING') statusHtml = '<span class="badge bg-info">PROCESSING</span>';
                else if (r.ai_status === 'DONE') statusHtml = '<span class="badge bg-success">DONE</span>';
                else if (r.ai_status === 'FAILED') statusHtml = '<span class="badge bg-danger">FAILED</span>';

                const tr = document.createElement('tr');
                tr.style.cursor = 'pointer';
                tr.innerHTML = `
                    <td>${escHtml(r.report_date)}</td>
                    <td class="fw-semibold">${escHtml(r.tl_code)}</td>
                    <td>${escHtml(r.tl_name)}</td>
                    <td>${escHtml(r.circle)}</td>
                    <td class="text-center">${scoreHtml}</td>
                    <td class="text-center">${verdictHtml}</td>
                    <td class="text-center">${statusHtml}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary" onclick="event.stopPropagation(); openPvrDetail(${r.id})" title="View Detail">
                            <i class="fa-solid fa-eye"></i>
                        </button>
                    </td>
                `;
                tr.addEventListener('click', () => openPvrDetail(r.id));
                tbody.appendChild(tr);
            });
        }

        // Pagination
        const total = data.total || 0;
        const totalPages = Math.ceil(total / PVR_PAGE_SIZE) || 1;
        document.getElementById('pvrPaginationInfo').textContent = `Page ${pvrCurrentPage} of ${totalPages} (${total} records)`;
        document.getElementById('pvrPrevBtn').disabled = pvrCurrentPage <= 1;
        document.getElementById('pvrNextBtn').disabled = pvrCurrentPage >= totalPages;

    } catch (err) {
        tbody.innerHTML = '<tr><td colspan="8" class="text-center text-danger py-3">Network error</td></tr>';
    }
}

function pvrChangePage(delta) {
    pvrCurrentPage += delta;
    if (pvrCurrentPage < 1) pvrCurrentPage = 1;
    loadRecentPvrs();
}

// ─── PVR Detail Modal ────────────────────────────────────────────────
async function openPvrDetail(id) {
    pvrCurrentDetailId = id;
    const modal = new bootstrap.Modal(document.getElementById('pvrDetailModal'));
    const body = document.getElementById('pvrDetailBody');
    body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div></div>';
    modal.show();

    try {
        const resp = await fetch(`${PVR_API}/${id}`, { headers: authHeaders() });
        if (!resp.ok) {
            body.innerHTML = '<div class="text-danger text-center py-4">Failed to load PVR detail</div>';
            return;
        }
        const d = await resp.json();
        document.getElementById('pvrDownloadLink').href = `${PVR_API}/${id}/file`;

        let findingsHtml = '';
        const findings = (d.ai_findings && d.ai_findings.findings) ? d.ai_findings.findings : [];
        findings.forEach(f => {
            const sc = f.status === 'PASS' ? 'text-success' : f.status === 'FAIL' ? 'text-danger' : 'text-warning';
            findingsHtml += `<tr><td class="fw-semibold">${escHtml(f.item)}</td><td class="${sc} fw-bold">${escHtml(f.status)}</td><td>${escHtml(f.remark)}</td></tr>`;
        });

        let sugHtml = '';
        const suggestions = (d.ai_findings && d.ai_findings.suggestions) ? d.ai_findings.suggestions : [];
        if (suggestions.length > 0) {
            sugHtml = '<h6 class="fw-bold mt-3">Suggestions</h6><ul>';
            suggestions.forEach(s => { sugHtml += `<li>${escHtml(s)}</li>`; });
            sugHtml += '</ul>';
        }

        let verdictClass = 'bg-secondary';
        if (d.ai_verdict === 'GOOD') verdictClass = 'bg-success';
        else if (d.ai_verdict === 'AVERAGE') verdictClass = 'bg-warning text-dark';
        else if (d.ai_verdict === 'POOR') verdictClass = 'bg-danger';

        body.innerHTML = `
            <div class="row g-2 mb-3">
                <div class="col-6"><strong>TL Code:</strong> ${escHtml(d.tl_code)}</div>
                <div class="col-6"><strong>TL Name:</strong> ${escHtml(d.tl_name)}</div>
                <div class="col-6"><strong>Circle:</strong> ${escHtml(d.circle)}</div>
                <div class="col-6"><strong>Report Date:</strong> ${escHtml(d.report_date)}</div>
                <div class="col-6"><strong>Uploaded By:</strong> ${escHtml(d.uploaded_by)}</div>
                <div class="col-6"><strong>Uploaded At:</strong> ${d.uploaded_at ? new Date(d.uploaded_at).toLocaleString() : '—'}</div>
            </div>
            <hr>
            <div class="row g-3 mb-3">
                <div class="col-md-3 text-center">
                    <div class="display-4 fw-bold">${d.ai_score !== null && d.ai_score !== undefined ? d.ai_score : '—'}</div>
                    <small class="text-muted">/10 Score</small>
                </div>
                <div class="col-md-3 text-center pt-2">
                    <span class="badge fs-5 px-3 py-2 ${verdictClass}">${escHtml(d.ai_verdict || d.ai_status || 'PENDING')}</span>
                </div>
                <div class="col-md-6">
                    <p class="fw-semibold mb-1">Summary</p>
                    <p class="text-muted mb-0">${escHtml(d.ai_summary || 'N/A')}</p>
                </div>
            </div>
            ${findings.length > 0 ? `
                <h6 class="fw-bold">Checklist Findings</h6>
                <div class="table-responsive">
                    <table class="table table-sm table-bordered">
                        <thead class="table-light"><tr><th>Item</th><th>Status</th><th>Remark</th></tr></thead>
                        <tbody>${findingsHtml}</tbody>
                    </table>
                </div>
            ` : ''}
            ${sugHtml}
        `;
    } catch (err) {
        body.innerHTML = '<div class="text-danger text-center py-4">Network error</div>';
    }
}

async function reEvaluatePvr() {
    if (!pvrCurrentDetailId) return;
    setButtonLoading('btnReEvaluate', true);
    try {
        const resp = await fetch(`${PVR_API}/${pvrCurrentDetailId}/re-evaluate`, {
            method: 'POST',
            headers: authHeaders(),
        });
        const data = await resp.json();
        if (resp.ok) {
            showToast(data.message || 'Re-evaluation started', 'success');
            bootstrap.Modal.getInstance(document.getElementById('pvrDetailModal')).hide();
            showAiResultCard(pvrCurrentDetailId);
            loadRecentPvrs();
        } else {
            showToast(data.detail || 'Re-evaluation failed', 'danger');
        }
    } catch (err) {
        showToast('Network error: ' + err.message, 'danger');
    } finally {
        setButtonLoading('btnReEvaluate', false, '<i class="fa-solid fa-rotate me-1"></i> Re-Evaluate');
    }
}

// ─── Init ────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Set default date to today
    const dateInput = document.getElementById('pvrReportDate');
    if (dateInput) dateInput.value = new Date().toISOString().split('T')[0];

    // Populate circle dropdown
    populateOperationalCircleSelect('pvrCircle', loadRecentPvrs);

    // TL lookup
    setupTlLookup();

    // Upload form
    setupUploadForm();

    // TL filter on table
    const searchInput = document.getElementById('pvrSearchTl');
    if (searchInput) {
        let debounce = null;
        searchInput.addEventListener('input', () => {
            clearTimeout(debounce);
            debounce = setTimeout(() => { pvrCurrentPage = 1; loadRecentPvrs(); }, 500);
        });
    }
});
