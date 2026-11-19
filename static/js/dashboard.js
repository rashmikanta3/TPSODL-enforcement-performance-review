// =====================================================================
// TPSODL Enforcement Portal — Executive Dashboard & Visual Analytics
// Redesigned charts: Load Booking / DC / Collection by
// Circle → Division → Sub-Division → Section, Squad (Team) and Collector.
// Every chart is shareable as WhatsApp-ready images (1080 px wide,
// ≤ 1600 px tall per page, so WhatsApp does not downscale them).
// =====================================================================

/* ------------------------------------------------------------------ */
/* 0. Palette, formatting & small helpers                              */
/* ------------------------------------------------------------------ */
if (typeof Chart !== 'undefined' && typeof ChartDataLabels !== 'undefined') {
    Chart.register(ChartDataLabels);
    Chart.defaults.set('plugins.datalabels', { display: false });
}
if (typeof Chart !== 'undefined') {
    Chart.defaults.font.family = "'Segoe UI', Roboto, 'Noto Sans', Arial, sans-serif";
}

const FONT = "'Segoe UI', Roboto, 'Noto Sans', Arial, sans-serif";

// Theft types: fixed colour per type (never by rank), checked for colour-blind separation.
const THEFT_SERIES = [
    { key: 'hooking',      label: 'Hooking',      color: '#D62839', text: '#FFFFFF' },
    { key: 'meter_tamper', label: 'Meter Tamper', color: '#7B3FC4', text: '#FFFFFF' },
    { key: 'bypass',       label: 'Bypass',       color: '#F28C28', text: '#1F2937' },
    { key: 'misuse',       label: 'Misuse',       color: '#1F7AC9', text: '#FFFFFF' },
    { key: 'others',       label: 'Others',       color: '#8C96A3', text: '#FFFFFF' }
];

const LEVEL_LABEL = {
    circle: 'Circle', division: 'Division', subdivision: 'Sub-Division',
    section: 'Section', team: 'Squad', collector: 'Collector'
};
const HIER = ['circle', 'division', 'subdivision', 'section'];
const NEXT_LEVEL = { circle: 'division', division: 'subdivision', subdivision: 'section' };

const fmt = {
    num(v, d = 0) {
        return Number(v || 0).toLocaleString('en-IN', { maximumFractionDigits: d, minimumFractionDigits: 0 });
    },
    kw(v) { return `${fmt.num(v, 1)} kW`; },
    inr(v) {
        const n = Number(v || 0), a = Math.abs(n);
        if (a >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`;
        if (a >= 1e5) return `₹${(n / 1e5).toFixed(2)} L`;
        return `₹${Math.round(n).toLocaleString('en-IN')}`;
    },
    inrFull(v) { return `₹ ${Math.round(Number(v || 0)).toLocaleString('en-IN')}`; }
};
// Back-compat for any other page that used it
function formatIndianCurrency(val) { return fmt.inr(val).replace('₹', '₹ '); }

const METRICS = {
    load: {
        title: 'Load Booking (Theft Detection)', short: 'Load Booking', icon: 'fa-bolt',
        accent: '#D62839', tint: '#FDECEE',
        series: THEFT_SERIES,
        barValue: r => r.total_load,
        endLabel: r => `${fmt.kw(r.total_load)} · ${r.cases}`,
        segLabel: v => fmt.num(v, 1),
        axis: v => `${fmt.num(v)} kW`,
        tooltip: r => [`Total: ${fmt.kw(r.total_load)}`, `Theft cases: ${r.cases}`],
        chips: t => [
            { label: 'Total Load', value: fmt.kw(t.total_load) },
            { label: 'Theft Cases', value: fmt.num(t.cases) },
            ...THEFT_SERIES.filter(s => (t[s.key] || 0) > 0).map(s => ({
                label: s.label, color: s.color,
                value: `${fmt.num(t[s.key], 1)} kW (${t.total_load ? Math.round(t[s.key] * 100 / t.total_load) : 0}%)`
            }))
        ],
        endHint: 'kW · cases'
    },
    dc: {
        title: 'Disconnections (DC) & Arrears', short: 'Disconnection', icon: 'fa-scissors',
        accent: '#6D28D9', tint: '#F1EAFE',
        series: [{ key: 'dc_count', label: 'DC Executed', color: '#6D28D9', text: '#FFFFFF' }],
        barValue: r => r.dc_count,
        endLabel: r => `${fmt.num(r.dc_count)} DC · ${fmt.inr(r.dc_amount)}`,
        axis: v => fmt.num(v),
        tooltip: r => [`DC executed: ${fmt.num(r.dc_count)}`, `Arrears involved: ${fmt.inrFull(r.dc_amount)}`],
        chips: t => [
            { label: 'DC Executed', value: fmt.num(t.dc_count), color: '#6D28D9' },
            { label: 'Arrears Involved', value: fmt.inr(t.dc_amount) }
        ],
        endHint: 'DC count · arrears'
    },
    collection: {
        title: 'Collection Realization', short: 'Collection', icon: 'fa-indian-rupee-sign',
        accent: '#0E8A5F', tint: '#E6F6EF',
        series: [{ key: 'amount', label: 'Collection', color: '#0E8A5F', text: '#FFFFFF' }],
        barValue: r => r.amount,
        endLabel: r => `${fmt.inr(r.amount)} · ${fmt.num(r.mr_count)} MR`,
        axis: v => fmt.inr(v),
        tooltip: r => [`Collected: ${fmt.inrFull(r.amount)}`, `MR receipts: ${fmt.num(r.mr_count)}`],
        chips: t => [
            { label: 'Total Collection', value: fmt.inr(t.amount), color: '#0E8A5F' },
            { label: 'MR Receipts', value: fmt.num(t.mr_count) }
        ],
        endHint: 'amount · MR receipts'
    }
};

function getCircleFilterEl() {
    return document.getElementById('circleFilter') || document.getElementById('dashCircleSelect');
}
function getCircleFilterValue() { const el = getCircleFilterEl(); return el ? el.value : ''; }
function getDates() {
    return { from: document.getElementById('dashFromDate').value, to: document.getElementById('dashToDate').value };
}
function periodText() {
    const { from, to } = getDates();
    const f = d => { if (!d) return ''; const [y, m, dd] = d.split('-'); return `${dd}-${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][+m - 1]}-${y}`; };
    return from === to ? f(from) : `${f(from)} to ${f(to)}`;
}
function notify(msg, type) { if (typeof showToast === 'function') showToast(msg, type); else console.log(msg); }
function btnBusy(id, busy, html) { if (typeof setButtonLoading === 'function') setButtonLoading(id, busy, html); }
function esc(s) { return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
const sleep = ms => new Promise(r => setTimeout(r, ms));

/* ------------------------------------------------------------------ */
/* 1. Share-image engine (custom canvas, phone-first typography)       */
/* ------------------------------------------------------------------ */
const IMG = { W: 1080, PAD: 40, HEADER: 156, FOOTER: 64, ROW: 50, MAX_H: 1600 };

function ellipsize(ctx, text, maxW) {
    text = String(text ?? '');
    if (ctx.measureText(text).width <= maxW) return text;
    let lo = 0, hi = text.length;
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (ctx.measureText(text.slice(0, mid) + '…').width <= maxW) lo = mid; else hi = mid - 1; }
    return text.slice(0, lo) + '…';
}
// Shrink font (down to minSize) before falling back to an ellipsis.
function fitText(ctx, text, maxW, weight, size, minSize) {
    let fs = size;
    ctx.font = `${weight} ${fs}px ${FONT}`;
    while (ctx.measureText(String(text ?? '')).width > maxW && fs > minSize) { fs--; ctx.font = `${weight} ${fs}px ${FONT}`; }
    return ellipsize(ctx, text, maxW);
}
function localISODate(d = new Date()) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function roundRect(ctx, x, y, w, h, r) {
    r = Math.max(0, Math.min(r, h / 2, w / 2));
    ctx.beginPath();
    ctx.moveTo(x + r, y); ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y); ctx.closePath();
}
function nowStamp() {
    const d = new Date();
    return `${String(d.getDate()).padStart(2, '0')}-${['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][d.getMonth()]}-${d.getFullYear()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function drawHeader(ctx, W, { title, subtitle, accent, pageText }) {
    const g = ctx.createLinearGradient(0, 0, W, IMG.HEADER);
    g.addColorStop(0, '#0B2545'); g.addColorStop(1, '#16407A');
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, IMG.HEADER);
    ctx.fillStyle = accent || '#F4B400'; ctx.fillRect(0, IMG.HEADER - 8, W, 8);

    ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = '#93C5FD'; ctx.font = `700 17px ${FONT}`;
    ctx.fillText('TPSODL  •  ENFORCEMENT MIS', IMG.PAD, 40);

    let right = W - IMG.PAD;
    if (pageText) {
        ctx.font = `700 20px ${FONT}`;
        const pw = ctx.measureText(pageText).width + 28;
        ctx.fillStyle = 'rgba(255,255,255,0.16)'; roundRect(ctx, right - pw, 18, pw, 34, 17); ctx.fill();
        ctx.fillStyle = '#FFFFFF'; ctx.fillText(pageText, right - pw + 14, 42);
        right -= pw + 12;
    }
    ctx.fillStyle = '#FFFFFF'; ctx.font = `800 36px ${FONT}`;
    ctx.fillText(ellipsize(ctx, title, W - 2 * IMG.PAD), IMG.PAD, 88);
    ctx.fillStyle = '#E2E8F0'; ctx.font = `600 22px ${FONT}`;
    ctx.fillText(ellipsize(ctx, subtitle, W - 2 * IMG.PAD), IMG.PAD, 126);
}

function drawFooter(ctx, W, H, rightText) {
    ctx.strokeStyle = '#E2E8F0'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(IMG.PAD, H - IMG.FOOTER + 8); ctx.lineTo(W - IMG.PAD, H - IMG.FOOTER + 8); ctx.stroke();
    ctx.font = `500 17px ${FONT}`; ctx.fillStyle = '#64748B'; ctx.textBaseline = 'middle';
    ctx.textAlign = 'left'; ctx.fillText(`Generated ${nowStamp()}  •  TPSODL Enforcement Portal`, IMG.PAD, H - IMG.FOOTER / 2 + 4);
    if (rightText) { ctx.textAlign = 'right'; ctx.font = `700 17px ${FONT}`; ctx.fillText(rightText, W - IMG.PAD, H - IMG.FOOTER / 2 + 4); }
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
}

// Summary chips (totals + colour legend). Returns height used.
function layoutChips(ctx, chips, maxW) {
    const placed = []; let x = 0, y = 0; const H = 66, GAP = 12;
    chips.forEach(ch => {
        ctx.font = `600 15px ${FONT}`; const lw = ctx.measureText(ch.label.toUpperCase()).width;
        ctx.font = `800 23px ${FONT}`; const vw = ctx.measureText(ch.value).width;
        const w = Math.max(lw, vw) + 32 + (ch.color ? 22 : 0);
        if (x > 0 && x + w > maxW) { x = 0; y += H + GAP; }
        placed.push({ ...ch, x, y, w, h: H }); x += w + GAP;
    });
    return { placed, height: chips.length ? y + H : 0 };
}
function drawChips(ctx, chips, ox, oy, maxW) {
    const { placed, height } = layoutChips(ctx, chips, maxW);
    placed.forEach(c => {
        ctx.fillStyle = '#F1F5F9'; roundRect(ctx, ox + c.x, oy + c.y, c.w, c.h, 12); ctx.fill();
        let tx = ox + c.x + 16;
        if (c.color) { ctx.fillStyle = c.color; roundRect(ctx, tx, oy + c.y + 14, 14, 38, 4); ctx.fill(); tx += 24; }
        ctx.fillStyle = '#64748B'; ctx.font = `600 15px ${FONT}`; ctx.fillText(c.label.toUpperCase(), tx, oy + c.y + 25);
        ctx.fillStyle = '#0F172A'; ctx.font = `800 23px ${FONT}`; ctx.fillText(c.value, tx, oy + c.y + 53);
    });
    return oy + height;
}

function newCanvas(W, H) { const c = document.createElement('canvas'); c.width = W; c.height = H; return c; }

/**
 * Ranked horizontal bar chart, paged for WhatsApp.
 * spec: { title, subtitle, accent, rows, series, barValue(row), endLabel(row), segLabel(v), chips[], endHint }
 */
function renderBarPages(spec) {
    const W = IMG.W, PAD = IMG.PAD, ROW = IMG.ROW;
    const rows = spec.rows || [];
    const maxVal = Math.max(1e-9, ...rows.map(spec.barValue));
    const series = spec.series.filter(s => rows.some(r => (r[s.key] || 0) > 0));
    const multi = series.length > 1;
    const measure = newCanvas(10, 10).getContext('2d');
    const chipsH = layoutChips(measure, spec.chips || [], W - 2 * PAD).height;
    // Fit as many rows as possible while keeping every page ≤ 1600 px tall, then balance pages.
    const fixedH = IMG.HEADER + 22 + chipsH + (chipsH ? 18 : 0) + 36 + 14 + IMG.FOOTER;
    const fit = Math.max(8, Math.floor((IMG.MAX_H - fixedH) / ROW));
    const pages = Math.max(1, Math.ceil(rows.length / fit));
    const per = Math.max(1, Math.ceil(rows.length / pages));
    const out = [];

    for (let p = 0; p < pages; p++) {
        const slice = rows.slice(p * per, (p + 1) * per);
        const top = IMG.HEADER + 22 + chipsH + (chipsH ? 18 : 0) + 36;   // 36 = column caption row
        const H = top + Math.max(1, slice.length) * ROW + 14 + IMG.FOOTER;
        const c = newCanvas(W, H), ctx = c.getContext('2d');
        ctx.fillStyle = '#FFFFFF'; ctx.fillRect(0, 0, W, H);
        drawHeader(ctx, W, { title: spec.title, subtitle: spec.subtitle, accent: spec.accent, pageText: pages > 1 ? `Page ${p + 1}/${pages}` : '' });
        let y = IMG.HEADER + 22;
        if (chipsH) y = drawChips(ctx, spec.chips, PAD, y, W - 2 * PAD) + 18;

        const rankX = PAD + 18, labelX = PAD + 46, labelW = 300;
        const barX = labelX + labelW + 14, valueW = 228;
        const barMax = W - PAD - valueW - barX;

        ctx.font = `700 15px ${FONT}`; ctx.fillStyle = '#94A3B8';
        ctx.fillText((spec.levelLabel || 'NAME').toUpperCase(), labelX, y + 20);
        ctx.textAlign = 'right'; ctx.fillText((spec.endHint || '').toUpperCase(), W - PAD, y + 20); ctx.textAlign = 'left';
        y += 36;

        if (!slice.length) {
            ctx.font = `600 22px ${FONT}`; ctx.fillStyle = '#64748B';
            ctx.fillText('No records for the selected period.', labelX, y + 32);
        }

        slice.forEach((r, i) => {
            const ry = y + i * ROW, cy = ry + ROW / 2;
            if (i % 2 === 0) { ctx.fillStyle = '#F6F8FB'; ctx.fillRect(PAD - 12, ry, W - 2 * PAD + 24, ROW); }

            // rank badge (gold / silver / bronze for top 3)
            const rank = r._rank;
            const medal = { 1: '#F4B400', 2: '#A7B1BC', 3: '#CD7F32' }[rank];
            ctx.fillStyle = medal || '#E2E8F0';
            ctx.beginPath(); ctx.arc(rankX, cy, 17, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = medal ? '#FFFFFF' : '#334155';
            ctx.font = `800 ${rank >= 100 ? 13 : 16}px ${FONT}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            ctx.fillText(String(rank), rankX, cy + 1); ctx.textAlign = 'left';

            // label + parent
            if (r.parent) {
                ctx.fillStyle = '#0F172A';
                ctx.fillText(fitText(ctx, r.label, labelW, 700, 21, 16), labelX, cy - 10);
                ctx.font = `500 15px ${FONT}`; ctx.fillStyle = '#64748B';
                ctx.fillText(ellipsize(ctx, r.parent, labelW), labelX, cy + 13);
            } else {
                ctx.fillStyle = '#0F172A';
                ctx.fillText(fitText(ctx, r.label, labelW, 700, 21, 16), labelX, cy + 1);
            }

            // bar track + segments
            const bh = 30, by = cy - bh / 2;
            const total = spec.barValue(r);
            const totalW = Math.max(total > 0 ? 3 : 0, (total / maxVal) * barMax);
            ctx.save(); roundRect(ctx, barX, by, totalW, bh, 6); ctx.clip();
            let x = barX;
            series.forEach(s => {
                const v = r[s.key] || 0; if (v <= 0) return;
                const w = (v / maxVal) * barMax;
                if (multi) { ctx.fillStyle = s.color; }
                else { const g = ctx.createLinearGradient(barX, 0, barX + barMax, 0); g.addColorStop(0, s.color + 'B3'); g.addColorStop(1, s.color); ctx.fillStyle = g; }
                ctx.fillRect(x, by, w, bh);
                if (multi && w > 2) { ctx.fillStyle = '#FFFFFF'; ctx.fillRect(x + w - 1, by, 2, bh); } // 2px spacer
                if (multi && w >= 58 && spec.segLabel) {
                    ctx.font = `800 16px ${FONT}`; ctx.fillStyle = s.text || '#FFFFFF'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
                    ctx.fillText(ellipsize(ctx, spec.segLabel(v), w - 6), x + w / 2, cy + 1); ctx.textAlign = 'left';
                }
                x += w;
            });
            ctx.restore();

            // end value label
            let fs = 20; const txt = spec.endLabel(r);
            ctx.font = `800 ${fs}px ${FONT}`;
            const avail = W - PAD - (barX + totalW + 10);
            while (ctx.measureText(txt).width > avail && fs > 14) { fs--; ctx.font = `800 ${fs}px ${FONT}`; }
            ctx.fillStyle = '#0F172A'; ctx.textBaseline = 'middle';
            ctx.fillText(txt, barX + totalW + 10, cy + 1);
            ctx.textBaseline = 'alphabetic';
        });

        const from = p * per + 1, to = p * per + slice.length;
        drawFooter(ctx, W, H, rows.length ? `${spec.levelLabel || 'Rows'} ${from}–${to} of ${spec.totalCount ?? rows.length}` : '');
        out.push(c);
    }
    return out;
}

/**
 * 4-column ranked bar grid — packs ~80 rows into one WhatsApp image (1600 px wide,
 * ≤ 1600 px tall). Ranks run down column 1, then column 2, etc.
 */
function renderBarGridPages(spec) {
    const W = 1600, PAD = 40, COLS = 4, GAP = 24, ROW = 56;
    const rows = spec.rows || [];
    const maxVal = Math.max(1e-9, ...rows.map(spec.barValue));
    const series = spec.series.filter(s => rows.some(r => (r[s.key] || 0) > 0));
    const multi = series.length > 1;
    const measure = newCanvas(10, 10).getContext('2d');
    const chipsH = layoutChips(measure, spec.chips || [], W - 2 * PAD).height;
    const fixedH = IMG.HEADER + 22 + chipsH + (chipsH ? 18 : 0) + 36 + 14 + IMG.FOOTER;
    const perCol = Math.max(6, Math.floor((IMG.MAX_H - fixedH) / ROW));
    const pages = Math.max(1, Math.ceil(rows.length / (perCol * COLS)));
    const perPage = Math.ceil(rows.length / pages);
    const colW = (W - 2 * PAD - (COLS - 1) * GAP) / COLS;
    const out = [];

    for (let p = 0; p < pages; p++) {
        const slice = rows.slice(p * perPage, (p + 1) * perPage);
        const rowsInCol = Math.max(1, Math.ceil(slice.length / COLS));
        const H = fixedH + rowsInCol * ROW;
        const c = newCanvas(W, H), ctx = c.getContext('2d');
        ctx.fillStyle = '#FFFFFF'; ctx.fillRect(0, 0, W, H);
        drawHeader(ctx, W, { title: spec.title, subtitle: spec.subtitle, accent: spec.accent, pageText: pages > 1 ? `Page ${p + 1}/${pages}` : '' });
        let y = IMG.HEADER + 22;
        if (chipsH) y = drawChips(ctx, spec.chips, PAD, y, W - 2 * PAD) + 18;
        ctx.font = `700 15px ${FONT}`; ctx.fillStyle = '#94A3B8';
        ctx.fillText(`RANK • ${(spec.levelLabel || 'NAME').toUpperCase()}`, PAD, y + 20);
        ctx.textAlign = 'right'; ctx.fillText(`BAR END: ${(spec.endHint || '').toUpperCase()}`, W - PAD, y + 20); ctx.textAlign = 'left';
        y += 36;

        for (let col = 1; col < COLS; col++) {   // column dividers
            const x = PAD + col * (colW + GAP) - GAP / 2;
            ctx.strokeStyle = '#E2E8F0'; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y + rowsInCol * ROW); ctx.stroke();
        }

        slice.forEach((r, i) => {
            const col = Math.floor(i / rowsInCol), ri = i % rowsInCol;
            const x0 = PAD + col * (colW + GAP), ry = y + ri * ROW;
            if (ri % 2 === 0) { ctx.fillStyle = '#F6F8FB'; ctx.fillRect(x0 - 6, ry, colW + 12, ROW); }

            // line 1: rank badge + name (+ parent in grey if room)
            const rank = r._rank, medal = { 1: '#F4B400', 2: '#A7B1BC', 3: '#CD7F32' }[rank];
            ctx.fillStyle = medal || '#E2E8F0';
            ctx.beginPath(); ctx.arc(x0 + 13, ry + 18, 13, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = medal ? '#FFFFFF' : '#334155'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            ctx.font = `800 ${rank >= 100 ? 11 : 13}px ${FONT}`; ctx.fillText(String(rank), x0 + 13, ry + 19);
            ctx.textAlign = 'left';
            const nameX = x0 + 32, nameW = colW - 34;
            ctx.fillStyle = '#0F172A';
            const name = fitText(ctx, r.label, nameW, 700, 18, 14);
            ctx.fillText(name, nameX, ry + 19);
            if (r.parent) {
                const used = ctx.measureText(name).width + 8;
                ctx.font = `500 13px ${FONT}`;
                if (ctx.measureText(r.parent).width <= nameW - used) {   // only when it fits in full
                    ctx.fillStyle = '#64748B'; ctx.fillText(r.parent, nameX + used, ry + 20);
                }
            }

            // line 2: bar + value
            const valueW = 138, barX = nameX, barMax = colW - 32 - valueW, bh = 18, by = ry + 30;
            const total = spec.barValue(r);
            const totalW = Math.max(total > 0 ? 3 : 0, (total / maxVal) * barMax);
            ctx.save(); roundRect(ctx, barX, by, totalW, bh, 4); ctx.clip();
            let x = barX;
            series.forEach(s => {
                const v = r[s.key] || 0; if (v <= 0) return;
                const w = (v / maxVal) * barMax;
                if (multi) ctx.fillStyle = s.color;
                else { const g = ctx.createLinearGradient(barX, 0, barX + barMax, 0); g.addColorStop(0, s.color + 'B3'); g.addColorStop(1, s.color); ctx.fillStyle = g; }
                ctx.fillRect(x, by, w, bh);
                if (multi && w > 2) { ctx.fillStyle = '#FFFFFF'; ctx.fillRect(x + w - 1, by, 2, bh); }
                if (multi && w >= 34 && spec.segLabel) {
                    ctx.font = `800 12px ${FONT}`; ctx.fillStyle = s.text || '#FFFFFF'; ctx.textAlign = 'center';
                    ctx.fillText(ellipsize(ctx, fmt.num(v, 0), w - 4), x + w / 2, by + bh / 2 + 1); ctx.textAlign = 'left';
                }
                x += w;
            });
            ctx.restore();
            ctx.fillStyle = '#0F172A';
            ctx.fillText(fitText(ctx, spec.endLabel(r), colW - 32 - totalW - 8, 800, 16, 12), barX + totalW + 8, by + bh / 2 + 1);
            ctx.textBaseline = 'alphabetic';
        });

        const from = p * perPage + 1, to = p * perPage + slice.length;
        drawFooter(ctx, W, H, `${spec.levelLabel || 'Rows'} ${from}–${to} of ${spec.totalCount ?? rows.length}`);
        out.push(c);
    }
    return out;
}

/**
 * Paged table image (landscape) — for the squad summary.
 * cols: [{ title, w, align, cell(row) -> string | {text, sub, pill:{bg,fg}} }]
 */
function renderTablePages({ title, subtitle, accent, rows, cols, chips, perPage = 20, rowH = 50 }) {
    const W = 1600, PAD = 40;
    const pages = Math.max(1, Math.ceil(rows.length / perPage));
    const measure = newCanvas(10, 10).getContext('2d');
    const chipsH = layoutChips(measure, chips || [], W - 2 * PAD).height;
    const totalW = cols.reduce((a, c) => a + c.w, 0);
    const scale = (W - 2 * PAD) / totalW;
    const out = [];
    for (let p = 0; p < pages; p++) {
        const slice = rows.slice(p * perPage, (p + 1) * perPage);
        const top = IMG.HEADER + 20 + (chipsH ? chipsH + 18 : 0);
        const H = top + 48 + Math.max(1, slice.length) * rowH + 14 + IMG.FOOTER;
        const c = newCanvas(W, H), ctx = c.getContext('2d');
        ctx.fillStyle = '#FFFFFF'; ctx.fillRect(0, 0, W, H);
        drawHeader(ctx, W, { title, subtitle, accent, pageText: pages > 1 ? `Page ${p + 1}/${pages}` : '' });
        let y = IMG.HEADER + 20;
        if (chipsH) y = drawChips(ctx, chips, PAD, y, W - 2 * PAD) + 18;

        // header row
        ctx.fillStyle = '#0B2545'; ctx.fillRect(PAD, y, W - 2 * PAD, 48);
        let x = PAD;
        ctx.font = `700 18px ${FONT}`; ctx.fillStyle = '#FFFFFF'; ctx.textBaseline = 'middle';
        cols.forEach(col => {
            const w = col.w * scale;
            ctx.textAlign = col.align || 'left';
            const tx = col.align === 'right' ? x + w - 12 : col.align === 'center' ? x + w / 2 : x + 12;
            ctx.fillText(ellipsize(ctx, col.title, w - 16), tx, y + 25); x += w;
        });
        y += 48;

        slice.forEach((r, i) => {
            const ry = y + i * rowH, cy = ry + rowH / 2;
            ctx.fillStyle = i % 2 ? '#F6F8FB' : '#FFFFFF'; ctx.fillRect(PAD, ry, W - 2 * PAD, rowH);
            let x2 = PAD;
            cols.forEach(col => {
                const w = col.w * scale; let v = col.cell(r, p * perPage + i);
                if (v == null) v = '';
                const o = typeof v === 'object' ? v : { text: String(v) };
                const align = col.align || 'left';
                const tx = align === 'right' ? x2 + w - 12 : align === 'center' ? x2 + w / 2 : x2 + 12;
                ctx.textAlign = align;
                if (o.pill) {
                    ctx.font = `700 16px ${FONT}`;
                    const t = ellipsize(ctx, o.text, w - 28), pw = ctx.measureText(t).width + 20;
                    const px = align === 'center' ? x2 + (w - pw) / 2 : x2 + 10;
                    ctx.fillStyle = o.pill.bg; roundRect(ctx, px, cy - 15, pw, 30, 15); ctx.fill();
                    ctx.fillStyle = o.pill.fg; ctx.textAlign = 'left'; ctx.fillText(t, px + 10, cy + 1);
                } else if (o.sub) {
                    ctx.fillStyle = o.color || '#0F172A'; ctx.fillText(fitText(ctx, o.text, w - 20, 700, 19, 15), tx, cy - 9);
                    ctx.font = `500 14px ${FONT}`; ctx.fillStyle = '#64748B'; ctx.fillText(ellipsize(ctx, o.sub, w - 20), tx, cy + 13);
                } else {
                    ctx.fillStyle = o.color || '#0F172A';
                    ctx.fillText(fitText(ctx, o.text, w - 20, o.bold ? 800 : 600, 19, 15), tx, cy + 1);
                }
                x2 += w;
            });
        });
        // cell borders: horizontal + vertical grid and outer frame
        const gridBottom = y + slice.length * rowH;
        ctx.strokeStyle = '#B8C2D0'; ctx.lineWidth = 1.5; ctx.beginPath();
        for (let i = 1; i < slice.length; i++) { ctx.moveTo(PAD, y + i * rowH + 0.5); ctx.lineTo(W - PAD, y + i * rowH + 0.5); }
        let gx = PAD;
        cols.slice(0, -1).forEach(col => { gx += col.w * scale; ctx.moveTo(Math.round(gx) + 0.5, y - 48); ctx.lineTo(Math.round(gx) + 0.5, gridBottom); });
        ctx.stroke();
        ctx.strokeStyle = '#0B2545'; ctx.lineWidth = 2.5; ctx.strokeRect(PAD, y - 48, W - 2 * PAD, gridBottom - (y - 48));
        ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
        drawFooter(ctx, W, H, `Squads ${p * perPage + 1}–${p * perPage + slice.length} of ${rows.length}`);
        out.push(c);
    }
    return out;
}

/**
 * Share or download canvases.
 * On phones (Android/iOS, HTTPS) the native share sheet opens with the images
 * already attached → pick WhatsApp. Elsewhere the PNGs download and WhatsApp
 * opens with the summary text so the images can be attached.
 */
async function deliverImages(canvases, baseName, message, mode) {
    const stamp = getDates().to || localISODate();
    const files = [];
    for (let i = 0; i < canvases.length; i++) {
        const blob = await new Promise(res => canvases[i].toBlob(res, 'image/png'));
        const suffix = canvases.length > 1 ? `_p${i + 1}of${canvases.length}` : '';
        files.push(new File([blob], `TPSODL_${baseName}_${stamp}${suffix}.png`, { type: 'image/png' }));
    }
    if (mode === 'whatsapp' && navigator.canShare && navigator.canShare({ files })) {
        try { await navigator.share({ files, text: message }); return; }
        catch (e) { if (e && e.name === 'AbortError') return; console.warn('Native share failed, falling back to download', e); }
    }
    for (const f of files) {
        const url = URL.createObjectURL(f);
        const a = document.createElement('a'); a.href = url; a.download = f.name;
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 4000);
        if (files.length > 1) await sleep(400);
    }
    if (mode === 'whatsapp') {
        const extra = `\n\n📎 ${files.length} image${files.length > 1 ? 's' : ''} downloaded to your device — please attach ${files.length > 1 ? 'them' : 'it'} here.`;
        window.open('https://api.whatsapp.com/send?text=' + encodeURIComponent(message + extra), '_blank');
    } else {
        notify(`${files.length} image${files.length > 1 ? 's' : ''} downloaded`, 'success');
    }
}

/* ------------------------------------------------------------------ */
/* 2. Screen chart plugin: value label at the end of each bar          */
/* ------------------------------------------------------------------ */
const endLabelPlugin = {
    id: 'endLabels',
    afterDatasetsDraw(chart, _args, opts) {
        const labels = (opts && opts.labels) || [];
        const { ctx } = chart;
        ctx.save();
        ctx.font = `700 12px ${FONT}`; ctx.fillStyle = '#0F172A'; ctx.textBaseline = 'middle';
        labels.forEach((txt, i) => {
            let x = -Infinity, y = null;
            chart.data.datasets.forEach((_d, di) => {
                const meta = chart.getDatasetMeta(di);
                if (meta.hidden) return;
                const el = meta.data[i]; if (!el) return;
                x = Math.max(x, el.x); y = el.y;
            });
            if (y !== null) ctx.fillText(txt, x + 6, y);
        });
        ctx.restore();
    }
};

/* ------------------------------------------------------------------ */
/* 3. BreakdownCard — one reusable component per metric                 */
/* ------------------------------------------------------------------ */
class BreakdownCard {
    constructor({ mountId, metric, levels, level, title, subtitle, defaultView = 'all', search = true }) {
        this.mountId = mountId; this.metric = metric; this.m = METRICS[metric];
        this.levels = levels; this.level = level || levels[0];
        this.title = title || this.m.title; this.subtitle = subtitle || '';
        this.filters = {}; this.view = defaultView; this.query = '';
        this.rows = []; this.totals = {}; this.available = levels.slice();
        this.chart = null; this.search = search;
        this.build();
    }

    $(sel) { return this.root ? this.root.querySelector(sel) : null; }

    build() {
        const mount = document.getElementById(this.mountId);
        if (!mount) return;
        const id = this.mountId;
        mount.innerHTML = `
        <div class="card shadow-sm mb-4 bd-card" style="--bd-accent:${this.m.accent};--bd-tint:${this.m.tint}">
          <div class="card-header bg-white d-flex justify-content-between align-items-center flex-wrap gap-2 py-3">
            <div class="d-flex align-items-center gap-2">
              <div class="bd-icon"><i class="fa-solid ${this.m.icon}"></i></div>
              <div>
                <h6 class="fw-bold mb-0 text-dark">${esc(this.title)}</h6>
                <small class="text-muted bd-sub">${esc(this.subtitle)}</small>
              </div>
            </div>
            <div class="btn-group btn-group-sm">
              <button class="btn btn-outline-secondary fw-semibold" data-act="png" title="Download readable PNG image(s)"><i class="fa-solid fa-image me-1"></i>PNG</button>
              <button class="btn btn-whatsapp fw-semibold" data-act="wa" title="Share on WhatsApp"><i class="fa-brands fa-whatsapp me-1"></i>WhatsApp</button>
            </div>
          </div>
          <div class="card-body pt-2">
            <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-2">
              <div class="bd-levels" role="tablist"></div>
              <div class="d-flex gap-2 align-items-center">
                <select class="form-select form-select-sm bd-view" style="width:auto">
                  <option value="all">Show all</option>
                  <option value="top10">Top 10</option>
                  <option value="top25">Top 25</option>
                  <option value="bottom10">Bottom 10</option>
                  <option value="bottom25">Bottom 25</option>
                </select>
                ${this.search ? `<input type="search" class="form-control form-control-sm bd-search" placeholder="Search…" style="width:150px">` : ''}
              </div>
            </div>
            <div class="bd-crumbs mb-2"></div>
            <div class="bd-chips mb-2"></div>
            <div class="bd-scroll"><div class="bd-holder"><canvas id="${id}-canvas"></canvas></div></div>
            <div class="bd-foot small text-muted mt-2"></div>
          </div>
        </div>`;
        this.root = mount;
        this.$('.bd-view').value = this.view;
        this.$('.bd-view').addEventListener('change', e => { this.view = e.target.value; this.render(); });
        const s = this.$('.bd-search');
        if (s) s.addEventListener('input', e => { this.query = e.target.value.trim().toLowerCase(); this.render(); });
        this.$('[data-act="png"]').addEventListener('click', () => this.share('png'));
        this.$('[data-act="wa"]').addEventListener('click', () => this.share('whatsapp'));
        this.renderLevelTabs();
    }

    renderLevelTabs() {
        const box = this.$('.bd-levels'); if (!box) return;
        if (this.levels.length < 2) { box.innerHTML = ''; return; }
        box.innerHTML = this.levels.map(l => {
            const on = l === this.level, ok = this.available.includes(l);
            return `<button type="button" class="bd-tab ${on ? 'active' : ''}" data-level="${l}" ${ok ? '' : 'disabled title="Not available for this data"'}>${LEVEL_LABEL[l]}</button>`;
        }).join('');
        box.querySelectorAll('button[data-level]').forEach(b => b.addEventListener('click', () => this.setLevel(b.dataset.level)));
    }

    setLevel(level) {
        if (HIER.includes(level)) {   // keep only parent filters above the chosen level
            const idx = HIER.indexOf(level);
            HIER.forEach((h, i) => { if (i >= idx) delete this.filters[h]; });
        }
        const gc = getCircleFilterValue(); if (gc) this.filters.circle = gc;
        this.level = level; this.load();
    }

    setGlobalCircle(circle) {
        this.filters = circle ? { circle } : {};
        if (circle && this.level === 'circle' && this.levels.includes('division')) this.level = 'division';
        if (!circle && HIER.includes(this.level) && this.levels.includes('circle')) this.level = 'circle';
    }

    drill(row) {
        const next = NEXT_LEVEL[this.level];
        if (!next || !this.levels.includes(next) || !this.available.includes(next)) return;
        this.filters[this.level] = row.label;
        this.level = next; this.load();
    }

    scopeParts() {
        const parts = [];
        parts.push(this.filters.circle || 'All Circles');
        if (this.filters.division) parts.push(this.filters.division);
        if (this.filters.subdivision) parts.push(this.filters.subdivision);
        return parts;
    }

    renderCrumbs() {
        const box = this.$('.bd-crumbs'); if (!box) return;
        if (!HIER.includes(this.level) && !this.filters.circle && !this.filters.division) { box.innerHTML = ''; return; }
        const gc = getCircleFilterValue();
        const items = [];
        items.push(`<a href="#" data-to="circle" class="${gc ? 'disabled' : ''}"><i class="fa-solid fa-sitemap me-1"></i>All Circles</a>`);
        if (this.filters.circle) items.push(`<a href="#" data-to="division">${esc(this.filters.circle)}</a>`);
        if (this.filters.division) items.push(`<a href="#" data-to="subdivision">${esc(this.filters.division)}</a>`);
        if (this.filters.subdivision) items.push(`<a href="#" data-to="section">${esc(this.filters.subdivision)}</a>`);
        items.push(`<span class="cur">${LEVEL_LABEL[this.level]}-wise</span>`);
        box.innerHTML = `<div class="bd-crumb">${items.join('<i class="fa-solid fa-chevron-right sep"></i>')}</div>`;
        box.querySelectorAll('a[data-to]').forEach(a => a.addEventListener('click', e => {
            e.preventDefault(); if (a.classList.contains('disabled')) return; this.setLevel(a.dataset.to);
        }));
    }

    async load() {
        const { from, to } = getDates();
        const p = new URLSearchParams({ metric: this.metric, level: this.level, from_date: from, to_date: to });
        const gc = getCircleFilterValue();
        if (gc) this.filters.circle = gc;
        ['circle', 'division', 'subdivision'].forEach(k => { if (this.filters[k]) p.set(k, this.filters[k]); });
        const holder = this.$('.bd-holder');
        if (holder) holder.classList.add('loading');
        try {
            const res = await fetch(`/api/analytics/charts/breakdown?${p}`);
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || res.statusText);
            this.available = data.available_levels || this.levels;
            this.rows = (data.rows || []).map((r, i) => ({ ...r, _rank: i + 1 }));
            this.totals = data.totals || {};
        } catch (err) {
            console.error(`Breakdown ${this.metric}/${this.level} failed:`, err);
            this.rows = []; this.totals = {};
        } finally {
            if (holder) holder.classList.remove('loading');
        }
        this.renderLevelTabs(); this.renderCrumbs(); this.render();
    }

    visibleRows() {
        let rows = this.rows;
        if (this.query) rows = rows.filter(r => `${r.label} ${r.parent || ''}`.toLowerCase().includes(this.query));
        const v = this.view;
        if (v.startsWith('top')) rows = rows.slice(0, +v.slice(3));
        if (v.startsWith('bottom')) rows = rows.slice(-(+v.slice(6))).reverse();
        return rows;
    }

    render() {
        const rows = this.visibleRows();
        const m = this.m;
        // summary chips (totals + theft-type legend)
        const chipsBox = this.$('.bd-chips');
        if (chipsBox) {
            chipsBox.innerHTML = this.rows.length ? m.chips(this.totals).map(c => `
                <span class="bd-chip">${c.color ? `<i style="background:${c.color}"></i>` : ''}
                  <small>${esc(c.label)}</small><b>${esc(c.value)}</b></span>`).join('') : '';
        }
        const sub = this.$('.bd-sub');
        if (sub) sub.textContent = `${LEVEL_LABEL[this.level]}-wise • ${this.scopeParts().join(' › ')} • ${this.rows.length} ${LEVEL_LABEL[this.level].toLowerCase()}${this.rows.length === 1 ? '' : 's'}`;
        const foot = this.$('.bd-foot');
        if (foot) {
            const canDrill = NEXT_LEVEL[this.level] && this.levels.includes(NEXT_LEVEL[this.level]);
            foot.innerHTML = `Bar end shows <b>${m.endHint}</b>. ${canDrill ? `<i class="fa-solid fa-hand-pointer ms-1"></i> Tap a bar to open its ${LEVEL_LABEL[NEXT_LEVEL[this.level]].toLowerCase()}s.` : ''}`;
        }

        const canvas = document.getElementById(`${this.mountId}-canvas`);
        const holder = this.$('.bd-holder');
        if (!canvas || !holder || typeof Chart === 'undefined') return;
        if (this.chart) { this.chart.destroy(); this.chart = null; }
        holder.querySelector('.bd-empty')?.remove();
        if (!rows.length) {
            holder.style.height = '120px';
            holder.insertAdjacentHTML('beforeend', `<div class="bd-empty">No ${m.short.toLowerCase()} records for this selection.</div>`);
            return;
        }
        holder.style.height = `${Math.max(220, rows.length * 34 + 56)}px`;

        const series = m.series.filter(s => rows.some(r => (r[s.key] || 0) > 0));
        const multi = series.length > 1;
        const datasets = series.map(s => ({
            label: s.label,
            data: rows.map(r => r[s.key] || 0),
            backgroundColor: s.color,
            borderColor: '#FFFFFF', borderWidth: multi ? { right: 2 } : 0, borderSkipped: false,
            borderRadius: multi ? 0 : 4,
            stack: 'one', barPercentage: 0.82, categoryPercentage: 0.9,
            datalabels: multi ? {
                display: ctx => {
                    const el = ctx.chart.getDatasetMeta(ctx.datasetIndex).data[ctx.dataIndex];
                    return !!el && ctx.dataset.data[ctx.dataIndex] > 0 && Math.abs(el.x - el.base) > 40;
                },
                color: s.text, anchor: 'center', align: 'center', clamp: true,
                font: { size: 11, weight: 'bold' }, formatter: v => m.segLabel(v)
            } : { display: false }
        }));
        const self = this;
        this.chart = new Chart(canvas, {
            type: 'bar',
            data: { labels: rows.map(r => r.label), datasets },
            plugins: [endLabelPlugin],
            options: {
                indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                animation: { duration: 350 },
                layout: { padding: { right: 170 } },
                interaction: { mode: 'index', axis: 'y', intersect: false },
                onHover: (e, els) => {
                    const ok = els.length && NEXT_LEVEL[self.level] && self.levels.includes(NEXT_LEVEL[self.level]);
                    e.native.target.style.cursor = ok ? 'pointer' : 'default';
                },
                onClick: (_e, els) => { if (els.length) self.drill(rows[els[0].index]); },
                plugins: {
                    legend: { display: false },
                    endLabels: { labels: rows.map(m.endLabel) },
                    tooltip: {
                        backgroundColor: '#0F172A', padding: 10, titleFont: { size: 13, weight: 'bold' }, bodyFont: { size: 12 },
                        callbacks: {
                            title: items => { const r = rows[items[0].dataIndex]; return `#${r._rank}  ${r.label}${r.parent ? `  (${r.parent})` : ''}`; },
                            label: ctx => multi ? `${ctx.dataset.label}: ${fmt.num(ctx.raw, 2)} kW` : null,
                            afterBody: items => m.tooltip(rows[items[0].dataIndex])
                        }
                    }
                },
                scales: {
                    x: { stacked: true, beginAtZero: true, grid: { color: '#EEF2F7' }, border: { display: false },
                         ticks: { color: '#64748B', font: { size: 11 }, callback: v => m.axis(v), maxTicksLimit: 6 } },
                    y: { stacked: true, grid: { display: false }, border: { display: false },
                         ticks: { autoSkip: false, color: '#0F172A', font: { size: 12, weight: '600' },
                                  callback: (_v, i) => { const r = rows[i]; if (!r) return ''; const t = `${r._rank}. ${r.label}`; return t.length > 30 ? t.slice(0, 29) + '…' : t; } } }
                }
            }
        });
    }

    async share(mode) {
        const rows = this.visibleRows();
        const viewTxt = { all: '', top10: 'Top 10 • ', top25: 'Top 25 • ', bottom10: 'Bottom 10 • ', bottom25: 'Bottom 25 • ' }[this.view] || '';
        const levelLabel = LEVEL_LABEL[this.level];
        // > 25 rows → 4-column grid (≈80 per image); otherwise the large single-column layout
        const pages = (rows.length > 25 ? renderBarGridPages : renderBarPages)({
            title: `${this.m.short} — ${levelLabel}-wise`,
            subtitle: `${viewTxt}${this.scopeParts().join(' › ')}  •  ${periodText()}`,
            accent: this.m.accent, rows, series: this.m.series,
            barValue: this.m.barValue, endLabel: this.m.endLabel, segLabel: this.m.segLabel,
            chips: this.m.chips(this.totals), levelLabel, endHint: this.m.endHint, totalCount: rows.length
        });
        const t = this.totals, m = this.metric;
        const headline = m === 'load' ? `⚡ Total: ${fmt.kw(t.total_load)} (${fmt.num(t.cases)} theft cases)`
            : m === 'dc' ? `🔌 DC: ${fmt.num(t.dc_count)} consumers (${fmt.inr(t.dc_amount)} arrears)`
            : `💰 Collection: ${fmt.inr(t.amount)} (${fmt.num(t.mr_count)} MR)`;
        const msg = `*TPSODL Enforcement — ${this.m.short} ${levelLabel}-wise*\n📅 ${periodText()}  |  ${this.scopeParts().join(' › ')}\n${headline}`;
        await deliverImages(pages, `${this.m.short.replace(/\s+/g, '')}_${levelLabel.replace(/[^A-Za-z]/g, '')}`, msg, mode);
    }
}

/* ------------------------------------------------------------------ */
/* 4. Page state & boot                                                */
/* ------------------------------------------------------------------ */
const dash = { kpis: {}, exec: { level: 'circle', rows: [] }, squad: { rows: [], counts: {} }, cards: [] };

document.addEventListener('DOMContentLoaded', () => {
    const today = localISODate();
    const fromEl = document.getElementById('dashFromDate'), toEl = document.getElementById('dashToDate');
    if (fromEl && !fromEl.value) fromEl.value = today;
    if (toEl && !toEl.value) toEl.value = today;

    dash.cards = [
        new BreakdownCard({ mountId: 'bdLoad', metric: 'load', levels: ['circle', 'division', 'subdivision', 'section', 'team'],
            title: 'Load Booking — Theft Type Breakdown' }),
        new BreakdownCard({ mountId: 'bdDC', metric: 'dc', levels: ['circle', 'division', 'subdivision', 'section', 'team'],
            title: 'Disconnections (DC) & Arrears Involved' }),
        new BreakdownCard({ mountId: 'bdColl', metric: 'collection', levels: ['circle', 'division', 'subdivision', 'section', 'team'],
            title: 'Collection Realization' }),
        new BreakdownCard({ mountId: 'bdCollector', metric: 'collection', levels: ['collector'], level: 'collector',
            title: 'Collector-wise Collection (Ranked)', defaultView: 'all' })
    ];

    const cEl = getCircleFilterEl();
    document.getElementById('squadCircleFilter')?.addEventListener('change', renderSquadTable);
    if (cEl) {
        cEl.disabled = false; cEl.removeAttribute('disabled');
        cEl.addEventListener('change', () => refreshDashboard());
    }
    refreshDashboard();
});

async function refreshDashboard() {
    const { from, to } = getDates();
    const circle = getCircleFilterValue();
    const execDateEl = document.getElementById('execSummaryDate');
    if (execDateEl) execDateEl.innerText = periodText();
    const execCircleEl = document.getElementById('execSummaryCircle');
    if (execCircleEl) execCircleEl.innerText = circle || 'ALL CIRCLES';

    dash.cards.forEach(c => c.setGlobalCircle(circle));
    btnBusy('btnRefreshDash', true);
    try {
        await Promise.all([
            loadKPIs(from, to, circle),
            loadExecBreakdown(from, to, circle),
            loadSquadPerformance(from, to, circle),
            ...dash.cards.map(c => c.load())
        ]);
        notify('Dashboard analytics refreshed!');
    } catch (err) {
        console.error('Dashboard error:', err);
        notify('Failed to refresh some dashboard components', 'danger');
    } finally {
        btnBusy('btnRefreshDash', false, '<i class="fa-solid fa-arrows-rotate me-1"></i> Apply Filter');
    }
}

/* ------------------------------------------------------------------ */
/* 5. KPIs + executive circle/division table                           */
/* ------------------------------------------------------------------ */
async function loadKPIs(from, to, circle) {
    let url = `/api/analytics/kpis?from_date=${from}&to_date=${to}`;
    if (circle) url += `&circle=${encodeURIComponent(circle)}`;
    const data = await (await fetch(url)).json();
    dash.kpis = data;
    const set = (id, v) => { const el = document.getElementById(id); if (el) el.innerText = v; };
    set('kpiLoadBooked', fmt.kw(data.total_load_kw));
    set('kpiTheftCount', fmt.num(data.total_theft_cases));
    set('kpiCollection', fmt.inr(data.total_collection_amount));
    set('kpiMRCount', fmt.num(data.total_mr_count));
    set('kpiDCCount', fmt.num(data.total_dc_count));
    set('kpiDCAmount', fmt.inr(data.total_dc_amount));
}

async function loadExecBreakdown(from, to, circle) {
    const level = circle ? 'division' : 'circle';
    const get = async metric => {
        const p = new URLSearchParams({ metric, level, from_date: from, to_date: to });
        if (circle) p.set('circle', circle);
        try { const r = await fetch(`/api/analytics/charts/breakdown?${p}`); return r.ok ? (await r.json()).rows || [] : []; }
        catch { return []; }
    };
    const [lb, dc, co] = await Promise.all([get('load'), get('dc'), get('collection')]);
    const map = new Map();
    const row = l => { if (!map.has(l)) map.set(l, { label: l, total_load: 0, cases: 0, amount: 0, mr_count: 0, dc_count: 0, dc_amount: 0 }); return map.get(l); };
    lb.forEach(r => Object.assign(row(r.label), { total_load: r.total_load, cases: r.cases }));
    co.forEach(r => Object.assign(row(r.label), { amount: r.amount, mr_count: r.mr_count }));
    dc.forEach(r => Object.assign(row(r.label), { dc_count: r.dc_count, dc_amount: r.dc_amount }));
    dash.exec = { level, rows: [...map.values()].sort((a, b) => b.total_load - a.total_load || b.amount - a.amount) };
    renderExecTable();
}

function renderExecTable() {
    const box = document.getElementById('execCircleBreakdownRow');
    if (!box) return;
    const { level, rows } = dash.exec;
    if (!rows.length) { box.innerHTML = '<div class="col-12 text-muted small py-2">No activity recorded for this period.</div>'; return; }
    const tot = rows.reduce((a, r) => { ['total_load', 'cases', 'amount', 'mr_count', 'dc_count', 'dc_amount'].forEach(k => a[k] += r[k] || 0); return a; },
        { total_load: 0, cases: 0, amount: 0, mr_count: 0, dc_count: 0, dc_amount: 0 });
    const tr = (r, cls = '') => `<tr class="${cls}"><td class="text-start fw-bold">${esc(r.label)}</td>
        <td>${fmt.kw(r.total_load)}</td><td>${fmt.num(r.cases)}</td><td>${fmt.inr(r.amount)}</td>
        <td>${fmt.num(r.mr_count)}</td><td>${fmt.num(r.dc_count)}</td><td>${fmt.inr(r.dc_amount)}</td></tr>`;
    box.innerHTML = `<div class="col-12"><div class="table-responsive"><table class="table table-sm exec-table mb-0 text-end align-middle">
        <thead><tr><th class="text-start">${LEVEL_LABEL[level]}</th><th>Load Booked</th><th>Cases</th><th>Collection</th><th>MR</th><th>DC</th><th>DC Arrears</th></tr></thead>
        <tbody>${rows.map(r => tr(r)).join('')}${tr({ label: 'TOTAL', ...tot }, 'exec-total')}</tbody></table></div></div>`;
}

function renderExecPoster() {
    const W = 1080, PAD = 40, k = dash.kpis || {};
    const circle = getCircleFilterValue() || 'ALL CIRCLES';
    const c = dash.squad.counts || {};
    const active = (c.INDEPENDENT_WITH_TL || 0) + (c.INDEPENDENT_WITHOUT_TL_COLLECTION || 0) + (c.MERGED || 0);
    const tiles = [
        { t: 'LOAD BOOKED', v: fmt.kw(k.total_load_kw), s: `${fmt.num(k.total_theft_cases)} theft cases`, bg: '#1D4ED8' },
        { t: 'COLLECTION', v: fmt.inr(k.total_collection_amount), s: `${fmt.num(k.total_mr_count)} MR receipts`, bg: '#0E8A5F' },
        { t: 'DC EXECUTED', v: fmt.num(k.total_dc_count), s: `${fmt.inr(k.total_dc_amount)} arrears`, bg: '#B91C1C' },
        { t: 'ACTIVE SQUADS', v: fmt.num(active), s: `of ${fmt.num((dash.squad.rows || []).length)} squads`, bg: '#C2410C' },
        { t: 'THEFT CASES', v: fmt.num(k.total_theft_cases), s: 'detected', bg: '#7B3FC4' },
        { t: 'MR RECEIPTS', v: fmt.num(k.total_mr_count), s: 'issued', bg: '#334155' }
    ];
    const rows = dash.exec.rows || [];
    const tileH = 150, rowH = 52;
    const H = IMG.HEADER + 30 + 2 * tileH + 16 + 30 + 52 + (rows.length + 1) * rowH + 30 + IMG.FOOTER;
    const cv = newCanvas(W, H), ctx = cv.getContext('2d');
    ctx.fillStyle = '#FFFFFF'; ctx.fillRect(0, 0, W, H);
    drawHeader(ctx, W, { title: 'Daily Enforcement Performance', subtitle: `${circle}  •  ${periodText()}`, accent: '#F4B400' });
    let y = IMG.HEADER + 30;
    const tw = (W - 2 * PAD - 2 * 16) / 3;
    tiles.forEach((t, i) => {
        const x = PAD + (i % 3) * (tw + 16), ty = y + Math.floor(i / 3) * (tileH + 16);
        ctx.fillStyle = t.bg; roundRect(ctx, x, ty, tw, tileH, 16); ctx.fill();
        ctx.fillStyle = 'rgba(255,255,255,0.8)'; ctx.font = `700 18px ${FONT}`; ctx.fillText(t.t, x + 20, ty + 36);
        ctx.fillStyle = '#FFFFFF'; let fs = 40; ctx.font = `800 ${fs}px ${FONT}`;
        while (ctx.measureText(t.v).width > tw - 40 && fs > 24) { fs -= 2; ctx.font = `800 ${fs}px ${FONT}`; }
        ctx.fillText(t.v, x + 20, ty + 90);
        ctx.fillStyle = 'rgba(255,255,255,0.85)'; ctx.font = `600 18px ${FONT}`; ctx.fillText(ellipsize(ctx, t.s, tw - 40), x + 20, ty + 126);
    });
    y += 2 * tileH + 16 + 30;

    const cols = [
        { t: LEVEL_LABEL[dash.exec.level], w: 230, a: 'left', f: r => r.label },
        { t: 'Load', w: 150, f: r => fmt.kw(r.total_load) }, { t: 'Cases', w: 90, f: r => fmt.num(r.cases) },
        { t: 'Collection', w: 150, f: r => fmt.inr(r.amount) }, { t: 'MR', w: 80, f: r => fmt.num(r.mr_count) },
        { t: 'DC', w: 80, f: r => fmt.num(r.dc_count) }, { t: 'DC Arrears', w: 140, f: r => fmt.inr(r.dc_amount) }
    ];
    const scale = (W - 2 * PAD) / cols.reduce((a, c2) => a + c2.w, 0);
    ctx.fillStyle = '#0B2545'; roundRect(ctx, PAD, y, W - 2 * PAD, 52, 8); ctx.fill();
    ctx.textBaseline = 'middle';
    let x = PAD; ctx.font = `700 19px ${FONT}`; ctx.fillStyle = '#FFFFFF';
    cols.forEach(cl => { const w = cl.w * scale; ctx.textAlign = cl.a || 'right'; ctx.fillText(cl.t, cl.a === 'left' ? x + 14 : x + w - 14, y + 27); x += w; });
    y += 52;
    const tot = rows.reduce((a, r) => { ['total_load', 'cases', 'amount', 'mr_count', 'dc_count', 'dc_amount'].forEach(kk => a[kk] += r[kk] || 0); return a; },
        { label: 'TOTAL', total_load: 0, cases: 0, amount: 0, mr_count: 0, dc_count: 0, dc_amount: 0 });
    [...rows, tot].forEach((r, i) => {
        const isTot = i === rows.length;
        ctx.fillStyle = isTot ? '#DCE6F2' : (i % 2 ? '#F6F8FB' : '#FFFFFF'); ctx.fillRect(PAD, y, W - 2 * PAD, rowH);
        let x2 = PAD;
        cols.forEach(cl => {
            const w = cl.w * scale; ctx.textAlign = cl.a || 'right';
            ctx.font = `${isTot || cl.a === 'left' ? 800 : 600} 20px ${FONT}`; ctx.fillStyle = '#0F172A';
            ctx.fillText(ellipsize(ctx, cl.f(r), w - 20), cl.a === 'left' ? x2 + 14 : x2 + w - 14, y + rowH / 2 + 1); x2 += w;
        });
        y += rowH;
    });
    ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
    drawFooter(ctx, W, H, '');
    return cv;
}

async function shareDashboardWhatsApp(mode = 'whatsapp') {
    btnBusy('btnShareWhatsApp', true);
    try {
        const k = dash.kpis || {}, c = dash.squad.counts || {};
        const active = (c.INDEPENDENT_WITH_TL || 0) + (c.INDEPENDENT_WITHOUT_TL_COLLECTION || 0) + (c.MERGED || 0);
        const msg = `*TPSODL ENFORCEMENT DAILY PERFORMANCE SUMMARY*
📅 ${periodText()} (${getCircleFilterValue() || 'ALL CIRCLES'})
⚡ Load Booked: ${fmt.kw(k.total_load_kw)} (${fmt.num(k.total_theft_cases)} cases)
💰 Collection: ${fmt.inr(k.total_collection_amount)} (${fmt.num(k.total_mr_count)} MR)
🔌 DC: ${fmt.num(k.total_dc_count)} consumers (${fmt.inr(k.total_dc_amount)})
🚗 Active Squads: ${active}`;
        await deliverImages([renderExecPoster()], 'Daily_Enforcement_Summary', msg, mode);
    } catch (err) {
        console.error('Share failed:', err); notify('Could not create the summary image', 'danger');
    } finally {
        btnBusy('btnShareWhatsApp', false, '<i class="fa-brands fa-whatsapp me-1 fs-6"></i> Share on WhatsApp');
    }
}

/* ------------------------------------------------------------------ */
/* 6. Daily Squad Operations & Performance Summary                     */
/* ------------------------------------------------------------------ */
const MODE_STYLE = {
    INDEPENDENT_WITH_TL: { t: 'Active with TL', bg: '#DCFCE7', fg: '#166534', cls: 'badge-independent-tl' },
    INDEPENDENT_WITHOUT_TL_COLLECTION: { t: 'Collection Only', bg: '#DBEAFE', fg: '#1E40AF', cls: 'badge-independent-coll' },
    MERGED: { t: 'Merged', bg: '#FEF3C7', fg: '#92400E', cls: 'badge-merged' },
    OFFICE_DUTY_NO_VEHICLE: { t: 'Office (No Veh)', bg: '#E2E8F0', fg: '#334155', cls: 'bg-secondary' },
    NON_OPERATIONAL: { t: 'Non-Operational', bg: '#FEE2E2', fg: '#991B1B', cls: 'badge-non-op' },
    UNREPORTED: { t: 'Unreported', bg: '#F1F5F9', fg: '#64748B', cls: 'bg-light text-muted border' }
};

// Employee codes are not shown: "Sanjay Behera (TL101)" -> "Sanjay Behera"
function stripCode(name) {
    const s = String(name ?? '').replace(/\s*[(\[][^()\[\]]*[)\]]\s*$/, '').trim();
    return s || String(name ?? '');
}
function squadCircle() { const el = document.getElementById('squadCircleFilter'); return el ? el.value : ''; }
function squadRows() {
    const c = squadCircle(), rows = dash.squad.rows || [];
    return c ? rows.filter(r => String(r.circle || '').toUpperCase() === c.toUpperCase()) : rows;
}
function squadCounts(rows) {
    const k = { INDEPENDENT_WITH_TL: 0, INDEPENDENT_WITHOUT_TL_COLLECTION: 0, MERGED: 0, OFFICE_DUTY_NO_VEHICLE: 0, NON_OPERATIONAL: 0, UNREPORTED: 0 };
    rows.forEach(r => { const m = r.operation_mode in k ? r.operation_mode : 'UNREPORTED'; k[m]++; });
    return k;
}
function fillSquadCircleOptions() {
    const sel = document.getElementById('squadCircleFilter'); if (!sel) return;
    const keep = sel.value;
    const circles = [...new Set((dash.squad.rows || []).map(r => r.circle).filter(Boolean))].sort();
    sel.innerHTML = `<option value="">All Circles (${(dash.squad.rows || []).length})</option>` +
        circles.map(c => `<option value="${esc(c)}">${esc(c)} (${dash.squad.rows.filter(r => r.circle === c).length})</option>`).join('');
    sel.value = circles.includes(keep) ? keep : '';
}

async function loadSquadPerformance(from, to, circle) {
    let url = `/api/analytics/squad-performance?from_date=${from}&to_date=${to}`;
    if (circle) url += `&circle=${encodeURIComponent(circle)}`;
    const tbody = document.getElementById('squadMasterSummaryBody') || document.getElementById('squadPerformanceBody');
    if (!tbody) return;
    try {
        const data = await (await fetch(url)).json();
        const counts = data.counts || {};
        dash.squad = { rows: data.rows || [], counts };
        // Top KPI card always reflects the page-level filter
        const active = (counts.INDEPENDENT_WITH_TL || 0) + (counts.INDEPENDENT_WITHOUT_TL_COLLECTION || 0) + (counts.MERGED || 0);
        const setK = (id, v) => { const el = document.getElementById(id); if (el) el.innerText = v || 0; };
        setK('kpiActiveSquads', active);
        setK('kpiTotalSquads', dash.squad.rows.length);
        fillSquadCircleOptions();
        renderSquadTable();
    } catch (err) {
        console.error('Failed to load squad performance:', err);
        tbody.innerHTML = '<tr><td colspan="10" class="text-center text-danger py-4">Error loading squad performance summary.</td></tr>';
    }
}

function renderSquadTable() {
    const tbody = document.getElementById('squadMasterSummaryBody') || document.getElementById('squadPerformanceBody');
    if (!tbody) return;
    const rows = squadRows(), counts = squadCounts(rows);
    const setC = (id, v) => { const el = document.getElementById(id); if (el) el.innerText = v || 0; };
    setC('cntActiveTL', counts.INDEPENDENT_WITH_TL); setC('cntActiveColl', counts.INDEPENDENT_WITHOUT_TL_COLLECTION);
    setC('cntMerged', counts.MERGED); setC('cntOfficeDuty', counts.OFFICE_DUTY_NO_VEHICLE);
    setC('cntNonOp', counts.NON_OPERATIONAL); setC('cntUnreported', counts.UNREPORTED);
    if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="11" class="text-center text-muted py-4">No squad operations data recorded for this selection.</td></tr>';
        return;
    }
    const tot = { km: 0, kw: 0, cases: 0, dc: 0, dcAmt: 0, coll: 0 };
    tbody.innerHTML = rows.map((r, i) => {
        const ms = MODE_STYLE[r.is_office ? 'OFFICE_DUTY_NO_VEHICLE' : r.operation_mode] || MODE_STYLE.UNREPORTED;
        const badge = `<span class="badge ${ms.cls}">${ms.t}</span>${r.operation_mode === 'MERGED' && r.merged_status ? `<small class="text-muted d-block">${esc(r.merged_status)}</small>` : ''}`;
        if (!r.is_office) { tot.km += +r.km_run || 0; tot.kw += +r.load_booked_kw || 0; tot.cases += +r.theft_cases || 0; tot.dc += +r.dc_count || 0; tot.dcAmt += +r.dc_amount || 0; tot.coll += +r.amount_collected || 0; }
        return `<tr>
            <td class="text-center text-muted">${i + 1}</td>
            <td><span class="fw-bold text-dark">${esc(r.team_name)}</span>${r.is_office ? '<span class="badge bg-secondary-subtle text-secondary ms-1" style="font-size:.68rem">OFFICE</span>' : ''}</td>
            <td><span class="badge bg-light text-primary border">${esc(r.circle)}</span></td>
            <td><span class="fw-semibold text-dark">${esc(stripCode(r.operated_by_tl) || 'Unassigned')}</span></td>
            <td>${badge}</td>
            <td class="text-center fw-bold">${esc(r.form_d_attendance || '- / -')}</td>
            <td class="text-center">${r.is_office ? '-' : fmt.num(r.km_run)}</td>
            <td class="text-end fw-semibold">${r.is_office ? '-' : `${fmt.kw(r.load_booked_kw)} <small class="text-muted">(${r.theft_cases})</small>`}</td>
            <td class="text-end fw-semibold text-danger">${r.is_office ? '-' : `${r.dc_count} <small class="text-muted">/ ${fmt.inr(r.dc_amount)}</small>`}</td>
            <td class="text-end fw-bold text-success">${r.is_office ? '-' : fmt.inr(r.amount_collected)}</td>
            <td><small class="text-muted">${esc(r.remarks || '-')}</small></td>
        </tr>`;
    }).join('') + `<tr class="squad-total">
            <td></td><td colspan="5">TOTAL — ${rows.length} squads${squadCircle() ? ` (${esc(squadCircle())})` : ''}</td>
            <td class="text-center">${fmt.num(tot.km)}</td>
            <td class="text-end">${fmt.kw(tot.kw)} (${fmt.num(tot.cases)})</td>
            <td class="text-end">${fmt.num(tot.dc)} / ${fmt.inr(tot.dcAmt)}</td>
            <td class="text-end">${fmt.inr(tot.coll)}</td><td></td></tr>`;
}

function exportSquadExcel() {
    const { from, to } = getDates();
    const circle = squadCircle() || getCircleFilterValue();
    let url = `/api/analytics/squad-performance/export?from_date=${from}&to_date=${to}`;
    if (circle) url += `&circle=${encodeURIComponent(circle)}`;
    window.location.href = url;
}

async function shareSquadTable(mode = 'whatsapp') {
    const rows = squadRows(), c = squadCounts(rows);
    const scope = squadCircle() || getCircleFilterValue() || 'ALL CIRCLES';
    if (!rows.length) { notify('No squad data to share', 'warning'); return; }
    const cols = [
        { title: '#', w: 46, align: 'center', cell: (_r, i) => i + 1 },
        { title: 'Squad', w: 220, cell: r => ({ text: r.team_name, sub: r.circle }) },
        { title: 'Operated By (TL)', w: 280, cell: r => stripCode(r.operated_by_tl) || 'Unassigned' },
        { title: 'Mode', w: 175, cell: r => { const s = MODE_STYLE[r.is_office ? 'OFFICE_DUTY_NO_VEHICLE' : r.operation_mode] || MODE_STYLE.UNREPORTED; return { text: s.t, pill: { bg: s.bg, fg: s.fg } }; } },
        { title: 'Form D', w: 86, align: 'center', cell: r => r.form_d_attendance || '-' },
        { title: 'KM', w: 80, align: 'right', cell: r => r.is_office ? '-' : fmt.num(r.km_run) },
        { title: 'Load (Cases)', w: 165, align: 'right', cell: r => r.is_office ? '-' : `${fmt.kw(r.load_booked_kw)} (${r.theft_cases})` },
        { title: 'DC / Arrears', w: 165, align: 'right', cell: r => r.is_office ? '-' : `${r.dc_count} / ${fmt.inr(r.dc_amount)}` },
        { title: 'Collection', w: 150, align: 'right', cell: r => r.is_office ? '-' : { text: fmt.inr(r.amount_collected), bold: true, color: '#0E7A53' } }
    ];
    const chips = [
        { label: 'Active with TL', value: fmt.num(c.INDEPENDENT_WITH_TL), color: '#16A34A' },
        { label: 'Collection Only', value: fmt.num(c.INDEPENDENT_WITHOUT_TL_COLLECTION), color: '#2563EB' },
        { label: 'Merged', value: fmt.num(c.MERGED), color: '#D97706' },
        { label: 'Office (No Veh)', value: fmt.num(c.OFFICE_DUTY_NO_VEHICLE), color: '#64748B' },
        { label: 'Non-Operational', value: fmt.num(c.NON_OPERATIONAL), color: '#DC2626' },
        { label: 'Unreported', value: fmt.num(c.UNREPORTED), color: '#CBD5E1' }
    ];
    const pages = renderTablePages({
        title: 'Daily Squad Operations & Performance Summary',
        subtitle: `${scope}  •  ${periodText()}  •  ${rows.length} squads`,
        accent: '#F4B400', rows, cols, chips
    });
    const msg = `*TPSODL — Daily Squad Operations & Performance*\n📅 ${periodText()} (${scope})\n🚗 ${rows.length} squads: ${c.INDEPENDENT_WITH_TL || 0} with TL, ${c.INDEPENDENT_WITHOUT_TL_COLLECTION || 0} collection-only, ${c.MERGED || 0} merged, ${c.NON_OPERATIONAL || 0} non-op, ${c.UNREPORTED || 0} unreported`;
    await deliverImages(pages, `Squad_Operations_Summary${squadCircle() ? '_' + squadCircle().replace(/\s+/g, '_') : ''}`, msg, mode);
}

/* ------------------------------------------------------------------ */
/* 7. Existing exports kept                                            */
/* ------------------------------------------------------------------ */
function exportDashLoadBookings(format) {
    const { from, to } = getDates();
    const circle = getCircleFilterValue();
    let url = `/api/reports/load-bookings/export?format=${format}&from_date=${from}&to_date=${to}`;
    if (circle) url += `&circle=${encodeURIComponent(circle)}`;
    window.location.href = url;
}

// Legacy helpers (kept so older buttons elsewhere keep working)
async function downloadCardAsImage(cardId, filename) {
    const card = document.getElementById(cardId);
    if (!card || typeof html2canvas === 'undefined') return;
    const canvas = await html2canvas(card, { scale: 2, useCORS: true, backgroundColor: '#ffffff' });
    await deliverImages([canvas], filename, '', 'png');
}
async function shareCardWhatsApp(cardId, title) {
    const card = document.getElementById(cardId);
    if (!card || typeof html2canvas === 'undefined') return;
    const canvas = await html2canvas(card, { scale: 2, useCORS: true, backgroundColor: '#ffffff' });
    await deliverImages([canvas], title.replace(/\s+/g, '_'), `*TPSODL Enforcement MIS*\n📊 ${title}`, 'whatsapp');
}