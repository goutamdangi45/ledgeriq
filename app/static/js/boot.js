(async function () {
  const A = window.App;
  try {
    const me = await A.api('GET', '/api/auth/me');
    A.csrf = me.csrf; A.currencies = me.currencies; A.user = me.user;
    if (A.user) { await A.loadMeta(); A.startShell(); } else A.showAuth();
  } catch (e) {
    document.getElementById('app').innerHTML = '<p class="boot">Could not reach the server. Please refresh the page.</p>';
  }
})();
