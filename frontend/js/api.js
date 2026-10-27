// Thin fetch wrapper for the Memory REST API.
export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

export async function api(path, { method = 'GET', body, form } = {}) {
  const opts = { method, headers: {} };
  if (form) opts.body = form;
  else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new ApiError(0, 'Memory server is not reachable. Is it running?');
  }
  const data = res.headers.get('content-type')?.includes('json') ? await res.json() : null;
  if (!res.ok) {
    const detail = data?.detail;
    const msg = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map(d => d.msg).join('; ') : `Request failed (${res.status})`;
    throw new ApiError(res.status, msg);
  }
  return data;
}

export const Tasks = {
  create: body => api('/api/tasks', { method: 'POST', body }),
  get: id => api(`/api/tasks/${id}`),
  update: (id, body) => api(`/api/tasks/${id}`, { method: 'PATCH', body }),
  remove: id => api(`/api/tasks/${id}`, { method: 'DELETE' }),
  place: (id, slot_index) => api(`/api/tasks/${id}/place`, { method: 'POST', body: { slot_index } }),
  unplace: (id, to = 'backlog') => api(`/api/tasks/${id}/unplace`, { method: 'POST', body: { to } }),
  addStep: (id, text) => api(`/api/tasks/${id}/checklist`, { method: 'POST', body: { text } }),
  updateStep: (itemId, body) => api(`/api/checklist/${itemId}`, { method: 'PATCH', body }),
  deleteStep: itemId => api(`/api/checklist/${itemId}`, { method: 'DELETE' }),
  reorderSteps: (id, ids) => api(`/api/tasks/${id}/checklist/reorder`, { method: 'POST', body: { ids } }),
  upload: (id, files, isScreenshot = false) => {
    const form = new FormData();
    for (const f of files) form.append('files', f, f.name || 'screenshot.png');
    form.append('is_screenshot', String(isScreenshot));
    return api(`/api/tasks/${id}/attachments`, { method: 'POST', form });
  },
  deleteAttachment: attId => api(`/api/attachments/${attId}`, { method: 'DELETE' }),
  link: (id, other_id) => api(`/api/tasks/${id}/links`, { method: 'POST', body: { other_id } }),
  unlink: (id, otherId) => api(`/api/tasks/${id}/links/${otherId}`, { method: 'DELETE' }),
  addDependency: (id, dependsOnId) => api(`/api/tasks/${id}/dependencies`, { method: 'POST', body: { depends_on_id: dependsOnId } }),
  removeDependency: (id, dependsOnId) => api(`/api/tasks/${id}/dependencies/${dependsOnId}`, { method: 'DELETE' }),
};
