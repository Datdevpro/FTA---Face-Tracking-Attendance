/**
 * FTA - Main Application Module
 * Shared utilities, toast notifications, sidebar navigation.
 */

// --- Toast Notification System ---
class ToastManager {
    constructor() {
        this.container = null;
        this.init();
    }

    init() {
        this.container = document.createElement('div');
        this.container.className = 'toast-container';
        document.body.appendChild(this.container);
    }

    show(type, title, message, duration = 4000) {
        const icons = {
            success: '✅',
            error: '❌',
            warning: '⚠️',
            info: 'ℹ️',
        };

        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.innerHTML = `
            <span class="toast-icon">${icons[type] || 'ℹ️'}</span>
            <div class="toast-content">
                <div class="toast-title">${title}</div>
                ${message ? `<div class="toast-message">${message}</div>` : ''}
            </div>
        `;

        this.container.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    }

    success(title, message) { this.show('success', title, message); }
    error(title, message) { this.show('error', title, message); }
    warning(title, message) { this.show('warning', title, message); }
    info(title, message) { this.show('info', title, message); }
}

const toast = new ToastManager();

// --- Clock ---
function updateClock() {
    const el = document.getElementById('clock');
    if (el) {
        const now = new Date();
        el.textContent = now.toLocaleString('vi-VN', {
            weekday: 'long',
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        });
    }
}

// --- Sidebar Navigation ---
function initSidebar() {
    const currentPage = window.location.pathname.split('/').pop() || 'index.html';

    document.querySelectorAll('.nav-item').forEach(item => {
        const href = item.getAttribute('href');
        if (href && href.includes(currentPage)) {
            item.classList.add('active');
        }

        item.addEventListener('click', (e) => {
            if (href) {
                window.location.href = href;
            }
        });
    });

    // Mobile menu toggle
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.querySelector('.sidebar');
    if (menuToggle && sidebar) {
        menuToggle.addEventListener('click', () => {
            sidebar.classList.toggle('open');
        });
    }
}

// --- Auth Check ---
function checkAuth() {
    if (!api.isAuthenticated()) {
        const currentPage = window.location.pathname.split('/').pop();
        if (currentPage !== 'login.html') {
            window.location.href = '/static/login.html';
            return false;
        }
    }
    return true;
}

// --- Load User Info ---
async function loadUserInfo() {
    try {
        const user = await api.getMe();
        if (user) {
            const nameEl = document.getElementById('userName');
            const roleEl = document.getElementById('userRole');
            const avatarEl = document.getElementById('userAvatar');

            if (nameEl) nameEl.textContent = user.full_name;
            if (roleEl) roleEl.textContent = user.role;
            if (avatarEl) avatarEl.textContent = user.full_name.charAt(0).toUpperCase();
        }
    } catch (e) {
        console.error('Failed to load user info:', e);
    }
}

// --- Logout ---
function logout() {
    api.clearToken();
    window.location.href = '/static/login.html';
}

// --- Utility: Format date ---
function formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleDateString('vi-VN');
}

function formatTime(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    return d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatDateTime(dateStr) {
    if (!dateStr) return '';
    return `${formatDate(dateStr)} ${formatTime(dateStr)}`;
}

// --- Utility: Status badge ---
function statusBadge(status) {
    const map = {
        'PRESENT': { class: 'badge-success', text: 'Đúng giờ' },
        'LATE': { class: 'badge-warning', text: 'Đi trễ' },
        'ABSENT': { class: 'badge-danger', text: 'Vắng mặt' },
        'HALF_DAY': { class: 'badge-info', text: 'Nửa ngày' },
    };
    const s = map[status] || { class: 'badge-muted', text: status };
    return `<span class="badge ${s.class}">${s.text}</span>`;
}

// --- Utility: Generate initials ---
function getInitials(name) {
    if (!name) return '?';
    return name.split(' ').map(w => w[0]).join('').toUpperCase().substring(0, 2);
}

// --- Modal helpers ---
function openModal(modalId) {
    document.getElementById(modalId)?.classList.add('active');
}

function closeModal(modalId) {
    document.getElementById(modalId)?.classList.remove('active');
}

// --- Sidebar HTML Template ---
function getSidebarHTML() {
    return `
    <div class="sidebar-header">
        <div class="sidebar-logo">
            <div class="sidebar-logo-icon">👤</div>
            <span class="sidebar-logo-text">FTA</span>
        </div>
    </div>
    <nav class="sidebar-nav">
        <div class="nav-section">
            <div class="nav-section-title">Tổng quan</div>
            <a class="nav-item" href="/static/index.html">
                <span class="nav-item-icon">📊</span>
                Dashboard
            </a>
            <a class="nav-item" href="/static/live_monitor.html">
                <span class="nav-item-icon">📹</span>
                Camera trực tiếp
            </a>
        </div>
        <div class="nav-section">
            <div class="nav-section-title">Quản lý</div>
            <a class="nav-item" href="/static/employees.html">
                <span class="nav-item-icon">👥</span>
                Nhân viên
            </a>
            <a class="nav-item" href="/static/attendance.html">
                <span class="nav-item-icon">📋</span>
                Chấm công
            </a>
            <a class="nav-item" href="/static/reports.html">
                <span class="nav-item-icon">📈</span>
                Báo cáo
            </a>
        </div>
    </nav>
    <div class="sidebar-footer">
        <div class="user-info">
            <div class="user-avatar" id="userAvatar">A</div>
            <div class="user-details">
                <div class="user-name" id="userName">Admin</div>
                <div class="user-role" id="userRole">ADMIN</div>
            </div>
            <button class="btn btn-ghost btn-icon btn-sm" onclick="logout()" title="Đăng xuất">🚪</button>
        </div>
    </div>
    `;
}

// --- Init on page load ---
document.addEventListener('DOMContentLoaded', () => {
    // Inject sidebar
    const sidebar = document.querySelector('.sidebar');
    if (sidebar && !sidebar.innerHTML.trim()) {
        sidebar.innerHTML = getSidebarHTML();
    }

    if (checkAuth()) {
        initSidebar();
        loadUserInfo();
        updateClock();
        setInterval(updateClock, 1000);
    }
});
