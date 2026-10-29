'use strict';
const $ = (selector) => document.querySelector(selector);
const state = { people: [], documents: [], view: 'people' };
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const personName = id => state.people.find(p => p.id === id)?.name || '';
const dates = p => [p.born?.slice(0,4), p.died?.slice(0,4)].filter(Boolean).join(' – ') || 'Dates not yet recorded';
const initials = name => name.split(/\s+/).slice(0,2).map(n => n[0]).join('');
async function load() {
  const response = await fetch('/api/archive');
  if (!response.ok) throw new Error('Could not load the archive. Check that the local server is running.');
  const data = await response.json();
  state.people = data.people; state.documents = data.documents;
  $('#people-count').textContent = state.people.length;
  $('#documents-count').textContent = state.documents.length;
  document.querySelectorAll('.person-select').forEach(select => {
    select.innerHTML = '<option value="">Not recorded</option>' + state.people.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
  });
  render();
}
function render() {
  const view = state.view;
  const query = $('#search').value.toLowerCase().trim();
  $('#section-title').textContent = {people:'Our family', documents:'The document archive', timeline:'Across generations'}[view];
  $('#section-kicker').textContent = {people:'THE PEOPLE WHO CAME BEFORE US',documents:'THE RECORDS THAT KEEP THEIR STORIES',timeline:'A HISTORY, ONE MOMENT AT A TIME'}[view];
  $('#add').textContent = view === 'documents' ? '+ Add document' : '+ Add family member';
  const collection = $('#collection');
  collection.className = view === 'timeline' ? 'grid timeline' : 'grid';
  const source = view === 'documents' ? state.documents : state.people;
  const records = source.filter(record => [record.name,record.title,record.birthplace,record.notes,record.category,personName(record.person_id)].filter(Boolean).join(' ').toLowerCase().includes(query));
  if (view === 'timeline') {
    const events = records.flatMap(p => ['born','died'].filter(k => p[k]).map(k => ({date:p[k],name:p.name,label:k==='born'?'Born':'Died',place:k==='born'?p.birthplace:''}))).sort((a,b) => a.date.localeCompare(b.date));
    collection.innerHTML = events.map(e => `<article class="event"><time datetime="${escapeHtml(e.date)}">${escapeHtml(e.date)}</time><div><strong>${escapeHtml(e.name)}</strong><p>${e.label}${e.place?' · '+escapeHtml(e.place):''}</p></div></article>`).join('');
    if (!events.length) empty(query ? 'No matching events' : 'The story unfolds here', 'Add family members with birth or death dates to begin your family timeline.');
    return;
  }
  collection.innerHTML = records.map(r => view === 'people'
    ? `<button class="card" data-person="${r.id}"><span class="avatar">${escapeHtml(initials(r.name))}</span><h3>${escapeHtml(r.name)}</h3><p>${escapeHtml(dates(r))}<br>${escapeHtml(r.birthplace || 'Birthplace not yet recorded')}</p><span class="open">Explore their story →</span></button>`
    : `<button class="card" data-document="${r.id}"><span class="badge">${escapeHtml(r.category)}</span><h3>${escapeHtml(r.title)}</h3><p>${escapeHtml(personName(r.person_id) || 'Family collection')}<br>${escapeHtml(r.filename)} · ${(r.size/1024).toFixed(1)} KB</p><span class="open">View record →</span></button>`).join('');
  if (!records.length) empty(query ? 'No matching records' : view === 'people' ? 'Every family story starts with a name.' : 'Keep the originals. Preserve the stories.', query ? 'Try another name, place, or detail.' : view === 'people' ? 'Add your first family member, then connect generations and gather their records.' : 'Add photographs, certificates, letters, and research to your family collection.');
}
function empty(title, description) {
  $('#collection').innerHTML = `<div class="empty"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(description)}</p>${!$('#search').value?'<button class="primary" id="empty-add">'+(state.view==='documents'?'Add your first document':'Add a family member')+'</button>':''}</div>`;
  $('#empty-add')?.addEventListener('click', openAdd);
}
function openAdd() {
  const dialog = $(state.view === 'documents' ? '#document-dialog' : '#person-dialog');
  dialog.querySelector('form').reset(); dialog.querySelector('.form-error').textContent = ''; dialog.showModal();
}
function showPerson(id) {
  const p = state.people.find(p => p.id === id);
  const parents = [p.parent1,p.parent2].filter(Boolean).map(personName);
  const children = state.people.filter(c => c.parent1 === id || c.parent2 === id);
  const documents = state.documents.filter(d => d.person_id === id);
  $('#detail').innerHTML = `<h2>${escapeHtml(p.name)}</h2><p>${escapeHtml(dates(p))}${p.birthplace?' · '+escapeHtml(p.birthplace):''}</p><h3>Life story & notes</h3><p>${escapeHtml(p.notes || 'No story recorded yet.')}</p><h3>Family connections</h3><p>Parents: ${escapeHtml(parents.join(' & ') || 'Not recorded')}<br>Children: ${escapeHtml(children.map(c=>c.name).join(', ') || 'None recorded')}</p><h3>Documents (${documents.length})</h3>${documents.map(d=>`<p><a href="/api/documents/${d.id}">${escapeHtml(d.title)} ↓</a></p>`).join('') || '<p>No documents linked yet.</p>'}`;
  $('#detail-dialog').showModal();
}
function showDocument(id) {
  const d = state.documents.find(d => d.id === id);
  $('#detail').innerHTML = `<p class="eyebrow">${escapeHtml(d.category)}</p><h2>${escapeHtml(d.title)}</h2><p>${escapeHtml(personName(d.person_id) || 'Family collection')}</p><h3>Source & notes</h3><p>${escapeHtml(d.notes || 'No source notes recorded yet.')}</p><p>${escapeHtml(d.filename)} · ${(d.size/1024).toFixed(1)} KB</p><a href="/api/documents/${d.id}">Download original file ↓</a>`;
  $('#detail-dialog').showModal();
}
async function save(form, endpoint) {
  const button = form.querySelector('[type="submit"]');
  const error = form.querySelector('.form-error');
  button.disabled = true; error.textContent = '';
  let saved = false;
  try {
    const data = Object.fromEntries(new FormData(form));
    if (endpoint === 'documents') {
      const file = data.file;
      if (!file.size || file.size > 15 * 1024 * 1024) throw new Error('Choose a nonempty file up to 15 MB.');
      data.content = await new Promise((resolve,reject) => {
        const reader = new FileReader(); reader.onerror = () => reject(new Error('Could not read this file.'));
        reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.readAsDataURL(file);
      });
      data.filename = file.name; delete data.file;
    }
    const response = await fetch('/api/'+endpoint, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Unable to save record.');
    saved = true;
    form.closest('dialog').close();
    await load();
    $('#status').textContent = '';
  } catch (e) {
    if (saved) $('#status').textContent = 'Record saved. Refresh the page to reload the archive.';
    else error.textContent = e.message;
  } finally { button.disabled = false; }
}
document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => {
  state.view = tab.dataset.view;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t === tab));
  $('#search').value = ''; render();
}));
document.querySelectorAll('.close').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
$('#add').addEventListener('click', openAdd);
$('#search').addEventListener('input', render);
$('#collection').addEventListener('click', e => {
  const person = e.target.closest('[data-person]'); const document = e.target.closest('[data-document]');
  if (person) showPerson(person.dataset.person);
  if (document) showDocument(document.dataset.document);
});
$('#person-form').addEventListener('submit', e => { e.preventDefault(); save(e.target,'people'); });
$('#document-form').addEventListener('submit', e => { e.preventDefault(); save(e.target,'documents'); });
load().catch(e => { $('#status').textContent = e.message; });
