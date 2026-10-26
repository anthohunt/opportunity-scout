document.addEventListener('submit', e => {
  const m = e.target.dataset.confirm;
  if (m && !confirm(m)) e.preventDefault();
});
// État d'une piste : changé sur place, sans recharger la page (repli : envoi normal du formulaire).
document.addEventListener('click', async e => {
  const b = e.target.closest('form.etat button');
  if (!b) return;
  e.preventDefault();
  const f = b.form, card = f.closest('.card');
  f.classList.add('busy');
  try {
    const r = await fetch(f.action, { method: 'POST', headers: { 'Accept': 'application/json' },
      body: new URLSearchParams({ etat: b.value }), credentials: 'same-origin' });
    if (!r.ok) throw new Error(r.status);
    f.querySelectorAll('button').forEach(x => { const on = x === b; x.classList.toggle('on', on); x.setAttribute('aria-pressed', on); });
    card.className = card.className.replace(/etat-\w+/, 'etat-' + b.value);
  } catch (_) { f.requestSubmit(b); }
  finally { f.classList.remove('busy'); }
});
