// Official TPSODL Electrical Hierarchy & Real-Time Load Booking Entry Desk

const TPSODL_HIERARCHY = {
  "ASKA": {
    "AED ASKA-I": {
      "ASKA": ["ESO ASKA-1", "ESO BALISIRA", "ESO DHARAKOTE"],
      "NUAGAON": ["ESO NUAGAM-I", "ESO NUAGAM-II"]
    },
    "AED ASKA-II": {
      "BUGUDA": ["ESO BALIPADAR", "ESO BUGUDA"],
      "K S NAGAR": ["ESO BUDHAAMBA", "ESO K S NAGAR"]
    },
    "GSED DIGAPAHANDI": {
      "CHIKITI": ["ESO CHIKITI", "ESO NUAPADA", "ESO PATRAPUR", "ESO SURANGI"],
      "DIGAPAHANDI": ["ESO BOMAKEI", "ESO DIGAPAHANDI", "ESO PUDAMARI"]
    }
  },
  "BERHAMPUR": {
    "GANJAM NORTH": {
      "CHATRAPUR": ["ESO CHATRAPUR-I", "ESO CHATRAPUR-II"],
      "KHALLIKOTE": ["ESO KESHPUR", "ESO KHALLIKOTE"],
      "RAMBHA": ["ESO GANJAM", "ESO MALUD", "ESO RAMBHA"]
    },
    "HED HINJILICUT": {
      "HINJILICUT": ["ESO HINJILICUT", "ESO KANCHURU", "ESO PITALA"],
      "SHERAGADA": ["ESO KONKARADA", "ESO PATTAPUR", "ESO SHERAGADA"]
    },
    "PSED PURUSOTTAMPUR": {
      "KODALA": ["ESO BEGUNIAPADA", "ESO KODALA"],
      "P S PUR": ["ESO P S PUR", "ESO TARATARINI"],
      "POLASARA": ["ESO CHIRIKIPADA", "ESO POLOSARA"]
    }
  },
  "BERHAMPUR CITY": {
    "BERHAMPUR-I": {
      "BIJIPUR": ["ESO BIJIPUR", "ESO LANJIPALLI"],
      "GOPALPUR": ["ESO GOPALPUR", "ESO HEAD QUARTER", "ESO UNIVERSITY"],
      "SUB.DIV.NO-2": ["ESO AMBAPUA", "ESO MEDICAL"]
    },
    "BERHAMPUR-II": {
      "SUB.DIVISION NO-1": ["ESO E.S.O.NO.1", "ESO E.S.O.NO.2", "ESO E.S.O.NO.3"],
      "SUB.DIVISION NO-3": ["ESO G.NUAGAM-2", "ESO GANDHINAGAR"]
    },
    "BERHAMPUR-III": {
      "KANISI": ["ESO GOLANTHARA", "ESO JAGAPUR", "ESO KANISI"],
      "SUB.DIVISION NO-4": ["ESO KUKUDAKHANDI", "ESO LATHI", "ESO LUCHAPADA"]
    }
  },
  "BHANJANAGAR": {
    "BNED BHANJANAGAR": {
      "BELAGUNTHA": ["ESO BELAGUNTHA", "ESO J N PRASAD"],
      "BHANJANAGAR-I": ["ESO BHEJIPUT", "ESO E S O-I", "ESO TILISINGI"],
      "BHANJANAGAR-II": ["ESO E S O-II", "ESO K B PUR", "ESO KANTEIPALLY"],
      "SORODA": ["ESO BADAGADA", "ESO SORODA"]
    },
    "BoED BOUDH": {
      "BOUDH": ["ESO BOUDH", "ESO PURUNAKATAK"],
      "MANAMUNDA": ["ESO BAUNSUNI", "ESO MANAMUNDA"]
    },
    "PED PHULBANI": {
      "BALLIGUDA": ["ESO BALLIGUDA", "ESO DARINGIBADI", "ESO TUMUDIBANDHA"],
      "G.UDAYAGIRI": ["ESO G.UDAYAGIRI", "ESO RAIKIA", "ESO TIKABALI"],
      "PHULBANI": ["ESO KHAJURIPADA", "ESO PHIRINGAI", "ESO PHULBANI"]
    }
  },
  "JEYPORE": {
    "JED JEYPORE": {
      "BORIGUMA": ["ESO B.SINGIPUR", "ESO BORIGUMA", "ESO KOTPAD"],
      "JEYPORE SDO-I": ["ESO BAIPARIGUDA", "ESO JYP NO.2", "ESO JYP NO.3"],
      "JEYPORE SDO-II": ["ESO JYP NO.1", "ESO KUNDRA", "ESO RANDHAPALLI"]
    },
    "KED KORAPUT": {
      "KORAPUT": ["ESO KORAPUT SEC-I", "ESO KORAPUT SEC-II"],
      "LAXMIPUR": ["ESO BANDHUGAON", "ESO KAKIRIGUMA", "ESO LAXMIPUR"],
      "SUNABEDA": ["ESO NANDAPUR", "ESO PATTANGI", "ESO SIMILIGUDA", "ESO SUNABEDA"]
    },
    "MED MALKANAGIRI": {
      "BALIMELA": ["ESO BALIMELA", "ESO MATHILI"],
      "MALKANGIRI": ["ESO KALIMELA", "ESO MALKANGIRI"]
    },
    "NED NABARANGAPUR": {
      "NAWARANGPUR": ["ESO NABARANGAPUR", "ESO NABARANGPUR RURAL", "ESO T KHUNTI"],
      "PAPADAHANDI": ["ESO DABUGAON", "ESO KOSAGUMUDA", "ESO PAPADAHANDI"],
      "UMARKOT": ["ESO CHANDAHANDI", "ESO JHARIGAM", "ESO RAIGHAR", "ESO UMERKOTE"]
    }
  },
  "RAYAGADA": {
    "GED GUNUPUR": {
      "GUMUDA": ["ESO GUDARI", "ESO GUMUDA", "ESO PADMAPUR", "ESO RAMNAGUDA"],
      "GUNUPUR": ["ESO GUNUPUR", "ESO GUNUPUR RURAL"]
    },
    "PKED PARLAKHEMUNDI": {
      "KASINAGAR": ["ESO GUMMA", "ESO KASINAGAR"],
      "MOHANA": ["ESO ADABA", "ESO CHANDRAGIRI", "ESO MOHANA"],
      "PARLAKHEMUNDI": ["ESO PARLAKHEMUNDI", "ESO PARLAKHEMUNDI RURAL"],
      "R.UDAYGIRI": ["ESO KHAJURIPADA", "ESO KHAJURIPADA-I", "ESO R.UDAYGIRI"],
      "UPPALADA": ["ESO GARABANDHA", "ESO RAIGADA", "ESO UPALADA"]
    },
    "RED RAYAGADA": {
      "BISSAM CUTTACK": ["ESO BISSAM CTC", "ESO MUNIGUDA"],
      "RAYAGADA": ["ESO J.K.PUR", "ESO RAYAGADA RURAL", "ESO RAYAGADA-1", "ESO RAYAGADA-2"],
      "THERUBALLI": ["ESO KASIPUR", "ESO SIKARPAI", "ESO THERUBALI"]
    }
  }
};

// State Variables
let resolvedCircle = null;
let resolvedEmpCode = null;

// Normalize Circle Helper
function normalizeCircle(name) {
    if (!name) return '';
    const upper = name.trim().toUpperCase();
    if (upper === 'CITY' || upper === 'BERHAMPUR CITY') return 'BERHAMPUR CITY';
    if (TPSODL_HIERARCHY[upper]) return upper;
    const match = Object.keys(TPSODL_HIERARCHY).find(c => c.toUpperCase() === upper);
    return match || upper;
}

document.addEventListener('DOMContentLoaded', () => {
    // Set default booking date to today
    const dInput = document.getElementById('lbBookingDate');
    if (dInput) dInput.value = new Date().toISOString().split('T')[0];

    // Clear duplicate page errors on input
    const pageInput = document.getElementById('lbPageNumber');
    if (pageInput) {
        pageInput.addEventListener('input', () => {
            pageInput.classList.remove('is-invalid');
            const alertBox = document.getElementById('lbPageErrorAlert');
            if (alertBox) alertBox.style.display = 'none';
        });
    }

    const bookInput = document.getElementById('lbBookNumber');
    if (bookInput) {
        bookInput.addEventListener('input', () => {
            const pageEl = document.getElementById('lbPageNumber');
            if (pageEl) pageEl.classList.remove('is-invalid');
            const alertBox = document.getElementById('lbPageErrorAlert');
            if (alertBox) alertBox.style.display = 'none';
        });
    }

    // Trigger verification on Enter in Employee Code input
    const empInput = document.getElementById('lbEmpCode');
    if (empInput) {
        empInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                verifyEmployeeCode();
            }
        });
    }
});

// 1. Verify Employee / Team Leader Code
async function verifyEmployeeCode() {
    const empInput = document.getElementById('lbEmpCode');
    const code = empInput ? empInput.value.trim() : '';
    const notice = document.getElementById('verifyStatusNotice');
    const empNameEl = document.getElementById('lbEmpName');
    const assignedCircleEl = document.getElementById('lbAssignedCircle');

    if (!code) {
        showToast("Please enter an Employee ID or Team Leader Code", "warning");
        if (empInput) empInput.focus();
        return;
    }

    setButtonLoading('btnVerifyEmp', true);
    if (notice) notice.style.display = 'none';

    try {
        const res = await fetch(`/api/load-booking/verify-employee?emp_code=${encodeURIComponent(code)}`);
        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.detail || "Employee / Team Leader Code not found");
        }

        resolvedEmpCode = data.emp_code;
        resolvedCircle = normalizeCircle(data.circle);

        if (typeof isCircleAuthorizedClient === 'function' && !isCircleAuthorizedClient(resolvedCircle)) {
            const authCircles = (typeof getUserAuthorizedCircles === 'function') ? getUserAuthorizedCircles().join(', ') : '';
            throw new Error(`Unauthorized: Verified Employee belongs to circle '${resolvedCircle}', but your account is authorized only for: ${authCircles}`);
        }

        // Update inline text displays
        if (empNameEl) {
            empNameEl.innerText = data.name;
            empNameEl.classList.remove('text-muted');
            empNameEl.classList.add('text-primary');
        }

        if (assignedCircleEl) {
            assignedCircleEl.innerText = resolvedCircle;
            assignedCircleEl.classList.remove('text-muted');
            assignedCircleEl.classList.add('text-success');
        }

        // Show verification success notice
        if (notice) {
            notice.style.display = 'block';
            notice.className = 'small mt-1 text-success fw-semibold';
            notice.innerHTML = `<i class="fa-solid fa-circle-check me-1"></i> Verified: <strong>${data.name}</strong> (${resolvedCircle})`;
        }

        // Populate Dependent Electrical Hierarchy (Divisions for this circle)
        populateDivisions(resolvedCircle);

        showToast(`Verified! Circle: ${resolvedCircle}`, "success");
    } catch(err) {
        resolvedEmpCode = null;
        resolvedCircle = null;

        if (empNameEl) {
            empNameEl.innerText = "Auto-populated upon lookup";
            empNameEl.className = 'fw-bold text-muted small';
        }

        if (assignedCircleEl) {
            assignedCircleEl.innerText = "Auto-populated upon lookup";
            assignedCircleEl.className = 'fw-bold text-muted small';
        }

        resetHierarchyDropdowns();

        if (notice) {
            notice.style.display = 'block';
            notice.className = 'small mt-1 text-danger fw-semibold';
            notice.innerHTML = `<i class="fa-solid fa-circle-xmark me-1"></i> ${err.message}`;
        }

        showToast(err.message, "danger");
    } finally {
        setButtonLoading('btnVerifyEmp', false, '<i class="fa-solid fa-circle-check me-1"></i> Verify Code');
    }
}

// 2. Populate Divisions for the resolved circle
function populateDivisions(circle) {
    const divSelect = document.getElementById('lbDivision');
    const subdivSelect = document.getElementById('lbSubdivision');
    const secSelect = document.getElementById('lbSection');

    divSelect.innerHTML = '<option value="">-- Choose Division --</option>';
    subdivSelect.innerHTML = '<option value="">-- Choose Division First --</option>';
    secSelect.innerHTML = '<option value="">-- Choose Subdivision First --</option>';

    if (!circle || !TPSODL_HIERARCHY[circle]) return;

    const divisions = TPSODL_HIERARCHY[circle];
    Object.keys(divisions).forEach(divName => {
        divSelect.insertAdjacentHTML('beforeend', `<option value="${divName}">${divName}</option>`);
    });
}

function resetHierarchyDropdowns() {
    const divSelect = document.getElementById('lbDivision');
    const subdivSelect = document.getElementById('lbSubdivision');
    const secSelect = document.getElementById('lbSection');

    if (divSelect) divSelect.innerHTML = '<option value="">-- Verify Employee Code First --</option>';
    if (subdivSelect) subdivSelect.innerHTML = '<option value="">-- Choose Division First --</option>';
    if (secSelect) secSelect.innerHTML = '<option value="">-- Choose Subdivision First --</option>';
}

// 3. Division Change -> Populates Subdivisions
function onDivisionChange(division) {
    const subdivSelect = document.getElementById('lbSubdivision');
    const secSelect = document.getElementById('lbSection');

    subdivSelect.innerHTML = '<option value="">-- Choose Subdivision --</option>';
    secSelect.innerHTML = '<option value="">-- Choose Subdivision First --</option>';

    if (!resolvedCircle || !division || !TPSODL_HIERARCHY[resolvedCircle] || !TPSODL_HIERARCHY[resolvedCircle][division]) {
        return;
    }

    const subdivisions = TPSODL_HIERARCHY[resolvedCircle][division];
    Object.keys(subdivisions).forEach(subName => {
        subdivSelect.insertAdjacentHTML('beforeend', `<option value="${subName}">${subName}</option>`);
    });
}

// 4. Subdivision Change -> Populates Sections (ESO)
function onSubdivisionChange(subdivision) {
    const division = document.getElementById('lbDivision').value;
    const secSelect = document.getElementById('lbSection');

    secSelect.innerHTML = '<option value="">-- Choose Section --</option>';

    if (!resolvedCircle || !division || !subdivision ||
        !TPSODL_HIERARCHY[resolvedCircle] ||
        !TPSODL_HIERARCHY[resolvedCircle][division] ||
        !TPSODL_HIERARCHY[resolvedCircle][division][subdivision]) {
        return;
    }

    const sections = TPSODL_HIERARCHY[resolvedCircle][division][subdivision] || [];
    sections.forEach(secName => {
        secSelect.insertAdjacentHTML('beforeend', `<option value="${secName}">${secName}</option>`);
    });
}

// 5. Submit Load Booking
async function submitLoadBooking(e) {
    e.preventDefault();

    if (!resolvedCircle || !resolvedEmpCode) {
        showToast("Please enter and verify Employee / TL Code first!", "warning");
        const empInput = document.getElementById('lbEmpCode');
        if (empInput) empInput.focus();
        return;
    }

    if (typeof isCircleAuthorizedClient === 'function' && !isCircleAuthorizedClient(resolvedCircle)) {
        showToast(`Unauthorized: You do not have permissions for circle: ${resolvedCircle}`, "danger");
        return;
    }

    const divSelect = document.getElementById('lbDivision');
    const division = divSelect ? divSelect.value.trim() : '';
    if (!division) {
        showToast("Please select a Division", "warning");
        if (divSelect) divSelect.focus();
        return;
    }

    const subdivSelect = document.getElementById('lbSubdivision');
    const subdivision = subdivSelect ? subdivSelect.value.trim() : '';
    if (!subdivision) {
        showToast("Please select a Subdivision", "warning");
        if (subdivSelect) subdivSelect.focus();
        return;
    }

    const secSelect = document.getElementById('lbSection');
    const section = secSelect ? secSelect.value.trim() : '';
    if (!section) {
        showToast("Please select a Section (ESO)", "warning");
        if (secSelect) secSelect.focus();
        return;
    }

    const bookInput = document.getElementById('lbBookNumber');
    const bookNumber = bookInput ? bookInput.value.trim() : '';
    if (!bookNumber) {
        showToast("Please enter Book Number", "warning");
        if (bookInput) bookInput.focus();
        return;
    }

    const pageInput = document.getElementById('lbPageNumber');
    const pageNumber = pageInput ? pageInput.value.trim() : '';
    if (!pageNumber) {
        showToast("Please enter Page Number", "warning");
        if (pageInput) pageInput.focus();
        return;
    }

    const loadInput = document.getElementById('lbBookedLoad');
    const bookedLoadVal = loadInput ? parseFloat(loadInput.value) : 0;
    if (isNaN(bookedLoadVal) || bookedLoadVal <= 0 || bookedLoadVal > 100) {
        showToast("Load must be between 0.001 and 100 kW", "warning");
        if (loadInput) loadInput.focus();
        return;
    }

    const theftTypeSelect = document.getElementById('lbTheftType');
    const theftType = theftTypeSelect ? theftTypeSelect.value : 'Hooking';

    const bookingDate = document.getElementById('lbBookingDate').value || new Date().toISOString().split('T')[0];

    setButtonLoading('btnSaveLBk', true);

    // Payload: Squad team resolution is handled strictly backend-side via daily operations logic
    const payload = {
        booking_date: bookingDate,
        book_number: bookNumber,
        page_number: pageNumber,
        page_no: pageNumber,
        tl_code: resolvedEmpCode,
        punch_emp_code: resolvedEmpCode,
        circle: resolvedCircle,
        division: division,
        subdivision: subdivision,
        section: section,
        theft_type: theftType,
        booked_load: bookedLoadVal
    };

    try {
        const res = await fetch('/api/load-booking/save', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || "Error saving load booking");
        }

        showToast(data.message || "Load Booking saved successfully!", "success");

        // Clear page input and load input for next quick entry in same book
        if (pageInput) {
            pageInput.value = '';
            pageInput.classList.remove('is-invalid');
            pageInput.focus();
        }
        if (loadInput) loadInput.value = '';

        const alertBox = document.getElementById('lbPageErrorAlert');
        if (alertBox) alertBox.style.display = 'none';
    } catch(err) {
        const errDetail = err.message || "";
        if (errDetail.toLowerCase().includes("duplicate") || errDetail.toLowerCase().includes("already been booked")) {
            if (pageInput) {
                pageInput.classList.add('is-invalid');
                pageInput.focus();
            }
            const alertBox = document.getElementById('lbPageErrorAlert');
            const alertTxt = document.getElementById('lbPageErrorText');
            if (alertBox) alertBox.style.display = 'block';
            if (alertTxt) alertTxt.innerText = errDetail;
            showToast("Duplicate Page Number! This page has already been used.", "danger");
        } else {
            showToast(err.message, "danger");
        }
    } finally {
        setButtonLoading('btnSaveLBk', false, '<i class="fa-solid fa-floppy-disk me-1"></i> 💾 Submit Load Booking');
    }
}
