/* LedgerIQ core: API client, helpers, modal forms, auth screen, shell and router. */
(function () {
  const App = (window.App = { user: null, csrf: null, currencies: [], cats: [], methods: [], views: {}, active: null });

  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const LOCALES = { INR: 'en-IN', USD: 'en-US', EUR: 'de-DE', GBP: 'en-GB', JPY: 'ja-JP', AED: 'en-AE' };
  const money = (n) => {
    const cur = (App.user && App.user.currency) || 'INR';
    return new Intl.NumberFormat(LOCALES[cur] || 'en-US', { style: 'currency', currency: cur }).format(n || 0);
  };
  const isoDate = (d = new Date()) => d.toLocaleDateString('en-CA');
  const thisMonth = () => isoDate().slice(0, 7);
  const monthLabel = (m) => new Date(m + '-01T00:00:00').toLocaleDateString('en', { month: 'short', year: '2-digit' });
  const niceDate = (d) => new Date(d + 'T00:00:00').toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  const monthRange = (offset = 0) => {
    const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() + offset);
    const e = new Date(d.getFullYear(), d.getMonth() + 1, 0);
    return [isoDate(d), isoDate(e)];
  };

  class ApiErr extends Error { constructor(m, status, field) { super(m); this.status = status; this.field = field; } }
  async function api(method, url, body) {
    let res;
    try {
      res = await fetch(url, { method, credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': App.csrf || '' },
        body: body === undefined ? undefined : JSON.stringify(body) });
    } catch (e) { throw new ApiErr('Network problem. Please check your connection and try again.', 0); }
    let data = null;
    try { data = await res.json(); } catch (e) { /* non-JSON */ }
    if (!res.ok) {
      if (res.status === 401 && App.user) { App.user = null; showAuth('Your session has ended. Please log in again.'); }
      throw new ApiErr((data && data.error) || 'Request failed', res.status, data && data.field);
    }
    return data;
  }
  const qs = (o) => Object.entries(o).filter(([, v]) => v !== '' && v != null).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join('&');

  function toast(msg, type) {
    const t = document.createElement('div');
    t.className = 'toast ' + (type || ''); t.textContent = msg;
    $('#toasts').appendChild(t); setTimeout(() => t.remove(), 4200);
  }
  const bar = (pct, cls) => `<div class="bar"><span class="${cls || ''}" data-w="${Math.max(0, Math.min(100, pct || 0))}"></span></div>`;
  function paint(root) {
    $$('[data-w]', root).forEach((e) => { requestAnimationFrame(() => { e.style.width = e.dataset.w + '%'; }); });
    window.Charts.paint(root);
  }

  /* ---------- generic modal form ---------- */
  function fieldHtml(f, v) {
    const val = v == null ? '' : v, id = 'f_' + f.name, req = f.required ? 'required' : '';
    let input;
    if (f.type === 'select') {
      input = `<select id="${id}" name="${f.name}" ${req}>${(f.options || []).map((o) => `<option value="${esc(o.value)}" ${String(o.value) === String(val) ? 'selected' : ''}>${esc(o.label)}</option>`).join('')}</select>`;
    } else if (f.type === 'textarea') {
      input = `<textarea id="${id}" name="${f.name}" maxlength="${f.max || 500}" ${req}>${esc(val)}</textarea>`;
    } else if (f.type === 'checkbox') {
      return `<div class="field"><label class="check"><input type="checkbox" name="${f.name}" ${val ? 'checked' : ''}> ${esc(f.label)}</label></div>`;
    } else {
      input = `<input id="${id}" name="${f.name}" type="${f.type || 'text'}" value="${esc(val)}" ${req} ${f.step ? `step="${f.step}"` : ''} ${f.min != null ? `min="${f.min}"` : ''} ${f.max != null ? `max="${f.max}"` : ''} ${f.autocomplete ? `autocomplete="${f.autocomplete}"` : ''} ${f.type === 'number' ? 'inputmode="decimal"' : ''}>`;
    }
    return `<div class="field" data-f="${f.name}"><label for="${id}">${esc(f.label)}</label>${input}${f.help ? `<div class="help">${esc(f.help)}</div>` : ''}</div>`;
  }
  function modal({ title, fields, values = {}, submit = 'Save', onSubmit, wire }) {
    const dlg = $('#modal');
    dlg.innerHTML = `<form novalidate><div class="dlg-head"><h2>${esc(title)}</h2><button type="button" class="btn sm" data-close aria-label="Close">✕</button></div>
      ${fields.map((f) => fieldHtml(f, values[f.name])).join('')}<div class="form-error" role="alert"></div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Cancel</button><button class="btn primary">${esc(submit)}</button></div></form>`;
    const form = $('form', dlg), errBox = $('.form-error', dlg);
    $$('[data-close]', dlg).forEach((b) => b.addEventListener('click', () => dlg.close()));
    if (wire) wire(form);
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      $$('.field.err', form).forEach((e) => e.classList.remove('err')); errBox.textContent = '';
      const data = {};
      fields.forEach((f) => {
        const el = form.elements[f.name];
        data[f.name] = f.type === 'checkbox' ? el.checked : el.value;
      });
      for (const f of fields) {
        if (f.required && f.type !== 'checkbox' && String(data[f.name]).trim() === '') {
          const w = $(`[data-f="${f.name}"]`, form); if (w) w.classList.add('err');
          errBox.textContent = `${f.label} is required`; return;
        }
      }
      const btn = $('.btn.primary', form); btn.disabled = true;
      try { await onSubmit(data); dlg.close(); }
      catch (e) {
        errBox.textContent = e.message;
        if (e.field) { const w = $(`[data-f="${e.field}"]`, form); if (w) w.classList.add('err'); }
      } finally { btn.disabled = false; }
    });
    dlg.showModal();
    const first = $('input:not([type=hidden]),select,textarea', form); if (first) first.focus();
  }

  /* ---------- auth screen ---------- */
  function showAuth(message) {
    let mode = 'login';
    const root = $('#app');
    const draw = () => {
      root.innerHTML = `<div class="auth"><div class="card"><div class="hero"><h1>LedgerIQ</h1><p>Smart Expense &amp; Financial Advisor</p></div>
        <div class="tabs"><button data-m="login" class="${mode === 'login' ? 'active' : ''}">Log in</button><button data-m="register" class="${mode === 'register' ? 'active' : ''}">Create account</button></div>
        ${message ? `<div class="notice warn" role="status">${esc(message)}</div><br>` : ''}
        <form novalidate>${mode === 'register' ? fieldHtml({ name: 'name', label: 'Full name', required: true, autocomplete: 'name' }) : ''}
        ${fieldHtml({ name: 'email', label: 'Email', type: 'email', required: true, autocomplete: 'email' })}
        ${fieldHtml({ name: 'password', label: 'Password', type: 'password', required: true, autocomplete: mode === 'login' ? 'current-password' : 'new-password', help: mode === 'register' ? 'At least 8 characters with a letter and a number.' : '' })}
        ${mode === 'register' ? fieldHtml({ name: 'currency', label: 'Currency', type: 'select', options: App.currencies.map((c) => ({ value: c, label: c })) }, 'INR') : ''}
        <div class="form-error" role="alert"></div><button class="btn primary block">${mode === 'login' ? 'Log in' : 'Create account'}</button></form>
        <p class="muted small">Suggestions in this app are general guidance, not professional financial advice.</p></div></div>`;
      $$('.tabs button', root).forEach((b) => b.addEventListener('click', () => { mode = b.dataset.m; message = ''; draw(); }));
      const form = $('form', root);
      form.addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const body = Object.fromEntries(new FormData(form).entries()), err = $('.form-error', form), btn = $('.btn', form);
        err.textContent = ''; btn.disabled = true;
        try {
          const r = await api('POST', '/api/auth/' + mode, body);
          App.user = r.user; App.csrf = r.csrf; await loadMeta(); location.hash = '#/dashboard'; startShell();
        } catch (e) { err.textContent = e.message; } finally { btn.disabled = false; }
      });
    };
    draw();
  }

  async function loadMeta() {
    const c = await api('GET', '/api/categories');
    App.cats = c.items; App.methods = c.payment_methods;
  }

  /* ---------- shell + router ---------- */
  const NAV = [['dashboard', 'Dashboard', '▦'], ['transactions', 'Transactions', '⇄'], ['budgets', 'Budgets', '◈'], ['goals', 'Savings goals', '◎'],
    ['reports', 'Reports', '▤'], ['advisor', 'Financial advisor', '✦'], ['forecast', 'Future prediction', '↗'], ['notifications', 'Notifications', '🔔'], ['profile', 'Profile', '☺']];

  function startShell() {
    $('#app').innerHTML = `<div class="shell"><aside class="side" id="side"><div class="logo"><i>L</i>LedgerIQ</div>
      <nav class="nav">${NAV.map(([k, l, ic]) => `<a href="#/${k}" data-k="${k}"><span>${ic}&nbsp; ${l}</span>${k === 'notifications' ? '<span class="badge hidden" id="nbadge"></span>' : ''}</a>`).join('')}</nav>
      <div class="user small"><div><strong>${esc(App.user.name)}</strong></div><div class="muted">${esc(App.user.email)}</div><br><button class="btn sm" id="logout">Log out</button></div></aside>
      <div><div class="topbar"><button class="btn sm" id="menu" aria-label="Menu">☰</button><strong>LedgerIQ</strong></div><main id="view" tabindex="-1"></main></div></div>`;
    $('#menu').addEventListener('click', () => $('#side').classList.toggle('open'));
    $('#side').addEventListener('click', (e) => { if (e.target.closest('a')) $('#side').classList.remove('open'); });
    $('#logout').addEventListener('click', async () => {
      try { await api('POST', '/api/auth/logout'); } catch (e) { /* ignore */ }
      const me = await api('GET', '/api/auth/me'); App.csrf = me.csrf; App.user = null; location.hash = ''; showAuth();
    });
    route();
  }

  async function route() {
    if (!App.user) return;
    const key = (location.hash.replace(/^#\//, '') || 'dashboard').split('?')[0];
    const view = App.views[key] || App.views.dashboard;
    const name = App.views[key] ? key : 'dashboard';
    $$('.nav a').forEach((a) => a.classList.toggle('active', a.dataset.k === name));
    const el = $('#view'); App.active = name;
    el.innerHTML = '<p class="muted">Loading…</p>';
    try { await view(el); paint(el); el.focus({ preventScroll: true }); }
    catch (e) { if (e.status !== 401) el.innerHTML = `<div class="card"><h2>Something went wrong</h2><p>${esc(e.message)}</p><button class="btn" id="retry">Try again</button></div>`; const r = $('#retry'); if (r) r.addEventListener('click', route); }
    refreshBadge();
  }
  async function refreshBadge() {
    try {
      const n = await api('GET', '/api/notifications'), b = $('#nbadge');
      if (b) { b.textContent = n.unread; b.classList.toggle('hidden', !n.unread); }
    } catch (e) { /* ignore */ }
  }

  Object.assign(App, { $, $$, esc, money, isoDate, thisMonth, monthLabel, niceDate, monthRange, api, qs, toast, bar, paint, modal, showAuth, startShell, route, loadMeta, ApiErr });
  window.addEventListener('hashchange', route);
})();
