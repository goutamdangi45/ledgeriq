/* Dependency-free SVG charts (CSP friendly: presentation attributes only). */
(function () {
  const PALETTE = ['#0f766e', '#2563eb', '#d97706', '#9333ea', '#dc2626', '#0891b2', '#65a30d', '#db2777', '#64748b', '#ca8a04'];
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const compact = (n) => new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(n);

  function niceMax(v) {
    if (v <= 0) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(v))), f = v / p;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
  }

  function donut(items, centerTop, centerBottom, money) {
    const total = items.reduce((a, b) => a + b.value, 0);
    if (!total) return '<div class="empty">No data for this period</div>';
    const R = 70, C = 2 * Math.PI * R;
    let off = 0;
    const segs = items.map((it, i) => {
      const len = (it.value / total) * C;
      const s = `<circle r="${R}" cx="90" cy="90" fill="none" stroke="${PALETTE[i % PALETTE.length]}" stroke-width="26" stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-off}"><title>${esc(it.label)}: ${esc(money ? money(it.value) : it.value)}</title></circle>`;
      off += len; return s;
    }).join('');
    const legend = items.map((it, i) => `<span><i data-c="${PALETTE[i % PALETTE.length]}"></i>${esc(it.label)} · ${(it.value * 100 / total).toFixed(0)}%</span>`).join('');
    return `<div class="chart"><svg viewBox="0 0 180 180" role="img" aria-label="Spending by category"><g transform="rotate(-90 90 90)">${segs}</g>
      <text x="90" y="88" text-anchor="middle" class="ax" font-size="10">${esc(centerTop || '')}</text>
      <text x="90" y="106" text-anchor="middle" font-size="13" font-weight="700" fill="currentColor">${esc(centerBottom || '')}</text></svg></div><div class="legend" data-legend>${legend}</div>`;
  }

  function frame(W, H, L, B, min, max, ticks, fmt) {
    let g = '';
    for (let i = 0; i <= ticks; i++) {
      const v = min + ((max - min) * i) / ticks, y = H - B - ((H - B - 10) * i) / ticks;
      g += `<line x1="${L}" x2="${W - 8}" y1="${y}" y2="${y}" class="gl"/><text x="${L - 6}" y="${y + 4}" text-anchor="end" class="ax">${esc(fmt(v))}</text>`;
    }
    return g;
  }

  function bars(labels, series, fmt) {
    fmt = fmt || compact;
    const W = 600, H = 250, L = 52, B = 28;
    const max = niceMax(Math.max(1, ...series.flatMap((s) => s.values)));
    const gw = (W - L - 8) / labels.length, bw = Math.min(26, (gw * 0.7) / series.length);
    let out = frame(W, H, L, B, 0, max, 4, fmt);
    labels.forEach((lab, i) => {
      const gx = L + gw * i + gw / 2 - (bw * series.length) / 2;
      series.forEach((s, j) => {
        const h = ((H - B - 10) * s.values[i]) / max;
        out += `<rect x="${gx + j * bw}" y="${H - B - h}" width="${bw - 2}" height="${Math.max(h, 0)}" rx="3" fill="${s.color}"><title>${esc(s.name)} ${esc(lab)}: ${esc(fmt(s.values[i]))}</title></rect>`;
      });
      out += `<text x="${L + gw * i + gw / 2}" y="${H - 8}" text-anchor="middle" class="ax">${esc(lab)}</text>`;
    });
    const legend = series.map((s) => `<span><i data-c="${s.color}"></i>${esc(s.name)}</span>`).join('');
    return `<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img">${out}</svg></div><div class="legend" data-legend>${legend}</div>`;
  }

  function lines(labels, series, fmt) {
    fmt = fmt || compact;
    const W = 600, H = 260, L = 56, B = 28;
    const all = series.flatMap((s) => s.values);
    let min = Math.min(0, ...all), max = Math.max(1, ...all);
    max = niceMax(max); if (min < 0) min = -niceMax(-min);
    const x = (i) => L + ((W - L - 12) * i) / Math.max(labels.length - 1, 1);
    const y = (v) => H - B - ((H - B - 10) * (v - min)) / (max - min || 1);
    let out = frame(W, H, L, B, min, max, 4, fmt);
    series.forEach((s) => {
      const pts = s.values.map((v, i) => `${x(i)},${y(v)}`).join(' ');
      out += `<polyline points="${pts}" fill="none" stroke="${s.color}" stroke-width="2.5" stroke-linejoin="round" ${s.dash ? 'stroke-dasharray="6 4"' : ''}/>`;
      s.values.forEach((v, i) => { out += `<circle cx="${x(i)}" cy="${y(v)}" r="3" fill="${s.color}"><title>${esc(s.name)} ${esc(labels[i])}: ${esc(fmt(v))}</title></circle>`; });
    });
    labels.forEach((lab, i) => { if (labels.length <= 8 || i % 2 === 0) out += `<text x="${x(i)}" y="${H - 8}" text-anchor="middle" class="ax">${esc(lab)}</text>`; });
    const legend = series.map((s) => `<span><i data-c="${s.color}"></i>${esc(s.name)}</span>`).join('');
    return `<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img">${out}</svg></div><div class="legend" data-legend>${legend}</div>`;
  }

  /* CSP forbids inline style attributes, so legend swatch colours are applied through the CSSOM. */
  function paint(root) { root.querySelectorAll('[data-c]').forEach((e) => { e.style.background = e.dataset.c; }); }

  window.Charts = { PALETTE, donut, bars, lines, paint, compact };
})();
