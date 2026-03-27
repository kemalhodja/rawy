class RawyApp {
  constructor() {
    this.api = window.api;
    this.currentView = 'auth';
    this.init();
  }

  init() {
    if (this.api.isLoggedIn()) {
      this.showApp();
    } else {
      this.showAuth();
    }
  }

  showAuth() {
    this.currentView = 'auth';
    const app = document.querySelector('.app-shell');
    app.innerHTML = `
      <header class="brand">
        <h1>Rawy</h1>
        <p>Voice-first knowledge</p>
      </header>
      
      <div class="auth-container">
        <div class="auth-tabs">
          <button class="auth-tab active" onclick="app.switchAuthTab('login')">Giris</button>
          <button class="auth-tab" onclick="app.switchAuthTab('register')">Kayit</button>
        </div>
        
        <form id="login-form" class="auth-form" onsubmit="app.handleLogin(event)">
          <input type="email" name="email" placeholder="Email" required class="auth-input">
          <input type="password" name="password" placeholder="Sifre" required class="auth-input">
          <button type="submit" class="auth-btn">Giris Yap</button>
          <p id="login-error" class="auth-error"></p>
        </form>
        
        <form id="register-form" class="auth-form hidden" onsubmit="app.handleRegister(event)">
          <input type="email" name="email" placeholder="Email" required class="auth-input">
          <input type="password" name="password" placeholder="Sifre" required class="auth-input" minlength="6">
          <button type="submit" class="auth-btn">Kayit Ol</button>
          <p id="register-error" class="auth-error"></p>
        </form>
      </div>
    `;
  }

  switchAuthTab(tab) {
    document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.auth-form').forEach(f => f.classList.add('hidden'));
    
    if (tab === 'login') {
      document.querySelector('.auth-tab:first-child').classList.add('active');
      document.getElementById('login-form').classList.remove('hidden');
    } else {
      document.querySelector('.auth-tab:last-child').classList.add('active');
      document.getElementById('register-form').classList.remove('hidden');
    }
  }

  async handleLogin(e) {
    e.preventDefault();
    const form = e.target;
    const errorEl = document.getElementById('login-error');
    
    try {
      await this.api.login(form.email.value, form.password.value);
      this.showApp();
    } catch (err) {
      errorEl.textContent = 'Giris basarisiz: ' + err.message;
    }
  }

  async handleRegister(e) {
    e.preventDefault();
    const form = e.target;
    const errorEl = document.getElementById('register-error');
    
    try {
      await this.api.register(form.email.value, form.password.value);
      await this.api.login(form.email.value, form.password.value);
      this.showApp();
    } catch (err) {
      errorEl.textContent = 'Kayit basarisiz: ' + err.message;
    }
  }

  showApp() {
    this.currentView = 'app';
    const app = document.querySelector('.app-shell');
    app.innerHTML = `
      <header class="brand">
        <h1>Rawy</h1>
        <p id="user-info">Yukleniyor...</p>
        <button onclick="app.logout()" class="logout-btn">Cikis</button>
      </header>

      <nav class="tabs">
        <button class="tab-btn active" onclick="app.switchTab('calendar')">Ajanda</button>
        <button class="tab-btn" onclick="app.switchTab('voice')">Sesler</button>
        <button class="tab-btn" onclick="app.switchTab('notes')">Notlar</button>
      </nav>

      <main>
        <section id="calendar-panel" class="panel active">
          <h2>Ajanda</h2>
          <div id="calendar-content">Yukleniyor...</div>
        </section>
        
        <section id="voice-panel" class="panel">
          <h2>Ses Kayit</h2>
          <div class="voice-capture">
            <button id="record-btn" class="record-btn" onmousedown="app.startRecord()" onmouseup="app.stopRecord()" ontouchstart="app.startRecord()" ontouchend="app.stopRecord()">
              <span class="record-icon"></span>
            </button>
            <p class="voice-hint">Basili tut - kayit</p>
            <p id="record-status"></p>
          </div>
          <div id="voices-list"></div>
        </section>
        
        <section id="notes-panel" class="panel">
          <h2>Notlar</h2>
          <div id="notes-content">Yukleniyor...</div>
        </section>
      </main>
    `;

    this.loadData();
  }

  switchTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    event.target.classList.add('active');
    document.getElementById(tab + '-panel').classList.add('active');
  }

  async loadData() {
    try {
      const user = await this.api.loadUser();
      document.getElementById('user-info').textContent = user.email + ' - ' + user.plan;
      this.loadVoices();
      this.loadCalendar();
    } catch (err) {
      console.error('Load error:', err);
    }
  }

  async loadVoices() {
    try {
      const data = await this.api.listVoices();
      const container = document.getElementById('voices-list');
      if (!data.items || data.items.length === 0) {
        container.innerHTML = '<p class="empty">Henuz ses kaydi yok.</p>';
        return;
      }
      container.innerHTML = data.items.map(v => `
        <div class="voice-item">
          <h4>${v.title || 'Isimsiz Not'}</h4>
          <p>${v.preview || 'Transkript yok'}</p>
          <small>${new Date(v.created_at).toLocaleString('tr-TR')}</small>
        </div>
      `).join('');
    } catch (err) {
      console.error('Voices error:', err);
    }
  }

  async loadCalendar() {
    try {
      const data = await this.api.getCalendar();
      const container = document.getElementById('calendar-content');
      const days = data.slice(0, 7);
      if (days.length === 0) {
        container.innerHTML = '<p class="empty">Ajanda bos.</p>';
        return;
      }
      container.innerHTML = days.map(d => `
        <div class="calendar-day">
          <h4>${new Date(d.date).toLocaleDateString('tr-TR', { weekday: 'long', day: 'numeric' })}</h4>
          ${(d.blocks || []).map(b => `
            <div class="calendar-block ${b.is_focus ? 'focus' : ''}">
              <span class="time">${(b.start_time || '').slice(0, 5) || '--:--'}</span>
              <span>${b.title}</span>
            </div>
          `).join('')}
        </div>
      `).join('');
    } catch (err) {
      document.getElementById('calendar-content').innerHTML = '<p class="empty">Yuklenemedi.</p>';
    }
  }

  async startRecord() {
    const btn = document.getElementById('record-btn');
    const status = document.getElementById('record-status');
    
    try {
      this.mediaRecorder = null;
      this.chunks = [];
      
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.mediaRecorder = new MediaRecorder(stream);
      
      this.mediaRecorder.ondataavailable = e => this.chunks.push(e.data);
      this.mediaRecorder.onstop = async () => {
        const blob = new Blob(this.chunks, { type: 'audio/webm' });
        status.textContent = 'Yukleniyor...';
        try {
          await this.api.uploadVoice(blob);
          status.textContent = 'Yuklendi!';
          setTimeout(() => this.loadVoices(), 500);
        } catch (err) {
          status.textContent = 'Hata: ' + err.message;
        }
      };
      
      this.mediaRecorder.start();
      btn.classList.add('recording');
      status.textContent = 'Kaydediyor...';
    } catch (err) {
      status.textContent = 'Mikrofon erisimi reddedildi.';
    }
  }

  stopRecord() {
    const btn = document.getElementById('record-btn');
    if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
      this.mediaRecorder.stop();
      btn.classList.remove('recording');
      this.mediaRecorder.stream.getTracks().forEach(t => t.stop());
    }
  }

  logout() {
    this.api.logout();
    this.showAuth();
  }
}

window.app = new RawyApp();
