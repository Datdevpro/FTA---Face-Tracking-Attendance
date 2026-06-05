/**
 * FTA - API Client Module
 * Handles all HTTP communication with the backend.
 */

const API_BASE = '/api';

class APIClient {
    constructor() {
        this.token = localStorage.getItem('fta_token') || null;
    }

    setToken(token) {
        this.token = token;
        localStorage.setItem('fta_token', token);
    }

    clearToken() {
        this.token = null;
        localStorage.removeItem('fta_token');
    }

    isAuthenticated() {
        return !!this.token;
    }

    async request(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;
        const headers = {
            ...(options.headers || {}),
        };

        if (this.token) {
            headers['Authorization'] = `Bearer ${this.token}`;
        }

        // Don't set Content-Type for FormData
        if (!(options.body instanceof FormData) && !headers['Content-Type']) {
            headers['Content-Type'] = 'application/json';
        }

        try {
            const response = await fetch(url, {
                ...options,
                headers,
            });

            if (response.status === 401) {
                this.clearToken();
                window.location.href = '/static/login.html';
                return null;
            }

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }

            // Check if response is JSON
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            }

            return response;
        } catch (error) {
            if (error.message === 'Failed to fetch') {
                throw new Error('Server không phản hồi. Vui lòng kiểm tra kết nối.');
            }
            throw error;
        }
    }

    // --- Auth ---
    async login(username, password) {
        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formData,
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || 'Login failed');
        }

        const data = await response.json();
        this.setToken(data.access_token);
        return data;
    }

    async getMe() {
        return this.request('/auth/me');
    }

    // --- Employees ---
    async getEmployees(params = {}) {
        const query = new URLSearchParams(params).toString();
        return this.request(`/employees?${query}`);
    }

    async getEmployee(id) {
        return this.request(`/employees/${id}`);
    }

    async createEmployee(data) {
        return this.request('/employees', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }

    async updateEmployee(id, data) {
        return this.request(`/employees/${id}`, {
            method: 'PUT',
            body: JSON.stringify(data),
        });
    }

    async deleteEmployee(id) {
        return this.request(`/employees/${id}`, { method: 'DELETE' });
    }

    // --- Departments ---
    async getDepartments() {
        return this.request('/departments');
    }

    async createDepartment(data) {
        return this.request('/departments', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }

    // --- Face Recognition ---
    async registerFace(employeeId, files) {
        const formData = new FormData();
        for (const file of files) {
            formData.append('files', file);
        }
        return this.request(`/recognition/register/${employeeId}`, {
            method: 'POST',
            body: formData,
        });
    }

    async getEmployeeFaces(employeeId) {
        return this.request(`/recognition/faces/${employeeId}`);
    }

    async deleteFace(encodingId) {
        return this.request(`/recognition/face/${encodingId}`, {
            method: 'DELETE',
        });
    }

    async getRecognitionStatus() {
        return this.request('/recognition/status');
    }

    // --- Attendance ---
    async getAttendance(params = {}) {
        const query = new URLSearchParams(params).toString();
        return this.request(`/attendance?${query}`);
    }

    async getTodayAttendance() {
        return this.request('/attendance/today');
    }

    async createManualAttendance(data) {
        return this.request('/attendance/manual', {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }

    async getAttendanceSummary(year, month) {
        return this.request(`/attendance/summary?year=${year}&month=${month}`);
    }

    // --- Reports ---
    async getDashboardStats() {
        return this.request('/reports/dashboard-stats');
    }

    async getDailyReport(date) {
        const params = date ? `?report_date=${date}` : '';
        return this.request(`/reports/daily${params}`);
    }

    async getMonthlyReport(year, month) {
        return this.request(`/reports/monthly?year=${year}&month=${month}`);
    }

    async exportExcel(year, month) {
        const response = await this.request(
            `/reports/export/excel?year=${year}&month=${month}`
        );
        if (response instanceof Response) {
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `attendance_${year}_${String(month).padStart(2, '0')}.xlsx`;
            a.click();
            URL.revokeObjectURL(url);
        }
    }

    // --- System ---
    async getHealth() {
        return this.request('/health');
    }

    async getCameraStatus() {
        return this.request('/camera/status');
    }

    async startCamera() {
        return this.request('/camera/start', { method: 'POST' });
    }

    async stopCamera() {
        return this.request('/camera/stop', { method: 'POST' });
    }
}

// Singleton
const api = new APIClient();
