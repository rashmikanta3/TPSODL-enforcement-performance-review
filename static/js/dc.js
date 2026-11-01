document.addEventListener('DOMContentLoaded', () => {
    const dcDateEl = document.getElementById('dcDate');
    if (dcDateEl) {
        dcDateEl.value = new Date().toISOString().split('T')[0];
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

    setButtonLoading('btnSaveDC', true);

    const toggle = document.getElementById('dcSquadToggle');
    const squadSelect = document.getElementById('dcActiveSquadSelect');
    const teamId = (toggle.checked && squadSelect.value) ? parseInt(squadSelect.value) : null;

    const payload = {
        vcr_number: document.getElementById('dcVCRNumber').value.trim(),
        dc_date: document.getElementById('dcDate').value,
        amount_pending: parseFloat(document.getElementById('dcAmountPending').value),
        dc_authority_tl_code: document.getElementById('dcAuthorityEmpId').value.trim(),
        dc_authority_emp_id: document.getElementById('dcAuthorityEmpId').value.trim(),
        team_id: teamId,
        remarks: document.getElementById('dcRemarks').value.trim()
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
        document.getElementById('dcForm').reset();
        document.getElementById('dcDate').value = new Date().toISOString().split('T')[0];
        document.getElementById('dcSquadSelectContainer').style.display = 'none';
    } catch(err) {
        alert(err.message);
    } finally {
        setButtonLoading('btnSaveDC', false, '<i class="fa-solid fa-save me-1"></i> Submit Disconnection (DC) Entry');
    }
}
