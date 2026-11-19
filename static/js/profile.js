document.addEventListener('DOMContentLoaded', () => {
    const userStr = localStorage.getItem('tpsodl_user');
    if (userStr) {
        const user = JSON.parse(userStr);
        document.getElementById('cpUsername').value = user.username;
    }
});

async function handleChangePassword(e) {
    e.preventDefault();
    const username = document.getElementById('cpUsername').value;
    const old_password = document.getElementById('cpOldPassword').value;
    const new_password = document.getElementById('cpNewPassword').value;
    const confirm_password = document.getElementById('cpConfirmPassword').value;

    if (new_password !== confirm_password) {
        alert("New passwords do not match!");
        return;
    }

    setButtonLoading('btnChangePassword', true);
    try {
        const res = await fetch('/api/auth/change-password', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ username, old_password, new_password })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "Failed to update password");

        showToast("Password changed successfully!");
        document.getElementById('changePasswordForm').reset();
    } catch (err) {
        alert(err.message);
    } finally {
        setButtonLoading('btnChangePassword', false, '<i class="fa-solid fa-key me-1"></i> Update Password');
    }
}
