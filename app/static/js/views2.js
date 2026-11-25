/* Views: goals, reports, advisor, forecast (future prediction), notifications, profile. */
(function () {
  const A = window.App, { $, $$, esc, money, api, qs, toast, bar, modal, niceDate, monthLabel, head } = A;
  const C = window.Charts;

  /* ================= SAVINGS GOALS ================= */
  const goalFields = [
    { name: 'name', label: 'Goal name', required: true, max: 80 },
    { name: 'target_amount', label: 'Target amount', type: 'number', step: '0.01', min: '0.01', required: true },
    { name: 'current_amount', label: 'Already saved', type: 'number', step: '0.01', min: '0' },
    { name: 'target_date', label: 'Target date (optional)', type: 'date', help: 'Add a date to get a suggested monthly saving amount.' }];
  A.views.goals = async (el) => {
    const r = await api('GET', '/api/goals');
    el.innerHTML = head('Savings goals', '<button class="btn primary" id="add">+ New goal</button>') + (r.items.length ? `<div class="grid g3">${r.items.map((g) => `
      <div class="card"><div class="row"><h3>${esc(g.name)}</h3><span class="tag ${g.status === 'overdue' ? 'est' : ''}">${g.status === 'completed' ? 'Completed 🎉' : g.status === 'overdue' ? 'Past target date' : 'In progress'}</span></div>
      <div class="stat"><div class="value">${g.percent}%</div><div class="muted small">${money(g.current_amount)} of ${money(g.target_amount)}</div></div><br>${bar(g.percent, g.status === 'completed' ? 'done' : '')}
      <div class="row small muted"><span>Remaining ${money(g.remaining)}</span><span>${g.target_date ? 'By ' + niceDate(g.target_date) : 'No target date'}</span></div>
      ${g.monthly_needed ? `<div class="notice small">Suggested saving: <b>${money(g.monthly_needed)}</b> per month ${g.months_left ? `for ${g.months_left} month(s)` : '(target date has passed)'} <span class="tag">estimate</span></div>` : ''}
      <div class="list-actions"><button class="btn sm" data-add="${g.id}">Add funds</button><button class="btn sm" data-wd="${g.id}">Withdraw</button><button class="btn sm" data-edit="${g.id}">Edit</button><button class="btn sm danger" data-del="${g.id}">Delete</button></div></div>`).join('')}</div>`
      : '<div class="card empty">No savings goals yet. Set a target such as an emergency fund or a new laptop and track your progress.</div>');
    const byId = Object.fromEntries(r.items.map((g) => [g.id, g]));
    $('#add', el).addEventListener('click', () => modal({ title: 'New savings goal', fields: goalFields, values: { current_amount: 0 }, submit: 'Create goal',
      onSubmit: async (v) => { await api('POST', '/api/goals', { ...v, target_date: v.target_date || null }); toast('Goal created'); A.route(); } }));
    $$('[data-edit]', el).forEach((b) => b.addEventListener('click', () => { const g = byId[b.dataset.edit]; modal({ title: 'Edit goal', fields: goalFields, values: g,
      onSubmit: async (v) => { await api('PUT', '/api/goals/' + g.id, { ...v, target_date: v.target_date || null }); toast('Goal updated'); A.route(); } }); }));
    const money_ = (action) => (b) => b.addEventListener('click', () => { const g = byId[b.dataset[action === 'withdraw' ? 'wd' : 'add']]; modal({
      title: (action === 'withdraw' ? 'Withdraw from ' : 'Add funds to ') + g.name, submit: action === 'withdraw' ? 'Withdraw' : 'Add funds',
      fields: [{ name: 'amount', label: 'Amount', type: 'number', step: '0.01', min: '0.01', required: true }],
      onSubmit: async (v) => { await api('POST', `/api/goals/${g.id}/contribute`, { amount: v.amount, action }); toast('Goal updated'); A.route(); } }); });
    $$('[data-add]', el).forEach(money_('add')); $$('[data-wd]', el).forEach(money_('withdraw'));
    $$('[data-del]', el).forEach((b) => b.addEventListener('click', async () => {
      if (!confirm('Delete this goal?')) return;
      try { await api('DELETE', '/api/goals/' + b.dataset.del); toast('Goal deleted'); A.route(); } catch (e) { toast(e.message, 'error'); }
    }));
  };

  /* ================= REPORTS (extends to Future Prediction) ================= */
  let RP = null;
  A.views.reports = async (el) => {
    RP = RP || { from: A.monthRange(0)[0], to: A.monthRange(0)[1] };
    const r = await api('GET', '/api/reports?' + qs(RP));
    const ex = r.expense_by_category;
    el.innerHTML = head('Reports', `<a class="btn" href="/api/reports/export.csv?${qs(RP)}">Export CSV</a><a class="btn primary" href="#/forecast">View financial projections →</a>`) + `
      <form class="card filters" id="rf" novalidate><div class="field"><label for="rfrom">From</label><input id="rfrom" type="date" name="from" value="${RP.from}"></div>
        <div class="field"><label for="rto">To</label><input id="rto" type="date" name="to" value="${RP.to}"></div>
        <div class="field"><label for="rp">Quick range</label><select id="rp"><option value="">Choose…</option>${A.periodPresets().map((p, i) => `<option value="${i}">${p[0]}</option>`).join('')}</select></div>
        <button class="btn primary">Apply</button></form>
      <div class="grid g4"><div class="card stat"><div class="label">Income</div><div class="value inc">${money(r.totals.income)}</div></div>
        <div class="card stat"><div class="label">Expenses</div><div class="value exp">${money(r.totals.expense)}</div></div>
        <div class="card stat"><div class="label">Savings rate <span class="tag">calculated</span></div><div class="value">${r.savings_rate == null ? '—' : r.savings_rate + '%'}</div></div>
        <div class="card stat"><div class="label">Avg daily spend <span class="tag">calculated</span></div><div class="value">${money(r.avg_daily_expense)}</div></div></div><br>
      <div class="grid g2"><div class="card"><h2>Expenses by category</h2>${ex.length ? `<div class="tbl-wrap"><table><thead><tr><th>Category</th><th class="num">Amount</th><th>Share</th></tr></thead><tbody>${ex.map((c) => `<tr><td>${esc(c.category)}</td><td class="num">${money(c.total)}</td><td class="minw">${bar(c.percent)}<span class="small muted">${c.percent}%</span></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No expenses in this range.</div>'}</div>
        <div class="card"><h2>Income by category</h2>${r.income_by_category.length ? `<div class="tbl-wrap"><table><thead><tr><th>Category</th><th class="num">Amount</th><th class="num">Share</th></tr></thead><tbody>${r.income_by_category.map((c) => `<tr><td>${esc(c.category)}</td><td class="num">${money(c.total)}</td><td class="num">${c.percent}%</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No income in this range.</div>'}</div>
        <div class="card"><h2>Month by month</h2>${r.by_month.length ? C.bars(r.by_month.map((m) => monthLabel(m.month)), [{ name: 'Income', color: '#16a34a', values: r.by_month.map((m) => m.income) }, { name: 'Expenses', color: '#dc2626', values: r.by_month.map((m) => m.expense) }]) : '<div class="empty">No data.</div>'}</div>
        <div class="card"><h2>Payment methods &amp; highlights</h2>${r.by_payment_method.map((p) => `<div class="row item"><span>${esc(p.method)} <span class="muted small">(${p.count})</span></span><b>${money(p.total)}</b></div>`).join('') || '<div class="empty">No data.</div>'}
        ${r.largest_expense ? `<div class="notice small">Largest expense: <b>${money(r.largest_expense.amount)}</b> on ${esc(r.largest_expense.category)} (${niceDate(r.largest_expense.date)})</div>` : ''}</div></div>`;
    $('#rp', el).addEventListener('change', (e) => { if (e.target.value === '') return; const p = A.periodPresets()[e.target.value]; $('#rfrom', el).value = p[1]; $('#rto', el).value = p[2]; });
    $('#rf', el).addEventListener('submit', (e) => { e.preventDefault(); RP = { from: $('#rfrom', el).value, to: $('#rto', el).value }; A.route(); });
  };

  /* ================= FINANCIAL ADVISOR ================= */
  A.views.advisor = async (el) => {
    const r = await api('GET', '/api/advisor');
    const label = { high: 'Needs attention', medium: 'Worth reviewing', low: 'For your information', positive: 'Good news', info: 'Info' };
    el.innerHTML = head('Financial advisor') + `<div class="notice warn small" role="note">${esc(r.disclaimer)}</div><br>` +
      (r.suggestions.map((s) => `<div class="card sug ${s.severity}"><div class="row"><h3>${esc(s.title)}</h3><span class="tag">${label[s.severity]}</span></div>
        <p>${esc(s.message)}</p><details><summary>Why am I seeing this?</summary><p class="small muted">${esc(s.why)} <span class="tag">system-calculated</span></p></details>
        ${s.action ? `<div class="list-actions"><a class="btn sm primary" href="${esc(s.action.route)}">${esc(s.action.label)}</a></div>` : ''}</div>`).join(''));
  };

  /* ================= FUTURE PREDICTION (extension of Reports) ================= */
  const FP = { tab: 'budget', buffer_pct: 5, inflation_pct: 0, income_growth_pct: 0, expense_growth_pct: 0 };
  A.views.forecast = async (el) => {
    const tabs = [['budget', 'Next-year budget'], ['balance', 'Balance after 1 year'], ['projections', 'Financial projections']];
    el.innerHTML = head('Future prediction') + `<div class="notice warn small" role="note"><span class="tag est">Estimate</span> These figures are projected from your past data using simple averages. They are not guaranteed and not financial advice.</div><br>
      <div class="tabs" role="tablist">${tabs.map(([k, l]) => `<button role="tab" data-t="${k}" class="${FP.tab === k ? 'active' : ''}">${l}</button>`).join('')}</div><div id="fp"></div>`;
    $$('.tabs button', el).forEach((b) => b.addEventListener('click', () => { FP.tab = b.dataset.t; A.route(); }));
    const box = $('#fp', el);
    const controls = (fields) => `<form class="card filters" id="fpf" novalidate>${fields.map(([k, l, help]) => `<div class="field"><label for="p_${k}">${l}</label><input id="p_${k}" type="number" step="0.5" name="${k}" value="${FP[k]}"><div class="help">${help}</div></div>`).join('')}<button class="btn primary">Recalculate</button></form>`;
    const wire = () => { const f = $('#fpf', box); f.addEventListener('submit', (e) => { e.preventDefault(); for (const i of f.elements) if (i.name) FP[i.name] = i.value; A.route(); }); };
    const basis = (b) => `<p class="small muted">Based on ${b.months} completed month(s) of history (${niceDate(b.from)} – ${niceDate(b.to)}). Confidence: <b>${b.confidence}</b>. ${esc(b.note)}</p>`;

    if (FP.tab === 'budget') {
      const p = await api('GET', '/api/forecast/next-year-budget?' + qs({ buffer_pct: FP.buffer_pct, inflation_pct: FP.inflation_pct }));
      box.innerHTML = controls([['buffer_pct', 'Safety buffer %', 'Extra room added to each category'], ['inflation_pct', 'Expected price rise %', 'Yearly cost increase']]) + basis({ ...p.based_on, months: p.months_of_data, confidence: p.confidence, note: p.note }) +
        (p.categories.length ? `<div class="grid g4"><div class="card stat"><div class="label">Suggested monthly total <span class="tag est">estimate</span></div><div class="value">${money(p.total_monthly)}</div></div>
        <div class="card stat"><div class="label">Suggested yearly total</div><div class="value">${money(p.total_yearly)}</div></div></div><br>
        <div class="card"><div class="tbl-wrap"><table class="stack"><thead><tr><th>Category</th><th class="num">Past monthly avg</th><th class="num">Suggested / month</th><th class="num">Suggested / year</th></tr></thead><tbody>${p.categories.map((c) => `<tr><td data-l="Category">${esc(c.category)}</td><td data-l="Past avg" class="num">${money(c.past_monthly_avg)}</td><td data-l="Per month" class="num"><b>${money(c.suggested_monthly)}</b></td><td data-l="Per year" class="num">${money(c.suggested_yearly)}</td></tr>`).join('')}</tbody></table></div>
        <div class="list-actions"><button class="btn primary" id="apply">Use as my budgets…</button></div></div>` : '<div class="card empty">Add some expenses first — the next-year budget is generated from your past spending.</div>');
      wire();
      const ap = $('#apply', box);
      if (ap) ap.addEventListener('click', () => modal({ title: 'Create budgets from this plan', submit: 'Create budgets', values: { month: A.thisMonth(), months: 12 },
        fields: [{ name: 'month', label: 'Starting month', type: 'month', required: true }, { name: 'months', label: 'Number of months', type: 'number', min: 1, max: 12, required: true, help: 'Existing budgets are never overwritten.' }],
        onSubmit: async (v) => { const r = await api('POST', '/api/forecast/apply-budget', { ...v, buffer_pct: FP.buffer_pct, inflation_pct: FP.inflation_pct }); toast(`Created ${r.created} budget(s), skipped ${r.skipped_existing} existing`); } }));
    } else {
      const path = FP.tab === 'balance' ? 'balance' : 'projections';
      const p = await api('GET', `/api/forecast/${path}?` + qs({ income_growth_pct: FP.income_growth_pct, expense_growth_pct: FP.expense_growth_pct }));
      const ctl = controls([['income_growth_pct', 'Income growth % / year', 'Expected raise'], ['expense_growth_pct', 'Expense growth % / year', 'Expected cost increase']]);
      if (FP.tab === 'balance') {
        const s = p.scenarios;
        box.innerHTML = ctl + basis(p.based_on) + `<div class="grid g4"><div class="card stat"><div class="label">Balance today</div><div class="value">${money(p.current_balance)}</div></div>
          <div class="card stat"><div class="label">After 1 year — expected <span class="tag est">estimate</span></div><div class="value">${money(s.expected.final_balance)}</div></div>
          <div class="card stat"><div class="label">Conservative</div><div class="value">${money(s.conservative.final_balance)}</div><div class="small muted">income −10%, expenses +10%</div></div>
          <div class="card stat"><div class="label">Optimistic</div><div class="value">${money(s.optimistic.final_balance)}</div><div class="small muted">income +5%, expenses −5%</div></div></div><br>
          <div class="card"><div class="row item"><span>Average monthly income</span><b>${money(p.avg_monthly_income)}</b></div><div class="row item"><span>Average monthly expenses</span><b>${money(p.avg_monthly_expense)}</b></div>
          <div class="row item"><span>Average monthly saving</span><b>${money(p.avg_monthly_income - p.avg_monthly_expense)}</b></div></div>`;
      } else {
        const rows = p.projection.expected.rows, L = rows.map((r) => monthLabel(r.month));
        box.innerHTML = ctl + basis(p.based_on) + `<div class="card"><h2>Projected balance over the next 12 months</h2>${C.lines(L, [
          { name: 'Conservative', color: '#d97706', dash: true, values: p.projection.conservative.rows.map((r) => r.balance) },
          { name: 'Expected', color: '#0f766e', values: rows.map((r) => r.balance) },
          { name: 'Optimistic', color: '#2563eb', dash: true, values: p.projection.optimistic.rows.map((r) => r.balance) }])}</div><br>
          <div class="card"><h2>Expected scenario, month by month</h2><div class="tbl-wrap"><table class="stack"><thead><tr><th>Month</th><th class="num">Income</th><th class="num">Expenses</th><th class="num">Net</th><th class="num">Balance</th></tr></thead><tbody>${rows.map((r) => `<tr><td data-l="Month">${monthLabel(r.month)}</td><td data-l="Income" class="num">${money(r.income)}</td><td data-l="Expenses" class="num">${money(r.expense)}</td><td data-l="Net" class="num ${r.net < 0 ? 'exp' : ''}">${money(r.net)}</td><td data-l="Balance" class="num"><b>${money(r.balance)}</b></td></tr>`).join('')}</tbody></table></div></div>`;
      }
      wire();
    }
  };

  /* ================= NOTIFICATIONS (Manage Notifications) ================= */
  A.views.notifications = async (el) => {
    const r = await api('GET', '/api/notifications');
    el.innerHTML = head('Notifications', `<button class="btn" id="readall" ${r.unread ? '' : 'disabled'}>Mark all as read</button><a class="btn" href="#/profile">Preferences</a>`) +
      `<div class="card">${r.items.length ? r.items.map((n) => `<div class="item row"><div><span class="${n.is_read ? 'muted' : ''}">${n.is_read ? '' : '<b class="inc">● </b>'}${esc(n.message)}</span><div class="small muted">${new Date(n.created_at).toLocaleString()}</div></div>
        <div class="list-actions">${n.is_read ? '' : `<button class="btn sm" data-read="${n.id}">Mark read</button>`}<button class="btn sm danger" data-del="${n.id}">Delete</button></div></div>`).join('') : '<div class="empty">You are all caught up. Budget alerts appear here.</div>'}</div>`;
    const reload = () => A.route();
    $('#readall', el).addEventListener('click', async () => { await api('POST', '/api/notifications/read-all'); reload(); });
    $$('[data-read]', el).forEach((b) => b.addEventListener('click', async () => { await api('POST', `/api/notifications/${b.dataset.read}/read`); reload(); }));
    $$('[data-del]', el).forEach((b) => b.addEventListener('click', async () => { await api('DELETE', '/api/notifications/' + b.dataset.del); reload(); }));
  };

  /* ================= PROFILE (Manage Profile) ================= */
  A.views.profile = async (el) => {
    const u = A.user;
    el.innerHTML = head('Profile') + `<div class="grid g2"><form class="card" id="pf" novalidate><h2>Account details</h2><br>
      <div class="field"><label>Email</label><input value="${esc(u.email)}" disabled></div>
      <div class="field"><label for="pn">Name</label><input id="pn" name="name" value="${esc(u.name)}" required maxlength="80"></div>
      <div class="field"><label for="pc">Currency</label><select id="pc" name="currency">${A.currencies.map((c) => `<option ${c === u.currency ? 'selected' : ''}>${c}</option>`).join('')}</select></div>
      <h3>Notification preferences</h3><br><div class="field"><label class="check"><input type="checkbox" name="notify_budget" ${u.notify_budget ? 'checked' : ''}> Budget alerts</label></div>
      <div class="field"><label class="check"><input type="checkbox" name="notify_goals" ${u.notify_goals ? 'checked' : ''}> Savings goal updates</label></div>
      <div class="form-error" role="alert"></div><button class="btn primary">Save profile</button></form>
      <form class="card" id="pw" novalidate><h2>Change password</h2><br>
      <div class="field"><label for="cp">Current password</label><input id="cp" type="password" name="current_password" autocomplete="current-password" required></div>
      <div class="field"><label for="np">New password</label><input id="np" type="password" name="new_password" autocomplete="new-password" required><div class="help">At least 8 characters with a letter and a number.</div></div>
      <div class="form-error" role="alert"></div><button class="btn primary">Update password</button></form></div>`;
    const submit = (id, fn) => { const f = $(id, el), err = $('.form-error', f); f.addEventListener('submit', async (e) => { e.preventDefault(); err.textContent = ''; try { await fn(f); } catch (x) { err.textContent = x.message; } }); };
    submit('#pf', async (f) => {
      A.user = await api('PUT', '/api/profile', { name: f.elements.name.value, currency: f.elements.currency.value, notify_budget: f.elements.notify_budget.checked, notify_goals: f.elements.notify_goals.checked });
      toast('Profile saved'); A.startShell();
    });
    submit('#pw', async (f) => { await api('PUT', '/api/profile/password', { current_password: f.elements.current_password.value, new_password: f.elements.new_password.value }); f.reset(); toast('Password updated'); });
  };
})();
