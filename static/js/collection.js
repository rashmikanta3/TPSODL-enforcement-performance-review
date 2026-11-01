// Field Collection Register & Upload Desk Logic

document.addEventListener('DOMContentLoaded', () => {
    // Default dates to current month range
    const now = new Date();
    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().split('T')[0];
    const today = now.toISOString().split('T')[0];

    const fromInput = document.getElementById('coll-from-date');
    const toInput = document.getElementById('coll-to-date');

    if (fromInput) fromInput.value = firstDay;
    if (toInput) toInput.value = today;

    if (typeof populateOperationalCircleSelect === 'function') {
        populateOperationalCircleSelect('coll-filter-circle', loadCollectionStats, { includeAllOption: true });
    } else {
        loadCollectionStats();
    }
});

function downloadCollectionTemplate() {
    window.location.href = '/api/collection/template';
}

function resetCollectionFilters() {
    const now = new Date();
    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1).toISOString().split('T')[0];
    const today = now.toISOString().split('T')[0];

    document.getElementById('coll-from-date').value = firstDay;
    document.getElementById('coll-to-date').value = today;

    if (typeof populateOperationalCircleSelect === 'function') {
        populateOperationalCircleSelect('coll-filter-circle', loadCollectionStats, { includeAllOption: true });
    } else {
        document.getElementById('coll-filter-circle').value = 'ALL';
        loadCollectionStats();
    }
}

async function loadCollectionStats() {
    const circle = document.getElementById('coll-filter-circle').value;
    const fromDate = document.getElementById('coll-from-date').value;
    const toDate = document.getElementById('coll-to-date').value;

    let url = `/api/collection/stats?circle=${encodeURIComponent(circle)}`;
    if (fromDate) url += `&from_date=${fromDate}`;
    if (toDate) url += `&to_date=${toDate}`;

    try {
        const res = await fetch(url);
        const data = await res.json();

        document.getElementById('stat-total-amt').innerText = `₹ ${Number(data.total_amount).toLocaleString('en-IN')}`;
        document.getElementById('stat-total-cnt').innerText = Number(data.total_count).toLocaleString('en-IN');
    } catch(err) {
        console.error("Error loading collection stats:", err);
    }
}

async function handleCollectionUploadSubmit(e) {
    e.preventDefault();
    const fileInput = document.getElementById('coll-upload-file');
    if (!fileInput.files.length) {
        showToast("Please choose an Excel file first", "warning");
        return;
    }

    setButtonLoading('coll-upload-btn', true);
    const feedback = document.getElementById('upload-feedback');
    feedback.style.display = 'none';

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    try {
        const res = await fetch('/api/collection/upload', {
            method: 'POST',
            body: formData
        });
        const d = await res.json();
        if (!res.ok) throw new Error(d.detail || "Upload failed");

        feedback.style.display = 'block';
        if (d.success) {
            const inserted = d.total_inserted ?? d.updated_count ?? 0;
            const skipped = d.skipped_duplicates ?? 0;
            feedback.className = 'alert alert-success mt-3 p-3 rounded-3 small';
            feedback.innerHTML = `
                <div class="fw-bold fs-6 mb-1">
                    <i class="fa-solid fa-circle-check me-2 text-success"></i>Collection Register Upload Ingested!
                </div>
                <div class="d-flex gap-4 flex-wrap mt-2">
                    <div><strong>Total Processed:</strong> ${d.total_rows}</div>
                    <div><strong class="text-success">Inserted Records:</strong> ${inserted}</div>
                    <div><strong class="text-warning">Skipped Duplicates:</strong> ${skipped}</div>
                </div>
            `;
            
            if (d.errors && d.errors.length) {
                feedback.innerHTML += `<div class="mt-3 pt-2 border-top text-muted small">` +
                    `<strong>Notices (${d.errors.length} skipped):</strong><br>` +
                    d.errors.slice(0, 8).map(er => `• Row ${er.row} (MR: ${er.mr}): ${er.reason}`).join('<br>') +
                    `</div>`;
            }
            showToast(`Collection upload completed! Inserted ${inserted} records (${skipped} duplicates skipped).`);
        } else {
            feedback.className = 'alert alert-danger mt-3 p-3 rounded-3 small';
            feedback.innerHTML = `<i class="fa-solid fa-circle-xmark me-2"></i>${d.message || "Failed to parse records."}`;
        }

        // Refresh stats
        loadCollectionStats();
        document.getElementById('coll-upload-form').reset();
    } catch(err) {
        feedback.style.display = 'block';
        feedback.className = 'alert alert-danger mt-3 p-3 rounded-3 small';
        feedback.innerText = err.message;
        alert(err.message);
    } finally {
        setButtonLoading('coll-upload-btn', false, '<i class="fa-solid fa-cloud-arrow-up me-1"></i> Upload & Ingest Records');
    }
}
