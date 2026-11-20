// PVR Desk: Upload / View / Download (Google Drive backed)

const PVR = {
    status: null,          // /api/pvr/status
    user: null,
    optionsCache: {},      // circle|date -> /options response
    rows: {},              // id -> row (View tab)
    modals: {},
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);

function esc(v) {
    if (v === null || v === undefined) return '';
    return String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function fmtBytes(b) {
    if (b === null || b === undefined) return '-';
    if (b < 1024) return `${b} B`;
    if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
    if (b < 1073741824) return `${(b / 1048576).toFixed(2)} MB`;
    return `${(b / 1073741824).toFixed(2)} GB`;
}

function fmtDateTime(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    return isNaN(d) ? '-' : d.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}

function fmtDate(iso) {          // 2026-11-20 -> 20-11-2026
    if (!iso) return '-';
    const [y, m, d] = iso.split('-');
    return `${d}-${m}-${y}`;
}

function errorFrom(data, fallback) {
    const d = data && data.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d) && d.length) return d.map(e => `${(e.loc || []).slice(-1)[0]}: ${e.msg}`).join('; ');
    return fallback;
}

function handleAuthFailure(status) {
    if (status === 401) $('pvrSessionAlert')?.classList.remove('d-none');
}

// fetch wrapper -> {ok, status, data, message}; never throws
async function api(url, options = {}) {
    let res;
    try {
        res = await fetch(url, { credentials: 'same-origin', ...options });
    } catch (e) {
        return { ok: false, status: 0, data: null, message: 'Cannot reach the server. Check your connection and try again.' };
    }
    let data = null;
    try { data = await res.json(); } catch (e) { /* not JSON */ }
    if (res.ok) return { ok: true, status: res.status, data };
    handleAuthFailure(res.status);
    const fallback = res.status === 401 ? 'Your session has expired. Please sign in again.'
        : res.status === 403 ? 'You do not have permission for this action.'
        : res.status >= 500 ? 'Server error. Please try again.' : `Request failed (${res.status}).`;
    return { ok: false, status: res.status, data, message: errorFrom(data, fallback) };
}

// multipart upload with progress, speed/ETA and cancel (fetch has no upload progress).
// onProgress(pct, info) where info = {loaded, total, bps, etaSec}. Returns {promise, cancel}.
function xhrUpload(url, formData, onProgress) {
    const xhr = new XMLHttpRequest();
    const promise = new Promise((resolve) => {
        const started = performance.now();
        xhr.open('POST', url);
        xhr.withCredentials = true;
        xhr.upload.onprogress = (e) => {
            if (!e.lengthComputable) return;
            const secs = Math.max((performance.now() - started) / 1000, 0.001);
            const bps = e.loaded / secs;
            const etaSec = bps > 0 ? (e.total - e.loaded) / bps : null;
            onProgress(Math.round(e.loaded * 100 / e.total), { loaded: e.loaded, total: e.total, bps, etaSec });
        };
        xhr.onload = () => {
            let data = null;
            try { data = JSON.parse(xhr.responseText); } catch (e) { /* ignore */ }
            const ok = xhr.status >= 200 && xhr.status < 300;
            if (!ok) handleAuthFailure(xhr.status);
            resolve({ ok, status: xhr.status, data, message: ok ? null : errorFrom(data, `Upload failed (${xhr.status}).`) });
        };
        xhr.onerror = () => resolve({ ok: false, status: 0, data: null, message: 'Network error during upload. Please try again.' });
        xhr.onabort = () => resolve({ ok: false, status: -1, aborted: true, data: null, message: 'Upload cancelled.' });
        xhr.send(formData);
    });
    return { promise, cancel: () => xhr.abort() };
}

function fmtSpeed(bps) {
    if (!bps) return '';
    return bps >= 1048576 ? `${(bps / 1048576).toFixed(1)} MB/s` : `${Math.round(bps / 1024)} KB/s`;
}

function fmtEta(sec) {
    if (sec === null || sec === undefined || !isFinite(sec)) return '';
    if (sec < 1) return 'less than 1s left';
    if (sec < 60) return `${Math.ceil(sec)}s left`;
    return `${Math.floor(sec / 60)}m ${Math.ceil(sec % 60)}s left`;
}

// "3.10 MB (from 11.80 MB)" when the stored file was compressed
function fmtStoredSize(r) {
    const stored = fmtBytes(r.file_size);
    return r.original_size && r.file_size && r.original_size > r.file_size
        ? `${stored} <span class="text-muted">(from ${fmtBytes(r.original_size)})</span>` : stored;
}

function storageBadge(r) {
    if (r.storage_status === 'PENDING') {
        return '<span class="badge bg-warning-subtle text-warning-emphasis border border-warning-subtle" title="Uploaded to the portal; copying to Google Drive">⏳ Saving to Drive</span>';
    }
    if (r.storage_status === 'FAILED') {
        const why = r.storage_error ? ` title="${esc(r.storage_error)}"` : '';
        return `<span class="badge bg-danger-subtle text-danger border border-danger-subtle"${why}>❌ Failed</span>`;
    }
    return '<span class="badge bg-success-subtle text-success border border-success-subtle">✅ Saved</span>';
}

function setOptions(select, items, { placeholder = null, value = null } = {}) {
    if (!select) return;
    select.innerHTML = (placeholder !== null ? `<option value="">${esc(placeholder)}</option>` : '') +
        items.map(i => `<option value="${esc(i.value)}">${esc(i.label)}</option>`).join('');
    if (value !== null && value !== undefined) select.value = String(value);
}

const tlLabel = (t) => `${t.name}${t.tl_code ? ` (${t.tl_code})` : ''}`;

async function getOptions(circle, date) {
    const key = `${circle}|${date || ''}`;
    if (PVR.optionsCache[key]) return PVR.optionsCache[key];
    const params = new URLSearchParams({ circle });
    if (date) params.set('date', date);
    const r = await api(`/api/pvr/options?${params}`);
    if (!r.ok) { showToast(esc(r.message), 'danger'); return null; }
    PVR.optionsCache[key] = r.data;
    return r.data;
}

// Client-side PDF check: extension, size and %PDF magic bytes (server re-checks)
async function validatePdf(file) {
    if (!file) return 'Please choose a PDF file.';
    if (!file.name.toLowerCase().endsWith('.pdf')) return 'Only .pdf files are allowed.';
    const maxMb = PVR.status?.max_upload_mb || 25;
    if (file.size > maxMb * 1048576) return `File is ${fmtBytes(file.size)}; the limit is ${maxMb} MB.`;
    if (file.size === 0) return 'The file is empty.';
    try {
        const head = new Uint8Array(await file.slice(0, 1024).arrayBuffer());
        const text = String.fromCharCode(...head);
        if (!text.replace(/^[\s\x00﻿ï»¿]+/, '').startsWith('%PDF')) {
            return 'This file is not a real PDF (it may just be renamed to .pdf).';
        }
    } catch (e) { /* let the server decide */ }
    return null;
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', async () => {
    ['pvrViewModal', 'pvrEditModal', 'pvrReuploadModal', 'pvrDeleteModal'].forEach(id => {
        const el = $(id);
        if (el && window.bootstrap) PVR.modals[id] = new bootstrap.Modal(el);
    });
    $('pvrViewModal')?.addEventListener('hidden.bs.modal', () => { $('pvrModalFrame').src = 'about:blank'; });

    const r = await api('/api/pvr/status');
    if (!r.ok) {
        if (r.status !== 401) showToast(`Could not load the PVR desk: ${esc(r.message)}`, 'danger');
        document.querySelectorAll('#btnPvrUpload, #btnPvrList, #btnPvrPreview').forEach(b => b.disabled = true);
        return;
    }
    PVR.status = r.data;
    PVR.user = r.data.user;

    $('pvrMaxMb').textContent = r.data.max_upload_mb;
    $('dMaxDays').textContent = r.data.zip_max_days;
    $('dMaxFiles').textContent = r.data.zip_max_files;
    if (!r.data.drive_configured) {
        $('pvrDriveAlert').classList.remove('d-none');
        $('btnPvrUpload').disabled = true;
        $('btnPvrZip').disabled = true;
    }

    const today = r.data.today;
    ['upDate', 'vDate', 'dFrom', 'dTo', 'eDate'].forEach(id => { $(id).value = today; $(id).max = today; });

    await initUpload();
    initView();
    initDownload();
});

// ---------------------------------------------------------------------------
// UPLOAD TAB
// ---------------------------------------------------------------------------
let upState = { options: null, duplicate: false };

async function initUpload() {
    const circles = PVR.user.circles || [];
    const base = await api('/api/pvr/options');
    const locked = base.ok ? base.data : {};

    if (PVR.user.role === 'USER') {
        const c = locked.locked_circle;
        if (!c) {
            setOptions($('upCircle'), [], { placeholder: 'No team assigned to your account' });
            $('btnPvrUpload').disabled = true;
            return;
        }
        setOptions($('upCircle'), [{ value: c, label: c }], { value: c });
        $('upCircle').disabled = true;
    } else {
        setOptions($('upCircle'), circles.map(c => ({ value: c, label: c })),
            { placeholder: 'Select circle...', value: circles.length === 1 ? circles[0] : '' });
    }

    $('upCircle').addEventListener('change', () => loadUploadOptions());
    $('upDate').addEventListener('change', () => loadUploadOptions(true));
    $('upTeam').addEventListener('change', () => { applySuggestedTl(); checkDuplicate(); });
    $('upTl').addEventListener('change', checkDuplicate);
    $('upFile').addEventListener('change', onUploadFileChange);
    $('pvrUploadForm').addEventListener('submit', submitUpload);

    if ($('upCircle').value) await loadUploadOptions();
}

async function loadUploadOptions(keepSelection = false) {
    const circle = $('upCircle').value;
    const date = $('upDate').value;
    const prevTeam = $('upTeam').value;
    if (!circle) {
        setOptions($('upTeam'), [], { placeholder: 'Select circle first' });
        setOptions($('upTl'), [], { placeholder: 'Select circle first' });
        return;
    }
    setOptions($('upTeam'), [], { placeholder: 'Loading...' });
    const opt = await getOptions(circle, date);
    if (!opt) return;
    upState.options = opt;

    setOptions($('upTeam'), opt.teams.map(t => ({ value: t.id, label: t.name })),
        { placeholder: opt.teams.length ? 'Select team...' : 'No active teams in this circle' });
    setOptions($('upTl'), opt.team_leads.map(t => ({ value: t.id, label: tlLabel(t) })),
        { placeholder: opt.team_leads.length ? 'Select team leader...' : 'No active team leaders' });

    if (opt.locked_team_id) {
        $('upTeam').value = String(opt.locked_team_id);
        $('upTeam').disabled = true;
    } else if (keepSelection && prevTeam) {
        $('upTeam').value = prevTeam;
    }
    applySuggestedTl();
    checkDuplicate();
}

function applySuggestedTl() {
    const teamId = $('upTeam').value;
    const sug = upState.options?.suggested_tl?.[teamId];
    if (sug) {
        $('upTl').value = String(sug);
        $('upTlHint').textContent = 'Pre-selected from the daily team operation / default TL. You can change it.';
    } else {
        $('upTlHint').textContent = '';
    }
}

async function checkDuplicate() {
    const date = $('upDate').value;
    const tl = $('upTl').value;
    const alertBox = $('upDuplicateAlert');
    upState.duplicate = false;
    alertBox.classList.add('d-none');
    refreshUploadButton();
    if (!date || !tl) return;

    const r = await api(`/api/pvr/check?${new URLSearchParams({ date, team_lead_id: tl })}`);
    if (!r.ok || !r.data.exists) return;
    // ignore stale responses
    if ($('upDate').value !== date || $('upTl').value !== tl) return;

    upState.duplicate = true;
    $('upDuplicateMsg').textContent = r.data.message;
    const viewBtn = $('upDuplicateView');
    if (r.data.pvr && r.data.pvr.can_view) {
        viewBtn.classList.remove('d-none');
        viewBtn.onclick = () => openPdf(r.data.pvr);
    } else {
        viewBtn.classList.add('d-none');
    }
    alertBox.classList.remove('d-none');
    refreshUploadButton();
}

function refreshUploadButton() {
    $('btnPvrUpload').disabled = upState.duplicate || !PVR.status?.drive_configured;
}

async function onUploadFileChange() {
    const file = $('upFile').files[0];
    const info = $('upFileInfo');
    if (!file) { info.textContent = 'No file selected.'; info.className = 'form-text small'; return; }
    const err = await validatePdf(file);
    if (err) {
        info.textContent = err;
        info.className = 'form-text small text-danger fw-semibold';
        $('upFile').value = '';
        return;
    }
    info.innerHTML = `<i class="fa-solid fa-file-pdf text-danger me-1"></i>${esc(file.name)} &middot; ${fmtBytes(file.size)}`;
    info.className = 'form-text small text-success';
}

async function submitUpload(e) {
    e.preventDefault();
    const date = $('upDate').value, circle = $('upCircle').value, team = $('upTeam').value, tl = $('upTl').value;
    const file = $('upFile').files[0];

    if (!date || !circle || !team || !tl) return showToast('Please fill date, circle, team and team leader.', 'warning');
    if (date > PVR.status.today) return showToast('PVR date cannot be in the future.', 'warning');
    if (upState.duplicate) return showToast('A PVR already exists for this team leader and date.', 'warning');
    const err = await validatePdf(file);
    if (err) return showToast(err, 'danger');

    const fd = new FormData();
    fd.append('date', date);
    fd.append('circle', circle);
    fd.append('team_id', team);
    fd.append('team_lead_id', tl);
    fd.append('file', file);

    const btn = $('btnPvrUpload');
    btn.disabled = true;
    $('upProgressWrap').classList.remove('d-none');
    const bar = $('upProgress');
    const setPct = (p, info) => {
        bar.style.width = `${p}%`;
        bar.textContent = `${p}%`;
        $('upProgressText').textContent = p < 100
            ? ['Uploading', info && `${fmtBytes(info.loaded)} / ${fmtBytes(info.total)}`,
               info && fmtSpeed(info.bps), info && fmtEta(info.etaSec)].filter(Boolean).join(' · ')
            : 'Processing…';
    };
    setPct(0);

    const job = xhrUpload('/api/pvr/upload', fd, setPct);
    const cancelBtn = $('btnPvrCancel');
    cancelBtn.classList.remove('d-none');
    cancelBtn.onclick = job.cancel;
    const r = await job.promise;
    cancelBtn.classList.add('d-none');
    $('upProgressWrap').classList.add('d-none');

    if (!r.ok) {
        if (r.aborted) showToast('Upload cancelled.', 'warning');
        else showToast(esc(r.message), 'danger');
        if (r.status === 409) await checkDuplicate();
        else refreshUploadButton();
        return;
    }
    const p = r.data.pvr;
    showToast(`Uploaded ✔ – saving to Google Drive in background (${esc(p.tl_name)}, ${fmtDate(p.pvr_date)}).`, 'success');
    $('upFile').value = '';
    $('upFileInfo').textContent = 'No file selected.';
    $('upFileInfo').className = 'form-text small';
    await checkDuplicate();   // now shows "already uploaded"
}

// ---------------------------------------------------------------------------
// VIEW TAB
// ---------------------------------------------------------------------------
function initView() {
    const circles = PVR.user.circles || [];
    const items = circles.map(c => ({ value: c, label: c }));
    if (PVR.user.role === 'USER') {
        setOptions($('vCircle'), items, { value: circles[0] || '' });
        $('vCircle').disabled = true;
        $('vTl').disabled = true;
    } else {
        setOptions($('vCircle'), items, { placeholder: circles.length > 1 ? 'All circles' : null });
    }
    $('vCircle').addEventListener('change', loadViewTls);
    $('pvrViewForm').addEventListener('submit', (e) => { e.preventDefault(); loadList(); });
    $('pvrViewTabBtn').addEventListener('shown.bs.tab', () => { if (!$('vBody').dataset.loaded) loadList(); });
    loadViewTls();
}

async function loadViewTls() {
    const circle = $('vCircle').value;
    if (!circle || PVR.user.role === 'USER') {
        setOptions($('vTl'), [], { placeholder: 'All team leaders' });
        return;
    }
    const opt = await getOptions(circle, null);
    setOptions($('vTl'), (opt?.team_leads || []).map(t => ({ value: t.id, label: tlLabel(t) })),
        { placeholder: 'All team leaders' });
}

async function loadList(quiet = false) {
    const date = $('vDate').value;
    if (!date) return quiet ? null : showToast('Please choose a date.', 'warning');
    const params = new URLSearchParams({ date });
    if ($('vCircle').value) params.set('circle', $('vCircle').value);
    if ($('vTl').value) params.set('team_lead_id', $('vTl').value);

    const body = $('vBody');
    body.dataset.loaded = '1';
    if (!quiet) showTrackerSkeleton();
    if (!quiet) body.innerHTML = `<tr><td colspan="10" class="text-center text-muted py-4"><span class="spinner-border spinner-border-sm me-2"></span>Loading...</td></tr>`;

    const r = await api(`/api/pvr/list?${params}`);
    if (!r.ok) {
        if (quiet) return;
        body.innerHTML = `<tr><td colspan="10" class="text-center text-danger py-4"><i class="fa-solid fa-triangle-exclamation me-2"></i>${esc(r.message)}</td></tr>`;
        return;
    }
    renderList(r.data);
}

function renderList({ rows, tracker }) {
    const body = $('vBody');
    $('vCount').textContent = `${rows.length} uploaded`;
    PVR.rows = Object.fromEntries(rows.map(r => [String(r.id), r]));
    const isAdmin = PVR.user.role === 'ADMIN';

    body.innerHTML = rows.length ? rows.map(r => `
        <tr>
            <td class="ps-3 fw-semibold">${fmtDate(r.pvr_date)}</td>
            <td><span class="badge bg-secondary-subtle text-secondary border">${esc(r.circle)}</span></td>
            <td>${esc(r.team_name)}</td>
            <td class="fw-medium">${esc(r.tl_name)}${r.tl_code ? ` <span class="text-muted">(${esc(r.tl_code)})</span>` : ''}</td>
            <td><i class="fa-solid fa-file-pdf text-danger me-1"></i><span title="${esc(r.file_name)}">${esc(r.file_name)}</span>
                ${r.page_count ? `<div class="text-muted">${r.page_count} page${r.page_count === 1 ? '' : 's'}</div>` : ''}</td>
            <td class="text-nowrap">${fmtStoredSize(r)}</td>
            <td>${storageBadge(r)}</td>
            <td>${esc(r.uploaded_by || '-')}</td>
            <td>${fmtDateTime(r.uploaded_at)}${r.updated_at ? `<div class="text-muted">edited ${fmtDateTime(r.updated_at)}</div>` : ''}</td>
            <td class="text-end pe-3 text-nowrap">
                <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-primary" data-act="view" data-id="${r.id}" title="View"><i class="fa-solid fa-eye"></i></button>
                    <a class="btn btn-outline-secondary" href="/api/pvr/${r.id}/file" title="Download"><i class="fa-solid fa-download"></i></a>
                    ${isAdmin && r.storage_status === 'FAILED' ? `
                    <button class="btn btn-outline-success" data-act="retry" data-id="${r.id}" title="Retry Drive upload"><i class="fa-solid fa-arrows-rotate"></i></button>` : ''}
                    ${isAdmin ? `
                    <button class="btn btn-outline-dark" data-act="edit" data-id="${r.id}" title="Edit"><i class="fa-solid fa-pen"></i></button>
                    <button class="btn btn-outline-warning" data-act="reupload" data-id="${r.id}" title="Re-upload"><i class="fa-solid fa-rotate"></i></button>
                    <button class="btn btn-outline-danger" data-act="delete" data-id="${r.id}" title="Delete"><i class="fa-solid fa-trash"></i></button>` : ''}
                </div>
            </td>
        </tr>`).join('')
        : `<tr><td colspan="10" class="text-center text-muted py-4"><i class="fa-solid fa-folder-open me-2"></i>No PVR uploaded for these filters.</td></tr>`;

    body.querySelectorAll('button[data-act]').forEach(btn => btn.addEventListener('click', () => {
        const row = PVR.rows[btn.dataset.id];
        if (!row) return;
        ({ view: openPdf, edit: openEdit, reupload: openReupload, delete: openDelete, retry: retryUpload })[btn.dataset.act](row);
    }));

    // While uploads are still being copied to Drive, refresh quietly so badges turn ✅
    clearTimeout(PVR.pollTimer);
    if (rows.some(r => r.storage_status === 'PENDING')) {
        PVR.pollTimer = setTimeout(() => loadList(true), 4000);
    }

    renderTracker(tracker);
}

// ---------------------------------------------------------------------------
// PVR submission tracker (Admin / Sub-Admin)
// ---------------------------------------------------------------------------
const CIRCLE_COLORS = {
    BERHAMPUR: '#0d6efd', CITY: '#6f42c1', ASKA: '#198754',
    BHANJANAGAR: '#fd7e14', JEYPORE: '#d63384', RAYAGADA: '#0aa2c0',
};
const circleColor = (c) => CIRCLE_COLORS[c] || '#6c757d';

function fmtLongDate(iso) {           // 2026-11-20 -> 20 Nov 2026
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

function initials(name) {
    const parts = String(name || '?').trim().split(/\s+/);
    return ((parts[0] || '?')[0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

function pctColor(p) { return p >= 90 ? 'success' : p >= 60 ? 'warning' : 'danger'; }

function showTrackerSkeleton() {
    const box = $('vTracker');
    if (!box || !['ADMIN', 'SUB_ADMIN'].includes(PVR.user?.role)) return;
    box.classList.remove('d-none');
    box.innerHTML = `
        <div class="card shadow-sm border-0"><div class="card-body">
            <div class="pvr-skel mb-3" style="height:20px;width:55%"></div>
            <div class="row g-2 mb-3">${'<div class="col-4"><div class="pvr-skel" style="height:64px"></div></div>'.repeat(3)}</div>
            <div class="pvr-skel mb-3" style="height:10px"></div>
            <div class="pvr-skel mb-2" style="height:44px"></div><div class="pvr-skel" style="height:44px"></div>
        </div></div>`;
}

// Plain text for WhatsApp (*bold* is WhatsApp markdown)
function trackerShareText(t) {
    const lines = [`PVR pending – ${fmtLongDate(t.date)}`,
                   `Uploaded ${t.uploaded}/${t.expected}${t.percent !== null ? ` (${t.percent}%)` : ''}`];
    t.by_circle.filter(c => c.pending.length).forEach(c => {
        lines.push('', `*${c.circle}* (${c.uploaded}/${c.expected} uploaded)`);
        c.pending.forEach((p, i) => {
            lines.push(`${i + 1}. ${p.name}${p.tl_code ? ` (${p.tl_code})` : ''} – ${p.teams.join(', ')}` +
                       (p.contact_no ? ` – ${p.contact_no}` : ''));
        });
    });
    return lines.join('\n');
}

async function copyText(text) {
    try {
        await navigator.clipboard.writeText(text);
    } catch (e) {               // non-HTTPS / older browsers
        const ta = document.createElement('textarea');
        ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
        document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); } finally { ta.remove(); }
    }
}

function renderTracker(t) {
    const box = $('vTracker');
    if (!box) return;
    if (!t) { box.classList.add('d-none'); box.innerHTML = ''; return; }
    box.classList.remove('d-none');
    PVR.tracker = t;

    const title = `<h6 class="fw-bold mb-0"><i class="fa-solid fa-clipboard-check text-primary me-2"></i>PVR Submission Tracker – ${esc(fmtLongDate(t.date))}</h6>`;

    if (!t.has_operations && !t.not_entered.length) {
        box.innerHTML = `<div class="card shadow-sm border-0"><div class="card-body text-center py-4">${title}
            <div class="text-muted mt-3"><i class="fa-regular fa-calendar-xmark fs-2 d-block mb-2 opacity-50"></i>
            No team operation data for this date.</div></div></div>`;
        return;
    }

    const overdue = PVR.status && t.date < PVR.status.today;
    const pendTone = t.pending_count === 0 ? 'success' : (overdue ? 'danger' : 'warning');
    const pct = t.percent ?? 0;
    const tile = (num, label, icon, tone) => `
        <div class="col-4"><div class="stat bg-${tone}-subtle text-${tone}-emphasis border border-${tone}-subtle">
            <div class="lbl"><i class="${icon} me-1"></i>${label}</div><div class="num">${num}</div></div></div>`;

    let html = `<div class="card shadow-sm border-0 pvr-trk"><div class="card-body">
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">${title}
            ${t.expected ? `<span class="small text-muted">${t.uploaded} of ${t.expected} received</span>` : ''}</div>
        <div class="row g-2 mb-3">
            ${tile(t.expected, 'Expected', 'fa-solid fa-users', 'primary')}
            ${tile(t.uploaded, 'Uploaded ✅', 'fa-solid fa-circle-check', 'success')}
            ${tile(t.pending_count, `Pending ⏳${overdue && t.pending_count ? ' (late)' : ''}`, 'fa-solid fa-hourglass-half', pendTone)}
        </div>`;
    if (t.expected) {
        html += `<div class="d-flex align-items-center gap-2 mb-3">
            <div class="progress flex-grow-1" role="progressbar" aria-label="Uploaded" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100">
                <div class="progress-bar bg-${pctColor(pct)}" style="width:${pct}%"></div></div>
            <span class="fw-semibold small text-${pctColor(pct)}-emphasis">${pct}%</span></div>`;
    }

    if (t.expected && t.pending_count === 0) {
        html += `<div class="alert alert-success d-flex align-items-center mb-0"><span class="fs-4 me-2">🎉</span>
                 <strong>All PVRs received for this date</strong></div>`;
    } else if (t.expected) {
        html += `<div class="d-flex flex-wrap gap-2 mb-3 trk-actions">
            <button type="button" class="btn btn-sm btn-outline-secondary" id="trkCopy"><i class="fa-regular fa-copy me-1"></i>Copy list</button>
            <button type="button" class="btn btn-sm btn-success" id="trkWa"><i class="fa-brands fa-whatsapp me-1"></i>Share on WhatsApp</button>
        </div><div class="accordion" id="trkCircles">`;
        t.by_circle.forEach((c, idx) => {
            const color = circleColor(c.circle);
            const cp = c.expected ? Math.round(100 * c.uploaded / c.expected) : 0;
            const done = c.pending.length === 0;
            const id = `trkC${idx}`;
            html += `<div class="accordion-item" style="--trk-color:${color}">
                <h2 class="accordion-header"><button class="accordion-button ${done ? 'collapsed' : ''}" type="button"
                    data-bs-toggle="collapse" data-bs-target="#${id}" aria-expanded="${!done}">
                    <span class="rounded-circle d-inline-block flex-shrink-0" style="width:10px;height:10px;background:${color}"></span>
                    <span class="fw-semibold cname text-truncate">${esc(c.circle)}</span>
                    <span class="ms-auto d-flex align-items-center gap-2 small text-muted me-2 flex-shrink-0">
                        <span class="d-none d-sm-inline">${c.uploaded}/${c.expected} uploaded</span>
                        <span class="progress circle-progress"><span class="progress-bar bg-${pctColor(cp)}" style="width:${cp}%"></span></span>
                        ${done ? '<span class="badge bg-success-subtle text-success border border-success-subtle">✔ Done</span>'
                               : `<span class="badge bg-${overdue ? 'danger' : 'warning'} ${overdue ? '' : 'text-dark'}">${c.pending.length} pending</span>`}
                    </span></button></h2>
                <div id="${id}" class="accordion-collapse collapse ${done ? '' : 'show'}"><div class="accordion-body p-2">
                    ${done ? '<div class="small text-success px-1">✔ All PVRs uploaded in this circle.</div>' : `
                    <div class="row g-2">${c.pending.map(p => `
                        <div class="col-12 col-md-6 col-xl-4"><div class="pvr-tl">
                            <span class="avatar">${esc(initials(p.name))}</span>
                            <div class="meta"><div class="nm" title="${esc(p.name)}">${esc(p.name)}
                                ${p.tl_code ? `<span class="text-muted fw-normal small">· ${esc(p.tl_code)}</span>` : ''}</div>
                                <div class="sub" title="${esc(p.teams.join(', '))}"><i class="fa-solid fa-people-group me-1"></i>${esc(p.teams.join(', '))}</div></div>
                            ${p.contact_no ? `<a class="btn btn-sm btn-outline-success call" href="tel:${esc(String(p.contact_no).replace(/[^+0-9]/g, ''))}"
                                title="Call ${esc(p.contact_no)}" aria-label="Call ${esc(p.name)}">📞</a>` : ''}
                        </div></div>`).join('')}</div>`}
                </div></div></div>`;
        });
        html += '</div>';
    } else {
        html += `<div class="text-muted small"><i class="fa-solid fa-circle-info me-1"></i>No team was expected to submit a PVR on this date.</div>`;
    }

    const muted = (id, icon, label, items, hint, itemHtml) => items.length ? `
        <div class="mt-3"><a class="text-decoration-none small fw-semibold text-secondary" data-bs-toggle="collapse" href="#${id}" role="button" aria-expanded="false">
            <i class="${icon} me-1"></i>${label} (${items.length}) <i class="fa-solid fa-chevron-down ms-1 small"></i></a>
            <div class="collapse" id="${id}">${hint ? `<div class="small text-muted mt-1"><i class="fa-solid fa-lightbulb me-1"></i>${hint}</div>` : ''}
                <ul class="list-group list-group-flush muted-list mt-1">${items.map(itemHtml).join('')}</ul></div></div>` : '';

    html += muted('trkNotReq', 'fa-solid fa-user-slash', 'Not required today', t.not_required, '', r => `
        <li class="list-group-item d-flex flex-wrap justify-content-between align-items-center gap-1 px-1">
            <span>${esc(r.tl_name || '—')} <span class="text-body-tertiary">· ${esc(r.team)} · ${esc(r.circle)}</span></span>
            <span class="badge bg-secondary-subtle text-secondary border">${esc(r.reason)}</span></li>`);
    html += muted('trkNotEnt', 'fa-solid fa-clipboard-question', 'Operation not entered', t.not_entered,
        'Fill team operation in Attendance to track these teams.', r => `
        <li class="list-group-item d-flex flex-wrap justify-content-between align-items-center gap-1 px-1">
            <span>${esc(r.team)} <span class="text-body-tertiary">· ${esc(r.circle)}</span></span>
            <span class="badge bg-light text-secondary border">Default TL: ${esc(r.default_tl || '—')}</span></li>`);

    box.innerHTML = html + '</div></div>';

    $('trkCopy')?.addEventListener('click', async () => {
        await copyText(trackerShareText(PVR.tracker));
        showToast('Pending list copied. Paste it in WhatsApp.', 'success');
    });
    $('trkWa')?.addEventListener('click', () => {
        window.open(`https://wa.me/?text=${encodeURIComponent(trackerShareText(PVR.tracker))}`, '_blank', 'noopener');
    });
}

function openPdf(row) {
    $('pvrModalTitle').textContent = row.file_name;
    $('pvrModalFrame').src = `/api/pvr/${row.id}/file?inline=1`;
    $('pvrModalNewTab').href = `/api/pvr/${row.id}/file?inline=1`;
    $('pvrModalDownload').href = `/api/pvr/${row.id}/file`;
    PVR.modals.pvrViewModal?.show();
}

// ----- ADMIN: retry a FAILED Drive upload -----
async function retryUpload(row) {
    const r = await api(`/api/pvr/${row.id}/retry`, { method: 'POST' });
    if (!r.ok) return showToast(esc(r.message), 'danger');
    showToast('Retrying the Google Drive upload…', 'success');
    loadList();
}

// ----- ADMIN: edit -----
let editRow = null;

async function fillEditSelects(circle, date, teamId, tlId) {
    const opt = await getOptions(circle, date);
    if (!opt) return;
    setOptions($('eTeam'), opt.teams.map(t => ({ value: t.id, label: t.name })), { value: teamId ?? '' });
    setOptions($('eTl'), opt.team_leads.map(t => ({ value: t.id, label: tlLabel(t) })), { value: tlId ?? '' });
}

async function openEdit(row) {
    editRow = row;
    setOptions($('eCircle'), (PVR.user.circles || []).map(c => ({ value: c, label: c })), { value: row.circle });
    $('eDate').value = row.pvr_date;
    await fillEditSelects(row.circle, row.pvr_date, row.team_id, row.team_lead_id);
    PVR.modals.pvrEditModal?.show();
}

document.addEventListener('DOMContentLoaded', () => {
    $('eCircle')?.addEventListener('change', () => fillEditSelects($('eCircle').value, $('eDate').value, null, null));
    $('btnPvrEditSave')?.addEventListener('click', saveEdit);
    $('btnPvrReupload')?.addEventListener('click', submitReupload);
    $('btnPvrDelete')?.addEventListener('click', submitDelete);
    $('rFile')?.addEventListener('change', async () => {
        const f = $('rFile').files[0];
        const err = f ? await validatePdf(f) : null;
        $('rFileInfo').textContent = err || (f ? `${f.name} · ${fmtBytes(f.size)}` : '');
        $('rFileInfo').className = `form-text small ${err ? 'text-danger fw-semibold' : 'text-success'}`;
        if (err) $('rFile').value = '';
    });
});

async function saveEdit() {
    if (!editRow) return;
    const body = {
        pvr_date: $('eDate').value, circle: $('eCircle').value,
        team_id: parseInt($('eTeam').value, 10), team_lead_id: parseInt($('eTl').value, 10),
    };
    if (!body.pvr_date || !body.circle || !body.team_id || !body.team_lead_id) {
        return showToast('Please fill all fields.', 'warning');
    }
    setButtonLoading('btnPvrEditSave', true);
    const r = await api(`/api/pvr/${editRow.id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    setButtonLoading('btnPvrEditSave', false, 'Save changes');
    if (!r.ok) return showToast(esc(r.message), 'danger');
    PVR.modals.pvrEditModal?.hide();
    PVR.optionsCache = {};
    showToast(r.data.pvr.storage_status === 'UPLOADED'
        ? 'PVR updated and the file was moved in Google Drive.'
        : 'PVR updated. It will be saved to the new Drive folder.', 'success');
    loadList();
}

// ----- ADMIN: re-upload -----
let reuploadRow = null;

function openReupload(row) {
    reuploadRow = row;
    $('rInfo').innerHTML = `<strong>${esc(row.tl_name)}</strong> · ${esc(row.circle)} · ${fmtDate(row.pvr_date)}<br><span class="text-muted">Current: ${esc(row.file_name)} (${fmtBytes(row.file_size)})</span>`;
    $('rFile').value = '';
    $('rFileInfo').textContent = '';
    $('rProgressWrap').classList.add('d-none');
    PVR.modals.pvrReuploadModal?.show();
}

async function submitReupload() {
    if (!reuploadRow) return;
    const file = $('rFile').files[0];
    const err = await validatePdf(file);
    if (err) return showToast(err, 'danger');
    const fd = new FormData();
    fd.append('file', file);
    $('btnPvrReupload').disabled = true;
    $('rProgressWrap').classList.remove('d-none');
    const r = await xhrUpload(`/api/pvr/${reuploadRow.id}/reupload`, fd, (p) => {
        $('rProgress').style.width = `${p}%`;
        $('rProgress').textContent = p < 100 ? `${p}%` : 'Processing…';
    }).promise;
    $('btnPvrReupload').disabled = false;
    if (!r.ok) return showToast(esc(r.message), 'danger');
    PVR.modals.pvrReuploadModal?.hide();
    showToast('New file uploaded ✔ – saving to Google Drive in background. The old file goes to Drive trash once it is saved.', 'success');
    loadList();
}

// ----- ADMIN: delete -----
let deleteRow = null;

function openDelete(row) {
    deleteRow = row;
    $('delInfo').textContent = `${row.tl_name} · ${row.circle} · ${fmtDate(row.pvr_date)} · ${row.file_name}`;
    PVR.modals.pvrDeleteModal?.show();
}

async function submitDelete() {
    if (!deleteRow) return;
    setButtonLoading('btnPvrDelete', true);
    const r = await api(`/api/pvr/${deleteRow.id}`, { method: 'DELETE' });
    setButtonLoading('btnPvrDelete', false, '<i class="fa-solid fa-trash me-1"></i>Yes, delete');
    if (!r.ok) return showToast(esc(r.message), 'danger');
    PVR.modals.pvrDeleteModal?.hide();
    showToast(esc(r.data.message), 'success');
    loadList();
}

// ---------------------------------------------------------------------------
// DOWNLOAD TAB: multi-selects + summary + ZIP
// ---------------------------------------------------------------------------
class MultiSelect {
    constructor(container, placeholder, onChange) {
        this.items = [];
        this.selected = new Set();
        this.placeholder = placeholder;
        this.onChange = onChange;
        container.innerHTML = `
            <div class="dropdown">
                <button class="btn btn-sm btn-outline-secondary w-100 text-start dropdown-toggle text-truncate" type="button"
                        data-bs-toggle="dropdown" data-bs-auto-close="outside"></button>
                <div class="dropdown-menu pvr-ms-menu p-2 shadow">
                    <input type="search" class="form-control form-control-sm mb-2" placeholder="Search...">
                    <div class="d-flex gap-2 mb-2">
                        <button type="button" class="btn btn-link btn-sm p-0" data-ms="all">Select all</button>
                        <button type="button" class="btn btn-link btn-sm p-0 text-danger" data-ms="clear">Clear</button>
                    </div>
                    <div data-ms="list"></div>
                </div>
            </div>`;
        this.btn = container.querySelector('button.dropdown-toggle');
        this.search = container.querySelector('input[type=search]');
        this.list = container.querySelector('[data-ms=list]');
        this.search.addEventListener('input', () => this.render());
        container.querySelector('[data-ms=all]').addEventListener('click', () => {
            this.visible().forEach(i => this.selected.add(String(i.value)));
            this.render(); this.changed();
        });
        container.querySelector('[data-ms=clear]').addEventListener('click', () => {
            this.selected.clear(); this.render(); this.changed();
        });
        this.list.addEventListener('change', (e) => {
            if (e.target.type !== 'checkbox') return;
            e.target.checked ? this.selected.add(e.target.value) : this.selected.delete(e.target.value);
            this.updateLabel(); this.changed();
        });
        this.render();
    }
    setItems(items) {
        this.items = items;
        const valid = new Set(items.map(i => String(i.value)));
        this.selected = new Set([...this.selected].filter(v => valid.has(v)));
        this.render();
    }
    visible() {
        const q = this.search.value.trim().toLowerCase();
        return q ? this.items.filter(i => i.label.toLowerCase().includes(q)) : this.items;
    }
    values() { return [...this.selected]; }
    changed() { if (this.onChange) this.onChange(this.values()); }
    updateLabel() {
        const n = this.selected.size;
        this.btn.textContent = n === 0 ? this.placeholder
            : n === 1 ? (this.items.find(i => String(i.value) === [...this.selected][0])?.label || '1 selected')
            : `${n} selected`;
    }
    render() {
        const vis = this.visible();
        this.list.innerHTML = vis.length ? vis.map((i, idx) => `
            <div class="form-check">
                <input class="form-check-input" type="checkbox" id="${this.btn.id || 'ms'}_${idx}_${esc(i.value)}" value="${esc(i.value)}" ${this.selected.has(String(i.value)) ? 'checked' : ''}>
                <label class="form-check-label small" for="${this.btn.id || 'ms'}_${idx}_${esc(i.value)}">${esc(i.label)}</label>
            </div>`).join('') : '<div class="small text-muted px-2">No matches</div>';
        this.updateLabel();
    }
}

let dCircles = null, dTls = null;

function initDownload() {
    const circles = PVR.user.circles || [];
    dTls = new MultiSelect($('dTls'), 'All team leaders');
    dCircles = new MultiSelect($('dCircles'), 'All circles', () => loadDownloadTls());
    dCircles.btn.id = 'msCircles';
    dTls.btn.id = 'msTls';
    dCircles.setItems(circles.map(c => ({ value: c, label: c })));
    if (PVR.user.role === 'USER') {
        $('dTls').querySelector('button').disabled = true;
    }
    loadDownloadTls();

    $('btnPvrPreview').addEventListener('click', previewDownload);
    $('btnPvrZip').addEventListener('click', downloadZip);
    ['dFrom', 'dTo'].forEach(id => $(id).addEventListener('change', () => $('dSummaryCard').classList.add('d-none')));
}

async function loadDownloadTls() {
    if (PVR.user.role === 'USER') return;
    const circles = dCircles.values().length ? dCircles.values() : (PVR.user.circles || []);
    const all = [];
    for (const c of circles) {
        const opt = await getOptions(c, null);
        (opt?.team_leads || []).forEach(t => all.push({ value: String(t.id), label: `${tlLabel(t)} · ${c}` }));
    }
    dTls.setItems(all);
    $('dSummaryCard').classList.add('d-none');
}

function downloadParams() {
    const from = $('dFrom').value, to = $('dTo').value;
    if (!from || !to) { showToast('Please choose both From and To dates.', 'warning'); return null; }
    if (to < from) { showToast("'To date' cannot be before 'From date'.", 'warning'); return null; }
    const days = Math.round((new Date(to) - new Date(from)) / 86400000) + 1;
    const max = PVR.status.zip_max_days;
    if (days > max) { showToast(`Date range is ${days} days; the maximum is ${max}.`, 'warning'); return null; }
    const p = new URLSearchParams({ from_date: from, to_date: to });
    if (dCircles.values().length) p.set('circles', dCircles.values().join(','));
    if (dTls.values().length) p.set('team_lead_ids', dTls.values().join(','));
    return p;
}

let lastSummary = null;

async function previewDownload() {
    const params = downloadParams();
    if (!params) return;
    setButtonLoading('btnPvrPreview', true);
    const r = await api(`/api/pvr/summary?${params}`);
    setButtonLoading('btnPvrPreview', false, '<i class="fa-solid fa-list-check me-1"></i>Preview');
    if (!r.ok) return showToast(esc(r.message), 'danger');

    lastSummary = { params: params.toString(), ...r.data };
    const s = r.data;
    $('dSummaryText').innerHTML = s.count
        ? `<i class="fa-solid fa-file-zipper text-success me-2"></i>${s.count} PVR${s.count === 1 ? '' : 's'}, total ${fmtBytes(s.total_bytes)}` +
          (s.over_limit ? ` <span class="badge bg-danger ms-2">Over the ${s.max_files}-file limit — narrow the filters</span>` : '')
        : '<i class="fa-solid fa-circle-info text-muted me-2"></i>No PVR found for the selected filters.';
    $('btnPvrZip').disabled = !s.count || s.over_limit || !PVR.status.drive_configured;
    $('dBody').innerHTML = s.rows.map(r => `
        <tr><td class="ps-3">${fmtDate(r.pvr_date)}</td><td>${esc(r.circle)}</td><td>${esc(r.tl_name)}</td>
            <td>${esc(r.file_name)} ${r.storage_status !== 'UPLOADED' ? storageBadge(r) : ''}</td><td class="text-end pe-3">${fmtBytes(r.file_size)}</td></tr>`).join('') +
        (s.count > s.rows.length ? `<tr><td colspan="5" class="text-center text-muted small">… and ${s.count - s.rows.length} more</td></tr>` : '');
    $('dSummaryCard').classList.remove('d-none');
}

async function downloadZip() {
    const params = downloadParams();
    if (!params) return;
    if (!lastSummary || lastSummary.params !== params.toString()) {
        await previewDownload();     // filters changed: refresh the summary first
        return;
    }
    const url = `/api/pvr/bulk-download?${params}`;

    // Very large ZIPs: let the browser stream straight to disk instead of holding a Blob in memory
    if (lastSummary.total_bytes > 400 * 1048576) {
        showToast('Preparing a large ZIP. The download will start when it is ready.', 'success');
        window.location.href = url;
        return;
    }

    const btnHtml = '<i class="fa-solid fa-file-zipper me-1"></i>Download ZIP';
    const btn = $('btnPvrZip');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Preparing ZIP...';
    try {
        let res;
        try {
            res = await fetch(url, { credentials: 'same-origin' });
        } catch (e) {
            return showToast('Network error while downloading. Please try again.', 'danger');
        }
        if (!res.ok) {
            let data = null;
            try { data = await res.json(); } catch (e) { /* ignore */ }
            handleAuthFailure(res.status);
            return showToast(esc(errorFrom(data, `Download failed (${res.status}).`)), 'danger');
        }
        const blob = await res.blob();
        const cd = res.headers.get('Content-Disposition') || '';
        const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
        const name = m ? decodeURIComponent(m[1]) : 'PVR.zip';
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 10000);

        const missing = parseInt(res.headers.get('X-PVR-Missing') || '0', 10);
        showToast(missing ? `ZIP downloaded. ${missing} file(s) were missing in Drive — see missing_files.txt.`
                          : 'ZIP downloaded.', missing ? 'warning' : 'success');
    } finally {
        btn.innerHTML = btnHtml;
        btn.disabled = false;
    }
}
