/* Views: dashboard, transactions, budgets. */
(function () {
  const A = window.App, { $, $$, esc, money, api, qs, toast, bar, modal, niceDate, monthLabel } = A;
  const COLORS = window.Charts.PALETTE;

  const head = (title, actions = '') => `<div class="page-head"><h1>${title}</h1><div class="actions">${actions}</div></div>`;
  const periodPresets = () => {
    const [a, b] = A.monthRange(0), [c, d] = A.monthRange(-1);
    const y = new Date().getFullYear();
    return [['This month', a, b], ['Last month', c, d], ['This year', `${y}-01-01`, `${y}-12-31`], ['All time', '2000-01-01', A.isoDate()]];
  };
  A.head = head;
  A.periodPresets = periodPresets;

  const txnRow = (t, actions) => `<tr><td data-l="Date">${niceDate(t.date)}</td><td data-l="Category"><span class="pill">${esc(t.category)}</span></td>
    <td data-l="Notes" class="muted">${esc(t.notes) || '—'}</td><td data-l="Method">${esc(t.payment_method || '')}</td>
    <td data-l="Amount" class="num ${t.type === 'income' ? 'inc' : 'exp'}">${t.type === 'income' ? '+' : '−'}${money(t.amount)}</td>${actions ? `<td class="num">${actions(t)}</td>` : ''}</tr>`;

  /* ================= DASHBOARD (Use case: View Dashboard) ================= */
  A.views.dashboard = async (el) => {
    const params = A.dashParams || { from: A.periodPresets()[0][1], to: A.periodPresets()[0][2] };
    const d = await api('GET', '/api/dashboard?' + qs(params));
    const cats = d.expense_by_category;
    el.innerHTML = head(`Hello, ${esc(A.user.name.split(' ')[0])}`, `<select id="preset" aria-label="Period">${periodPresets().map((p, i) => `<option value="${i}" ${p[1] === params.from && p[2] === params.to ? 'selected' : ''}>${p[0]}</option>`).join('')}</select>
      <button class="btn primary" id="addtxn">+ Add transaction</button>`) + `
      <p class="muted small">Showing ${niceDate(d.period.from)} – ${niceDate(d.period.to)}. Totals and charts are <span class="tag">auto-calculated</span> from the transactions you entered.</p>
      <div class="grid g4">
        <div class="card stat"><div class="label">Income</div><div class="value inc">${money(d.totals.income)}</div></div>
        <div class="card stat"><div class="label">Expenses</div><div class="value exp">${money(d.totals.expense)}</div></div>
        <div class="card stat"><div class="label">Net for period</div><div class="value ${d.totals.net < 0 ? 'exp' : ''}">${money(d.totals.net)}</div></div>
        <div class="card stat"><div class="label">Total balance <span class="tag">all time</span></div><div class="value">${money(d.balance)}</div></div>
      </div><br>
      <div class="grid g2">
        <div class="card"><div class="section-title"><h2>Spending by category</h2></div>
          ${cats.length ? `<div class="donut-wrap"><div>${window.Charts.donut(cats.map((c) => ({ label: c.category, value: c.total })), 'Total spent', money(d.totals.expense), money).split('<div class="legend"')[0]}</div><div class="legend-col">${cats.map((c, i) => `<div class="row small"><span><i class="sw" data-c="${COLORS[i % COLORS.length]}"></i> ${esc(c.category)}</span><span>${money(c.total)} · ${c.percent}%</span></div>`).join('')}</div></div>` : '<div class="empty">No expenses in this period yet.</div>'}</div>
        <div class="card"><div class="section-title"><h2>Last 6 months</h2></div>${window.Charts.bars(d.trend.map((t) => monthLabel(t.month)), [{ name: 'Income', color: '#16a34a', values: d.trend.map((t) => t.income) }, { name: 'Expenses', color: '#dc2626', values: d.trend.map((t) => t.expense) }], window.Charts.compact)}</div>
        <div class="card"><div class="section-title"><h2>Budget status</h2><a href="#/budgets">Manage</a></div>
          ${d.budgets.length ? d.budgets.map((b) => `<div class="item"><div class="row"><strong>${esc(b.category)}</strong><span class="small ${b.level === 'over' ? 'exp' : b.level === 'warning' ? 'warn' : 'muted'}">${money(b.spent)} / ${money(b.planned)}</span></div>${bar(b.percent, b.level)}</div>`).join('') : '<div class="empty">No budget for this month. <a href="#/budgets">Create one</a></div>'}</div>
        <div class="card"><div class="section-title"><h2>Savings progress</h2><a href="#/goals">All goals</a></div>
          ${d.goals.length ? d.goals.map((g) => `<div class="item"><div class="row"><strong>${esc(g.name)}</strong><span class="small muted">${money(g.current_amount)} / ${money(g.target_amount)}</span></div>${bar(g.percent, g.status === 'completed' ? 'done' : '')}</div>`).join('') : '<div class="empty">No savings goals yet. <a href="#/goals">Set one</a></div>'}</div>
      </div><br>
      <div class="card"><div class="section-title"><h2>Recent transactions</h2><a href="#/transactions">View all</a></div>
        ${d.recent.length ? `<div class="tbl-wrap"><table class="stack"><thead><tr><th>Date</th><th>Category</th><th>Notes</th><th>Method</th><th class="num">Amount</th></tr></thead><tbody>${d.recent.map((t) => txnRow(t)).join('')}</tbody></table></div>` : '<div class="empty">Nothing recorded yet. Add your first transaction to get started.</div>'}</div>`;
    $('#preset', el).addEventListener('change', (e) => { const p = periodPresets()[e.target.value]; A.dashParams = { from: p[1], to: p[2] }; A.route(); });
    $('#addtxn', el).addEventListener('click', () => A.txnForm(null, () => A.route()));
  };

  /* ================= TRANSACTIONS (Manage Transactions + Search / Filter) ================= */
  const catOptions = (type, withAll) => [...(withAll ? [{ value: '', label: 'All categories' }] : []), ...A.cats.filter((c) => !type || c.type === type).map((c) => ({ value: c.id, label: type ? c.name : `${c.name} (${c.type})` }))];

  A.txnForm = (t, done) => {
    const clientId = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now()) + Math.random();
    modal({
      title: t ? 'Edit transaction' : 'Add transaction', submit: t ? 'Save changes' : 'Add',
      values: t ? { ...t } : { type: 'expense', date: A.isoDate(), payment_method: 'UPI' },
      fields: [
        { name: 'type', label: 'Type', type: 'select', options: [{ value: 'expense', label: 'Expense' }, { value: 'income', label: 'Income' }] },
        { name: 'amount', label: 'Amount', type: 'number', step: '0.01', min: '0.01', required: true },
        { name: 'date', label: 'Date', type: 'date', required: true },
        { name: 'category_id', label: 'Category', type: 'select', options: catOptions((t && t.type) || 'expense') },
        { name: 'payment_method', label: 'Payment method', type: 'select', options: A.methods.map((m) => ({ value: m, label: m })) },
        { name: 'notes', label: 'Notes (optional)', type: 'textarea' }],
      wire: (form) => {
        const sel = form.elements.type, cat = form.elements.category_id, keep = t ? String(t.category_id) : null;
        sel.addEventListener('change', () => { cat.innerHTML = catOptions(sel.value).map((o) => `<option value="${o.value}">${esc(o.label)}</option>`).join(''); });
        if (keep) cat.value = keep;
      },
      onSubmit: async (v) => {
        const body = { ...v, category_id: Number(v.category_id), amount: v.amount };
        if (t) await api('PUT', '/api/transactions/' + t.id, body);
        else { body.client_id = clientId; await api('POST', '/api/transactions', body); }
        toast(t ? 'Transaction updated' : 'Transaction added'); done();
      },
    });
  };

  const TF = { q: '', type: '', category_id: '', payment_method: '', from: '', to: '', min_amount: '', max_amount: '', sort: 'date_desc', page: 1 };

  A.views.transactions = async (el) => {
    el.innerHTML = head('Transactions', '<a class="btn" id="csv" href="#">Export CSV</a><button class="btn primary" id="add">+ Add transaction</button>') + `
      <form class="card filters" id="filters" novalidate>
        <div class="field"><label for="q">Search</label><input id="q" name="q" placeholder="Notes or category" value="${esc(TF.q)}"></div>
        <div class="field"><label for="ft">Type</label><select id="ft" name="type"><option value="">All</option><option value="expense">Expense</option><option value="income">Income</option></select></div>
        <div class="field"><label for="fc">Category</label><select id="fc" name="category_id">${catOptions(null, true).map((o) => `<option value="${o.value}">${esc(o.label)}</option>`).join('')}</select></div>
        <div class="field"><label for="fm">Method</label><select id="fm" name="payment_method"><option value="">All</option>${A.methods.map((m) => `<option>${esc(m)}</option>`).join('')}</select></div>
        <div class="field"><label for="ff">From</label><input id="ff" type="date" name="from" value="${TF.from}"></div>
        <div class="field"><label for="fto">To</label><input id="fto" type="date" name="to" value="${TF.to}"></div>
        <div class="field"><label for="fmin">Min amount</label><input id="fmin" type="number" min="0" step="0.01" name="min_amount" value="${TF.min_amount}"></div>
        <div class="field"><label for="fmax">Max amount</label><input id="fmax" type="number" min="0" step="0.01" name="max_amount" value="${TF.max_amount}"></div>
        <div class="field"><label for="fs">Sort</label><select id="fs" name="sort"><option value="date_desc">Newest first</option><option value="date_asc">Oldest first</option><option value="amount_desc">Highest amount</option><option value="amount_asc">Lowest amount</option></select></div>
        <button type="button" class="btn" id="reset">Reset</button></form>
      <div class="card" id="results"></div>`;
    const form = $('#filters', el);
    ['type', 'category_id', 'payment_method', 'sort'].forEach((n) => { form.elements[n].value = TF[n]; });
    let timer;
    const read = () => { Object.keys(TF).forEach((k) => { if (form.elements[k]) TF[k] = form.elements[k].value; }); TF.page = 1; };
    form.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { read(); load(); }, 300); });
    form.addEventListener('submit', (e) => e.preventDefault());
    $('#reset', el).addEventListener('click', () => { Object.assign(TF, { q: '', type: '', category_id: '', payment_method: '', from: '', to: '', min_amount: '', max_amount: '', sort: 'date_desc', page: 1 }); A.route(); });
    $('#add', el).addEventListener('click', () => A.txnForm(null, load));

    async function load() {
      const box = $('#results', el);
      try {
        const r = await api('GET', '/api/transactions?' + qs({ ...TF, per_page: 12 }));
        $('#csv', el).href = '/api/transactions/export.csv?' + qs({ ...TF, page: '', sort: '' });
        box.innerHTML = `<div class="row small muted"><span>${r.total} transaction${r.total === 1 ? '' : 's'} match</span><span>Income <b class="inc">${money(r.totals.income)}</b> · Expenses <b class="exp">${money(r.totals.expense)}</b> <span class="tag">auto-calculated</span></span></div>
          ${r.items.length ? `<div class="tbl-wrap"><table class="stack"><thead><tr><th>Date</th><th>Category</th><th>Notes</th><th>Method</th><th class="num">Amount</th><th></th></tr></thead><tbody>${r.items.map((t) => txnRow(t, (x) => `<button class="btn sm" data-edit="${x.id}">Edit</button> <button class="btn sm danger" data-del="${x.id}">Delete</button>`)).join('')}</tbody></table></div>
          <div class="pager"><button class="btn sm" id="prev" ${r.page <= 1 ? 'disabled' : ''}>← Previous</button><span class="small muted">Page ${r.page} of ${r.pages}</span><button class="btn sm" id="next" ${r.page >= r.pages ? 'disabled' : ''}>Next →</button></div>` : '<div class="empty">No transactions found. Try changing the filters or add a new one.</div>'}`;
        const byId = Object.fromEntries(r.items.map((t) => [t.id, t]));
        $$('[data-edit]', box).forEach((b) => b.addEventListener('click', () => A.txnForm(byId[b.dataset.edit], load)));
        $$('[data-del]', box).forEach((b) => b.addEventListener('click', async () => {
          if (!confirm('Delete this transaction? This cannot be undone.')) return;
          try { await api('DELETE', '/api/transactions/' + b.dataset.del); toast('Transaction deleted'); load(); } catch (e) { toast(e.message, 'error'); }
        }));
        const p = $('#prev', box), n = $('#next', box);
        if (p) p.addEventListener('click', () => { TF.page--; load(); });
        if (n) n.addEventListener('click', () => { TF.page++; load(); });
      } catch (e) { box.innerHTML = `<div class="form-error">${esc(e.message)}</div>`; }
    }
    await load();
  };

  /* ================= BUDGETS (Manage Budgets) ================= */
  let budgetMonth = null;
  A.views.budgets = async (el) => {
    budgetMonth = budgetMonth || A.thisMonth();
    const r = await api('GET', '/api/budgets?month=' + budgetMonth);
    el.innerHTML = head('Budgets', `<input type="month" id="month" value="${budgetMonth}" aria-label="Month"><button class="btn primary" id="add">+ New budget</button>`) + `
      <p class="muted small">Planned amounts are <span class="tag">user-entered</span>; spent and remaining are <span class="tag">auto-calculated</span>. Alerts fire when spending reaches the threshold you choose.</p>
      ${r.items.length ? `<div class="grid g3">${r.items.map((b) => `<div class="card"><div class="row"><h3>${esc(b.category)}</h3><span class="tag ${b.level === 'ok' ? '' : 'est'}">${b.level === 'over' ? 'Over budget' : b.level === 'warning' ? 'Near limit' : 'On track'}</span></div>
        <div class="stat"><div class="value">${money(b.remaining)}</div><div class="muted small">${b.remaining < 0 ? 'over the limit' : 'remaining'}</div></div><br>${bar(b.percent, b.level)}
        <div class="row small muted"><span>Spent ${money(b.spent)}</span><span>Planned ${money(b.planned)}</span></div><div class="small muted">Alert at ${b.threshold}% · ${b.percent}% used</div>
        <div class="list-actions"><button class="btn sm" data-edit="${b.id}">Edit</button><button class="btn sm danger" data-del="${b.id}">Remove</button></div></div>`).join('')}</div>`
      : '<div class="card empty">No budgets for this month yet. Create a total or category budget, or generate one from your past spending in <a href="#/forecast">Future prediction</a>.</div>'}`;
    $('#month', el).addEventListener('change', (e) => { if (e.target.value) { budgetMonth = e.target.value; A.route(); } });
    $('#add', el).addEventListener('click', () => modal({
      title: 'New budget for ' + budgetMonth, submit: 'Create budget', values: { threshold: 80 },
      fields: [{ name: 'category_id', label: 'Applies to', type: 'select', options: [{ value: '', label: 'All spending (total budget)' }, ...catOptions('expense')] },
        { name: 'amount', label: 'Planned amount', type: 'number', step: '0.01', min: '0.01', required: true },
        { name: 'threshold', label: 'Alert at (% of budget)', type: 'number', min: 1, max: 100, required: true }],
      onSubmit: async (v) => { await api('POST', '/api/budgets', { ...v, month: budgetMonth, category_id: v.category_id || null }); toast('Budget created'); A.route(); } }));
    const byId = Object.fromEntries(r.items.map((b) => [b.id, b]));
    $$('[data-edit]', el).forEach((b) => b.addEventListener('click', () => { const x = byId[b.dataset.edit]; modal({
      title: 'Edit ' + x.category + ' budget', values: { amount: x.planned, threshold: x.threshold },
      fields: [{ name: 'amount', label: 'Planned amount', type: 'number', step: '0.01', min: '0.01', required: true }, { name: 'threshold', label: 'Alert at (% of budget)', type: 'number', min: 1, max: 100, required: true }],
      onSubmit: async (v) => { await api('PUT', '/api/budgets/' + x.id, v); toast('Budget updated'); A.route(); } }); }));
    $$('[data-del]', el).forEach((b) => b.addEventListener('click', async () => {
      if (!confirm('Remove this budget?')) return;
      try { await api('DELETE', '/api/budgets/' + b.dataset.del); toast('Budget removed'); A.route(); } catch (e) { toast(e.message, 'error'); }
    }));
  };
})();
