// Master Administration Desk: Squads, TPSODL Team Leaders, BA Employees, and Portal Users

let globalTeamsCache = [];
let globalTeamLeadsCache = [];
let globalEmployeesCache = [];
let globalUsersCache = [];

document.addEventListener('DOMContentLoaded', () => {
    // 1. Role verification check
    const currentUser = getCurrentUser();
    if (currentUser && currentUser.role !== 'ADMIN') {
        showToast("Notice: Master Administration controls require ADMIN privileges.", "warning");
    }

    // 2. Safe loading of entities inside DOMContentLoaded
    loadTeams();
    loadAllTeamLeads();
    loadAllEmployees();
    loadAllUsers();
});

// =========================================================================
// 1. TEAMS / SQUADS MANAGEMENT
// =========================================================================
async function loadAllTeams() {
    const tbody = document.getElementById('teamsTableBody');
    if (!tbody) return;

    try {
        const res = await fetch('/api/admin/teams/all');
        if (!res.ok) {
            if (res.status === 403) throw new Error("Admin access required");
            throw new Error("Failed to load squads");
        }
        const teams = await res.json();
        globalTeamsCache = Array.isArray(teams) ? teams : [];

        renderTeamsTable(globalTeamsCache);
        populateTeamDropdowns(globalTeamsCache);
        populateUserSquadOptions();
    } catch(err) {
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-3"><i class="fa-solid fa-triangle-exclamation me-1"></i> ${err.message}</td></tr>`;
        }
    }
}

async function loadTeams() {
    return await loadAllTeams();
}
const loadTeamsTable = loadTeams;

function renderTeamsTable(teams) {
    const tbody = document.getElementById('teamsTableBody');
    if (!tbody) return;

    if (!teams || teams.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-3">No squad teams registered yet.</td></tr>';
        return;
    }

    tbody.innerHTML = teams.map(t => {
        const isOffice = !!(t.is_office_team || !t.has_vehicle);
        const statusBadge = t.is_active 
            ? '<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="fa-solid fa-circle-check me-1"></i>Active</span>'
            : '<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle px-2 py-1"><i class="fa-solid fa-circle-xmark me-1"></i>Deactivated</span>';

        const officeBadge = isOffice
            ? '<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle ms-1"><i class="fa-solid fa-building me-1"></i>Office Team</span>'
            : '<span class="badge bg-info-subtle text-info border border-info-subtle ms-1"><i class="fa-solid fa-truck-pickup me-1"></i>Field Squad</span>';

        const toggleBtn = t.is_active
            ? `<button type="button" class="btn btn-outline-danger btn-sm py-0 px-2" onclick="toggleTeamStatus(${t.id})" title="Deactivate Squad">Deactivate</button>`
            : `<button type="button" class="btn btn-outline-success btn-sm py-0 px-2" onclick="toggleTeamStatus(${t.id})" title="Activate Squad">Activate</button>`;

        const tlDisplay = t.default_tl_name 
            ? `${t.default_tl_name} ${t.default_tl_code ? `<code class="ms-1 text-primary">(${t.default_tl_code})</code>` : ''}`
            : (t.assigned_team_lead || '<span class="text-muted">-</span>');

        return `
            <tr id="teamRow_${t.id}">
                <td class="text-muted fw-bold">${t.id}</td>
                <td class="fw-bold text-dark">${t.name} ${officeBadge}</td>
                <td><span class="badge bg-light text-primary border">${t.circle}</span></td>
                <td>${t.supervisor_name || '<span class="text-muted">-</span>'}</td>
                <td>${tlDisplay}</td>
                <td id="teamStatusCell_${t.id}">${statusBadge}</td>
                <td class="text-end">
                    <div class="d-inline-flex gap-1">
                        <button type="button" class="btn btn-outline-primary btn-sm py-0 px-2" onclick="openEditTeamModal(${t.id})" title="Edit Details">
                            <i class="fa-solid fa-pen-to-square"></i> Edit
                        </button>
                        <span id="teamToggleBtn_${t.id}">${toggleBtn}</span>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

function populateTeamDropdowns(teams) {
    const empSelect = document.getElementById('empTeamSelect');
    const empCircleEl = document.getElementById('empCircle');
    if (empSelect && empCircleEl) {
        filterSquadOptionsByCircle(empCircleEl.value, 'empTeamSelect');
    }
}

function filterSquadOptionsByCircle(circle, selectElementId, selectedTeamId = null) {
    const sel = document.getElementById(selectElementId);
    if (!sel) return;

    const filtered = (globalTeamsCache || []).filter(t => !circle || (t.circle && t.circle.toUpperCase() === circle.toUpperCase()));
    sel.innerHTML = '<option value="">-- Unassigned / Individual --</option>' +
        filtered.map(t => {
            const isSel = (selectedTeamId && t.id === parseInt(selectedTeamId)) ? 'selected' : '';
            return `<option value="${t.id}" ${isSel}>${t.name} (${t.circle})</option>`;
        }).join('');
}

function filterTLOptionsByCircle(circle, selectElementId, selectedTLId = null) {
    const sel = document.getElementById(selectElementId);
    if (!sel) return;

    const cUp = (circle || '').trim().toUpperCase();
    const filtered = (globalTeamLeadsCache || []).filter(tl => {
        if (!cUp) return true;
        const tlCirc = (tl.circle || '').toUpperCase();
        if (cUp in {'CITY': 1, 'BERHAMPUR CITY': 1} && tlCirc in {'CITY': 1, 'BERHAMPUR CITY': 1}) return true;
        return tlCirc === cUp;
    });

    sel.innerHTML = '<option value="">-- Select Permanent TL --</option>' +
        filtered.map(tl => {
            const isSel = (selectedTLId && tl.id === parseInt(selectedTLId)) ? 'selected' : '';
            return `<option value="${tl.id}" data-name="${tl.name}" ${isSel}>${tl.name} (${tl.tl_code})</option>`;
        }).join('');
}

async function createTeam(e) {
    e.preventDefault();
    setButtonLoading('btnCreateTeam', true);

    const nameEl = document.getElementById('tmName');
    const circEl = document.getElementById('tmCircle');
    const supEl = document.getElementById('tmSupervisor');
    const tlSelect = document.getElementById('tmDefaultTLSelect');
    const defaultTlId = tlSelect && tlSelect.value ? parseInt(tlSelect.value) : null;
    const assignedTL = tlSelect && tlSelect.selectedIndex > 0 ? tlSelect.options[tlSelect.selectedIndex].getAttribute('data-name') : '';
    const isOffice = document.getElementById('tmIsOfficeTeam')?.checked || false;

    const payload = {
        name: nameEl ? nameEl.value.trim() : '',
        circle: circEl ? circEl.value : 'BERHAMPUR',
        supervisor_name: supEl ? supEl.value.trim() : '',
        default_tl_id: defaultTlId,
        assigned_team_lead: assignedTL,
        has_vehicle: !isOffice,
        is_office_team: isOffice
    };

    try {
        const res = await fetch('/api/admin/teams', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to create team");

        showToast(data.message || "Squad created successfully!", "success");
        const form = document.getElementById('createTeamForm');
        if (form) form.reset();
        loadAllTeams();
    } catch(err) {
        showToast(err.message, "danger");
    } finally {
        setButtonLoading('btnCreateTeam', false, '<i class="fa-solid fa-save me-1"></i> Register Squad');
    }
}

function openEditTeamModal(teamId) {
    const team = globalTeamsCache.find(t => t.id === teamId);
    if (!team) return;

    const idEl = document.getElementById('editTeamId');
    const nameEl = document.getElementById('editTeamName');
    const circEl = document.getElementById('editTeamCircle');
    const supEl = document.getElementById('editTeamSupervisor');
    const actEl = document.getElementById('editTeamIsActive');

    if (idEl) idEl.value = team.id;
    if (nameEl) nameEl.value = team.name;
    if (circEl) circEl.value = team.circle;
    if (supEl) supEl.value = team.supervisor_name || '';
    if (actEl) actEl.checked = !!team.is_active;

    const offEl = document.getElementById('editTeamIsOfficeTeam');
    if (offEl) offEl.checked = !!(team.is_office_team || !team.has_vehicle);

    filterTLOptionsByCircle(team.circle, 'editTeamDefaultTLSelect', team.default_tl_id);

    const modalEl = document.getElementById('editTeamModal');
    if (modalEl) {
        const modal = new bootstrap.Modal(modalEl);
        modal.show();
    }
}

async function submitEditTeam(e) {
    e.preventDefault();
    const teamId = document.getElementById('editTeamId').value;
    setButtonLoading('btnSaveEditTeam', true);

    const tlSelect = document.getElementById('editTeamDefaultTLSelect');
    const defaultTlId = tlSelect && tlSelect.value ? parseInt(tlSelect.value) : 0;
    const assignedTL = tlSelect && tlSelect.selectedIndex > 0 ? tlSelect.options[tlSelect.selectedIndex].getAttribute('data-name') : '';
    const isOffice = document.getElementById('editTeamIsOfficeTeam')?.checked || false;

    const payload = {
        name: document.getElementById('editTeamName').value.trim(),
        circle: document.getElementById('editTeamCircle').value,
        supervisor_name: document.getElementById('editTeamSupervisor').value.trim(),
        default_tl_id: defaultTlId,
        assigned_team_lead: assignedTL,
        has_vehicle: !isOffice,
        is_office_team: isOffice,
        is_active: document.getElementById('editTeamIsActive').checked
    };

    try {
        const res = await fetch(`/api/admin/teams/${teamId}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to update team");

        showToast(data.message || "Team updated successfully!", "success");

        const modalEl = document.getElementById('editTeamModal');
        if (modalEl) {
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
        }

        loadAllTeams();
    } catch(err) {
        showToast(err.message, "danger");
    } finally {
        setButtonLoading('btnSaveEditTeam', false, 'Save Changes');
    }
}

async function toggleTeamStatus(teamId) {
    try {
        const res = await fetch(`/api/admin/teams/${teamId}/toggle-status`, {
            method: 'PATCH'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to toggle status");

        showToast(data.message, "success");

        const statusCell = document.getElementById(`teamStatusCell_${teamId}`);
        const toggleBtnSpan = document.getElementById(`teamToggleBtn_${teamId}`);

        if (statusCell) {
            statusCell.innerHTML = data.is_active
                ? '<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="fa-solid fa-circle-check me-1"></i>Active</span>'
                : '<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle px-2 py-1"><i class="fa-solid fa-circle-xmark me-1"></i>Deactivated</span>';
        }

        if (toggleBtnSpan) {
            toggleBtnSpan.innerHTML = data.is_active
                ? `<button type="button" class="btn btn-outline-danger btn-sm py-0 px-2" onclick="toggleTeamStatus(${teamId})" title="Deactivate Squad">Deactivate</button>`
                : `<button type="button" class="btn btn-outline-success btn-sm py-0 px-2" onclick="toggleTeamStatus(${teamId})" title="Activate Squad">Activate</button>`;
        }

        const t = globalTeamsCache.find(x => x.id === teamId);
        if (t) t.is_active = data.is_active;
    } catch(err) {
        showToast(err.message, "danger");
    }
}


// =========================================================================
// 2. TPSODL TEAM LEADERS MANAGEMENT
// =========================================================================
async function loadAllTeamLeads(circle = '') {
    const tbody = document.getElementById('teamLeadsTableBody');
    if (!tbody) return;

    try {
        const url = circle ? `/api/admin/team-leads/all?circle=${encodeURIComponent(circle)}` : '/api/admin/team-leads/all';
        const res = await fetch(url);
        if (!res.ok) {
            if (res.status === 403) throw new Error("Admin access required");
            throw new Error("Failed to load team leaders");
        }
        const tls = await res.json();
        globalTeamLeadsCache = Array.isArray(tls) ? tls : [];
        renderTeamLeadsTable(globalTeamLeadsCache);

        // Also populate team TL dropdowns
        const tmCircEl = document.getElementById('tmCircle');
        if (tmCircEl) {
            filterTLOptionsByCircle(tmCircEl.value, 'tmDefaultTLSelect');
        }
    } catch(err) {
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-3"><i class="fa-solid fa-triangle-exclamation me-1"></i> ${err.message}</td></tr>`;
        }
    }
}

function renderTeamLeadsTable(tls) {
    const tbody = document.getElementById('teamLeadsTableBody');
    if (!tbody) return;

    if (!tls || tls.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-3">No TPSODL Team Leaders found for this selection.</td></tr>';
        return;
    }

    tbody.innerHTML = tls.map(tl => {
        const statusBadge = tl.is_active
            ? '<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="fa-solid fa-circle-check me-1"></i>Active</span>'
            : '<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle px-2 py-1"><i class="fa-solid fa-circle-xmark me-1"></i>Deactivated</span>';

        const toggleBtn = tl.is_active
            ? `<button type="button" class="btn btn-outline-danger btn-sm py-0 px-2" onclick="toggleTeamLeadStatus(${tl.id})" title="Deactivate Team Leader">Deactivate</button>`
            : `<button type="button" class="btn btn-outline-success btn-sm py-0 px-2" onclick="toggleTeamLeadStatus(${tl.id})" title="Activate Team Leader">Activate</button>`;

        return `
            <tr id="tlRow_${tl.id}">
                <td><code class="fw-bold text-primary">${tl.tl_code}</code></td>
                <td class="fw-bold text-dark">${tl.name}</td>
                <td>${tl.designation || '<span class="text-muted">-</span>'}</td>
                <td><span class="badge bg-light text-primary border">${tl.circle}</span></td>
                <td>${tl.contact_no || '<span class="text-muted">-</span>'}</td>
                <td id="tlStatusCell_${tl.id}">${statusBadge}</td>
                <td class="text-end">
                    <div class="d-inline-flex gap-1">
                        <button type="button" class="btn btn-outline-primary btn-sm py-0 px-2" onclick="openEditTeamLeadModal(${tl.id})" title="Edit Details">
                            <i class="fa-solid fa-pen-to-square"></i> Edit
                        </button>
                        <span id="tlToggleBtn_${tl.id}">${toggleBtn}</span>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

async function createTeamLead(e) {
    e.preventDefault();
    setButtonLoading('btnCreateTL', true);

    const payload = {
        tl_code: document.getElementById('tlCode').value.trim(),
        name: document.getElementById('tlName').value.trim(),
        designation: document.getElementById('tlDesig') ? document.getElementById('tlDesig').value.trim() : null,
        circle: document.getElementById('tlCircle').value,
        contact_no: document.getElementById('tlContact') ? document.getElementById('tlContact').value.trim() : null
    };

    try {
        const res = await fetch('/api/admin/team-leads', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to register team leader");

        showToast(data.message || "Team leader registered successfully!", "success");
        const form = document.getElementById('createTeamLeadForm');
        if (form) form.reset();
        const filterEl = document.getElementById('filterTLCircle');
        const currentFilter = filterEl ? filterEl.value : '';
        loadAllTeamLeads(currentFilter);
    } catch(err) {
        showToast(err.message, "danger");
    } finally {
        setButtonLoading('btnCreateTL', false, '<i class="fa-solid fa-user-shield me-1"></i> Register Team Leader');
    }
}

function openEditTeamLeadModal(tlId) {
    const tl = globalTeamLeadsCache.find(x => x.id === tlId);
    if (!tl) return;

    const idEl = document.getElementById('editTLId');
    const codeEl = document.getElementById('editTLCode');
    const nameEl = document.getElementById('editTLName');
    const desigEl = document.getElementById('editTLDesignation');
    const circEl = document.getElementById('editTLCircle');
    const contactEl = document.getElementById('editTLContact');
    const actEl = document.getElementById('editTLIsActive');

    if (idEl) idEl.value = tl.id;
    if (codeEl) codeEl.value = tl.tl_code;
    if (nameEl) nameEl.value = tl.name;
    if (desigEl) desigEl.value = tl.designation || '';
    if (circEl) circEl.value = tl.circle;
    if (contactEl) contactEl.value = tl.contact_no || '';
    if (actEl) actEl.checked = !!tl.is_active;

    const modalEl = document.getElementById('editTeamLeadModal');
    if (modalEl) {
        const modal = new bootstrap.Modal(modalEl);
        modal.show();
    }
}

async function submitEditTeamLead(e) {
    e.preventDefault();
    const tlId = document.getElementById('editTLId').value;
    setButtonLoading('btnSaveEditTL', true);

    const payload = {
        tl_code: document.getElementById('editTLCode').value.trim(),
        name: document.getElementById('editTLName').value.trim(),
        designation: document.getElementById('editTLDesignation') ? document.getElementById('editTLDesignation').value.trim() : null,
        circle: document.getElementById('editTLCircle').value,
        contact_no: document.getElementById('editTLContact') ? document.getElementById('editTLContact').value.trim() : null,
        is_active: document.getElementById('editTLIsActive').checked
    };

    try {
        const res = await fetch(`/api/admin/team-leads/${tlId}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to update team leader");

        showToast(data.message || "Team leader updated successfully!", "success");

        const modalEl = document.getElementById('editTeamLeadModal');
        if (modalEl) {
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
        }

        const filterEl = document.getElementById('filterTLCircle');
        const currentFilter = filterEl ? filterEl.value : '';
        loadAllTeamLeads(currentFilter);
    } catch(err) {
        showToast(err.message, "danger");
    } finally {
        setButtonLoading('btnSaveEditTL', false, 'Save Changes');
    }
}

async function toggleTeamLeadStatus(tlId) {
    try {
        const res = await fetch(`/api/admin/team-leads/${tlId}/toggle-status`, {
            method: 'PATCH'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to toggle status");

        showToast(data.message, "success");

        const statusCell = document.getElementById(`tlStatusCell_${tlId}`);
        const toggleBtnSpan = document.getElementById(`tlToggleBtn_${tlId}`);

        if (statusCell) {
            statusCell.innerHTML = data.is_active
                ? '<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="fa-solid fa-circle-check me-1"></i>Active</span>'
                : '<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle px-2 py-1"><i class="fa-solid fa-circle-xmark me-1"></i>Deactivated</span>';
        }

        if (toggleBtnSpan) {
            toggleBtnSpan.innerHTML = data.is_active
                ? `<button type="button" class="btn btn-outline-danger btn-sm py-0 px-2" onclick="toggleTeamLeadStatus(${tlId})" title="Deactivate Team Leader">Deactivate</button>`
                : `<button type="button" class="btn btn-outline-success btn-sm py-0 px-2" onclick="toggleTeamLeadStatus(${tlId})" title="Activate Team Leader">Activate</button>`;
        }

        const tl = globalTeamLeadsCache.find(x => x.id === tlId);
        if (tl) tl.is_active = data.is_active;
    } catch(err) {
        showToast(err.message, "danger");
    }
}


// =========================================================================
// 3. BA CONTRACTOR EMPLOYEES MANAGEMENT
// =========================================================================
async function loadAllEmployees(circle = '') {
    const tbody = document.getElementById('employeesTableBody');
    if (!tbody) return;

    try {
        const url = circle ? `/api/admin/employees/all?circle=${encodeURIComponent(circle)}` : '/api/admin/employees/all';
        const res = await fetch(url);
        if (!res.ok) {
            if (res.status === 403) throw new Error("Admin access required");
            throw new Error("Failed to load employees");
        }
        const emps = await res.json();
        globalEmployeesCache = Array.isArray(emps) ? emps : [];
        renderEmployeesTable(globalEmployeesCache);
    } catch(err) {
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="7" class="text-center text-danger py-3"><i class="fa-solid fa-triangle-exclamation me-1"></i> ${err.message}</td></tr>`;
        }
    }
}

async function loadEmployees(circle = '') {
    return await loadAllEmployees(circle);
}
const loadEmployeesTable = loadEmployees;

function renderEmployeesTable(emps) {
    const tbody = document.getElementById('employeesTableBody');
    if (!tbody) return;

    if (!emps || emps.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted py-3">No personnel found for this selection.</td></tr>';
        return;
    }

    tbody.innerHTML = emps.map(e => {
        const statusBadge = e.is_active
            ? '<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="fa-solid fa-circle-check me-1"></i>Active</span>'
            : '<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle px-2 py-1"><i class="fa-solid fa-circle-xmark me-1"></i>Deactivated</span>';

        const toggleBtn = e.is_active
            ? `<button type="button" class="btn btn-outline-danger btn-sm py-0 px-2" onclick="toggleEmployeeStatus(${e.id})" title="Deactivate Employee">Deactivate</button>`
            : `<button type="button" class="btn btn-outline-success btn-sm py-0 px-2" onclick="toggleEmployeeStatus(${e.id})" title="Activate Employee">Activate</button>`;

        return `
            <tr id="empRow_${e.id}">
                <td><code class="fw-bold">${e.emp_code}</code></td>
                <td class="fw-bold text-dark">${e.name}</td>
                <td>${e.designation || '<span class="text-muted">-</span>'}</td>
                <td><span class="badge bg-light text-primary border">${e.circle}</span></td>
                <td><span class="badge bg-light text-dark border">${e.team_name || 'Unassigned'}</span></td>
                <td id="empStatusCell_${e.id}">${statusBadge}</td>
                <td class="text-end">
                    <div class="d-inline-flex gap-1">
                        <button type="button" class="btn btn-outline-primary btn-sm py-0 px-2" onclick="openEditEmployeeModal(${e.id})" title="Edit Details">
                            <i class="fa-solid fa-pen-to-square"></i> Edit
                        </button>
                        <span id="empToggleBtn_${e.id}">${toggleBtn}</span>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

async function createEmployee(e) {
    e.preventDefault();
    setButtonLoading('btnCreateEmp', true);

    const teamIdVal = document.getElementById('empTeamSelect') ? document.getElementById('empTeamSelect').value : '';
    const payload = {
        emp_code: document.getElementById('empCode').value.trim(),
        name: document.getElementById('empName').value.trim(),
        designation: document.getElementById('empDesig') ? document.getElementById('empDesig').value.trim() : null,
        circle: document.getElementById('empCircle').value,
        team_id: teamIdVal ? parseInt(teamIdVal) : null
    };

    try {
        const res = await fetch('/api/admin/employees', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to create employee");

        showToast(data.message || "BA Personnel registered successfully!", "success");
        const form = document.getElementById('createEmployeeForm');
        if (form) form.reset();
        const filterEl = document.getElementById('filterEmpCircle');
        const currentFilter = filterEl ? filterEl.value : '';
        loadAllEmployees(currentFilter);
    } catch(err) {
        showToast(err.message, "danger");
    } finally {
        setButtonLoading('btnCreateEmp', false, '<i class="fa-solid fa-user-check me-1"></i> Register BA Personnel');
    }
}

function openEditEmployeeModal(empId) {
    const emp = globalEmployeesCache.find(e => e.id === empId);
    if (!emp) return;

    const idEl = document.getElementById('editEmpId');
    const codeEl = document.getElementById('editEmpCode');
    const nameEl = document.getElementById('editEmpName');
    const desigEl = document.getElementById('editEmpDesignation');
    const circEl = document.getElementById('editEmpCircle');
    const actEl = document.getElementById('editEmpIsActive');

    if (idEl) idEl.value = emp.id;
    if (codeEl) codeEl.value = emp.emp_code;
    if (nameEl) nameEl.value = emp.name;
    if (desigEl) desigEl.value = emp.designation || '';
    if (circEl) circEl.value = emp.circle;
    if (actEl) actEl.checked = !!emp.is_active;

    filterSquadOptionsByCircle(emp.circle, 'editEmpTeamSelect', emp.team_id);

    const modalEl = document.getElementById('editEmployeeModal');
    if (modalEl) {
        const modal = new bootstrap.Modal(modalEl);
        modal.show();
    }
}

async function submitEditEmployee(e) {
    e.preventDefault();
    const empId = document.getElementById('editEmpId').value;
    setButtonLoading('btnSaveEditEmp', true);

    const teamSelect = document.getElementById('editEmpTeamSelect');
    const teamIdVal = teamSelect ? teamSelect.value : '';
    const payload = {
        emp_code: document.getElementById('editEmpCode').value.trim(),
        name: document.getElementById('editEmpName').value.trim(),
        designation: document.getElementById('editEmpDesignation') ? document.getElementById('editEmpDesignation').value.trim() : null,
        circle: document.getElementById('editEmpCircle').value,
        team_id: teamIdVal ? parseInt(teamIdVal) : 0,
        is_active: document.getElementById('editEmpIsActive').checked
    };

    try {
        const res = await fetch(`/api/admin/employees/${empId}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to update employee");

        showToast(data.message || "Personnel updated successfully!", "success");

        const modalEl = document.getElementById('editEmployeeModal');
        if (modalEl) {
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
        }

        const filterEl = document.getElementById('filterEmpCircle');
        const currentFilter = filterEl ? filterEl.value : '';
        loadAllEmployees(currentFilter);
    } catch(err) {
        showToast(err.message, "danger");
    } finally {
        setButtonLoading('btnSaveEditEmp', false, 'Save Changes');
    }
}

async function toggleEmployeeStatus(empId) {
    try {
        const res = await fetch(`/api/admin/employees/${empId}/toggle-status`, {
            method: 'PATCH'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to toggle status");

        showToast(data.message, "success");

        const statusCell = document.getElementById(`empStatusCell_${empId}`);
        const toggleBtnSpan = document.getElementById(`empToggleBtn_${empId}`);

        if (statusCell) {
            statusCell.innerHTML = data.is_active
                ? '<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="fa-solid fa-circle-check me-1"></i>Active</span>'
                : '<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle px-2 py-1"><i class="fa-solid fa-circle-xmark me-1"></i>Deactivated</span>';
        }

        if (toggleBtnSpan) {
            toggleBtnSpan.innerHTML = data.is_active
                ? `<button type="button" class="btn btn-outline-danger btn-sm py-0 px-2" onclick="toggleEmployeeStatus(${empId})" title="Deactivate Employee">Deactivate</button>`
                : `<button type="button" class="btn btn-outline-success btn-sm py-0 px-2" onclick="toggleEmployeeStatus(${empId})" title="Activate Employee">Activate</button>`;
        }

        const e = globalEmployeesCache.find(x => x.id === empId);
        if (e) e.is_active = data.is_active;
    } catch(err) {
        showToast(err.message, "danger");
    }
}


// =========================================================================
// 4. PORTAL USERS & RBAC MANAGEMENT
// =========================================================================
async function loadAllUsers() {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;

    try {
        const res = await fetch('/api/admin/users/all');
        if (!res.ok) {
            if (res.status === 403) throw new Error("Admin access required");
            throw new Error("Failed to load users");
        }
        const users = await res.json();
        globalUsersCache = Array.isArray(users) ? users : [];
        renderUsersTable(globalUsersCache);
    } catch(err) {
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger py-3"><i class="fa-solid fa-triangle-exclamation me-1"></i> ${err.message}</td></tr>`;
        }
    }
}

async function loadUsers() {
    return await loadAllUsers();
}
const loadUsersTable = loadUsers;

function renderUsersTable(users) {
    const tbody = document.getElementById('usersTableBody');
    if (!tbody) return;

    if (!users || users.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-3">No user accounts found.</td></tr>';
        return;
    }

    tbody.innerHTML = users.map(u => {
        let roleBadgeClass = 'bg-secondary';
        if (u.role === 'ADMIN') roleBadgeClass = 'bg-danger';
        else if (u.role === 'SUB_ADMIN') roleBadgeClass = 'bg-primary';

        const roleBadge = `<span class="badge ${roleBadgeClass} px-2 py-1">${u.role}</span>`;

        const canEditBadge = u.can_edit
            ? '<span class="badge bg-success-subtle text-success border border-success-subtle">Read / Write</span>'
            : '<span class="badge bg-light text-muted border">View-Only</span>';

        const statusBadge = u.is_active
            ? '<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="fa-solid fa-circle-check me-1"></i>Active</span>'
            : '<span class="badge bg-danger-subtle text-danger border border-danger-subtle px-2 py-1"><i class="fa-solid fa-user-slash me-1"></i>Blocked</span>';

        const toggleBtn = u.is_active
            ? `<button type="button" class="btn btn-outline-danger btn-sm py-0 px-2" onclick="toggleUserStatus(${u.id})" title="Block / Deactivate Login">Deactivate</button>`
            : `<button type="button" class="btn btn-outline-success btn-sm py-0 px-2" onclick="toggleUserStatus(${u.id})" title="Restore Login Access">Activate</button>`;

        const squadOrCircle = (u.role === 'USER')
            ? (u.team_name ? `<span class="badge bg-primary-subtle text-primary border border-primary-subtle"><i class="fa-solid fa-users me-1"></i> ${u.team_name}</span>` : '<span class="badge bg-warning-subtle text-dark border">No Squad Assigned</span>')
            : `<span class="badge bg-light text-dark border">${u.circle || 'ALL'}</span>`;

        return `
            <tr id="userRow_${u.id}">
                <td class="fw-bold text-dark"><i class="fa-solid fa-user-circle text-secondary me-1"></i> ${u.username}</td>
                <td>${roleBadge}</td>
                <td>${squadOrCircle}</td>
                <td>${canEditBadge}</td>
                <td id="userStatusCell_${u.id}">${statusBadge}</td>
                <td class="text-end">
                    <div class="d-inline-flex gap-1">
                        <button type="button" class="btn btn-outline-primary btn-sm py-0 px-2" onclick="openEditUserModal(${u.id})" title="Edit Role & Permissions">
                            <i class="fa-solid fa-pen-to-square"></i> Edit
                        </button>
                        <span id="userToggleBtn_${u.id}">${toggleBtn}</span>
                    </div>
                </td>
            </tr>
        `;
    }).join('');
}

function populateUserSquadOptions() {
    const usrTeamEl = document.getElementById('usrTeamId');
    const editTeamEl = document.getElementById('editUserTeamId');
    const teams = globalTeamsCache || [];
    let html = '<option value="">-- Select Assigned Squad --</option>';
    teams.forEach(t => {
        html += `<option value="${t.id}">${t.name} (${t.circle})</option>`;
    });
    if (usrTeamEl) usrTeamEl.innerHTML = html;
    if (editTeamEl) editTeamEl.innerHTML = html;
}

function handleUserRoleChange(role) {
    const circGroup = document.getElementById('usrCircleGroup');
    const editGroup = document.getElementById('usrCanEditGroup');
    const teamGroup = document.getElementById('usrTeamGroup');

    if (role === 'ADMIN') {
        if (circGroup) circGroup.style.display = 'none';
        if (editGroup) editGroup.style.display = 'none';
        if (teamGroup) teamGroup.style.display = 'none';
    } else if (role === 'USER') {
        if (circGroup) circGroup.style.display = 'none';
        if (editGroup) editGroup.style.display = 'none';
        if (teamGroup) teamGroup.style.display = 'block';
    } else {
        if (circGroup) circGroup.style.display = 'block';
        if (editGroup) editGroup.style.display = 'block';
        if (teamGroup) teamGroup.style.display = 'none';
    }
}

function handleEditUserRoleChange(role) {
    const circGroup = document.getElementById('editUserCircleGroup');
    const editGroup = document.getElementById('editUserCanEditGroup');
    const teamGroup = document.getElementById('editUserTeamGroup');

    if (role === 'ADMIN') {
        if (circGroup) circGroup.style.display = 'none';
        if (editGroup) editGroup.style.display = 'none';
        if (teamGroup) teamGroup.style.display = 'none';
    } else if (role === 'USER') {
        if (circGroup) circGroup.style.display = 'none';
        if (editGroup) editGroup.style.display = 'none';
        if (teamGroup) teamGroup.style.display = 'block';
    } else {
        if (circGroup) circGroup.style.display = 'block';
        if (editGroup) editGroup.style.display = 'block';
        if (teamGroup) teamGroup.style.display = 'none';
    }
}

async function createUser(e) {
    e.preventDefault();
    setButtonLoading('btnCreateUser', true);

    const role = document.getElementById('usrRole').value;
    const selectedCircles = Array.from(document.querySelectorAll('.usr-circle-check:checked')).map(cb => cb.value);
    const teamIdVal = document.getElementById('usrTeamId') ? document.getElementById('usrTeamId').value : '';

    if (role === 'USER') {
        if (!teamIdVal) {
            showToast("Please select an assigned squad for this field user account", "warning");
            setButtonLoading('btnCreateUser', false, '<i class="fa-solid fa-user-plus me-1"></i> Create Account');
            return;
        }
    } else if (role === 'SUB_ADMIN' && selectedCircles.length === 0) {
        showToast("Please select at least one assigned circle for this Sub-Admin account", "warning");
        setButtonLoading('btnCreateUser', false, '<i class="fa-solid fa-user-plus me-1"></i> Create Account');
        return;
    }

    const payload = {
        username: document.getElementById('usrName').value.trim(),
        password: document.getElementById('usrPass').value.trim(),
        role: role,
        circle: (role === 'SUB_ADMIN') ? (selectedCircles.length ? selectedCircles.join(',') : null) : null,
        team_id: (role === 'USER' && teamIdVal) ? parseInt(teamIdVal) : null,
        can_edit: (role === 'SUB_ADMIN' && document.getElementById('usrCanEdit')) ? document.getElementById('usrCanEdit').checked : false
    };

    try {
        const res = await fetch('/api/admin/users', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to create user account");

        showToast(data.message || "User account created successfully!", "success");
        const form = document.getElementById('createUserForm');
        if (form) form.reset();
        document.querySelectorAll('.usr-circle-check').forEach(cb => cb.checked = false);
        loadAllUsers();
    } catch(err) {
        showToast(err.message, "danger");
    } finally {
        setButtonLoading('btnCreateUser', false, '<i class="fa-solid fa-user-plus me-1"></i> Create Account');
    }
}

function openEditUserModal(userId) {
    const user = globalUsersCache.find(u => u.id === userId);
    if (!user) return;

    const idEl = document.getElementById('editUserId');
    const nameEl = document.getElementById('editUsername');
    const roleEl = document.getElementById('editUserRole');
    const editEl = document.getElementById('editUserCanEdit');
    const passEl = document.getElementById('editUserNewPass');
    const actEl = document.getElementById('editUserIsActive');

    if (idEl) idEl.value = user.id;
    if (nameEl) nameEl.value = user.username;
    if (roleEl) roleEl.value = user.role;
    if (editEl) editEl.checked = !!user.can_edit;
    if (passEl) passEl.value = '';
    if (actEl) actEl.checked = !!user.is_active;

    // Check assigned circles
    const assigned = user.circle ? user.circle.split(',').map(s => s.trim().toUpperCase()) : [];
    document.querySelectorAll('.edit-usr-circle-check').forEach(cb => {
        const val = cb.value.toUpperCase();
        cb.checked = assigned.includes(val) || 
                     (val === 'BERHAMPUR CITY' && assigned.includes('CITY')) || 
                     (val === 'CITY' && assigned.includes('BERHAMPUR CITY'));
    });

    const teamEl = document.getElementById('editUserTeamId');
    if (teamEl) teamEl.value = user.team_id || '';

    handleEditUserRoleChange(user.role);

    const modalEl = document.getElementById('editUserModal');
    if (modalEl) {
        const modal = new bootstrap.Modal(modalEl);
        modal.show();
    }
}

async function submitEditUser(e) {
    e.preventDefault();
    const userId = document.getElementById('editUserId').value;
    setButtonLoading('btnSaveEditUser', true);

    const role = document.getElementById('editUserRole').value;
    const newPass = document.getElementById('editUserNewPass') ? document.getElementById('editUserNewPass').value.trim() : '';
    const selectedCircles = Array.from(document.querySelectorAll('.edit-usr-circle-check:checked')).map(cb => cb.value);
    const teamIdVal = document.getElementById('editUserTeamId') ? document.getElementById('editUserTeamId').value : '';

    if (role === 'USER') {
        if (!teamIdVal) {
            showToast("Please select an assigned squad for this user account", "warning");
            setButtonLoading('btnSaveEditUser', false, 'Save Changes');
            return;
        }
    } else if (role === 'SUB_ADMIN' && selectedCircles.length === 0) {
        showToast("Please select at least one assigned circle for this Sub-Admin account", "warning");
        setButtonLoading('btnSaveEditUser', false, 'Save Changes');
        return;
    }

    const payload = {
        role: role,
        circle: (role === 'SUB_ADMIN') ? (selectedCircles.length ? selectedCircles.join(',') : null) : null,
        team_id: (role === 'USER' && teamIdVal) ? parseInt(teamIdVal) : null,
        can_edit: (role === 'SUB_ADMIN' && document.getElementById('editUserCanEdit')) ? document.getElementById('editUserCanEdit').checked : false,
        is_active: document.getElementById('editUserIsActive') ? document.getElementById('editUserIsActive').checked : true
    };
    if (newPass) {
        payload.password = newPass;
    }

    try {
        const res = await fetch(`/api/admin/users/${userId}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to update user account");

        showToast(data.message || "User account updated successfully!", "success");

        const modalEl = document.getElementById('editUserModal');
        if (modalEl) {
            const modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
        }

        loadAllUsers();
    } catch(err) {
        showToast(err.message, "danger");
    } finally {
        setButtonLoading('btnSaveEditUser', false, 'Save Changes');
    }
}

async function toggleUserStatus(userId) {
    try {
        const res = await fetch(`/api/admin/users/${userId}/toggle-status`, {
            method: 'PATCH'
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to toggle status");

        showToast(data.message, "success");

        const statusCell = document.getElementById(`userStatusCell_${userId}`);
        const toggleBtnSpan = document.getElementById(`userToggleBtn_${userId}`);

        if (statusCell) {
            statusCell.innerHTML = data.is_active
                ? '<span class="badge bg-success-subtle text-success border border-success-subtle px-2 py-1"><i class="fa-solid fa-circle-check me-1"></i>Active</span>'
                : '<span class="badge bg-danger-subtle text-danger border border-danger-subtle px-2 py-1"><i class="fa-solid fa-user-slash me-1"></i>Blocked</span>';
        }

        if (toggleBtnSpan) {
            toggleBtnSpan.innerHTML = data.is_active
                ? `<button type="button" class="btn btn-outline-danger btn-sm py-0 px-2" onclick="toggleUserStatus(${userId})" title="Block / Deactivate Login">Deactivate</button>`
                : `<button type="button" class="btn btn-outline-success btn-sm py-0 px-2" onclick="toggleUserStatus(${userId})" title="Restore Login Access">Activate</button>`;
        }

        const u = globalUsersCache.find(x => x.id === userId);
        if (u) u.is_active = data.is_active;
    } catch(err) {
        showToast(err.message, "danger");
    }
}
