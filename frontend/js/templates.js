// Task templates: start a task from a saved shape (steps, notes, priority, effort, repeat, notifications, due offset).
import { api } from './api.js';
import { mutate } from './store.js';
import { closePopover, confirmDialog, h, icon, popover, toastError } from './ui.js';

export const Templates = {
  list: () => api('/api/templates'),
  use: (id, title) => api(`/api/templates/${id}/use`, { method: 'POST', body: { title: title || null } }),
  fromTask: (taskId, name) => api(`/api/tasks/${taskId}/template`, { method: 'POST', body: { name } }),
  remove: id => api(`/api/templates/${id}`, { method: 'DELETE' }),
};

export const templateMeta = t => [t.checklist.length ? `${t.checklist.length} steps` : null, t.repeat || null,
  t.due_in_days != null ? `due in ${t.due_in_days}d` : null].filter(Boolean).join(' · ');

// Popover listing templates under `anchor`; picking one creates the task (in the basket) and calls onCreated(task).
export async function templatePicker(anchor, onCreated) {
  let list;
  try { list = await Templates.list(); } catch (e) { toastError(e); return; }
  const r = anchor.getBoundingClientRect();
  const items = list.length ? list.map(t => h('div', { class: 'tpl-opt' },
    h('button', { class: 'opt', onclick: async () => {
      closePopover();
      try { onCreated?.(await mutate(Templates.use(t.id))); } catch (e) { toastError(e); }
    } }, h('span', { class: 't' }, t.name), h('span', { class: 's' }, templateMeta(t))),
    h('button', { class: 'tpl-del', title: 'Delete template', onclick: async e => {
      e.stopPropagation();
      if (!(await confirmDialog('Delete template', `Delete the “${t.name}” template? Tasks made from it are kept.`, 'Delete', 'danger'))) return;
      try { await Templates.remove(t.id); templatePicker(anchor, onCreated); } catch (err) { toastError(err); }
    } }, icon('x')))) : [h('div', { class: 'none' }, 'No templates yet.')];
  popover({ x: r.left + r.width / 2, y: r.bottom }, [h('h4', {}, 'New from template'), ...items,
    h('div', { class: 'none' }, 'Save any task as a template from its pop-up.')]);
}
