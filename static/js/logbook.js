// Vehicle Daily Log Book Logic

document.addEventListener('DOMContentLoaded', () => {
    const dInput = document.getElementById('log-date');
    if (dInput) dInput.value = new Date().toISOString().split('T')[0];

    const startT = document.getElementById('lbStartTime');
    if (startT && !startT.value) startT.value = '09:00';

    const endT = document.getElementById('lbEndTime');
    if (endT && !endT.value) endT.value = '18:00';

    if (typeof populateOperationalCircleSelect === 'function') {
        populateOperationalCircleSelect('log-circle', onLogCircleChange);
    } else {
        onLogCircleChange();
    }
});

let logCircleTeams = [];

async function onLogCircleChange() {
    let circle = document.getElementById('log-circle').value;
    if (!circle) return;

    try {
        const res = await fetch(`/api/attendance/teams-by-circle/${encodeURIComponent(circle)}`);
        const allTeams = await res.json();
        // Exclude Office Teams (without vehicle) from Vehicle Log Book selection
        logCircleTeams = (allTeams || []).filter(t => t.has_vehicle !== false && !t.is_office_team);

        const teamSelect = document.getElementById('log-team');
        teamSelect.innerHTML = '<option value="">-- Choose Field Squad in ' + circle + ' --</option>' +
            logCircleTeams.map(t => `<option value="${t.id}">${t.name}</option>`).join('');

        document.getElementById('log-tl-name').value = '';
        document.getElementById('log-supervisor').value = '';
    } catch(err) {
        console.error("Error loading circle teams for logbook:", err);
    }
}

function onLogTeamSelect() {
    const teamId = document.getElementById('log-team').value;
    const team = logCircleTeams.find(t => t.id == teamId);

    if (team) {
        document.getElementById('log-tl-name').value = team.assigned_team_lead || 'TPSODL Team Leader';
        document.getElementById('log-supervisor').value = team.supervisor_name || '';
    } else {
        document.getElementById('log-tl-name').value = '';
        document.getElementById('log-supervisor').value = '';
    }
    checkExistingLog();
}

function calcKm() {
    const s = parseInt(document.getElementById('log-start').value || 0);
    const e = parseInt(document.getElementById('log-end').value || 0);
    const totalEl = document.getElementById('log-total');

    if (document.getElementById('log-end').value !== '' && e < s) {
        totalEl.value = 'Invalid (End < Start)';
        totalEl.className = 'form-control form-control-sm bg-light fw-bold text-danger';
    } else {
        const run = Math.max(0, e - s);
        totalEl.value = `${run} KM`;
        totalEl.className = 'form-control form-control-sm bg-light fw-bold text-primary';
    }
}

async function checkExistingLog() {
    const opDate = document.getElementById('log-date').value;
    const teamId = document.getElementById('log-team').value;
    if (!opDate || !teamId) return;

    const banner = document.getElementById('log-status-banner');
    banner.style.display = 'none';
}

async function handleLogSubmit(e) {
    e.preventDefault();
    const s = parseInt(document.getElementById('log-start').value);
    const eKm = parseInt(document.getElementById('log-end').value);

    if (eKm < s) {
        alert("Ending KM cannot be less than Starting KM!");
        return;
    }

    const startTimeEl = document.getElementById('lbStartTime');
    const endTimeEl = document.getElementById('lbEndTime');
    const startTime = startTimeEl ? startTimeEl.value : '';
    const endTime = endTimeEl ? endTimeEl.value : '';

    if (!startTime || !endTime) {
        alert("Please specify both Start Time and End Time.");
        return;
    }

    const circle = document.getElementById('log-circle') ? document.getElementById('log-circle').value : '';
    if (typeof isCircleAuthorizedClient === 'function' && circle && !isCircleAuthorizedClient(circle)) {
        showToast(`Unauthorized: You do not have permissions for circle: ${circle}`, "danger");
        return;
    }

    setButtonLoading('btnSaveLog', true);
    const teamId = parseInt(document.getElementById('log-team').value);

    const payload = {
        date: document.getElementById('log-date').value,
        team_id: teamId,
        vehicle_no: document.getElementById('log-vehicle').value.trim(),
        supervisor_name: document.getElementById('log-supervisor').value.trim(),
        start_km: s,
        end_km: eKm,
        start_time: startTime,
        end_time: endTime,
        area_movement: document.getElementById('log-route').value.trim()
    };

    try {
        const res = await fetch('/api/logbook/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Error saving vehicle log");

        const banner = document.getElementById('log-status-banner');
        banner.style.display = 'block';
        banner.style.backgroundColor = '#ecfdf5';
        banner.style.color = '#065f46';
        banner.style.border = '1px solid #a7f3d0';
        banner.innerHTML = `<i class="fa-solid fa-circle-check me-2"></i>Log Book saved! Total Run: <strong>${data.run_km} KM</strong>`;

        showToast(`Vehicle Log saved! Total Run: ${data.run_km} KM`);
        document.getElementById('log-start').value = '';
        document.getElementById('log-end').value = '';
        document.getElementById('log-total').value = '0 KM';
        document.getElementById('log-route').value = '';
    } catch(err) {
        alert(err.message);
    } finally {
        setButtonLoading('btnSaveLog', false, '<i class="fa-solid fa-save me-1"></i> Save Log Entry');
    }
}

const submitLogBook = handleLogSubmit;
