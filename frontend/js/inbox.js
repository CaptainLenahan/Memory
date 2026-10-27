// Outlook inbox (right-hand pane tab, and a compact panel on the desktop wallpaper). "→ Task" has Claude read the
// email and create a basket task with a title, summary, due date, priority and steps; "Suggest" asks Claude which
// emails need action at all.
import { api } from './api.js';
import { mutate } from './store.js';
import { h, icon, toast, toastError } from './ui.js';

const STALE_MS = 60_000;
let cache = { at: 0, messages: [], account: null, error: null, loading: false };
let suggestions = {};
let hooks = {};
const listeners = new Set();

export function initInbox(h_) { hooks = h_; }
export const onInboxChange = fn => listeners.add(fn);
const changed = () => listeners.forEach(fn => fn());

export async function loadInbox(force = false) {
  if (cache.loading || (!force && Date.now() - cache.at < STALE_MS)) return;
  cache.loading = true;
  changed();
  try {
    const r = await api('/api/mail/inbox');
    cache = { at: Date.now(), messages: r.messages, account: r.account, error: null, loading: false };
  } catch (e) {
    cache = { at: Date.now(), messages: [], account: null, error: e, loading: false };
  }
  changed();
}

async function suggest(btn) {
  btn.disabled = true;
  btn.lastChild.textContent = 'Reading…';
  try {
    suggestions = (await api('/api/mail/suggest', { method: 'POST' })).suggestions;
    const n = Object.keys(suggestions).length;
    toast(n ? `Claude found ${n} email${n === 1 ? '' : 's'} that need${n === 1 ? 's' : ''} action` : 'Claude found nothing that needs action');
    changed();
  } catch (e) {
    toastError(e);
    if (e.status === 400) hooks.openSettings?.();
  } finally { btn.disabled = false; btn.lastChild.textContent = 'Suggest'; }
}

async function toTask(m, btn) {
  btn.disabled = true;
  btn.textContent = 'Reading…';
  try {
    const t = await mutate(api(`/api/mail/${encodeURIComponent(m.id)}/task`, { method: 'POST' }));
    m.task_id = t.id;
    const note = t.existing ? 'already a task' : t.ai ? (t.actionable ? 'read by Claude' : 'Claude thinks it needs no action, added anyway') : 'add a Claude key in Settings for smart summaries';
    toast(`“${t.title}” is in your basket (${note})`, { action: 'Open', onAction: () => hooks.openTask?.(t.id) });
    changed();
  } catch (e) {
    toastError(e);
    btn.disabled = false;
    btn.textContent = '→ Task';
  }
}

const when = iso => {
  const d = new Date(iso);
  const today = new Date();
  return d.toDateString() === today.toDateString()
    ? d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
    : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
};

function row(m, compact) {
  const btn = m.task_id
    ? h('button', { class: 'btn small', title: 'Open the task', onclick: () => hooks.openTask?.(m.task_id) }, '✓ Task')
    : h('button', { class: 'btn small primary', title: 'Create a task from this email', onclick: e => toTask(m, e.currentTarget) }, '→ Task');
  return h('div', { class: `mail-row ${m.unread ? 'unread' : ''} ${compact ? 'compact' : ''}` },
    h('div', { class: 'mail-top' },
      h('span', { class: 'from' }, m.important ? '! ' : '', m.from),
      h('span', { class: 'time' }, when(m.received))),
    h('div', { class: 'subject', title: m.subject }, m.subject),
    compact ? null : h('div', { class: 'preview' }, m.preview),
    suggestions[m.id] && !m.task_id ? h('div', { class: 'suggest' }, icon('spark'), suggestions[m.id]) : null,
    h('div', { class: 'mail-actions' }, btn,
      !compact && m.link ? h('a', { class: 'btn small ghost', href: m.link, target: '_blank', rel: 'noopener' }, 'Outlook') : null));
}

// Body of the right-hand pane's Inbox tab.
export function inboxView() {
  loadInbox();
  const head = h('div', { class: 'lp-head' },
    h('h2', {}, icon('mail'), 'Inbox'),
    h('div', { class: 'sub' }, cache.account ? `Outlook · ${cache.account}` : 'Outlook'),
    h('div', { class: 'inbox-tools' },
      h('button', { class: 'btn small', onclick: () => loadInbox(true) }, 'Refresh'),
      h('button', { class: 'btn small claude', title: 'Ask Claude which emails need action', onclick: e => suggest(e.currentTarget) }, icon('spark'), h('span', {}, 'Suggest'))));
  let body;
  if (cache.error) {
    body = h('div', { class: 'lp-empty' }, cache.error.message,
      h('div', { style: { marginTop: '10px' } }, h('button', { class: 'btn small', onclick: () => hooks.openSettings?.() }, 'Open Settings')));
  } else if (!cache.at || (cache.loading && !cache.messages.length)) {
    body = h('div', { class: 'lp-empty' }, 'Loading your inbox…');
  } else if (!cache.messages.length) {
    body = h('div', { class: 'lp-empty' }, 'Your inbox is empty.');
  } else {
    body = h('div', { class: 'lp-list' }, cache.messages.map(m => row(m, false)));
  }
  return [head, body];
}

// Compact panel for the desktop wallpaper (mouse only).
export function inboxPanel() {
  loadInbox();
  const items = cache.messages.slice(0, 6);
  return [
    h('div', { class: 'wp-links-head' }, h('span', {}, 'Inbox'),
      h('button', { class: 'edit', onclick: () => loadInbox(true) }, cache.loading ? '…' : 'Refresh')),
    cache.error ? h('div', { class: 'none' }, 'Connect Outlook in Settings to see email here.')
      : items.length ? h('div', {}, items.map(m => row(m, true))) : h('div', { class: 'none' }, cache.at ? 'Inbox is empty.' : 'Loading…'),
  ];
}
