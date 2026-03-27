/**
 * Rawy API Client
 * Base URL: http://localhost:8080
 */

// API Base URL - auto-detect from browser location
const API_BASE = window.location.origin;

class RawyAPI {
  constructor() {
    this.token = localStorage.getItem('rawy_token');
    this.user = JSON.parse(localStorage.getItem('rawy_user') || 'null');
  }

  // Auth getters
  isLoggedIn() {
    return !!this.token;
  }

  getAuthHeaders() {
    return this.token ? { 'Authorization': `Bearer ${this.token}` } : {};
  }

  // Auth methods
  async register(email, password) {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async login(email, password) {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    this.token = data.access_token;
    localStorage.setItem('rawy_token', this.token);
    await this.loadUser();
    return data;
  }

  async loadUser() {
    const res = await fetch(`${API_BASE}/auth/me`, {
      headers: { ...this.getAuthHeaders() }
    });
    if (res.ok) {
      this.user = await res.json();
      localStorage.setItem('rawy_user', JSON.stringify(this.user));
    }
    return this.user;
  }

  logout() {
    this.token = null;
    this.user = null;
    localStorage.removeItem('rawy_token');
    localStorage.removeItem('rawy_user');
  }

  // Voice methods
  async uploadVoice(blob, filename = 'recording.webm') {
    const formData = new FormData();
    formData.append('file', blob, filename);

    const res = await fetch(`${API_BASE}/voice/upload`, {
      method: 'POST',
      headers: this.getAuthHeaders(),
      body: formData
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async listVoices() {
    const res = await fetch(`${API_BASE}/voice/`, {
      headers: this.getAuthHeaders()
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async getVoice(id) {
    const res = await fetch(`${API_BASE}/voice/${id}`, {
      headers: this.getAuthHeaders()
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  // Calendar methods
  async getCalendar() {
    const res = await fetch(`${API_BASE}/calendar/`, {
      headers: this.getAuthHeaders()
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  async createBlock(title, startAt, endAt) {
    const res = await fetch(`${API_BASE}/calendar/blocks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...this.getAuthHeaders() },
      body: JSON.stringify({ title, start_at: startAt, end_at: endAt, is_focus: true })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  // Billing
  async getPlans() {
    const res = await fetch(`${API_BASE}/billing/plans`);
    return res.json();
  }

  async getSubscription() {
    const res = await fetch(`${API_BASE}/billing/subscription`, {
      headers: this.getAuthHeaders()
    });
    return res.json();
  }
}

// Global instance
window.api = new RawyAPI();
