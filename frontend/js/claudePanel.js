// Claude drawer: chat with tools over your memory, plus AI delegation of synapses.
import { api } from './api.js';
import { mutate, store } from './store.js';
import { esc, h, icon, renderMarkdown, toast, toastError } from './ui.js';

const panel = () => document.getElementById('claude-panel');
const history = [];   // {role, content, actions?}
let busy = false;
let proposal = null;
let hooks = {};
let chatEl, input;

const SUGGESTIONS = [
  "What's most pressing right now?",
  'Plan my week',
  'Which backlog tasks could I drop or delegate?',
  'Break my top synapse into steps',
];

export function initClaudePanel(h_) { hooks = h_; build(); }

export const isOpen = () => panel().classList.contains('open');
export function open() { hooks.onOpen?.(); panel().classList.add('open'); renderChat(); setTimeout(() => input?.focus(), 200); }
export function close() { panel().classList.remove('open'); }
export function toggle() { isOpen() ? close() : open(); }

function build() {
  chatEl = h('div', { class: 'chat' });
  input = h('textarea', { class: 'input', placeholder: 'Ask about your tasks, or tell Claude what to add…', 'aria-label': 'Message Claude' });
  input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input.value); } });
  const sendBtn = h('button', { class: 'btn primary', title: 'Send', onclick: () => send(input.value) }, icon('send'));
  panel().replaceChildren(
    h('div', { class: 'drawer-head' },
      icon('spark'), h('h2', {}, 'Claude'),
      h('button', { class: 'btn small', title: 'Generate a daily briefing', onclick: briefing }, 'Briefing'),
      h('button', { class: 'btn small', title: 'Start a new conversation', onclick: () => { history.length = 0; proposal = null; renderChat(); } }, 'New chat'),
      h('button', { class: 'btn icon ghost', title: 'Close', onclick: close }, icon('x'))),
    h('div', { class: 'drawer-body' }, chatEl),
    h('div', { class: 'composer' }, input, sendBtn));
  panel().querySelector('.drawer-head svg').style.color = 'var(--claude)';
}

function renderChat() {
  const hasKey = store.state.settings?.has_anthropic_api_key;
  chatEl.replaceChildren();
  if (!hasKey) {
    chatEl.append(h('div', { class: 'setup-card' },
      h('strong', {}, 'Connect Claude'), h('br'),
      'Add your Anthropic API key in Settings to ask questions about your tasks, get reminders and insights, and let Claude delegate your synapses. The key stays on this computer.',
      h('div', { style: { marginTop: '10px' } }, h('button', { class: 'btn primary', onclick: () => hooks.openSettings?.() }, 'Open Settings'))));
  }
  if (!history.length && !proposal) {
    chatEl.append(h('div', { class: 'chat-empty' },
      icon('spark', 'spark'),
      h('div', {}, 'Ask anything about your memory. Claude can read your tasks, add new ones, set reminders and move work on or off the brain.'),
      h('div', { class: 'suggestions' }, SUGGESTIONS.map(q => h('button', { onclick: () => send(q) }, q)))));
  }
  for (const m of history) {
    const el = h('div', { class: `msg ${m.role}` });
    if (m.role === 'assistant') el.innerHTML = renderMarkdown(m.content);
    else el.textContent = m.content;
    if (m.actions?.length) el.append(h('div', { class: 'actions', html: m.actions.map(a => `✓ ${esc(a)}`).join('<br>') }));
    chatEl.append(el);
  }
  if (proposal) chatEl.append(proposalCard());
  if (busy) chatEl.append(h('div', { class: 'msg assistant thinking' }, busy === true ? 'Thinking' : busy));
  const body = chatEl.parentElement;
  requestAnimationFrame(() => { body.scrollTop = body.scrollHeight; });
}

async function send(text) {
  text = (text || '').trim();
  if (!text || busy) return;
  input.value = '';
  history.push({ role: 'user', content: text });
  busy = true;
  renderChat();
  try {
    const res = await api('/api/claude/chat', { method: 'POST', body: { messages: history.map(({ role, content }) => ({ role, content })) } });
    history.push({ role: 'assistant', content: res.reply, actions: res.actions });
    if (res.actions?.length) store.refresh();
  } catch (e) {
    history.pop();
    input.value = text;
    toastError(e);
  } finally {
    busy = false;
    renderChat();
  }
}

async function briefing() {
  if (busy) return;
  busy = 'Writing your briefing';
  renderChat();
  try {
    const res = await api('/api/claude/insight', { method: 'POST', body: { task_id: null } });
    history.push({ role: 'assistant', content: res.text });
    hooks.onBriefing?.();
  } catch (e) { toastError(e); } finally { busy = false; renderChat(); }
}

// ---------- delegation ----------
export async function delegate() {
  open();
  if (busy) return;
  busy = 'Claude is reviewing your brain and queue';
  proposal = null;
  renderChat();
  try {
    proposal = await api('/api/claude/delegate', { method: 'POST' });
  } catch (e) { toastError(e); } finally { busy = false; renderChat(); }
}

function proposalCard() {
  const p = proposal;
  const rows = [...p.assignments].sort((a, b) => (a.slot_index ?? 99) - (b.slot_index ?? 99)).map(a => {
    const changed = a.from_status !== (a.slot_index == null ? 'backlog' : 'active') || (a.slot_index != null && a.from_slot !== a.slot_index);
    return h('tr', {},
      h('td', {}, h('div', {}, a.title), a.reason ? h('div', { class: 'why' }, a.reason) : null),
      h('td', { class: `to ${a.slot_index == null ? 'backlog' : ''}` }, a.slot_index == null ? 'Queue' : `Synapse ${a.slot_index + 1}`,
        changed ? h('div', { class: 'why changed' }, a.from_status === 'active' ? `was synapse ${a.from_slot + 1}` : `was ${a.from_status}`) : null));
  });
  return h('div', { class: 'proposal' },
    h('h4', {}, 'Proposed delegation'),
    h('div', { class: 'summary', html: renderMarkdown(p.summary) }),
    h('table', {}, h('tbody', {}, rows)),
    h('div', { class: 'btns' },
      h('button', { class: 'btn', onclick: () => { proposal = null; renderChat(); } }, 'Discard'),
      h('button', { class: 'btn primary', onclick: applyProposal }, 'Apply to brain')));
}

async function applyProposal() {
  try {
    await mutate(api('/api/claude/delegate/apply', { method: 'POST', body: { assignments: proposal.assignments.map(({ task_id, slot_index, reason }) => ({ task_id, slot_index, reason })) } }));
    proposal = null;
    history.push({ role: 'assistant', content: 'Applied. Your synapses are now arranged as proposed — I pinned them so a re-think keeps them in place.' });
    renderChat();
    toast('Delegation applied to the brain');
  } catch (e) { toastError(e); }
}
