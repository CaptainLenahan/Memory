// Left rail (To Do-style lists), the right-hand list pane with quick add, and the queue strip under the brain.
import { inboxView } from './inbox.js';
import { quickLinkButtons } from './quicklinks.js';
import { templatePicker } from './templates.js';
import { Tasks } from './api.js';
import { mutate, store } from './store.js';
import { addDays, dueClass, esc, fmtDate, fmtWeek, h, icon, iconHtml, REGION_VAR, toastError, todayISO } from './ui.js';

let handlers = {};
let paneTab = 'tasks'; // right-hand pane: 'tasks' or 'inbox'

function paneTabs() {
  return h('div', { class: 'pane-tabs', role: 'tablist' }, [['tasks', 'check', 'Tasks'], ['inbox', 'mail', 'Inbox']].map(([id, ic, label]) =>
    h('button', { class: `pane-tab ${paneTab === id ? 'active' : ''}`, role: 'tab', 'aria-selected': String(paneTab === id),
      onclick: () => { paneTab = id; renderListPane(); } }, icon(ic), label)));
}
export function initLists(h_) { handlers = h_; }

function lists() {
  const today = todayISO();
  const open = t => t.status !== 'done';
  const base = [
    { id: 'myday', name: 'My Day', icon: 'sun', filter: t => open(t) && t.my_day === today, add: { my_day: today } },
    { id: 'important', name: 'Important', icon: 'star', filter: t => open(t) && t.important, add: { important: true } },
    { id: 'planned', name: 'Planned', icon: 'calendar', filter: t => open(t) && t.due_at, sort: (a, b) => a.due_at.localeCompare(b.due_at), add: { due_at: today }, group: plannedGroup },
    { id: 'all', name: 'All tasks', icon: 'infinity', filter: open },
    'sep',
    { id: 'basket', name: 'Basket', icon: 'basket', filter: t => t.status === 'basket', drop: 'basket', sub: 'New and imported tasks waiting to be placed. Drag one onto the brain.' },
    { id: 'brain', name: 'On the brain', icon: 'brain', filter: t => t.status === 'active', sort: (a, b) => a.slot_index - b.slot_index, sub: 'Tasks holding a synapse right now.' },
    { id: 'backlog', name: 'Backlog queue', icon: 'queue', filter: t => t.status === 'backlog', sort: (a, b) => b.score - a.score, drop: 'backlog', sub: 'Waiting for a free synapse, most pressing first.' },
    { id: 'done', name: 'Completed', icon: 'done', filter: t => t.status === 'done', sort: (a, b) => (b.completed_at || '').localeCompare(a.completed_at || '') },
  ];
  const plans = [...new Set(store.state.tasks.filter(t => t.source === 'planner' && t.plan_name).map(t => t.plan_name))].sort();
  return { base, plans: plans.map(p => ({ id: `plan:${p}`, name: p, icon: 'planner', filter: t => open(t) && t.plan_name === p, sub: 'Synced from Microsoft Planner' })) };
}

function plannedGroup(t) {
  const today = todayISO(), d = t.due_at.slice(0, 10);
  if (d < today) return 'Overdue';
  if (d === today) return 'Today';
  if (d <= addDays(today, 7)) return 'Next 7 days';
  return 'Later';
}

function currentList() {
  const { base, plans } = lists();
  return [...base, ...plans].find(l => l !== 'sep' && l.id === store.list) || base[5];
}

export function renderRail() {
  const rail = document.getElementById('rail');
  const { base, plans } = lists();
  const tasks = store.state.tasks;
  rail.replaceChildren();
  for (const l of base) {
    if (l === 'sep') { rail.append(h('div', { class: 'rail-sep' })); continue; }
    rail.append(railItem(l, tasks.filter(l.filter).length));
  }
  rail.append(h('div', { class: 'rail-sep' }), h('div', { class: 'rail-heading' }, 'Microsoft Planner'));
  if (!plans.length) rail.append(h('div', { class: 'rail-empty' }, 'Connect Planner in Settings to pull your plans in.'));
  for (const l of plans) rail.append(railItem(l, tasks.filter(l.filter).length));
  rail.append(h('div', { class: 'rail-sep' }), h('div', { class: 'rail-heading rail-heading-row' }, 'Quick links',
    h('button', { class: 'rail-edit', title: 'Edit quick links', onclick: () => handlers.openSettings?.() }, 'Edit')));
  rail.append(...quickLinkButtons('rail-item'));
}

function railItem(l, count) {
  const btn = h('button', {
    class: `rail-item ${store.list === l.id && !store.search ? 'active' : ''}`,
    onclick: () => { store.list = l.id; store.search = ''; paneTab = 'tasks'; document.getElementById('search').value = ''; renderRail(); renderListPane(); },
  }, icon(l.icon), h('span', {}, l.name), h('span', { class: 'count' }, count || ''));
  if (l.drop) btn.dataset.drop = l.drop;
  return btn;
}

export function locationLabel(t) {
  if (t.status === 'active') return { text: `Synapse ${t.slot_index + 1}`, cls: 'loc' };
  if (t.status === 'backlog') {
    const rank = store.backlog.findIndex(x => x.id === t.id) + 1;
    return { text: `Queue #${rank}`, cls: '' };
  }
  if (t.status === 'basket') return { text: 'Basket', cls: '' };
  return { text: 'Done', cls: '' };
}

export function taskRow(t) {
  const loc = locationLabel(t);
  const meta = [];
  meta.push(`<span class="${loc.cls}"><i class="region-dot" style="--c:${REGION_VAR[t.region] || REGION_VAR.balanced}"></i>${esc(loc.text)}</span>`);
  if (t.due_at) meta.push(`<span class="${dueClass(t)}">${iconHtml('calendar')}${esc(fmtDate(t.due_at))}</span>`);
  if (t.reminder_at && !t.reminded) meta.push(`<span>${iconHtml('bell')}</span>`);
  if (t.seq) meta.push(`<span class="step-chip ${t.seq.waiting && t.status !== 'done' ? 'waiting' : ''}" title="Step ${t.seq.step} of ${t.seq.of} in its sequence${t.seq.waiting ? ` · waits on ${t.seq.waiting}` : ''}">step ${t.seq.step}/${t.seq.of}</span>`);
  if (t.checklist_total) meta.push(`<span>${t.checklist_done}/${t.checklist_total}</span>`);
  if (t.attachment_count) meta.push(`<span>${iconHtml('clip')}${t.attachment_count}</span>`);
  if (t.status !== 'done' && t.assigned_week) meta.push(`<span class="${t.at_risk ? 'soon' : ''}" title="Estimated completion week">${iconHtml('week')}${esc(fmtWeek(t.assigned_week, store.state.weeks).replace('Week of ', 'wk '))}</span>`);
  if (t.plan_name) meta.push(`<span>${iconHtml('planner')}${esc(t.plan_name)}</span>`);

  const row = h('div', {
    class: `task-row ${t.status === 'done' ? 'done' : ''} ${store.selectedId === t.id ? 'selected' : ''}`,
    draggable: t.status !== 'done' ? 'true' : null, dataset: { taskId: t.id },
    onclick: e => { if (!e.target.closest('button')) handlers.openTask(t.id); },
  },
  h('button', {
    class: `check ${t.status === 'done' ? 'on' : ''}`, title: t.status === 'done' ? 'Mark not done' : 'Complete',
    onclick: () => toggleDone(t),
  }, icon('check')),
  h('div', { class: 'body' }, h('div', { class: 'title' }, t.title), h('div', { class: 'meta', html: meta.join('') })),
  h('button', {
    class: `star ${t.important ? 'on' : ''}`, title: 'Important',
    onclick: () => mutate(Tasks.update(t.id, { important: !t.important })).catch(toastError),
  }, icon('star')));
  return row;
}

export async function toggleDone(t) {
  try {
    await mutate(Tasks.update(t.id, { status: t.status === 'done' ? 'backlog' : 'done' }));
    if (t.status !== 'done') handlers.onCompleted?.(t);
  } catch (e) { toastError(e); }
}

export function renderListPane() {
  const pane = document.getElementById('listpane');
  if (paneTab === 'inbox' && !store.search.trim()) { pane.replaceChildren(paneTabs(), ...inboxView()); return; }
  const q = store.search.trim().toLowerCase();
  let l, tasks;
  if (q) {
    l = { id: 'search', name: `Search`, icon: 'target', sub: `Results for “${store.search}”` };
    tasks = store.state.tasks.filter(t => t.title.toLowerCase().includes(q) || (t.notes_html || '').toLowerCase().includes(q) || t.tags.some(x => x.toLowerCase().includes(q)));
  } else {
    l = currentList();
    tasks = store.state.tasks.filter(l.filter);
  }
  if (l.sort) tasks.sort(l.sort);

  const input = h('input', { placeholder: 'Add a task to your memory', 'aria-label': 'Add a task', maxlength: 500 });
  input.addEventListener('keydown', async e => {
    if (e.key !== 'Enter' || !input.value.trim()) return;
    const title = input.value.trim();
    input.value = '';
    try {
      const t = await mutate(Tasks.create({ title, ...(l.add || {}) }));
      handlers.onCreated?.(t);
    } catch (err) { toastError(err); }
  });
  const sub = l.sub || `${tasks.length} task${tasks.length === 1 ? '' : 's'}`;
  const listEl = h('div', { class: 'lp-list', dataset: l.drop ? { drop: l.drop } : {} });
  if (!tasks.length) {
    listEl.append(h('div', { class: 'lp-empty' }, q ? 'Nothing in memory matches that.' : l.id === 'basket' ? 'Your basket is empty. Type above to capture a task, or sync from Planner.' : 'Nothing here yet.'));
  } else {
    let lastGroup = null;
    for (const t of tasks) {
      if (l.group) {
        const g = l.group(t);
        if (g !== lastGroup) { listEl.append(h('div', { class: 'lp-group' }, g)); lastGroup = g; }
      }
      listEl.append(taskRow(t));
    }
  }
  const fromTemplate = h('button', { class: 'qa-tpl', title: 'New from template', onclick: e => {
    e.preventDefault();
    templatePicker(e.currentTarget, t => handlers.openTask(t.id));
  } }, icon('template'));
  pane.replaceChildren(...[
    paneTabs(),
    h('div', { class: 'lp-head' }, h('h2', {}, icon(l.icon), l.name), h('div', { class: 'sub' }, sub)),
    l.id === 'done' ? null : h('label', { class: 'quick-add' }, icon('plus'), input, fromTemplate),
    listEl,
  ].filter(Boolean));
}

export function renderQueue() {
  const box = document.getElementById('queue-items');
  const queue = store.backlog;
  box.replaceChildren();
  if (!queue.length) {
    box.append(h('span', { class: 'empty' }, 'Queue is empty — overflow from the brain waits here. Drag synapses down to park them.'));
    return;
  }
  queue.slice(0, 30).forEach((t, i) => {
    box.append(h('div', {
      class: 'chip', draggable: 'true', dataset: { taskId: t.id }, title: t.title,
      onclick: () => handlers.openTask(t.id),
    }, h('span', { class: 'rank' }, i + 1), h('i', { class: 'region-dot', style: `--c:${REGION_VAR[t.region]}` }), h('span', { class: 't' }, t.title)));
  });
}
