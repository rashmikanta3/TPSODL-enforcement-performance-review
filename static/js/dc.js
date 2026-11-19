
// Global flag for duplicate override
window._allowDuplicateDc = false;

function showDuplicateDcModal(data, onConfirm) {
    const modalEl = document.getElementById('duplicateVcrModal');
    if (!modalEl) {
        if (confirm(`${data.details || 'Duplicate VCR found.'}\n\nDo you want to proceed and save anyway?`)) {
            onConfirm();
        }
        return;
    }
    const msgEl = document.getElementById('duplicateVcrModalMsg');
    const detailsEl = document.getElementById('duplicateVcrDetails');
    if (msgEl) {
        msgEl.innerHTML = `VCR Number <strong>${data.vcr_number}</strong> has already been recorded for Disconnection.`;
    }
    if (detailsEl) {
        detailsEl.innerHTML = `<i class="fa-solid fa-circle-exclamation text-warning me-1"></i> ${data.details || 'A disconnection record with this VCR number already exists.'}`;
    }

    const modal = new bootstrap.Modal(modalEl);
    const confirmBtn = document.getElementById('btnConfirmDuplicate');
    
    const handleConfirm = () => {
        modal.hide();
        confirmBtn.removeEventListener('click', handleConfirm);
        onConfirm();
    };

    const newConfirmBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
    newConfirmBtn.addEventListener('click', handleConfirm);

    modal.show();
}
document.addEventListener('DOMContentLoaded', () => {
    const dcDateEl = document.getElementById('dcDate');
    if (dcDateEl) {
        dcDateEl.value = new Date().toISOString().split('T')[0];
    }
    if (typeof window.isSquadUser === 'function' && window.isSquadUser()) {
        const toggle = document.getElementById('dcSquadToggle');
        const container = document.getElementById('dcSquadSelectContainer');
        if (toggle && container) {
            toggle.checked = true;
            container.style.display = 'block';
            loadActiveSquads();
        }
    }
    loadRecentDC();

    // Search by VCR Number
    const btnSearchDc = document.getElementById('btnSearchDcVcr');
    const inputSearchDc = document.getElementById('dcSearchVcr');
    const btnClearDc = document.getElementById('btnClearDcSearch');
    if (btnSearchDc && inputSearchDc) {
        btnSearchDc.addEventListener('click', () => {
            loadRecentDC(inputSearchDc.value.trim());
        });
        inputSearchDc.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                loadRecentDC(inputSearchDc.value.trim());
            }
        });
    }
    if (btnClearDc && inputSearchDc) {
        btnClearDc.addEventListener('click', () => {
            inputSearchDc.value = '';
            loadRecentDC();
        });
    }

    // Export Disconnections to Excel
    const btnExportDc = document.getElementById('btnExportDcExcel');
    if (btnExportDc) {
        btnExportDc.addEventListener('click', () => {
            const sDate = document.getElementById('dcExportStartDate')?.value || '';
            const eDate = document.getElementById('dcExportEndDate')?.value || '';
            const circle = currentVCRCircle || document.getElementById('dcCircle')?.value || '';
            const params = new URLSearchParams();
            if (sDate) params.append('start_date', sDate);
            if (eDate) params.append('end_date', eDate);
            if (circle) params.append('circle', circle);
            window.location.href = `/api/dc/export-excel?${params.toString()}`;
        });
    }
});

let currentVCRCircle = '';

async function lookupVCR() {
    const vcrInput = document.getElementById('dcVCRNumber');
    const vcrNum = vcrInput ? vcrInput.value.trim() : '';
    if (!vcrNum) return;

    setButtonLoading('btnLookupVCR', true);
    try {
        const res = await fetch(`/api/dc/vcr-lookup?vcr_number=${encodeURIComponent(vcrNum)}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "VCR not found");

        document.getElementById('dcConsumerName').value = data.consumer_name || '';
        document.getElementById('dcConsumerAddress').value = data.consumer_address || '';
        document.getElementById('dcCircle').value = data.circle || '';
        document.getElementById('dcDivision').value = data.division || '';
        if (document.getElementById('dcSubdivision')) {
            document.getElementById('dcSubdivision').value = data.subdivision || '';
        }
        document.getElementById('dcSection').value = data.section || '';

        currentVCRCircle = data.circle || '';

        // Load circle-filtered team leaders for dropdown
        if (currentVCRCircle) {
            loadCircleTLs(currentVCRCircle);
        }

        if (typeof isCircleAuthorizedClient === 'function' && currentVCRCircle && !isCircleAuthorizedClient(currentVCRCircle)) {
            const authCircles = (typeof getUserAuthorizedCircles === 'function') ? getUserAuthorizedCircles().join(', ') : '';
            throw new Error(`Unauthorized: VCR ${vcrNum} belongs to circle '${currentVCRCircle}', but your account is authorized only for: ${authCircles}`);
        }

        // If squad attribution toggle is ON, refresh active squads for this circle
        const squadToggle = document.getElementById('dcSquadToggle');
        if (squadToggle && squadToggle.checked) {
            loadActiveSquads();
        }

        showToast(`VCR ${vcrNum} loaded successfully!`);
    } catch(err) {
        showToast(err.message, 'danger');
        document.getElementById('dcConsumerName').value = '';
        document.getElementById('dcConsumerAddress').value = '';
    } finally {
        setButtonLoading('btnLookupVCR', false, '<i class="fa-solid fa-magnifying-glass me-1"></i> Lookup');
    }
}

async function handleSquadToggle() {
    const toggle = document.getElementById('dcSquadToggle');
    const container = document.getElementById('dcSquadSelectContainer');
    if (toggle.checked) {
        container.style.display = 'block';
        loadActiveSquads();
    } else {
        container.style.display = 'none';
        document.getElementById('dcActiveSquadSelect').value = '';
    }
}

async function loadActiveSquads() {
    const dcDate = document.getElementById('dcDate').value;
    const circle = currentVCRCircle || document.getElementById('dcCircle').value;
    const select = document.getElementById('dcActiveSquadSelect');

    try {
        let url = `/api/attendance/active-squads?operation_date=${dcDate}`;
        if (circle) url += `&circle=${encodeURIComponent(circle)}`;

        const res = await fetch(url);
        const squads = await res.json();

        select.innerHTML = '<option value="">-- Select Operating Squad --</option>' +
            squads.map(s => `<option value="${s.id}">${s.name} (${s.tl_name} - ${s.mode})</option>`).join('');

        if (typeof window.isSquadUser === 'function' && window.isSquadUser()) {
            const mySquadId = window.getUserSquadId();
            if (mySquadId) {
                select.value = mySquadId;
                select.disabled = true;
            }
        }
    } catch(err) {
        console.error("Failed to load active squads:", err);
    }
}

async function submitDCPunch(e) {
    e.preventDefault();

    const circle = currentVCRCircle || document.getElementById('dcCircle').value;
    if (typeof isCircleAuthorizedClient === 'function' && circle && !isCircleAuthorizedClient(circle)) {
        showToast(`Unauthorized: You do not have permissions for circle: ${circle}`, "danger");
        return;
    }

    const vcrNumber = document.getElementById('dcVCRNumber').value.trim();

    if (vcrNumber && !window._allowDuplicateDc) {
        try {
            const checkRes = await fetch(`/api/vcr/check-exists?vcr_number=${encodeURIComponent(vcrNumber)}&form_type=dc`);
            const checkData = await checkRes.json();
            if (checkData.exists) {
                showDuplicateDcModal(checkData, () => {
                    window._allowDuplicateDc = true;
                    document.getElementById('dcForm').dispatchEvent(new Event('submit'));
                });
                return;
            }
        } catch (chkErr) {
            console.warn("Duplicate check error:", chkErr);
        }
    }

    setButtonLoading('btnSaveDC', true);

    const toggle = document.getElementById('dcSquadToggle');
    const squadSelect = document.getElementById('dcActiveSquadSelect');
    let teamId = (toggle.checked && squadSelect.value) ? parseInt(squadSelect.value) : null;

    if (typeof window.isSquadUser === 'function' && window.isSquadUser()) {
        teamId = window.getUserSquadId();
    }

    const payload = {
        vcr_number: document.getElementById('dcVCRNumber').value.trim(),
        dc_date: document.getElementById('dcDate').value,
        amount_pending: parseFloat(document.getElementById('dcAmountPending').value),
        dc_authority_tl_code: document.getElementById('dcAuthorityEmpId').value.trim(),
        dc_authority_emp_id: document.getElementById('dcAuthorityEmpId').value.trim(),
        team_id: teamId,
        remarks: document.getElementById('dcRemarks').value.trim(),
        allow_duplicate: !!window._allowDuplicateDc
    };

    try {
        const res = await fetch('/api/dc/punch', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Error saving DC record");

        showToast(data.message || "Disconnection Record saved successfully!");
        window._allowDuplicateDc = false;
        document.getElementById('dcForm').reset();
        document.getElementById('dcDate').value = new Date().toISOString().split('T')[0];
        document.getElementById('dcSquadSelectContainer').style.display = 'none';
        const nameDisp = document.getElementById('dcAuthorityTlName');
        if (nameDisp) nameDisp.value = '';
        const tlSel = document.getElementById('dcTlSelect');
        if (tlSel) tlSel.innerHTML = '<option value="">-- Verify VCR First to Filter by Circle --</option>';
        loadRecentDC();
    } catch(err) {
        const errDetail = err.message || "";
        if (errDetail.includes("Confirm to proceed")) {
            showDuplicateDcModal({ vcr_number: document.getElementById('dcVCRNumber').value.trim(), details: errDetail }, () => {
                window._allowDuplicateDc = true;
                document.getElementById('dcForm').dispatchEvent(new Event('submit'));
            });
            return;
        }
        alert(err.message);
    } finally {
        setButtonLoading('btnSaveDC', false, '<i class="fa-solid fa-save me-1"></i> Submit Disconnection (DC) Entry');
    }
}

// -------------------------------------------------------------
// DC Authority TPSODL Team Leader Lookup & Circle Filter Logic
// -------------------------------------------------------------
let dcLookupTimer = null;

function debounceDcTLLookup() {
    clearTimeout(dcLookupTimer);
    dcLookupTimer = setTimeout(() => {
        lookupDcTL();
    }, 300);
}

async function lookupDcTL() {
    const input = document.getElementById('dcAuthorityEmpId') || document.getElementById('dcAuthorityTlCode');
    const nameDisplay = document.getElementById('dcAuthorityTlName');
    const select = document.getElementById('dcTlSelect');
    if (!input || !nameDisplay) return;

    const code = input.value.trim();
    if (!code) {
        nameDisplay.value = '';
        if (select) select.value = '';
        return;
    }

    try {
        const res = await fetch(`/api/admin/team-leads/lookup?code=${encodeURIComponent(code)}`);
        const data = await res.json();
        if (res.ok && data.name) {
            nameDisplay.value = data.name;
            if (select) {
                let optFound = false;
                for (let i = 0; i < select.options.length; i++) {
                    if (select.options[i].value.toLowerCase() === data.tl_code.toLowerCase()) {
                        select.selectedIndex = i;
                        optFound = true;
                        break;
                    }
                }
                if (!optFound && data.circle && (!currentVCRCircle || select.options.length <= 1)) {
                    await loadCircleTLs(data.circle);
                    select.value = data.tl_code;
                }
            }
        } else {
            nameDisplay.value = '';
        }
    } catch (err) {
        console.warn("TL lookup failed:", err);
    }
}

async function loadCircleTLs(circle) {
    const select = document.getElementById('dcTlSelect');
    if (!select) return;

    if (!circle) {
        select.innerHTML = '<option value="">-- Verify VCR First to Filter by Circle --</option>';
        return;
    }

    try {
        const res = await fetch(`/api/admin/team-leads?circle=${encodeURIComponent(circle)}&active_only=true`);
        const tls = await res.json();
        if (!Array.isArray(tls) || tls.length === 0) {
            select.innerHTML = `<option value="">-- No Active Team Leaders Found for ${circle} --</option>`;
            return;
        }

        let html = `<option value="">-- Select Team Leader (${circle}) --</option>`;
        tls.forEach(tl => {
            html += `<option value="${tl.tl_code}" data-name="${tl.name}">${tl.name} (${tl.tl_code})</option>`;
        });
        select.innerHTML = html;

        const currentCode = (document.getElementById('dcAuthorityEmpId') || {}).value;
        if (currentCode) {
            select.value = currentCode;
        }
    } catch (err) {
        console.error("Failed to load circle TLs:", err);
    }
}

function onDcTlSelectChange() {
    const select = document.getElementById('dcTlSelect');
    const input = document.getElementById('dcAuthorityEmpId') || document.getElementById('dcAuthorityTlCode');
    const nameDisplay = document.getElementById('dcAuthorityTlName');
    if (!select || !input || !nameDisplay) return;

    const selectedOption = select.options[select.selectedIndex];
    if (selectedOption && select.value) {
        input.value = select.value;
        nameDisplay.value = selectedOption.getAttribute('data-name') || '';
    } else {
        input.value = '';
        nameDisplay.value = '';
    }
}

async function loadRecentDC(vcrNum = null) {
    const tbody = document.getElementById('recentDcTbody');
    if (!tbody) return;

    const isUser = typeof window.isSquadUser === 'function' && window.isSquadUser();
    const actionsHeader = document.getElementById('dcActionsHeader');
    if (isUser && actionsHeader) {
        actionsHeader.innerText = "Status";
    }

    try {
        let url = '/api/dc/recent?limit=' + (vcrNum ? '50' : '5');
        if (vcrNum) url += '&vcr_number=' + encodeURIComponent(vcrNum);
        const res = await fetch(url);
        const dcs = await res.json();

        if (!dcs || !dcs.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-3">No recent disconnections found.</td></tr>';
            return;
        }

        tbody.innerHTML = dcs.map(d => {
            const isLocked = !!d.is_locked;
            const lockBadge = isLocked
                ? '<span class="badge bg-secondary"><i class="fa-solid fa-lock me-1"></i> Locked</span>'
                : '<span class="badge bg-success"><i class="fa-solid fa-unlock me-1"></i> Unlocked</span>';

            let actionButtons = '';
            if (isUser) {
                actionButtons = '<span class="text-muted small"><i class="fa-solid fa-lock me-1"></i>Immutable</span>';
            } else {
                actionButtons = `
                    <div class="d-inline-flex gap-1">
                        <button type="button" class="btn btn-outline-secondary btn-sm py-0 px-2" onclick="toggleDCLock(${d.id})" title="Toggle Lock Status">
                            <i class="fa-solid ${isLocked ? 'fa-lock-open text-primary' : 'fa-lock text-secondary'}"></i>
                        </button>
                        <button type="button" class="btn btn-outline-danger btn-sm py-0 px-2" onclick="deleteDCEntry(${d.id})" title="Delete DC Entry">
                            <i class="fa-solid fa-trash"></i>
                        </button>
                    </div>
                `;
            }

            return `
                <tr>
                    <td class="fw-semibold text-dark">${d.dc_date}</td>
                    <td><code>${d.vcr_number}</code></td>
                    <td><span class="badge bg-light text-dark border">${d.team_name}</span> <small class="text-muted">(${d.circle})</small></td>
                    <td><small class="text-muted">${d.dc_authority_tl_code || '-'}</small></td>
                    <td><strong class="text-danger">₹${parseFloat(d.amount_pending || 0).toLocaleString('en-IN', {minimumFractionDigits: 2})}</strong></td>
                    <td>${lockBadge}</td>
                    <td class="text-end">${actionButtons}</td>
                </tr>
            `;
        }).join('');
    } catch(err) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-3">Failed to load recent disconnections: ${err.message}</td></tr>`;
    }
}

async function deleteDCEntry(dcId) {
    if (!confirm("Are you sure you want to delete this disconnection record?")) return;
    try {
        const res = await fetch(`/api/dc/${dcId}`, { method: 'DELETE' });
        const d = await res.json();
        if (!res.ok) throw new Error(d.detail || "Failed to delete record");
        showToast(d.message || "Disconnection record deleted successfully", "success");
        loadRecentDC();
    } catch(err) {
        showToast(err.message, "danger");
    }
}

async function toggleDCLock(dcId) {
    try {
        const res = await fetch(`/api/dc/${dcId}/toggle-lock`, { method: 'PATCH' });
        const d = await res.json();
        if (!res.ok) throw new Error(d.detail || "Failed to toggle lock");
        showToast(d.message || "Lock state updated", "success");
        loadRecentDC();
    } catch(err) {
        showToast(err.message, "danger");
    }
}

