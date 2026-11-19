// Dedicated VCR Master Bulk Upload Desk

document.addEventListener('DOMContentLoaded', () => {
    initVCRDropzone();
});

function initVCRDropzone() {
    const dropzone = document.getElementById('vcrDropzone');
    const fileInput = document.getElementById('vcrBulkFile');
    const fileBadge = document.getElementById('selectedFileBadge');

    if (!dropzone || !fileInput) return;

    // Click dropzone to trigger hidden file input
    dropzone.addEventListener('click', () => {
        fileInput.click();
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            updateSelectedFileDisplay(fileInput.files[0]);
        }
    });

    // Drag and Drop Events
    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.add('bg-primary-subtle', 'border-primary');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            dropzone.classList.remove('bg-primary-subtle', 'border-primary');
        }, false);
    });

    dropzone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files && files.length > 0) {
            fileInput.files = files;
            updateSelectedFileDisplay(files[0]);
        }
    }, false);
}

function updateSelectedFileDisplay(file) {
    const fileBadge = document.getElementById('selectedFileBadge');
    if (!fileBadge || !file) return;

    const sizeKb = (file.size / 1024).toFixed(1);
    fileBadge.className = 'badge bg-success-subtle text-success border border-success-subtle px-3 py-1 shadow-sm small';
    fileBadge.innerHTML = `<i class="fa-solid fa-file-excel me-1"></i> <strong>${file.name}</strong> (${sizeKb} KB)`;
}

function downloadVCRTemplate() {
    window.location.href = '/api/vcr/template';
}

async function uploadVCRBulk(e) {
    e.preventDefault();

    const fileInput = document.getElementById('vcrBulkFile');
    if (!fileInput || !fileInput.files.length) {
        showToast("Please choose or drag a VCR Excel file first", "warning");
        return;
    }

    setButtonLoading('btnUploadVCR', true);

    const resultCard = document.getElementById('vcrResultCard');
    if (resultCard) resultCard.style.display = 'none';

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    try {
        const res = await fetch('/api/vcr/bulk-upload', {
            method: 'POST',
            body: formData
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || "Failed to process VCR upload");
        }

        if (resultCard) {
            resultCard.style.display = 'block';

            document.getElementById('statTotalRows').innerText = data.total_rows || 0;
            document.getElementById('statInserted').innerText = data.inserted_count || 0;
            document.getElementById('statSkipped').innerText = data.skipped_duplicates || 0;

            const logContainer = document.getElementById('vcrSkippedLogContainer');
            const tbody = document.getElementById('vcrSkippedTbody');

            if (data.errors && data.errors.length > 0 && tbody) {
                tbody.innerHTML = data.errors.map(err => `
                    <tr>
                        <td class="fw-bold">${err.row || '-'}</td>
                        <td><code>${err.vcr || '-'}</code></td>
                        <td class="text-danger">${err.reason || '-'}</td>
                    </tr>
                `).join('');
                if (logContainer) logContainer.style.display = 'block';
            } else if (logContainer) {
                logContainer.style.display = 'none';
            }
        }

        showToast(`Ingestion completed! Inserted: ${data.inserted_count}, Skipped Duplicates: ${data.skipped_duplicates}`, "success");

        // Reset file input
        fileInput.value = '';
        const fileBadge = document.getElementById('selectedFileBadge');
        if (fileBadge) {
            fileBadge.className = 'badge bg-white text-secondary border px-3 py-1 shadow-sm small';
            fileBadge.innerHTML = `<i class="fa-solid fa-folder-open me-1"></i>No file selected yet`;
        }
    } catch(err) {
        showToast(err.message, "danger");
    } finally {
        setButtonLoading('btnUploadVCR', false, '<i class="fa-solid fa-upload me-1"></i> Ingest VCR Master Records');
    }
}

