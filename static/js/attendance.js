// Attendance & Daily Operations Desk Logic

document.addEventListener('DOMContentLoaded', () => {
    const dateInput = document.getElementById('att-date');
    if (dateInput) {
        dateInput.value = new Date().toISOString().split('T')[0];
    }
    if (typeof populateOperationalCircleSelect === 'function') {
        populateOperationalCircleSelect('att-circle-filter', onAttendanceCircleChange);
    } else {
        onAttendanceCircleChange();
    }
});

let currentCircleTeams = [];
let currentCircleTLs = [];

async function onAttendanceCircleChange() {
    const circle = document.getElementById('att-circle-filter').value;
    if (!circle) return;

    try {
        // 1. Load Teams in circle
        const resTeams = await fetch(`/api/attendance/teams-by-circle/${encodeURIComponent(circle)}`);
        currentCircleTeams = await resTeams.json();

        const teamSelect = document.getElementById('att-team');
        const mergeSelect = document.getElementById('merge-team');

        const opts = currentCircleTeams.map(t => {
            const tag = (t.has_vehicle === false || t.is_office_team) ? ' [Office Team - No Vehicle]' : '';
            return `<option value="${t.id}">${t.name}${tag}</option>`;
        }).join('');
        teamSelect.innerHTML = '<option value="">-- Choose Squad in ' + circle + ' --</option>' + opts;
        mergeSelect.innerHTML = '<option value="">-- Select Partner Squad in ' + circle + ' --</option>' + opts;

        // 2. Load TPSODL Team Leaders for this circle
        const resTLs = await fetch(`/api/attendance/tls-by-circle/${encodeURIComponent(circle)}`);
        currentCircleTLs = await resTLs.json();
        const tlSelect = document.getElementById('att-tl-name');
        tlSelect.innerHTML = '<option value="">-- Select Team Leader --</option>' +
            currentCircleTLs.map(tl => {
                if (typeof tl === 'object' && tl !== null) {
                    return `<option value="${tl.id}" data-name="${tl.name}">${tl.name} (${tl.tl_code})</option>`;
                }
                return `<option value="${tl}" data-name="${tl}">${tl}</option>`;
            }).join('');

        // Check if user is squad-isolated
        if (typeof window.isSquadUser === 'function' && window.isSquadUser()) {
            const mySquadId = window.getUserSquadId();
            if (mySquadId) {
                teamSelect.value = mySquadId;
                teamSelect.disabled = true;
                onDateOrTeamChange();
                return;
            }
        }

        // Clear roster table
        document.getElementById('roster-tbody').innerHTML = 
            '<tr><td colspan="4" class="text-center text-muted py-4">Please select a squad from the dropdown above</td></tr>';
    } catch(err) {
        console.error("Error loading circle teams/TLs:", err);
    }
}

async function onDateOrTeamChange() {
    const teamId = document.getElementById('att-team').value;
    const opDate = document.getElementById('att-date').value;
    if (!teamId) return;

    // Auto-select assigned TL for this squad if matching
    const teamObj = currentCircleTeams.find(t => t.id == teamId);
    let officeAlert = document.getElementById('att-office-alert');
    if (teamObj && (teamObj.has_vehicle === false || teamObj.is_office_team)) {
        if (!officeAlert) {
            officeAlert = document.createElement('div');
            officeAlert.id = 'att-office-alert';
            officeAlert.className = 'alert alert-info py-2 px-3 mb-3 d-flex align-items-center small';
            officeAlert.innerHTML = '<i class="fa-solid fa-building me-2 fs-5"></i><div><strong>Office Team (Without Vehicle):</strong> This squad performs administrative/office tasks. BA employee attendance marked here will appear in the Form D contractor register. Field performance attribution and vehicle running are disabled for this team.</div>';
            const cardBody = document.getElementById('att-team').closest('.card-body');
            if (cardBody) cardBody.prepend(officeAlert);
        } else {
            officeAlert.style.display = 'flex';
        }
    } else if (officeAlert) {
        officeAlert.style.display = 'none';
    }

    if (teamObj) {
        const tlSelect = document.getElementById('att-tl-name');
        for (let i = 0; i < tlSelect.options.length; i++) {
            const opt = tlSelect.options[i];
            if (teamObj.default_tl_id && opt.value == teamObj.default_tl_id) {
                tlSelect.selectedIndex = i;
                break;
            } else if (teamObj.assigned_team_lead && (opt.getAttribute('data-name') === teamObj.assigned_team_lead || opt.value === teamObj.assigned_team_lead)) {
                tlSelect.selectedIndex = i;
                break;
            }
        }
    }

    // Load BA squad members (TPSODL TL is company employee and does NOT punch in this BA portal)
    try {
        const res = await fetch(`/api/attendance/team-members/${teamId}`);
        const members = await res.json();
        const tbody = document.getElementById('roster-tbody');

        if (!members || !members.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-4">No BA contractor squad members found assigned to this squad</td></tr>';
        } else {
            tbody.innerHTML = members.map(m => `
                <tr>
                    <td><strong class="text-primary">${m.emp_code}</strong></td>
                    <td class="fw-semibold">${m.name}</td>
                    <td><span class="badge bg-light text-dark border">${m.designation}</span></td>
                    <td class="text-center">
                        <input type="hidden" class="att-emp-id" value="${m.id}">
                        <div class="btn-group btn-group-sm w-100" role="group">
                            <input type="radio" class="btn-check" name="status_${m.id}" id="p_${m.id}" value="P" checked>
                            <label class="btn btn-outline-success" for="p_${m.id}">P</label>

                            <input type="radio" class="btn-check" name="status_${m.id}" id="a_${m.id}" value="A">
                            <label class="btn btn-outline-danger" for="a_${m.id}">A</label>

                            <input type="radio" class="btn-check" name="status_${m.id}" id="l_${m.id}" value="L">
                            <label class="btn btn-outline-warning" for="l_${m.id}">L</label>

                            <input type="radio" class="btn-check" name="status_${m.id}" id="wo_${m.id}" value="WO">
                            <label class="btn btn-outline-secondary" for="wo_${m.id}">-</label>
                        </div>
                    </td>
                </tr>
            `).join('');
        }

        // Check if saved state exists
        if (opDate) {
            checkExistingDailyOperation(opDate, teamId);
        }
    } catch(err) {
        console.error("Error loading team members:", err);
    }
}

async function checkExistingDailyOperation(opDate, teamId) {
    try {
        const res = await fetch(`/api/attendance/status?operation_date=${opDate}&team_id=${teamId}`);
        const data = await res.json();
        const banner = document.getElementById('att-status-banner');

        if (data.exists) {
            const isLocked = !!data.is_locked;
            const isUser = (typeof window.isSquadUser === 'function') && window.isSquadUser();

            banner.style.display = 'block';
            if (isLocked) {
                banner.style.backgroundColor = '#f1f5f9';
                banner.style.color = '#334155';
                banner.style.border = '1px solid #cbd5e1';
                banner.innerHTML = `
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <span class="badge bg-secondary me-2"><i class="fa-solid fa-lock"></i> Locked</span>
                            <strong>Saved Entry (Locked):</strong> Squad recorded as <u>${data.operation_mode.replace(/_/g, ' ')}</u> on this date.
                            <div class="small text-muted mt-1"><i class="fa-solid fa-circle-info me-1"></i>Entries are locked upon submission. For corrections, contact your Circle Admin.</div>
                        </div>
                        ${!isUser ? `<button type="button" class="btn btn-sm btn-outline-primary" onclick="toggleAttendanceLock(${data.operation_id})"><i class="fa-solid fa-lock-open me-1"></i> Unlock</button>` : ''}
                    </div>
                `;
            } else {
                banner.style.backgroundColor = '#ecfdf5';
                banner.style.color = '#065f46';
                banner.style.border = '1px solid #a7f3d0';
                banner.innerHTML = `
                    <div class="d-flex justify-content-between align-items-center">
                        <div>
                            <span class="badge bg-success me-2"><i class="fa-solid fa-unlock"></i> Unlocked</span>
                            <strong>Saved Entry Found:</strong> Squad recorded as <u>${data.operation_mode.replace(/_/g, ' ')}</u> on this date.
                        </div>
                        ${!isUser ? `<button type="button" class="btn btn-sm btn-outline-secondary" onclick="toggleAttendanceLock(${data.operation_id})"><i class="fa-solid fa-lock me-1"></i> Lock</button>` : ''}
                    </div>
                `;
            }

            const saveBtn = document.getElementById('save-att-btn');
            if (saveBtn) {
                if (isUser && isLocked) {
                    saveBtn.disabled = true;
                    saveBtn.title = "Entries are locked upon submission. For corrections, contact your Circle Admin.";
                } else {
                    saveBtn.disabled = false;
                    saveBtn.title = "";
                }
            }

            const tlSelect = document.getElementById('att-tl-name');
            if (data.daily_tl_id) {
                for (let i = 0; i < tlSelect.options.length; i++) {
                    if (tlSelect.options[i].value == data.daily_tl_id) {
                        tlSelect.selectedIndex = i;
                        break;
                    }
                }
            } else if (data.tl_name) {
                for (let i = 0; i < tlSelect.options.length; i++) {
                    if (tlSelect.options[i].getAttribute('data-name') === data.tl_name || tlSelect.options[i].value === data.tl_name) {
                        tlSelect.selectedIndex = i;
                        break;
                    }
                }
            }

            document.getElementById('att-active').value = data.is_team_active ? 'true' : 'false';
            toggleTeamActiveStatus();

            document.getElementById('att-tl-present').value = data.operating_with_tl ? 'true' : 'false';
            toggleTLStatus();

            if (data.operation_mode === 'MERGED') {
                const rMerged = document.getElementById('modeMerged');
                if (rMerged) rMerged.checked = true;
                toggleMerge(true);
                if (data.merged_with_team_id) {
                    document.getElementById('merge-team').value = data.merged_with_team_id;
                }
            }

            if (data.remarks) {
                document.getElementById('att-remarks').value = data.remarks;
            }

            if (data.attendance) {
                Object.entries(data.attendance).forEach(([empId, status]) => {
                    const r = document.querySelector(`input[name="status_${empId}"][value="${status}"]`);
                    if (r) r.checked = true;
                });
            }
        } else {
            banner.style.display = 'none';
        }
    } catch(e) {
        console.error("Status check failed:", e);
    }
}

function toggleTeamActiveStatus() {
    const isActive = document.getElementById('att-active').value === 'true';
    const tlWrapper = document.getElementById('tl-status-wrapper');
    const absentBox = document.getElementById('tl-absent-box');
    const remarksBox = document.getElementById('remarks-box');

    if (!isActive) {
        tlWrapper.style.display = 'none';
        absentBox.style.display = 'none';
        remarksBox.style.display = 'block';
    } else {
        tlWrapper.style.display = 'block';
        toggleTLStatus();
    }
}

function toggleTLStatus() {
    const withTL = document.getElementById('att-tl-present').value === 'true';
    const absentBox = document.getElementById('tl-absent-box');
    const remarksBox = document.getElementById('remarks-box');

    if (!withTL) {
        absentBox.style.display = 'block';
        const isMerged = document.querySelector('input[name="tl_mode"]:checked')?.value === 'Merged';
        toggleMerge(isMerged);
    } else {
        absentBox.style.display = 'none';
        remarksBox.style.display = 'none';
    }
}

function toggleMerge(isMerged) {
    const mergeWrapper = document.getElementById('merge-team-wrapper');
    const remarksBox = document.getElementById('remarks-box');
    if (isMerged) {
        mergeWrapper.style.display = 'block';
        remarksBox.style.display = 'block';
    } else {
        mergeWrapper.style.display = 'none';
        remarksBox.style.display = 'none';
    }
}

async function handleAttendanceSubmit(e) {
    e.preventDefault();
    setButtonLoading('att-submit-btn', true);

    const teamId = parseInt(document.getElementById('att-team').value);
    const opDate = document.getElementById('att-date').value;
    const circle = document.getElementById('att-circle-filter').value;

    if (typeof isCircleAuthorizedClient === 'function' && !isCircleAuthorizedClient(circle)) {
        showToast(`Unauthorized: You do not have permissions for circle: ${circle}`, "danger");
        setButtonLoading('att-submit-btn', false);
        return;
    }

    const tlSelect = document.getElementById('att-tl-name');
    let dailyTlId = null;
    let tlName = '';
    if (tlSelect && tlSelect.selectedIndex > 0) {
        const selectedOpt = tlSelect.options[tlSelect.selectedIndex];
        dailyTlId = parseInt(selectedOpt.value) || null;
        tlName = selectedOpt.getAttribute('data-name') || selectedOpt.text;
    }

    const isActive = document.getElementById('att-active').value === 'true';
    const operatingWithTL = document.getElementById('att-tl-present').value === 'true';

    let opMode = "INDEPENDENT_WITH_TL";
    let mergedTeamId = null;

    if (!isActive) {
        opMode = "NON_OPERATIONAL";
    } else if (!operatingWithTL) {
        const modeVal = document.querySelector('input[name="tl_mode"]:checked')?.value;
        if (modeVal === 'Merged') {
            opMode = "MERGED";
            mergedTeamId = document.getElementById('merge-team').value ? parseInt(document.getElementById('merge-team').value) : null;
        } else {
            opMode = "INDEPENDENT_WITHOUT_TL_COLLECTION";
        }
    }

    // Collect BA members attendance (only BA squad personnel, TL does not punch)
    const empRows = document.querySelectorAll('#roster-tbody tr');
    const attList = [];
    empRows.forEach(row => {
        const idInput = row.querySelector('.att-emp-id');
        if (idInput) {
            const empId = parseInt(idInput.value);
            const checked = row.querySelector(`input[name="status_${empId}"]:checked`);
            attList.push({ employee_id: empId, status: checked ? checked.value : 'P' });
        }
    });

    const payload = {
        operation_date: opDate,
        team_id: teamId,
        circle: circle,
        daily_tl_id: dailyTlId,
        tl_name: tlName,
        is_team_active: isActive,
        operating_with_tl: operatingWithTL,
        operation_mode: opMode,
        merged_with_team_id: mergedTeamId,
        remarks: document.getElementById('att-remarks')?.value.trim() || null,
        attendance: attList
    };

    try {
        const res = await fetch('/api/attendance/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to save attendance");

        const banner = document.getElementById('att-status-banner');
        banner.style.display = 'block';
        banner.style.backgroundColor = '#ecfdf5';
        banner.style.color = '#065f46';
        banner.style.border = '1px solid #a7f3d0';
        banner.innerHTML = `<i class="fa-solid fa-circle-check me-2"></i>${data.message}`;

        showToast(data.message);
    } catch(err) {
        alert(err.message);
    } finally {
        setButtonLoading('att-submit-btn', false, '<i class="fa-solid fa-lock me-1"></i> Save & Lock Attendance');
    }
}

async function toggleAttendanceLock(opId) {
    try {
        const res = await fetch(`/api/attendance/operation/${opId}/toggle-lock`, { method: 'PATCH' });
        const d = await res.json();
        if (!res.ok) throw new Error(d.detail || "Failed to toggle lock");
        showToast(d.message || "Lock state updated", "success");
        const opDate = document.getElementById('att-date').value;
        const teamId = document.getElementById('att-team').value;
        if (opDate && teamId) checkExistingDailyOperation(opDate, teamId);
    } catch(err) {
        showToast(err.message, "danger");
    }
}

