// App bootstrap: wires the brain, lists, panels and live updates together.
import { api, Tasks } from './api.js';
import { Brain, slotColor } from './brain3d.js';
import * as claude from './claudePanel.js';
import { initDashboard, renderDashboard } from './dashboard.js';
import { dropOnSlot, initDragDrop, startSynapseDrag } from './dragdrop.js';
import { initLists, renderListPane, renderQueue, renderRail } from './lists.js';
import { openSettings, syncPlanner } from './settings.js';
import { connectEvents, mutate, store } from './store.js';
import { inboxPanel, initInbox, loadInbox, onInboxChange } from './inbox.js';
import { quickLinkButtons } from './quicklinks.js';
import { templateMeta, Templates } from './templates.js';
import * as panel from './taskPanel.js';
import { applyTheme, currentTheme, onThemeChange } from './themes.js';
import { addDays, closePopover, debounce, fmtDate, h, icon, modal, popover, REGION_VAR, renderMarkdown, toast, toastError, todayISO } from './ui.js';

// ?wallpaper: a brain-only view for a live desktop wallpaper (Lively). The wallpaper only gets mouse input, so quick
//   actions happen in place and anything that needs typing opens a pop-up window.
// ?popup=<id>: one of those pop-up windows: just the task editor (or the new-task form), no brain.
const params = new URLSearchParams(location.search);
const WALLPAPER = params.has('wallpaper');
const SCREEN = params.get('screen'); // set when Memory itself hosts the desktop wallpaper (one window per screen)
const POPUP = params.get('popup');
if (WALLPAPER) document.body.classList.add('wallpaper');
if (WALLPAPER && SCREEN != null) document.title = `Memory Wallpaper ${SCREEN}`; // how the host finds this window
if (POPUP) document.body.classList.add('popup-window');
const openWindow = body => api('/api/open', { method: 'POST', body }).catch(toastError);
const openTaskWindow = id => openWindow({ task_id: id, window: 'popup' });
const openNewTaskWindow = () => openWindow({ new: true, window: 'popup' });

// Windows opened from the wallpaper (?popup or ?win) tell the server they're open, so the wallpaper can hold the
// brain still meanwhile. Heartbeats cover a window that dies without saying goodbye.
const WIN = POPUP || params.get('win');
if (WIN) {
  const beat = () => fetch(`/api/windows/${WIN}/alive`, { method: 'POST' }).catch(() => {});
  beat();
  setInterval(beat, 10000);
  addEventListener('pagehide', () => navigator.sendBeacon(`/api/windows/${WIN}/closed`));
}

// Colour theme: start from the last one used (the server's setting arrives with the first state refresh).
try { applyTheme(JSON.parse(localStorage.getItem('memoryTheme'))?.id); } catch { applyTheme('blue'); }

// ---------- brain ----------
// Pop-up windows have no brain; a do-nothing stand-in keeps the shared wiring below simple.
const brain = POPUP ? new Proxy({}, { get: () => () => null }) : new Brain(document.getElementById('brain-canvas'), document.getElementById('brain-labels'), {
  onSelect: (id, ev) => (WALLPAPER ? quickCard(id, ev) : panel.open(id, { x: ev.clientX, y: ev.clientY })),
  onEmptySlot: (index, ev) => slotPicker(index, ev),
  onSynapseDragStart: (task, ev) => startSynapseDrag(task, ev),
  onSynapseMoved: (index, pos) => saveSlotPositions({ ...(store.state.settings.slot_positions || {}), [index]: pos }),
}, WALLPAPER ? { fps: [30, 15], maxPixelRatio: 1, pixelBudget: 1.6e6 } : {});
window.memoryBrain = brain; // handy for debugging in devtools

function slotPicker(index, ev) {
  const candidates = [...store.basket, ...store.backlog].slice(0, 14);
  const items = candidates.length
    ? candidates.map(t => h('button', { class: 'opt', onclick: () => { closePopover(); dropOnSlot(t.id, index); } },
        h('i', { class: 'region-dot', style: `--c:${REGION_VAR[t.region]}` }), h('span', { class: 't' }, t.title), h('span', { class: 's' }, t.status === 'basket' ? 'basket' : 'queue')))
    : [h('div', { class: 'none' }, WALLPAPER ? 'Basket and queue are empty.' : 'Basket and queue are empty. Add a task in the list on the right.')];
  if (WALLPAPER) items.push(h('button', { class: 'opt', onclick: () => { closePopover(); openNewTaskWindow(); } }, h('span', { class: 't' }, '+ New task…')));
  const side = store.state.slots.find(s => s.index === index)?.side;
  const where = side < 0 ? ' · logical side' : side > 0 ? ' · creative side' : '';
  popover({ x: ev.clientX, y: ev.clientY }, [h('h4', {}, `Fill synapse ${index + 1}${where}`), ...items]);
}

// ---------- wallpaper quick card: mouse-only task management right on the desktop ----------
const notesText = html => new DOMParser().parseFromString(html || '', 'text/html').body.textContent.replace(/\s+/g, ' ').trim();

async function quickCard(id, ev) {
  let t;
  try { t = await Tasks.get(id); } catch (e) { toastError(e); return; }
  const act = (label, fn, cls = '') => h('button', {
    class: `btn small ${cls}`, onclick: async () => { closePopover(); try { await fn(); } catch (e) { toastError(e); } },
  }, label);
  const steps = t.checklist.slice(0, 6).map(c => h('button', {
    class: `opt qc-step ${c.done ? 'done' : ''}`,
    onclick: async () => { try { await mutate(Tasks.updateStep(c.id, { done: !c.done })); quickCard(id, ev); } catch (e) { toastError(e); } },
  }, h('span', { class: `check ${c.done ? 'on' : ''}` }, icon('check')), h('span', { class: 't' }, c.text)));
  const notes = notesText(t.notes_html);
  const meta = [`${t.priority[0].toUpperCase()}${t.priority.slice(1)} priority`, t.due_at ? `due ${fmtDate(t.due_at)}` : null,
    t.checklist_total ? `${t.checklist_done}/${t.checklist_total} steps` : null, t.pinned ? 'pinned' : null].filter(Boolean).join(' · ');
  popover({ x: ev.clientX, y: ev.clientY }, [
    h('h4', { class: 'qc-title' }, h('i', { class: 'region-dot', style: `--c:${REGION_VAR[t.region]}` }), t.title),
    h('div', { class: 'qc-meta' }, meta),
    ...steps,
    t.checklist.length > 6 ? h('div', { class: 'none' }, `+${t.checklist.length - 6} more steps`) : null,
    notes ? h('div', { class: 'qc-notes', title: 'Open to edit notes', onclick: () => { closePopover(); openTaskWindow(id); } }, notes.length > 180 ? `${notes.slice(0, 180)}…` : notes) : null,
    h('div', { class: 'qc-actions' },
      act('✓ Complete', async () => {
        await mutate(Tasks.update(id, { status: 'done' }));
        toast(`Completed “${t.title}”`, { action: 'Undo', onAction: () => mutate(Tasks.update(id, { status: 'backlog' })) });
      }),
      act(t.pinned ? 'Unpin' : 'Pin', () => mutate(Tasks.update(id, { pinned: !t.pinned }))),
      act('To queue', () => mutate(Tasks.unplace(id, 'backlog'))),
      act('Open ↗', () => openTaskWindow(id), 'primary')),
  ].filter(Boolean));
}

// ---------- wallpaper: computer stats (top-left) and quick links (bottom-left) ----------
const fmtBytes = (b, digits = 1) => {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (b >= 1024 && i < units.length - 1) { b /= 1024; i++; }
  return `${b.toFixed(i >= 3 ? digits : 0)} ${units[i]}`;
};
const fmtUptime = s => { const d = Math.floor(s / 86400), hr = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60); return d ? `${d}d ${hr}h` : `${hr}h ${m}m`; };

function renderSystem({ specs: s, usage: u }) {
  const el = document.getElementById('wp-sys');
  const meter = (label, pct, text) => [
    h('span', { class: 'k' }, label), h('span', { class: 'v' }, text),
    h('span', { class: `bar ${pct >= 85 ? 'hot' : ''}` }, h('i', { style: { width: `${Math.max(0, Math.min(100, pct || 0))}%` } }))];
  const live = u.at ? [
    ...meter('CPU', u.cpu, `${Math.round(u.cpu)}%`),
    ...meter('RAM', 100 * u.ram_used / u.ram_total, `${Math.round(100 * u.ram_used / u.ram_total)}%  ${fmtBytes(u.ram_used)} / ${fmtBytes(u.ram_total)}`),
    ...(u.gpu == null ? [] : meter('GPU', u.gpu, `${Math.round(u.gpu)}%`)),
    ...meter('Disk', 100 * u.disk_used / u.disk_total, `${Math.round(100 * u.disk_used / u.disk_total)}%  ${fmtBytes(u.disk_free ?? (u.disk_total - u.disk_used))} free · ${Math.round(u.disk_active)}% busy`),
    h('span', { class: 'k' }, 'Net'), h('span', { class: 'v wide' }, `↓ ${fmtBytes(u.net_in)}/s   ↑ ${fmtBytes(u.net_out)}/s`),
    h('span', { class: 'k' }, 'Up'), h('span', { class: 'v wide' }, `${fmtUptime(u.uptime)}${u.battery ? ` · battery ${u.battery.percent}%${u.battery.charging ? ' charging' : ''}` : ''}`),
  ] : [h('span', { class: 'v wide' }, 'Reading sensors…')];
  el.replaceChildren(
    h('div', { class: 'host' }, s.host),
    h('div', {}, s.os),
    h('div', {}, `${s.cpu} · ${s.threads} threads`),
    h('div', {}, [s.gpus?.join(', '), s.ram_total ? `${fmtBytes(s.ram_total, 0)} RAM` : null, s.disk_total ? `${fmtBytes(s.disk_total, 0)} ${s.disk}` : null].filter(Boolean).join(' · ')),
    h('div', { class: 'grid' }, live));
}

async function pollSystem() {
  if (document.visibilityState === 'visible') {
    try { renderSystem(await api('/api/system')); } catch { /* server restarting */ }
  }
  setTimeout(pollSystem, 3000);
}

function renderQuickLinks() {
  const el = document.getElementById('wp-links');
  const buttons = quickLinkButtons('ql');
  el.replaceChildren(
    h('div', { class: 'wp-links-head' }, h('span', {}, 'Quick links'),
      h('button', { class: 'edit', title: 'Edit quick links', onclick: () => openWindow({ window: 'app', view: 'settings' }) }, 'Edit')),
    buttons.length ? h('div', { class: 'grid' }, buttons) : h('div', { class: 'none' }, 'Add links in Settings → Quick links.'));
}

const renderWallpaperInbox = () => document.getElementById('wp-inbox')?.replaceChildren(...inboxPanel());

if (WALLPAPER) {
  const view = document.getElementById('view-brain');
  view.append(h('div', { class: 'wp-sys', id: 'wp-sys', 'aria-hidden': 'true' }), h('div', { class: 'wp-links', id: 'wp-links' }),
    h('div', { class: 'wp-links wp-inbox', id: 'wp-inbox' }));
  pollSystem();
  setInterval(() => loadInbox(true), 5 * 60_000);
}
initInbox({
  openTask: id => (WALLPAPER ? openTaskWindow(id) : panel.open(id)),
  openSettings: () => (WALLPAPER ? openWindow({ window: 'app', view: 'settings' }) : openSettings()),
});
onInboxChange(() => (WALLPAPER ? renderWallpaperInbox() : renderListPane()));

// ---------- first run + updates (full app only) ----------
function showWelcome() {
  const step = (n, title, text, button) => h('div', { class: 'welcome-step' }, h('span', { class: 'n' }, String(n)),
    h('div', {}, h('div', { class: 'wt' }, title), h('div', { class: 'help' }, text), button || null));
  const done = () => api('/api/settings', { method: 'PUT', body: { welcomed: true } }).catch(() => {});
  modal({
    title: 'Welcome to Memory', wide: true, onClose: done,
    body: h('div', { class: 'welcome' },
      h('p', {}, 'Your tasks live on a brain: the most pressing ones sit on its synapses, logical work on the left, creative on the right, and everything else waits in the queue. Memory runs quietly in the background and starts with Windows.'),
      step(1, 'Capture tasks', 'Type in the box on the right (or pick a template), then drag tasks onto synapses. Click a synapse for notes, steps, files and dates.'),
      step(2, 'Connect Claude (optional)', 'Add an Anthropic API key to chat about your tasks, let AI sort your synapses, and turn emails into tasks.',
        h('button', { class: 'btn small', onclick: () => { document.querySelector('.modal-backdrop')?.remove(); done(); openSettings(); } }, 'Open Settings')),
      step(3, 'Connect Microsoft (optional)', 'Sign in to pull Planner tasks into your basket and see your Outlook inbox. Needs an Azure app registration; Settings and the README explain how.'),
      step(4, 'Put the brain on your desktop (optional)', 'Memory can show the brain as your desktop wallpaper, behind your icons, on every screen. Click synapses right on the desktop.',
        h('button', { class: 'btn small', onclick: async e => {
          e.currentTarget.disabled = true;
          try { await api('/api/settings', { method: 'PUT', body: { desktop_wallpaper: true } }); e.currentTarget.textContent = 'Wallpaper on'; } catch (err) { toastError(err); }
        } }, 'Turn on desktop wallpaper'))),
    actions: [{ label: 'Get started', kind: 'primary' }],
  });
}

async function checkForUpdate() {
  let v;
  try { v = await api('/api/version'); } catch { return; }
  if (!v.update_available || sessionStorage.getItem('memoryUpdateShown') === v.latest.version) return;
  sessionStorage.setItem('memoryUpdateShown', v.latest.version);
  toast(`Memory ${v.latest.version} is available (you have ${v.version}).`, {
    action: 'Download', onAction: () => window.open(v.latest.download || v.latest.url, '_blank'), timeout: 20000,
  });
}

// ---------- pop-up window: new-task form ----------
function newTaskForm() {
  document.title = 'New task · Memory';
  const input = h('input', { class: 'input', placeholder: 'What needs doing?', maxlength: 500, 'aria-label': 'New task' });
  const screen = h('div', { class: 'new-task-screen' }, h('div', { class: 'new-task-card' },
    h('h2', {}, 'New task'), input,
    h('div', { class: 'help' }, 'Enter adds it to your basket and opens it for steps, notes, files and dates. Esc closes.')));
  const chips = h('div', { class: 'tpl-chips' });
  Templates.list().then(list => chips.replaceChildren(...(list.length ? [h('div', { class: 'help' }, 'Or start from a template:')] : []),
    ...list.map(t => h('button', { class: 'tpl-chip', title: templateMeta(t), onclick: async () => {
      try { const task = await mutate(Templates.use(t.id, input.value.trim())); screen.remove(); panel.open(task.id); } catch (err) { toastError(err); }
    } }, icon('template'), t.name)))).catch(() => {});
  screen.firstChild.append(chips);
  input.addEventListener('keydown', async e => {
    if (e.key === 'Escape') window.close();
    if (e.key !== 'Enter' || !input.value.trim()) return;
    try {
      const t = await mutate(Tasks.create({ title: input.value.trim() }));
      screen.remove();
      panel.open(t.id);
    } catch (err) { toastError(err); }
  });
  document.body.append(screen);
  input.focus();
}

// Arrange mode: drag synapses around the brain; positions are saved in settings so the wallpaper uses them too.
async function saveSlotPositions(positions) {
  try { await mutate(api('/api/settings', { method: 'PUT', body: { slot_positions: positions } })); } catch (e) { toastError(e); }
}

function setArranging(on) {
  brain.setArrange(on);
  document.body.classList.toggle('arranging', on);
  document.getElementById('btn-arrange').classList.toggle('primary', on);
  document.getElementById('btn-arrange').textContent = on ? 'Done arranging' : 'Arrange';
  document.getElementById('arrange-bar')?.remove();
  if (!on) return;
  document.getElementById('view-brain').append(h('div', { class: 'arrange-bar', id: 'arrange-bar' },
    icon('move'), h('span', {}, 'Drag any synapse to a new spot on its hemisphere. Drag empty space to turn the brain.'),
    h('button', { class: 'btn small', onclick: () => saveSlotPositions({}) }, 'Reset layout'),
    h('button', { class: 'btn small primary', onclick: () => setArranging(false) }, 'Done')));
}

let slotSignature = '';
function renderBrain() {
  const { slots, tasks, links } = store.state;
  const custom = store.state.settings?.slot_positions || {};
  const sig = slots.map(s => `${s.index}:${s.side}:${s.frontness}`).join('|') + JSON.stringify(custom);
  if (sig !== slotSignature) { brain.setSlots(slots, custom); slotSignature = sig; }
  brain.setTasks(tasks, links, store.state.dependencies || []);

  const used = store.active.length;
  document.getElementById('ram-count').textContent = `${used} / ${slots.length}`;
  const bar = document.getElementById('ram-bar');
  bar.replaceChildren(...slots.map(s => {
    const t = tasks.find(x => x.status === 'active' && x.slot_index === s.index);
    return h('i', { class: t ? 'on' : '', style: t ? `--c:#${slotColor(s.side, t.region).getHexString()}` : null, title: t ? `${s.index + 1}. ${t.title}` : `${s.index + 1}. empty` });
  }));
  const basketCount = store.basket.length;
  document.getElementById('basket-pill').textContent = basketCount;
  document.getElementById('btn-sort').disabled = !basketCount;
}

// ---------- insight card ----------
let insightsCollapsed = window.innerWidth < 1600;
const renderInsights = debounce(async () => {
  const card = document.getElementById('insight-card');
  let data;
  try { data = await api('/api/insights'); } catch { return; }
  const items = data.computed.slice(0, 5);
  const briefingBtn = h('button', { class: 'btn small claude', title: 'Ask Claude for a daily briefing' }, 'Briefing');
  briefingBtn.addEventListener('click', async e => {
    e.stopPropagation();
    briefingBtn.disabled = true;
    briefingBtn.textContent = 'Thinking…';
    try { await api('/api/claude/insight', { method: 'POST', body: { task_id: null } }); renderInsights(); }
    catch (err) { toastError(err); if (err.status === 400) openSettings(); }
    finally { briefingBtn.disabled = false; briefingBtn.textContent = 'Briefing'; }
  });
  const todays = data.briefing && new Date(data.briefing.created_at).toDateString() === new Date().toDateString();
  card.classList.toggle('collapsed', insightsCollapsed);
  card.replaceChildren(...[
    h('h3', { style: { cursor: 'pointer' }, onclick: () => { insightsCollapsed = !insightsCollapsed; card.classList.toggle('collapsed', insightsCollapsed); } },
      insightsCollapsed ? '▸' : '▾', ` Insights${items.length ? ` (${items.length})` : ''}`, briefingBtn),
    ...items.map(i => h('div', { class: `ins ${i.severity}` }, i.text)),
    todays ? h('div', { class: 'briefing', html: renderMarkdown(data.briefing.text) }) : null,
    !items.length && !todays ? h('div', { class: 'ins' }, 'Your memory is calm. Capture a task to get started.') : null,
  ].filter(Boolean));
}, 400);

// ---------- wallpaper summary ----------
let windowsOpen = 0;
function lockForWindows(n) {
  n = n || 0;
  if (n === windowsOpen) return;
  windowsOpen = n;
  brain.setLocked(n > 0);
  brain.setPaused('windows', n > 0); // held still and mostly covered: no need to keep drawing
  if (n > 0) closePopover();
  renderWallpaperHud();
}
if (WALLPAPER) store.onEvent('windows', w => lockForWindows(w.open));
// built-in wallpaper: stop drawing while a maximised or full-screen window covers this screen
if (WALLPAPER && SCREEN != null) store.onEvent('wallpaper', w => brain.setPaused('covered', (w.covered || []).includes(Number(SCREEN))));

function renderWallpaperHud() {
  const ram = document.getElementById('ram');
  let line = document.getElementById('wp-line');
  if (!line) {
    line = h('div', { class: 'wp-line', id: 'wp-line' });
    ram.append(line, h('div', { class: 'wp-actions' },
      h('button', { class: 'btn small primary', onclick: openNewTaskWindow }, '+ New task'),
      h('button', { class: 'btn small', onclick: () => openWindow({ window: 'app' }) }, 'Open Memory')));
  }
  const today = todayISO();
  const weekEnd = addDays(today, 7);
  const open = store.state.tasks.filter(t => t.status !== 'done' && t.due_at);
  const overdue = open.filter(t => t.due_at.slice(0, 10) < today).length;
  const soon = open.filter(t => t.due_at.slice(0, 10) >= today && t.due_at.slice(0, 10) <= weekEnd).length;
  line.replaceChildren(...[
    windowsOpen ? h('div', { class: 'wp-lock' }, 'Brain held still while a Memory window is open') : null,
    overdue ? h('span', { class: 'bad' }, `${overdue} overdue`) : null,
    overdue && soon ? ' · ' : null,
    soon ? `${soon} due this week` : null,
    !overdue && !soon ? 'Nothing due this week' : null,
  ].filter(Boolean));
}

// ---------- render loop on state changes ----------
onThemeChange(() => {
  brain.setTheme();
  if (store.view === 'dashboard') renderDashboard();
});

let serverTheme = null; // follow the server only when its value changes, so a refresh in flight can't undo a local pick
store.on(() => {
  const theme = store.state.settings?.theme;
  if (theme && theme !== serverTheme) { serverTheme = theme; if (theme !== currentTheme().id) applyTheme(theme); }
  if (POPUP) { panel.refreshIfOpen(); return; }
  if (WALLPAPER) { renderBrain(); renderWallpaperHud(); renderQuickLinks(); renderWallpaperInbox(); lockForWindows(store.state.windows_open); return; }
  renderRail();
  renderListPane();
  renderQueue();
  renderBrain();
  renderInsights();
  if (store.view === 'dashboard') renderDashboard();
  panel.refreshIfOpen();
});

// ---------- wiring ----------
initLists({
  openTask: id => panel.open(id),
  openSettings,
  onCreated: t => { if (store.list === 'basket') toast(`Added “${t.title}” to the basket — drag it onto a synapse`); },
  onCompleted: t => toast(`Completed “${t.title}”`, { action: 'Undo', onAction: () => mutate(Tasks.update(t.id, { status: 'backlog' })) }),
});
initDragDrop(brain);
initDashboard({ openTask: id => panel.open(id) });
panel.initTaskPanel({
  onOpen: id => {
    claude.close(); renderListPane(); brain.setPaused('popup', true);
    history.replaceState(null, '', `#task=${id}`); // deep link: reload or bookmark reopens this task
  },
  onClose: () => {
    renderListPane(); brain.setPaused('popup', false);
    history.replaceState(null, '', location.pathname + location.search);
    if (POPUP) window.close();
  },
  onRender: t => { if (POPUP) document.title = `${t.title} · Memory`; },
  onPlaced: id => brain.focusTask(id),
  onCompleted: t => toast(`Completed “${t.title}”`),
  openSettings,
});
claude.initClaudePanel({ onOpen: () => panel.isOpen() && panel.close(), openSettings, onBriefing: renderInsights });

document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => {
  store.view = tab.dataset.view;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t === tab));
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === `view-${store.view}`));
  brain.setPaused('view', store.view !== 'brain');
  if (store.view === 'dashboard') renderDashboard();
  else brain.resize();
}));

const search = document.getElementById('search');
search.addEventListener('input', debounce(() => { store.search = search.value; renderRail(); renderListPane(); }, 150));
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); search.focus(); }
  if (e.key === 'Escape' && document.activeElement === search) { search.value = ''; store.search = ''; renderRail(); renderListPane(); search.blur(); }
});

document.getElementById('btn-settings').addEventListener('click', openSettings);
document.getElementById('btn-planner').addEventListener('click', syncPlanner);
document.getElementById('btn-claude').addEventListener('click', () => claude.toggle());
document.getElementById('btn-delegate').addEventListener('click', () => claude.delegate());
document.getElementById('btn-reset-view').addEventListener('click', () => brain.resetView());
document.getElementById('btn-arrange').addEventListener('click', () => setArranging(!document.body.classList.contains('arranging')));
document.getElementById('btn-rethink').addEventListener('click', async () => {
  try {
    await mutate(api('/api/rethink', { method: 'POST', body: { include_basket: false } }));
    toast('Re-thought: synapses re-allocated by priority (pinned ones kept)');
  } catch (e) { toastError(e); }
});
document.getElementById('btn-sort').addEventListener('click', async () => {
  const n = store.basket.length;
  try {
    await mutate(api('/api/rethink', { method: 'POST', body: { include_basket: true } }));
    toast(`Sorted ${n} basket task${n === 1 ? '' : 's'} onto the brain and into the queue`);
  } catch (e) { toastError(e); }
});

// ---------- deep links: /#task=ID opens that task ----------
function openFromHash() {
  if (location.hash === '#settings') { history.replaceState(null, '', location.pathname + location.search); openSettings(); return; }
  const m = location.hash.match(/^#task=(\d+)$/);
  if (m && Number(m[1]) !== panel.currentId()) panel.open(Number(m[1]));
}
if (!WALLPAPER) window.addEventListener('hashchange', openFromHash);

// ---------- live events ----------
// Reminders: desktop/email notifications come from the server (per task); open windows also show an in-app toast.
if (!POPUP) store.onEvent('reminder', r => {
  toast(r.text, { type: 'reminder', action: 'Open', onAction: () => (WALLPAPER ? openTaskWindow(r.task_id) : panel.open(r.task_id)), timeout: 15000 });
});
// One pop-up at a time: a newer pop-up window closes this one.
if (POPUP) store.onEvent('popup', p => { if (p.pid !== POPUP) window.close(); });
if (!WALLPAPER && !POPUP) store.onEvent('planner', p => {
  if (p.event === 'login') toast(p.ok ? 'Signed in to Microsoft' : `Microsoft sign-in failed: ${p.error}`, { type: p.ok ? 'info' : 'error' });
  else if (p.ok && p.created) toast(`Planner: ${p.created} new task(s) landed in your basket`);
});

store.refresh().then(() => {
  if (POPUP && location.hash === '#new') newTaskForm();
  else if (!WALLPAPER) openFromHash();
  if (!WALLPAPER && !POPUP) {
    if (!store.state.settings.welcomed && !store.state.tasks.length) showWelcome();
    checkForUpdate();
  }
}).catch(toastError);
connectEvents();
