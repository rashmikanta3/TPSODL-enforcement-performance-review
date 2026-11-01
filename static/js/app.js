// Global Application Utilities for TPSODL Enforcement Portal

function showToast(message, type = 'success') {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        document.body.appendChild(container);
    }

    const toastId = 'toast_' + Date.now();
    const bgClass = (type === 'danger' || type === 'error') ? 'bg-danger text-white' : 
                    (type === 'warning') ? 'bg-warning text-dark' : 'bg-success text-white';

    const toastHtml = `
        <div id="${toastId}" class="toast align-items-center ${bgClass} border-0 show shadow mb-2" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body fw-medium">
                    <i class="fa-solid ${type === 'danger' || type === 'error' ? 'fa-circle-exclamation' : 'fa-circle-check'} me-2"></i>
                    ${message}
                </div>
                <button type="button" class="btn-close ${type === 'warning' ? '' : 'btn-close-white'} me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;

    container.insertAdjacentHTML('beforeend', toastHtml);
    setTimeout(() => {
        const el = document.getElementById(toastId);
        if (el) el.remove();
    }, 4500);
}

function setButtonLoading(btnId, isLoading, originalHtml = '') {
    const btn = document.getElementById(btnId);
    if (!btn) return;

    if (isLoading) {
        btn.dataset.origHtml = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Processing...`;
    } else {
        btn.disabled = false;
        btn.innerHTML = originalHtml || btn.dataset.origHtml || 'Submit';
    }
}

function getCurrentUser() {
    try {
        const u = localStorage.getItem('tpsodl_user');
        return u ? JSON.parse(u) : null;
    } catch(e) {
        return null;
    }
}

const ALL_TPSODL_CIRCLES = [
    "JEYPORE",
    "RAYAGADA",
    "BHANJANAGAR",
    "ASKA",
    "BERHAMPUR",
    "BERHAMPUR CITY"
];

function getUserAuthorizedCircles() {
    const user = getCurrentUser();
    if (!user) return ALL_TPSODL_CIRCLES;
    if (user.role === 'ADMIN') return ALL_TPSODL_CIRCLES;
    
    const raw = user.circle ? user.circle.split(',').map(s => s.trim().toUpperCase()).filter(Boolean) : [];
    const authorized = [];
    raw.forEach(c => {
        const mapped = (c === 'CITY') ? 'BERHAMPUR CITY' : c;
        if (!authorized.includes(mapped)) authorized.push(mapped);
    });
    return authorized.length > 0 ? authorized : ALL_TPSODL_CIRCLES;
}

function isCircleAuthorizedClient(circle) {
    if (!circle) return false;
    const user = getCurrentUser();
    if (!user || user.role === 'ADMIN') return true;
    const authorized = getUserAuthorizedCircles();
    const target = (circle.trim().toUpperCase() === 'CITY') ? 'BERHAMPUR CITY' : circle.trim().toUpperCase();
    return authorized.includes(target);
}

function populateOperationalCircleSelect(selectId, onCircleChangeCallback, options = {}) {
    const el = document.getElementById(selectId);
    if (!el) return;
    const user = getCurrentUser();
    const authorized = getUserAuthorizedCircles();
    const isFilter = !!options.includeAllOption; // e.g. for collection filter

    el.innerHTML = '';

    if (isFilter && (!user || user.role === 'ADMIN')) {
        const allOpt = document.createElement('option');
        allOpt.value = 'ALL';
        allOpt.textContent = 'All Circles';
        el.appendChild(allOpt);
    }

    authorized.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c;
        opt.textContent = c;
        el.appendChild(opt);
    });

    if (user && (user.role === 'SUB_ADMIN' || user.role === 'USER')) {
        if (authorized.length === 1) {
            el.value = authorized[0];
            el.disabled = true;
        } else {
            el.disabled = false;
            el.value = authorized[0];
        }
    } else {
        el.disabled = false;
        if (isFilter) {
            el.value = 'ALL';
        } else if (authorized.length > 0) {
            el.value = authorized[0];
        }
    }

    if (onCircleChangeCallback && typeof onCircleChangeCallback === 'function') {
        onCircleChangeCallback();
    }
}

const OPERATIONAL_ROUTES = [
    '/attendance',
    '/logbook',
    '/load-booking',
    '/dc',
    '/collection',
    '/vcr-desk',
    '/vcr',
    '/admin-desk',
    '/admin',
    '/profile'
];

function enforceRouteAccess() {
    const path = window.location.pathname.toLowerCase();

    // Whitelist public pages - Executive dashboard is always 100% public & unrestricted
    if (path === '/' || path === '/dashboard' || path === '/login') {
        return;
    }

    const user = getCurrentUser();
    const isOperational = OPERATIONAL_ROUTES.some(r => path === r || path.startsWith(r + '/'));

    if (isOperational && !user) {
        // Unauthenticated visitor attempting to access operational desk
        sessionStorage.setItem('redirect_after_login', window.location.pathname + window.location.search);
        window.location.href = `/login?msg=auth_required&next=${encodeURIComponent(window.location.pathname)}`;
        return;
    }

    // Restrict /admin-desk strictly to ADMIN role
    if ((path === '/admin-desk' || path === '/admin') && user && user.role !== 'ADMIN') {
        window.location.href = '/dashboard';
        return;
    }
}

function interceptOperationalNavLinks() {
    const user = getCurrentUser();
    if (!user) {
        document.querySelectorAll('a.nav-link').forEach(link => {
            const href = link.getAttribute('href');
            if (href && href !== '/dashboard' && href !== '/' && href !== '/login') {
                const isOp = OPERATIONAL_ROUTES.some(r => href === r || href.startsWith(r + '/'));
                if (isOp) {
                    link.addEventListener('click', (e) => {
                        e.preventDefault();
                        sessionStorage.setItem('redirect_after_login', href);
                        showToast("Please sign in to access operational desks", "warning");
                        setTimeout(() => {
                            window.location.href = `/login?msg=auth_required&next=${encodeURIComponent(href)}`;
                        }, 400);
                    });
                }
            }
        });
    }
}

function updateNavUser() {
    const user = getCurrentUser();
    const userBadgeEl = document.getElementById('navUserBadge');
    const roleBadgeEl = document.getElementById('navRoleBadge');
    const circleBadgeEl = document.getElementById('navCircleBadge');
    const adminNav = document.getElementById('navAdminLink');
    const profileBtn = document.getElementById('navProfileBtn');
    const logoutBtn = document.getElementById('navLogoutBtn');
    const loginBtn = document.getElementById('navLoginBtn');

    if (user) {
        if (userBadgeEl) userBadgeEl.innerText = user.username;
        if (roleBadgeEl) {
            roleBadgeEl.innerText = user.role;
            roleBadgeEl.className = (user.role === 'ADMIN') ? 'badge bg-danger' : 
                                    (user.role === 'SUB_ADMIN') ? 'badge bg-warning text-dark' : 'badge bg-primary';
        }
        if (circleBadgeEl) {
            circleBadgeEl.innerText = user.circle || 'ALL CIRCLES';
            circleBadgeEl.className = 'badge bg-secondary';
        }

        if (profileBtn) profileBtn.style.display = 'inline-block';
        if (logoutBtn) logoutBtn.style.display = 'inline-block';
        if (loginBtn) loginBtn.style.display = 'none';

        if (adminNav) {
            adminNav.style.display = (user.role === 'ADMIN') ? 'block' : 'none';
        }

        // Check if Sub-Admin is view-only (can_edit == false)
        if (user.role === 'SUB_ADMIN' && !user.can_edit) {
            applyViewOnlyRestrictions();
        }
    } else {
        // Unauthenticated visitor / Guest -> PUBLIC VIEW
        if (userBadgeEl) userBadgeEl.innerText = 'GUEST';
        if (roleBadgeEl) {
            roleBadgeEl.innerText = 'PUBLIC';
            roleBadgeEl.className = 'badge bg-info text-dark fw-bold';
        }
        if (circleBadgeEl) {
            circleBadgeEl.innerText = 'ALL CIRCLES';
            circleBadgeEl.className = 'badge bg-secondary';
        }

        if (profileBtn) profileBtn.style.display = 'none';
        if (logoutBtn) logoutBtn.style.display = 'none';
        if (loginBtn) loginBtn.style.display = 'inline-block';

        if (adminNav) {
            adminNav.style.display = 'none';
        }
    }
}

function applyViewOnlyRestrictions() {
    // Disable primary submit buttons on forms if view-only
    const forms = document.querySelectorAll('form');
    forms.forEach(f => {
        const submitBtn = f.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.title = "View-Only Permission: Changes not permitted";
        }
    });

    const banner = document.getElementById('viewOnlyNotice');
    if (banner) {
        banner.style.display = 'block';
    }
}

function logout() {
    localStorage.removeItem('tpsodl_user');
    sessionStorage.removeItem('redirect_after_login');
    window.location.href = '/dashboard';
}

document.addEventListener('DOMContentLoaded', () => {
    enforceRouteAccess();
    updateNavUser();
    interceptOperationalNavLinks();
});
