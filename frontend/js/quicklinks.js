// Quick links (Settings → Quick links): web addresses, app links or file/folder paths, opened by the server so
// folders and apps work from the browser and the desktop wallpaper alike.
import { api } from './api.js';
import { store } from './store.js';
import { h, icon, toastError } from './ui.js';

export const isWebLink = target => /^https?:/i.test(target);
export const openQuickLink = index => api(`/api/quicklinks/${index}/open`, { method: 'POST' }).catch(toastError);

export function quickLinkButtons(cls) {
  return (store.state.settings?.quick_links || []).map((l, i) => h('button', {
    class: cls, title: l.target, onclick: () => openQuickLink(i),
  }, icon(isWebLink(l.target) ? 'link' : 'file'), h('span', {}, l.label)));
}
