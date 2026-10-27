// To Do / OneNote-style detail pop-up for a single task (synapse). It grows out of whatever was clicked.
import { api, Tasks } from './api.js';
import { locationLabel } from './lists.js';
import { Templates } from './templates.js';
import { mutate, store } from './store.js';
import {
  addDays, closePopover, confirmDialog, debounce, esc, fmtDate, fmtDateTime, fmtSize, fmtWeek, h, icon, lightbox,
  modal, popover, REGION_VAR, renderMarkdown, toast, toastError, todayISO,
} from './ui.js';

const panel = () => document.getElementById('task-panel');
const overlay = () => document.getElementById('task-overlay');
let task = null;          // current detail
let editor = null;        // persistent notes editor element for the open task
let saveState = null;
let pendingNotes = null;
let hooks = {};
let lastPointer = null;   // where the user last pressed, so the pop-up can grow out of it

export function initTaskPanel(h_) {
  hooks = h_;
  panel().addEventListener('keydown', e => {
    if (e.key !== 'Escape' || e.target.closest('.editor')) return;
    const box = document.querySelector('.lightbox');
    if (box) box.remove(); else close();
  });
  panel().addEventListener('paste', onPanelPaste);
  let downOnBackdrop = false;
  overlay().addEventListener('pointerdown', e => { downOnBackdrop = e.target === overlay(); });
  overlay().addEventListener('click', e => { if (downOnBackdrop && e.target === overlay()) close(); });
  document.addEventListener('pointerdown', e => { lastPointer = { x: e.clientX, y: e.clientY, at: performance.now() }; }, true);
}

export const isOpen = () => overlay().classList.contains('open');
export const currentId = () => (isOpen() ? task?.id : null);

// origin: optional {x, y} in client pixels; defaults to the last click.
export async function open(id, origin) {
  try {
    const detail = await Tasks.get(id);
    if (task?.id !== id) { flushNotes(); editor = null; }
    task = detail;
    store.selectedId = id;
    hooks.onOpen?.(id);
    render();
    if (!isOpen()) {
      setOrigin(origin || (lastPointer && performance.now() - lastPointer.at < 1500 ? lastPointer : null));
      overlay().classList.add('open');
      panel().focus({ preventScroll: true });
    }
  } catch (e) { toastError(e); }
}

function setOrigin(p) {
  const el = panel();
  if (!p) { el.style.transformOrigin = ''; return; }
  const left = (window.innerWidth - el.offsetWidth) / 2;
  const top = (window.innerHeight - el.offsetHeight) / 2;
  el.style.transformOrigin = `${Math.round(p.x - left)}px ${Math.round(p.y - top)}px`;
}

export function close() {
  if (!isOpen()) return;
  flushNotes();
  overlay().classList.remove('open');
  store.selectedId = null;
  task = null;
  editor = null;
  hooks.onClose?.();
}

// Called after store refreshes (SSE or local mutation) so the pop-up reflects server state.
export async function refreshIfOpen() {
  if (!isOpen() || !task) return;
  const active = document.activeElement;
  if (panel().contains(active) && active.matches('input:not([type=checkbox]), textarea, [contenteditable]')) return;
  try {
    const detail = await Tasks.get(task.id);
    if (!isOpen() || detail.id !== task?.id) return;
    task = detail;
    render();
  } catch (e) {
    if (e.status === 404) close();
  }
}

async function update(fields) {
  try {
    task = await mutate(Tasks.update(task.id, fields));
    render();
  } catch (e) { toastError(e); }
}

function apply(detail) { task = detail; store.refresh(); render(); }

// ---------- render ----------
function render() {
  const t = task;
  const focusKey = document.activeElement?.dataset?.key;
  const body = h('div', { class: 'popup-body' },
    h('div', { class: 'popup-grid' },
      h('div', {}, stepsCard(t), notesCard(t), filesCard(t)),
      h('div', {}, scheduleCard(t), planningCard(t), sequenceCard(t), linksCard(t), insightsCard(t), activityCard(t))));
  const created = new Date(t.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  const foot = h('div', { class: 'popup-foot' },
    h('span', { class: 'grow' }, `Created ${created}${t.source === 'planner' ? ' · from Planner' : ''}`),
    h('button', { class: 'btn small danger', onclick: remove }, icon('trash'), 'Delete'));
  const head = h('div', { class: 'popup-head' },
    header(t),
    h('button', { class: 'btn icon ghost', title: 'Close (Esc)', onclick: close }, icon('x')));
  panel().style.setProperty('--rc', REGION_VAR[t.region] || 'var(--accent)');
  const prev = panel().querySelector('.popup-body');
  const scroll = prev && prev.dataset.taskId === String(t.id) ? prev.scrollTop : 0;
  body.dataset.taskId = t.id;
  panel().replaceChildren(head, body, foot);
  hooks.onRender?.(t);
  body.scrollTop = scroll;
  if (focusKey) panel().querySelector(`[data-key="${focusKey}"]`)?.focus();
}

function header(t) {
  const title = h('textarea', { rows: 1, 'aria-label': 'Title', maxlength: 500, dataset: { key: 'title' } });
  title.value = t.title;
  const fit = () => { title.style.height = 'auto'; title.style.height = `${title.scrollHeight}px`; };
  requestAnimationFrame(fit);
  title.addEventListener('input', fit);
  title.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); title.blur(); } });
  title.addEventListener('blur', () => {
    const v = title.value.trim();
    if (v && v !== t.title) update({ title: v });
    else title.value = t.title;
  });

  const loc = locationLabel(t);
  const regionName = { logical: 'Left hemisphere · logical', creative: 'Right hemisphere · creative', balanced: 'Balanced' }[t.region];
  const actions = [];
  if (t.status === 'basket' || t.status === 'backlog') actions.push(h('button', { class: 'btn small primary', onclick: placeOnBrain }, icon('brain'), 'Place on brain'));
  if (t.status === 'basket' || t.status === 'active') actions.push(h('button', { class: 'btn small', onclick: () => moveTo('backlog') }, icon('queue'), 'Send to queue'));
  if (t.status === 'backlog') actions.push(h('button', { class: 'btn small', onclick: () => moveTo('basket') }, icon('basket'), 'Back to basket'));
  if (t.status === 'active') actions.push(h('button', {
    class: `btn small ${t.pinned ? 'primary' : ''}`, title: 'Pinned synapses are kept when the brain re-thinks',
    onclick: () => update({ pinned: !t.pinned }),
  }, icon('pin'), t.pinned ? 'Pinned' : 'Pin'));
  actions.push(h('button', { class: 'btn small ghost', title: 'Reuse this task’s shape later', onclick: saveAsTemplate }, icon('template'), 'Save as template'));

  const eyebrow = t.status === 'active' && t.slot_index != null ? `Synapse ${t.slot_index + 1}` : 'Task';
  return h('div', {},
    h('div', { class: 'eyebrow' }, eyebrow),
    h('div', { class: 'tp-title' },
      h('button', { class: `check ${t.status === 'done' ? 'on' : ''}`, title: t.status === 'done' ? 'Reopen' : 'Complete', onclick: toggleDone }, icon('check')),
      title,
      h('button', { class: `star ${t.important ? 'on' : ''}`, title: 'Important', onclick: () => update({ important: !t.important }) }, icon('star'))),
    h('div', { class: 'tp-status' },
      h('span', { class: 'loc' }, icon(t.status === 'active' ? 'brain' : t.status === 'backlog' ? 'queue' : t.status === 'basket' ? 'basket' : 'done'), loc.text),
      h('span', {}, '·'), h('span', {}, regionName),
      t.at_risk ? h('span', { class: 'warn-text' }, '· at risk for due date') : null),
    h('div', { class: 'tp-status' }, actions));
}

async function placeOnBrain() {
  try {
    task = await mutate(Tasks.update(task.id, { status: 'active' }));
    render();
    hooks.onPlaced?.(task.id);
  } catch (e) {
    if (e.status === 409) toast('All synapses are busy. Drag this task onto one to swap it in, or raise RAM slots in Settings.', { timeout: 6000 });
    else toastError(e);
  }
}

async function moveTo(dest) {
  try {
    await mutate(Tasks.unplace(task.id, dest));
    await refreshIfOpen();
  } catch (e) { toastError(e); }
}

async function toggleDone() {
  const wasDone = task.status === 'done';
  await update({ status: wasDone ? 'backlog' : 'done' });
  if (!wasDone) hooks.onCompleted?.(task);
}

async function remove() {
  const ok = await confirmDialog('Delete task', `Delete “${task.title}” and its notes, steps and files? This can't be undone.`, 'Delete', 'danger');
  if (!ok) return;
  try {
    await mutate(Tasks.remove(task.id));
    close();
  } catch (e) { toastError(e); }
}

// ---------- steps ----------
function stepsCard(t) {
  const list = h('ul', { class: 'steps' });
  let dragId = null;
  for (const c of t.checklist) {
    const input = h('input', { value: c.text, 'aria-label': 'Step', dataset: { key: `step-${c.id}` }, maxlength: 1000 });
    input.addEventListener('keydown', e => { if (e.key === 'Enter') input.blur(); });
    input.addEventListener('blur', async () => {
      const v = input.value.trim();
      if (!v) { input.value = c.text; return; }
      if (v !== c.text) try { apply(await Tasks.updateStep(c.id, { text: v })); } catch (e) { toastError(e); }
    });
    const li = h('li', { class: `step ${c.done ? 'done' : ''}`, draggable: 'true' },
      h('span', { class: 'handle', title: 'Drag to reorder' }, icon('grip')),
      h('button', { class: `check ${c.done ? 'on' : ''}`, 'aria-label': c.done ? 'Uncheck step' : 'Check step', onclick: async () => {
        try { apply(await Tasks.updateStep(c.id, { done: !c.done })); } catch (e) { toastError(e); }
      } }, icon('check')),
      input,
      h('button', { class: 'del', title: 'Delete step', onclick: async () => {
        try { apply(await Tasks.deleteStep(c.id)); } catch (e) { toastError(e); }
      } }, icon('x')));
    li.addEventListener('dragstart', e => { dragId = c.id; e.dataTransfer.effectAllowed = 'move'; e.stopPropagation(); });
    li.addEventListener('dragover', e => { if (dragId != null) { e.preventDefault(); e.stopPropagation(); li.classList.add('drag-over'); } });
    li.addEventListener('dragleave', () => li.classList.remove('drag-over'));
    li.addEventListener('drop', async e => {
      e.preventDefault(); e.stopPropagation();
      li.classList.remove('drag-over');
      if (dragId == null || dragId === c.id) return;
      const ids = t.checklist.map(x => x.id).filter(x => x !== dragId);
      ids.splice(ids.indexOf(c.id), 0, dragId);
      dragId = null;
      try { apply(await Tasks.reorderSteps(t.id, ids)); } catch (err) { toastError(err); }
    });
    list.append(li);
  }
  const add = h('input', { placeholder: 'Add step', dataset: { key: 'add-step' }, maxlength: 1000 });
  add.addEventListener('keydown', async e => {
    if (e.key !== 'Enter' || !add.value.trim()) return;
    const text = add.value.trim();
    add.value = '';
    try { apply(await Tasks.addStep(t.id, text)); } catch (err) { toastError(err); }
  });
  const pct = t.checklist_total ? Math.round(100 * t.checklist_done / t.checklist_total) : 0;
  return h('div', { class: 'card' },
    h('div', { class: 'card-title' }, 'Steps', t.checklist_total ? h('span', { class: 'act' }, `${t.checklist_done} of ${t.checklist_total}`) : null),
    h('div', { class: 'card-body' },
      t.checklist_total ? h('div', { class: 'progress' }, h('i', { style: { width: `${pct}%` } })) : null,
      list,
      h('label', { class: 'add-step' }, icon('plus'), add)));
}

// ---------- schedule ----------
function scheduleCard(t) {
  const today = todayISO();
  const inMyDay = t.my_day === today;
  const due = h('input', { type: 'date', class: 'input', value: t.due_at?.slice(0, 10) || '', 'aria-label': 'Due date' });
  due.addEventListener('change', () => update({ due_at: due.value || null }));
  const remind = h('input', { type: 'datetime-local', class: 'input', value: t.reminder_at || '', 'aria-label': 'Reminder' });
  remind.addEventListener('change', () => update({ reminder_at: remind.value || null }));
  const repeat = h('select', { class: 'input', 'aria-label': 'Repeat' },
    ['', 'daily', 'weekdays', 'weekly', 'monthly'].map(v => h('option', { value: v, selected: (t.repeat || '') === v }, v ? v[0].toUpperCase() + v.slice(1) : 'Does not repeat')));
  repeat.addEventListener('change', () => update({ repeat: repeat.value }));
  const quick = (label, days) => h('button', { class: 'btn small', onclick: () => update({ due_at: addDays(today, days) }) }, label);

  return h('div', { class: 'card' },
    h('div', { class: `row toggle-row ${inMyDay ? 'on' : ''}`, onclick: () => update({ my_day: inMyDay ? '' : today }) },
      icon('sun'), h('span', {}, inMyDay ? 'Added to My Day' : 'Add to My Day')),
    h('div', { class: 'row' }, icon('bell'), h('label', {}, 'Remind me'), h('div', { class: 'ctl' }, remind,
      t.reminder_at ? h('button', { class: 'clear', title: 'Clear', onclick: () => update({ reminder_at: null }) }, icon('x')) : null)),
    h('div', { class: 'row' }, icon('calendar'), h('label', {}, 'Due'), h('div', { class: 'ctl' }, due,
      t.due_at ? h('button', { class: 'clear', title: 'Clear', onclick: () => update({ due_at: null }) }, icon('x')) : null)),
    t.due_at ? null : h('div', { class: 'row' }, h('span', { style: { width: '18px' } }), h('div', { class: 'ctl' }, quick('Today', 0), quick('Tomorrow', 1), quick('Next week', 7))),
    h('div', { class: 'row' }, icon('repeat'), h('label', {}, 'Repeat'), h('div', { class: 'ctl' }, repeat)),
    h('div', { class: 'row', title: 'How reminders and due dates reach you for this task' }, icon('send'), h('label', {}, 'Notify'), h('div', { class: 'ctl' },
      seg([['desktop', 'Desktop'], ['email', 'Email'], ['both', 'Both'], ['off', 'Off']], t.notify || 'desktop', v => update({ notify: v })))));
}

function saveAsTemplate() {
  const name = h('input', { class: 'input', value: task.title, maxlength: 80 });
  modal({
    title: 'Save as template', body: h('div', {}, h('div', { class: 'help', style: { marginBottom: '8px' } },
      'Keeps the title, notes, steps, priority, effort, tags, repeat, notifications and how far out it’s due.'), name),
    actions: [{ label: 'Cancel' }, { label: 'Save template', kind: 'primary', onClick: async () => {
      try { const tpl = await Templates.fromTask(task.id, name.value.trim() || task.title); toast(`Saved the “${tpl.name}” template`); }
      catch (e) { toastError(e); return false; }
    } }],
  });
  setTimeout(() => { name.focus(); name.select(); }, 50);
}

// ---------- planning ----------
function seg(options, value, onPick) {
  return h('div', { class: 'seg' }, options.map(([v, label]) => h('button', { class: v === value ? 'on' : '', onclick: () => v !== value && onPick(v) }, label)));
}

function planningCard(t) {
  const weeks = store.state.weeks || [];
  const autoLabel = t.week_locked ? 'Auto' : `Auto · ${fmtWeek(t.assigned_week, weeks)}`;
  const weekSel = h('select', { class: 'input', 'aria-label': 'Completion week' },
    h('option', { value: 'auto', selected: !t.week_locked }, autoLabel),
    weeks.map(w => h('option', { value: w.week, selected: t.week_locked && t.assigned_week === w.week }, fmtWeek(w.week, weeks))));
  if (t.week_locked && t.assigned_week && !weeks.some(w => w.week === t.assigned_week)) {
    weekSel.append(h('option', { value: t.assigned_week, selected: true }, fmtWeek(t.assigned_week, weeks)));
  }
  weekSel.addEventListener('change', () => update(weekSel.value === 'auto' ? { assigned_week: null, week_locked: false } : { assigned_week: weekSel.value, week_locked: true }));

  const slider = h('input', { type: 'range', min: 0, max: 100, value: t.creative_score, 'aria-label': 'Logical to creative' });
  slider.addEventListener('change', () => update({ creative_score: Number(slider.value) }));

  const tagInput = h('input', { placeholder: t.tags.length ? '' : 'Add tags…', dataset: { key: 'tags' }, maxlength: 40 });
  tagInput.addEventListener('keydown', e => {
    if ((e.key === 'Enter' || e.key === ',') && tagInput.value.trim()) {
      e.preventDefault();
      const tag = tagInput.value.trim().replace(/^#/, '');
      if (!t.tags.includes(tag)) update({ tags: [...t.tags, tag] });
      tagInput.value = '';
    } else if (e.key === 'Backspace' && !tagInput.value && t.tags.length) {
      update({ tags: t.tags.slice(0, -1) });
    }
  });

  return h('div', { class: 'card' },
    h('div', { class: 'row' }, icon('flag'), h('label', {}, 'Priority'), h('div', { class: 'ctl' },
      seg([['low', 'Low'], ['medium', 'Medium'], ['high', 'High'], ['urgent', 'Urgent']], t.priority, v => update({ priority: v })))),
    h('div', { class: 'row' }, icon('clock'), h('label', {}, 'Effort'), h('div', { class: 'ctl' },
      seg([['S', 'S · 2h'], ['M', 'M · 6h'], ['L', 'L · 12h'], ['XL', 'XL · 24h']], t.effort, v => update({ effort: v })))),
    h('div', { class: 'row' }, icon('week'), h('label', {}, 'Finish by'), h('div', { class: 'ctl' }, weekSel)),
    t.at_risk ? h('div', { class: 'row' }, h('span', { style: { width: '18px' } }), h('span', { class: 'warn-text' },
      'Not enough weekly capacity before the due date. Raise capacity in Settings, trim effort, or move other work.')) : null,
    h('div', { class: 'row' }, icon('brain'), h('label', {}, 'Thinking style'), h('div', { class: 'ctl' },
      h('div', { class: 'slider-wrap' }, h('span', { class: 'l' }, 'Logical'), slider, h('span', { class: 'c' }, 'Creative')),
      t.creative_locked ? h('button', { class: 'btn small', title: 'Let Memory classify it again', onclick: () => update({ creative_locked: false }) }, 'Auto') : null)),
    h('div', { class: 'row' }, icon('tag'), h('label', {}, 'Tags'), h('div', { class: 'ctl tags' },
      t.tags.map(tag => h('span', { class: 'tag' }, `#${tag}`, h('button', { 'aria-label': `Remove ${tag}`, onclick: () => update({ tags: t.tags.filter(x => x !== tag) }) }, '×'))),
      tagInput)));
}

// ---------- notes (OneNote-style) ----------
const saveNotes = debounce(async (id, html) => {
  pendingNotes = null;
  try {
    const d = await Tasks.update(id, { notes_html: html });
    if (task?.id === id) task = d;
    if (saveState) saveState.textContent = 'Saved';
    store.refresh();
  } catch (e) { toastError(e); if (saveState) saveState.textContent = 'Not saved'; }
}, 700);

function flushNotes() {
  if (pendingNotes) saveNotes.flush(pendingNotes.id, pendingNotes.html);
}

function sanitize(html) {
  const tpl = document.createElement('template');
  tpl.innerHTML = html || '';
  tpl.content.querySelectorAll('script, style, iframe, object, embed, link, meta').forEach(n => n.remove());
  tpl.content.querySelectorAll('*').forEach(n => {
    for (const a of [...n.attributes]) {
      if (/^on/i.test(a.name) || (/^(href|src)$/i.test(a.name) && /^\s*javascript:/i.test(a.value))) n.removeAttribute(a.name);
    }
  });
  return tpl.innerHTML;
}

function notesChanged() {
  const html = editor.innerHTML;
  pendingNotes = { id: task.id, html };
  if (saveState) saveState.textContent = 'Saving…';
  saveNotes(task.id, html);
}

function notesCard(t) {
  if (!editor || editor.dataset.taskId !== String(t.id)) {
    editor = h('div', { class: 'editor', contenteditable: 'true', 'data-placeholder': 'Notes, meeting minutes, ideas… paste screenshots straight in.', dataset: { taskId: t.id } });
    editor.innerHTML = sanitize(t.notes_html);
    editor.addEventListener('input', notesChanged);
    editor.addEventListener('paste', onEditorPaste);
    editor.addEventListener('drop', onEditorDrop);
    editor.addEventListener('click', e => {
      const li = e.target.closest('ul.checks > li');
      if (li && e.offsetX < 20) {
        li.dataset.checked = li.dataset.checked === 'true' ? 'false' : 'true';
        notesChanged();
      }
      if (e.target.tagName === 'IMG') lightbox(e.target.src);
    });
    editor.addEventListener('keydown', e => { if (e.key === 'Escape') editor.blur(); });
  } else if (document.activeElement !== editor && !pendingNotes && editor.innerHTML !== t.notes_html) {
    editor.innerHTML = sanitize(t.notes_html);
  }
  saveState = h('span', { class: 'save-state act' }, '');
  const cmd = (c, v) => () => { editor.focus(); document.execCommand(c, false, v); notesChanged(); };
  const tb = (label, title, fn) => h('button', { title, onmousedown: e => e.preventDefault(), onclick: fn }, label);
  const toolbar = h('div', { class: 'editor-toolbar' },
    tb('H1', 'Heading', cmd('formatBlock', 'h1')), tb('H2', 'Subheading', cmd('formatBlock', 'h2')), tb('¶', 'Paragraph', cmd('formatBlock', 'p')),
    h('span', { class: 'sep' }),
    tb(h('b', {}, 'B'), 'Bold (Ctrl+B)', cmd('bold')), tb(h('i', {}, 'I'), 'Italic (Ctrl+I)', cmd('italic')), tb(h('u', {}, 'U'), 'Underline (Ctrl+U)', cmd('underline')),
    h('span', { class: 'sep' }),
    tb('•', 'Bulleted list', cmd('insertUnorderedList')), tb('1.', 'Numbered list', cmd('insertOrderedList')),
    tb('☐', 'To-do list', () => {
      editor.focus();
      document.execCommand('insertUnorderedList');
      const sel = window.getSelection();
      const ul = sel?.anchorNode && (sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement)?.closest('ul');
      if (ul && editor.contains(ul)) { ul.classList.add('checks'); ul.querySelectorAll('li').forEach(li => { li.dataset.checked ||= 'false'; }); }
      notesChanged();
    }),
    tb('❝', 'Quote', cmd('formatBlock', 'blockquote')), tb('</>', 'Code block', cmd('formatBlock', 'pre')),
    h('span', { class: 'sep' }),
    tb(icon('link'), 'Link', () => insertLink()),
    tb(icon('image'), 'Insert image', () => pickFiles(true)));
  return h('div', { class: 'card' },
    h('div', { class: 'card-title' }, 'Notes', saveState),
    toolbar, editor);
}

function insertLink() {
  const sel = window.getSelection();
  const range = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
  const input = h('input', { class: 'input', placeholder: 'https://…', type: 'url' });
  modal({
    title: 'Insert link', body: input,
    actions: [{ label: 'Cancel' }, { label: 'Insert', kind: 'primary', onClick: () => {
      const url = input.value.trim();
      if (!/^https?:\/\//i.test(url)) { toast('Links must start with http:// or https://', { type: 'error' }); return false; }
      editor.focus();
      if (range) { sel.removeAllRanges(); sel.addRange(range); }
      if (range && !range.collapsed) document.execCommand('createLink', false, url);
      else document.execCommand('insertHTML', false, `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(url)}</a>&nbsp;`);
      notesChanged();
    } }],
  });
  setTimeout(() => input.focus(), 50);
}

function imageFiles(dt) {
  return [...(dt?.files || [])].filter(f => f.type.startsWith('image/'));
}

async function uploadAndInsert(files, isScreenshot) {
  const id = task.id;
  try {
    const d = await Tasks.upload(id, files, isScreenshot);
    if (task?.id !== id) return;
    task = d;
    const imgs = d.attachments.filter(a => d.uploaded_ids.includes(a.id) && a.mime.startsWith('image/'));
    editor.focus();
    for (const a of imgs) document.execCommand('insertHTML', false, `<img src="/api/attachments/${a.id}" alt="${esc(a.filename)}" data-att="${a.id}"><p><br></p>`);
    notesChanged();
    render();
  } catch (e) { toastError(e); }
}

function onEditorPaste(e) {
  const imgs = imageFiles(e.clipboardData);
  if (!imgs.length) return;
  e.preventDefault();
  e.stopPropagation();
  uploadAndInsert(imgs.map((f, i) => new File([f], f.name && f.name !== 'image.png' ? f.name : `screenshot-${Date.now()}-${i}.png`, { type: f.type })), true);
}

function onEditorDrop(e) {
  const files = [...(e.dataTransfer?.files || [])];
  if (!files.length) return;
  e.preventDefault();
  e.stopPropagation();
  const imgs = files.filter(f => f.type.startsWith('image/'));
  const others = files.filter(f => !f.type.startsWith('image/'));
  if (imgs.length) uploadAndInsert(imgs, false);
  if (others.length) uploadFiles(others);
}

// Paste anywhere else in the pop-up: screenshots become attachments.
function onPanelPaste(e) {
  if (!task || e.target.closest('.editor') || e.target.matches('input, textarea')) return;
  const imgs = imageFiles(e.clipboardData);
  if (!imgs.length) return;
  e.preventDefault();
  uploadFiles(imgs.map((f, i) => new File([f], `screenshot-${Date.now()}-${i}.png`, { type: f.type })), true);
}

// ---------- files ----------
async function uploadFiles(files, isScreenshot = false) {
  try {
    apply(await Tasks.upload(task.id, files, isScreenshot));
    toast(`Attached ${files.length} file${files.length > 1 ? 's' : ''}`);
  } catch (e) { toastError(e); }
}

function pickFiles(imagesInline = false) {
  const input = h('input', { type: 'file', multiple: true, accept: imagesInline ? 'image/*' : null });
  input.addEventListener('change', () => {
    const files = [...input.files];
    if (!files.length) return;
    if (imagesInline) uploadAndInsert(files, false);
    else uploadFiles(files);
  });
  input.click();
}

function filesCard(t) {
  const zone = h('div', { class: 'dropzone', tabindex: 0, role: 'button', onclick: () => pickFiles() },
    'Drop files here, click to browse, or press ', h('b', {}, 'Ctrl+V'), ' to paste a screenshot');
  zone.addEventListener('dragover', e => { if (e.dataTransfer.types.includes('Files')) { e.preventDefault(); e.stopPropagation(); zone.classList.add('drop-over'); } });
  zone.addEventListener('dragleave', () => zone.classList.remove('drop-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault(); e.stopPropagation();
    zone.classList.remove('drop-over');
    const files = [...e.dataTransfer.files];
    if (files.length) uploadFiles(files);
  });
  zone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pickFiles(); } });
  const grid = h('div', { class: 'files' }, t.attachments.map(a => {
    const url = `/api/attachments/${a.id}`;
    const isImg = a.mime.startsWith('image/');
    return h('div', { class: 'file', title: a.filename },
      h('div', { class: 'thumb', onclick: () => (isImg ? lightbox(url) : window.open(url, '_blank')) },
        isImg ? h('img', { src: url, alt: a.filename, loading: 'lazy' }) : icon('file')),
      a.is_screenshot ? h('span', { class: 'badge' }, 'Screenshot') : null,
      h('div', { class: 'name' }, h('a', { href: `${url}?download=true`, download: a.filename, title: 'Download' }, a.filename)),
      h('div', { class: 'size' }, `${fmtSize(a.size)} · ${fmtDate(a.created_at)}`),
      h('button', { class: 'x', title: 'Remove', onclick: async () => {
        if (!(await confirmDialog('Remove file', `Remove “${a.filename}”?`, 'Remove', 'danger'))) return;
        try { apply(await Tasks.deleteAttachment(a.id)); } catch (e) { toastError(e); }
      } }, '×'));
  }));
  return h('div', { class: 'card' },
    h('div', { class: 'card-title' }, 'Files & screenshots', t.attachments.length ? h('span', { class: 'act' }, String(t.attachments.length)) : null),
    h('div', { class: 'card-body' }, zone, t.attachments.length ? grid : null));
}

// ---------- sequence (dependencies) ----------
function sequenceCard(t) {
  const seq = store.task(t.id)?.seq;
  const chain = seq ? store.state.tasks.filter(x => x.seq?.goal === seq.goal).sort((a, b) => a.seq.step - b.seq.step || a.title.localeCompare(b.title)) : [];
  const steps = chain.length ? h('ol', { class: 'seq-chain' }, chain.map(x => h('li', {
    class: `${x.id === t.id ? 'me' : ''} ${x.status === 'done' ? 'done' : ''}`,
    onclick: () => { if (x.id !== t.id) open(x.id); },
  },
  h('span', { class: 'n' }, x.status === 'done' ? '✓' : String(x.seq.step)),
  h('span', { class: 'lt' }, x.title),
  x.id === seq.goal ? h('span', { class: 'kind' }, 'goal') : x.id === t.id ? h('span', { class: 'kind' }, 'this task') : null))) : null;

  const rel = (items, onRemove) => items.map(o => h('div', { class: 'link-item', onclick: e => { if (!e.target.closest('button')) open(o.id); } },
    h('span', { class: `seq-dot ${o.status === 'done' ? 'done' : ''}` }), h('span', { class: 'lt' }, o.title),
    h('span', { class: 'kind' }, o.status === 'done' ? 'done' : o.status),
    h('button', { title: 'Remove', onclick: async () => { try { apply(await onRemove(o)); } catch (e) { toastError(e); } } }, icon('x'))));

  const exclude = new Set([t.id, ...t.needs.map(o => o.id), ...t.unlocks.map(o => o.id)]);
  const addNeeds = h('button', { class: 'btn small', onclick: e => pickTask(e.currentTarget, 'Needs first…', exclude, async x => apply(await Tasks.addDependency(t.id, x.id))) }, icon('plus'), 'Needs first');
  const addUnlocks = h('button', { class: 'btn small', onclick: e => pickTask(e.currentTarget, 'Unlocks…', exclude, async x => {
    await Tasks.addDependency(x.id, t.id);
    apply(await Tasks.get(t.id));
  }) }, icon('plus'), 'Unlocks');

  return h('div', { class: 'card' },
    h('div', { class: 'card-title' }, 'Sequence', seq ? h('span', { class: 'act' }, `step ${seq.step} of ${seq.of}`) : null),
    h('div', { class: 'card-body' },
      steps,
      t.needs.length ? h('div', { class: 'seq-label' }, 'Needs first') : null, ...rel(t.needs, o => Tasks.removeDependency(t.id, o.id)),
      t.unlocks.length ? h('div', { class: 'seq-label' }, 'Unlocks') : null, ...rel(t.unlocks, async o => { await Tasks.removeDependency(o.id, t.id); return Tasks.get(t.id); }),
      !chain.length ? h('div', { class: 'status-line' }, 'Chain tasks in order: say what has to be done first and what this unlocks. Steps are numbered 1, 2, 3… on the brain, with impulses flowing toward the goal.') : null,
      h('div', { class: 'seq-actions' }, addNeeds, addUnlocks)));
}

function pickTask(anchor, title, exclude, onPick) {
  const r = anchor.getBoundingClientRect();
  const search = h('input', { class: 'input', placeholder: 'Find a task…' });
  const listEl = h('div');
  const fill = () => {
    const q = search.value.toLowerCase();
    const opts = store.state.tasks.filter(x => !exclude.has(x.id) && x.title.toLowerCase().includes(q))
      .sort((a, b) => (a.status === 'done') - (b.status === 'done')).slice(0, 12);
    listEl.replaceChildren(...(opts.length ? opts.map(x => h('button', { class: 'opt', onclick: async () => {
      closePopover();
      try { await onPick(x); } catch (e) { toastError(e); }
    } }, h('span', { class: 't' }, x.title), h('span', { class: 's' }, x.status))) : [h('div', { class: 'none' }, 'No matching tasks')]));
  };
  search.addEventListener('input', fill);
  fill();
  popover({ x: r.left + r.width / 2, y: r.bottom }, [h('h4', {}, title), h('div', { style: { padding: '0 6px 6px' } }, search), listEl]);
  search.focus();
}

// ---------- links ----------
// Linking means "this task, then that one": the linked task becomes the next step (1 → 2), shown in Sequence.
function linksCard(t) {
  const items = t.links.filter(l => l.kind === 'auto').map(l => h('div', { class: 'link-item', onclick: () => open(l.id) },
    icon('link'), h('span', { class: 'lt' }, l.title), h('span', { class: 'kind' }, 'related')));
  const addBtn = h('button', { class: 'btn small act', title: 'Link a task that comes after this one', onclick: e => linkPicker(e.currentTarget) }, icon('plus'), 'Link next task');
  return h('div', { class: 'card' },
    h('div', { class: 'card-title' }, 'Connected synapses', addBtn),
    h('div', { class: 'card-body' },
      h('div', { class: 'status-line', style: { marginBottom: items.length ? '6px' : 0 } },
        'Linking a task makes it the next step after this one: they become 1 → 2, with impulses flowing toward the next task on the brain. Related tasks below connect automatically by shared words and tags.'),
      items));
}

function linkPicker(anchor) {
  const r = anchor.getBoundingClientRect();
  const search = h('input', { class: 'input', placeholder: 'Find a task…' });
  const listEl = h('div');
  const fill = () => {
    const q = search.value.toLowerCase();
    const linked = new Set(task.links.map(l => l.id));
    const opts = store.state.tasks.filter(x => x.id !== task.id && !linked.has(x.id) && x.status !== 'done' && x.title.toLowerCase().includes(q)).slice(0, 12);
    listEl.replaceChildren(...(opts.length ? opts.map(x => h('button', { class: 'opt', onclick: async () => {
      closePopover();
      try {
        await Tasks.addDependency(x.id, task.id);
        apply(await Tasks.get(task.id));
        toast(`“${x.title}” is now the next step after “${task.title}”`);
      } catch (e) { toastError(e); }
    } }, h('span', { class: 't' }, x.title), h('span', { class: 's' }, x.status))) : [h('div', { class: 'none' }, 'No matching tasks')]));
  };
  search.addEventListener('input', fill);
  fill();
  popover({ x: r.left + r.width / 2 - 100, y: r.bottom }, [h('h4', {}, 'Link to…'), h('div', { style: { padding: '0 6px 6px' } }, search), listEl]);
  search.focus();
}

// ---------- insights ----------
function insightsCard(t) {
  const btn = h('button', { class: 'btn small claude act' }, icon('spark'), 'Ask Claude');
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    btn.lastChild.textContent = 'Thinking…';
    try {
      await api('/api/claude/insight', { method: 'POST', body: { task_id: t.id } });
      if (task?.id === t.id) await refreshIfOpen();
    } catch (e) {
      toastError(e);
      if (e.status === 400) hooks.openSettings?.();
    } finally { btn.disabled = false; btn.lastChild.textContent = 'Ask Claude'; }
  });
  return h('div', { class: 'card' },
    h('div', { class: 'card-title' }, 'Insights', btn),
    h('div', { class: 'card-body' },
      t.insights.length ? t.insights.slice(0, 3).map(i => h('div', { class: 'ai-insight' }, h('div', { html: renderMarkdown(i.text) }), h('div', { class: 'when' }, fmtDateTime(i.created_at))))
        : h('div', { class: 'status-line' }, 'As this synapse grows with notes, steps and files, Claude can suggest next steps, risks and connections.')));
}

function activityCard(t) {
  return h('details', { class: 'card' },
    h('summary', { class: 'card-title' }, 'Activity', h('span', { class: 'act' }, String(t.activity.length))),
    h('div', { class: 'card-body' }, h('ul', { class: 'activity' }, t.activity.map(a => h('li', {}, h('time', {}, fmtDateTime(a.created_at)), h('span', {}, a.text))))));
}
