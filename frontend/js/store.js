// Client-side state: one snapshot of /api/state, refreshed on mutations and server-sent events.
import { api } from './api.js';
import { debounce } from './ui.js';

const listeners = new Set();
const eventHandlers = {};

export const store = {
  state: { tasks: [], links: [], slots: [], settings: {}, weeks: [] },
  view: 'brain',
  list: 'basket',
  search: '',
  selectedId: null,

  on(fn) { listeners.add(fn); return () => listeners.delete(fn); },
  emit() { for (const fn of listeners) fn(this.state); },

  async refresh() {
    this.state = await api('/api/state');
    this.emit();
    return this.state;
  },

  task(id) { return this.state.tasks.find(t => t.id === id); },
  get open() { return this.state.tasks.filter(t => t.status !== 'done'); },
  get backlog() { return this.state.tasks.filter(t => t.status === 'backlog').sort((a, b) => b.score - a.score); },
  get basket() { return this.state.tasks.filter(t => t.status === 'basket'); },
  get active() { return this.state.tasks.filter(t => t.status === 'active'); },

  onEvent(name, fn) { (eventHandlers[name] ||= []).push(fn); },
};

const refreshSoon = debounce(() => store.refresh().catch(() => {}), 150);

export function connectEvents(client = null) {
  let es;
  const open = () => {
    es = new EventSource(client ? `/api/events?client=${client}` : '/api/events');
    es.addEventListener('state', refreshSoon);
    for (const name of ['reminder', 'planner', 'popup', 'windows', 'wallpaper']) {
      es.addEventListener(name, e => {
        const data = JSON.parse(e.data || '{}');
        for (const fn of eventHandlers[name] || []) fn(data);
      });
    }
    es.onerror = () => { es.close(); setTimeout(open, 3000); };
    es.addEventListener('hello', refreshSoon);
  };
  open();
}

// Run an API mutation, then refresh the snapshot.
export async function mutate(promise) {
  const result = await promise;
  await store.refresh();
  return result;
}
