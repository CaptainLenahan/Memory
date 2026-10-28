// Settings dialog: RAM slots, capacity, Claude key/model, Microsoft Planner connection, notifications.
import { api } from './api.js';
import { mutate, store } from './store.js';
import { applyTheme, currentTheme, themed, THEMES } from './themes.js';
import { fmtDateTime, h, icon, modal, toast, toastError } from './ui.js';

const MODELS = [
  ['claude-opus-5-5', 'Claude Opus 5.5 (default)'],
  ['claude-sonnet-5-5', 'Claude Sonnet 5.5 (faster, lower cost)'],
  ['claude-haiku-5-5', 'Claude Haiku 5.5 (fastest)'],
  ['claude-fable-5-1', 'Claude Fable 5.1 (most capable)'],
];

export async function openSettings() {
  const s = await api('/api/settings').catch(toastError);
  if (!s) return;
  const ram = h('input', { class: 'input', type: 'number', min: 1, max: 15, value: s.ram_slots });
  const cap = h('input', { class: 'input', type: 'number', min: 1, max: 168, value: s.weekly_capacity_hours });
  const autoFill = h('input', { type: 'checkbox', checked: s.auto_fill });
  const key = h('input', { class: 'input', type: 'password', autocomplete: 'off', placeholder: s.has_anthropic_api_key ? '•••••••• saved — type to replace' : 'sk-ant-…' });
  const model = h('select', { class: 'input' }, MODELS.map(([v, l]) => h('option', { value: v, selected: s.model === v }, l)));
  const clientId = h('input', { class: 'input', value: s.azure_client_id || '', placeholder: '00000000-0000-0000-0000-000000000000' });
  const tenant = h('input', { class: 'input', value: s.azure_tenant_id || 'organizations', placeholder: 'organizations or your tenant ID' });
  const autoSync = h('input', { type: 'checkbox', checked: s.planner_auto_sync });
  const plannerBox = h('div');
  const links = quickLinksEditor(s.quick_links || []);
  const wallpaperOn = h('input', { type: 'checkbox', checked: s.desktop_wallpaper });
  const wallpaperScreens = h('select', { class: 'input' }, [['all', 'All screens'], ['primary', 'Main screen only']]
    .map(([v, l]) => h('option', { value: v, selected: (s.wallpaper_screens || 'all') === v }, l)));
  const wallpaperStatus = h('div', { class: 'status-line' }, '…');
  api('/api/wallpaper').then(w => {
    wallpaperStatus.textContent = w.running ? `On, ${w.screens} screen${w.screens === 1 ? '' : 's'}` : w.enabled ? `Not showing: ${w.reason}` : 'Off';
  }).catch(() => { wallpaperStatus.textContent = ''; });
  const aboutBox = h('div', { class: 'status-line' }, 'Memory');
  const checkUpdates = async () => {
    aboutBox.replaceChildren('Checking…');
    try {
      const v = await api('/api/version');
      aboutBox.replaceChildren(`Memory ${v.version}${v.frozen ? '' : ' (running from source)'} · `,
        v.update_available
          ? h('a', { href: v.latest.download || v.latest.url, target: '_blank', rel: 'noopener' }, `Download ${v.latest.version}`)
          : v.latest ? 'up to date' : 'no published releases visible (the repository may be private)',
        ' ', h('button', { class: 'btn small ghost', onclick: checkUpdates }, 'Check again'));
    } catch (e) { aboutBox.replaceChildren(e.message); }
  };
  checkUpdates();
  const notifyEmail = h('input', { class: 'input', type: 'email', value: s.notify_email || '', placeholder: 'Your Microsoft account (default)' });
  const testStatus = h('span', { class: 'status-line' });
  const testBtn = h('button', { class: 'btn', onclick: async () => {
    testStatus.textContent = 'Sending…';
    try {
      const r = await api('/api/notify/test', { method: 'POST' });
      testStatus.textContent = `Desktop: ${r.desktop ? 'sent' : 'unavailable'} · Email: ${r.email ? 'sent' : r.email_error}`;
    } catch (e) { testStatus.textContent = e.message; }
  } }, 'Send a test notification');

  const body = h('div', {},
    h('div', { class: 'form-section' }, 'Colour theme'),
    themePicker(),
    h('div', { class: 'form-section' }, 'Brain'),
    h('div', { class: 'form-grid' },
      h('label', {}, 'RAM slots (synapses)'), ram,
      h('div', { class: 'help' }, 'How many tasks can be actively worked on at once. 5–9 suits most people.'),
      h('label', {}, 'Weekly capacity (hours)'), cap,
      h('div', { class: 'help' }, 'Used to auto-assign each task an estimated completion week.'),
      h('label', {}, 'Auto-fill from queue'), h('label', {}, autoFill, ' Pull the next queued task into a synapse when one frees up')),
    h('div', { class: 'form-section' }, 'Claude'),
    h('div', { class: 'form-grid' },
      h('label', {}, 'Anthropic API key'), h('div', { style: { display: 'flex', gap: '8px' } }, key,
        s.has_anthropic_api_key ? h('button', { class: 'btn small danger', onclick: async () => {
          await api('/api/settings/anthropic_api_key', { method: 'DELETE' });
          key.placeholder = 'sk-ant-…';
          store.refresh();
          toast('API key removed');
        } }, 'Remove') : null),
      h('div', { class: 'help' }, 'Stored only in this app\'s local database. You can also set ANTHROPIC_API_KEY in .env.'),
      h('label', {}, 'Model'), model),
    h('div', { class: 'form-section' }, 'Microsoft Planner & Outlook'),
    h('div', { class: 'form-grid' },
      h('label', {}, 'Azure app client ID'), clientId,
      h('div', { class: 'help' }, 'From an Azure app registration with “Allow public client flows” on and delegated Tasks.ReadWrite, User.Read, Mail.Read and Mail.Send (mail powers the Inbox tab and email notifications). See README.'),
      h('label', {}, 'Tenant'), tenant,
      h('label', {}, 'Auto-sync'), h('label', {}, autoSync, ' Sync every 15 minutes while signed in')),
    plannerBox,
    h('div', { class: 'form-section' }, 'Desktop wallpaper'),
    h('div', { class: 'form-grid' },
      h('label', {}, 'Show on desktop'), h('label', {}, wallpaperOn, ' Show the brain as my desktop wallpaper, behind my icons'),
      h('label', {}, 'Screens'), wallpaperScreens,
      h('div', { class: 'help' }, 'Click synapses, drag them and use quick links right on the desktop. It pauses while a maximised or full-screen app covers it. If Lively Wallpaper is running, Memory leaves the desktop to it.'),
      h('label', {}, 'Status'), wallpaperStatus),
    h('div', { class: 'form-section' }, 'Quick links'),
    h('div', { class: 'help', style: { marginBottom: '8px' } }, 'Shown on the desktop wallpaper (bottom-left) and in the left rail. Use a web address, an app link like ms-teams:, or a folder/file path such as C:\\Reports or ~\\Downloads.'),
    links.el,
    h('div', { class: 'form-section' }, 'About'),
    aboutBox,
    h('div', { class: 'form-section' }, 'Notifications'),
    h('div', { class: 'form-grid' },
      h('label', {}, 'Email notifications to'), notifyEmail,
      h('div', { class: 'help' }, 'Each task picks Desktop, Email, Both or Off in its pop-up (Desktop is the default). Desktop ones are Windows notifications, so they arrive even with no Memory window open; email goes through Outlook, so sign in to Microsoft above.'),
      h('label', {}, 'Try it'), h('div', { style: { display: 'flex', gap: '8px', alignItems: 'center' } }, testBtn, testStatus)));

  const save = async () => {
    const values = {
      ram_slots: Number(ram.value), weekly_capacity_hours: Number(cap.value), auto_fill: autoFill.checked,
      model: model.value, azure_client_id: clientId.value.trim(), azure_tenant_id: tenant.value.trim() || 'organizations',
      planner_auto_sync: autoSync.checked, quick_links: links.value(), notify_email: notifyEmail.value.trim(),
    };
    // only when changed here: a dialog opened earlier must not switch the wallpaper back off (or on)
    if (wallpaperOn.checked !== !!s.desktop_wallpaper) values.desktop_wallpaper = wallpaperOn.checked;
    if (wallpaperScreens.value !== (s.wallpaper_screens || 'all')) values.wallpaper_screens = wallpaperScreens.value;
    if (key.value.trim()) values.anthropic_api_key = key.value.trim();
    try {
      await mutate(api('/api/settings', { method: 'PUT', body: values }));
      key.value = '';
      return true;
    } catch (e) { toastError(e); return false; }
  };

  renderPlanner(plannerBox, save);
  modal({
    title: 'Settings', body, wide: true,
    actions: [{ label: 'Cancel' }, { label: 'Save', kind: 'primary', onClick: async () => { const ok = await save(); if (ok) toast('Settings saved'); return ok; } }],
  });
}

function quickLinksEditor(initial) {
  const links = initial.map(l => ({ ...l }));
  const wrap = h('div', { class: 'ql-editor' });
  const draw = () => wrap.replaceChildren(...links.map((l, i) => {
    const label = h('input', { class: 'input', value: l.label, placeholder: 'Label', maxlength: 60, 'aria-label': 'Link label' });
    const target = h('input', { class: 'input', value: l.target, placeholder: 'https://…, ms-teams:, C:\\folder', 'aria-label': 'Link target' });
    label.addEventListener('input', () => { l.label = label.value; });
    target.addEventListener('input', () => { l.target = target.value; });
    return h('div', { class: 'ql-row' }, label, target,
      h('button', { class: 'btn icon ghost', title: 'Remove', onclick: () => { links.splice(i, 1); draw(); } }, icon('x')));
  }), h('button', { class: 'btn small', onclick: () => { links.push({ label: '', target: '' }); draw(); } }, icon('plus'), 'Add link'));
  draw();
  return { el: wrap, value: () => links.filter(l => l.label.trim() && l.target.trim()).map(l => ({ label: l.label.trim(), target: l.target.trim() })) };
}

// Applies instantly and saves on its own, so every window (and the desktop wallpaper) follows along.
function themePicker() {
  const wrap = h('div', { class: 'theme-picker', role: 'radiogroup', 'aria-label': 'Colour theme' });
  const draw = () => wrap.replaceChildren(...THEMES.map(t => {
    const on = currentTheme().id === t.id;
    return h('button', {
      class: `theme-swatch ${on ? 'on' : ''}`, role: 'radio', 'aria-checked': String(on), title: t.name,
      style: { '--sw-bg': themed('#071328', t), '--sw-panel': themed('#0e2040', t), '--sw-glow': themed('#5fd8ff', t), '--sw-btn': themed('#2f8cff', t) },
      onclick: async () => {
        if (on) return;
        applyTheme(t.id);
        draw();
        try { await api('/api/settings', { method: 'PUT', body: { theme: t.id } }); } catch (e) { toastError(e); }
      },
    }, h('span', { class: 'sw-art' }, h('i', { class: 'sw-orb' }), h('i', { class: 'sw-bar' })), h('span', { class: 'sw-name' }, t.name));
  }));
  draw();
  return h('div', {}, wrap,
    h('div', { class: 'help' }, 'Re-tints the whole interface and the brain. Logical/creative and due-date colours stay the same so they keep their meaning.'));
}

async function renderPlanner(box, save) {
  let st;
  try { st = await api('/api/planner/status'); } catch { return; }
  box.replaceChildren();
  const line = st.signed_in
    ? h('div', { class: 'status-line ok' }, `Signed in as ${st.account}${st.last_sync ? ` · last sync ${fmtDateTime(st.last_sync)}` : ''}`)
    : h('div', { class: 'status-line' }, st.configured ? 'Not signed in.' : 'Enter a client ID and save to connect.');
  const res = st.last_result;
  const resultLine = res ? h('div', { class: `status-line ${res.ok ? '' : 'bad'}` },
    res.ok ? `Last sync: ${res.fetched} fetched · ${res.created} new · ${res.updated} updated · ${res.completed} completed` : `Last sync failed: ${res.error}`) : null;
  const buttons = h('div', { style: { display: 'flex', gap: '8px', marginTop: '8px' } });
  if (st.signed_in) {
    buttons.append(
      h('button', { class: 'btn primary', onclick: async () => { await syncPlanner(); renderPlanner(box, save); } }, 'Sync now'),
      h('button', { class: 'btn', onclick: async () => { await api('/api/planner/logout', { method: 'POST' }); renderPlanner(box, save); } }, 'Sign out'));
  } else {
    buttons.append(h('button', { class: 'btn primary', onclick: async () => {
      if (!(await save())) return;
      try {
        const flow = await api('/api/planner/login', { method: 'POST', body: { method: 'browser' } });
        showDeviceCode(box, flow);
        waitForLogin(box, save);
      } catch (e) { toastError(e); }
    } }, 'Sign in with Microsoft'));
  }
  box.append(...[line, resultLine, st.error ? h('div', { class: 'status-line bad' }, st.error) : null, buttons].filter(Boolean));
  if (st.pending) showDeviceCode(box, st.pending);
}

function showDeviceCode(box, flow) {
  if (flow.method === 'browser' || (!flow.user_code && flow.message)) {
    box.querySelector('.device-code')?.remove();
    box.append(h('div', { class: 'device-code' },
      h('div', {}, flow.message || 'Finish signing in on the Microsoft page that opened in your browser.'),
      h('div', { class: 'status-line' }, 'Waiting for you to finish signing in… ',
        h('a', { href: '#', onclick: async e => {
          e.preventDefault();
          try { const f = await api('/api/planner/login', { method: 'POST', body: { method: 'code' } }); showDeviceCode(box, f); } catch (err) { toastError(err); }
        } }, 'Use a sign-in code instead'))));
    return;
  }
  box.querySelector('.device-code')?.remove();
  box.append(h('div', { class: 'device-code' },
    h('div', {}, 'Open ', h('a', { href: flow.verification_uri, target: '_blank', rel: 'noopener' }, flow.verification_uri), ' and enter this code:'),
    h('div', { class: 'code' }, flow.user_code),
    h('div', { class: 'status-line' }, 'Waiting for you to finish signing in…')));
}

function waitForLogin(box, save) {
  const timer = setInterval(async () => {
    if (!document.body.contains(box)) { clearInterval(timer); return; }
    const st = await api('/api/planner/status').catch(() => null);
    if (st && !st.pending) {
      clearInterval(timer);
      renderPlanner(box, save);
      if (st.signed_in) { toast('Connected to Microsoft Planner'); syncPlanner(); }
    }
  }, 3000);
}

export async function syncPlanner() {
  const btn = document.getElementById('btn-planner');
  btn.classList.add('syncing');
  try {
    const st = await api('/api/planner/status');
    if (!st.signed_in) {
      toast(st.configured ? 'Sign in to Microsoft in Settings to sync Planner.' : 'Connect Microsoft Planner in Settings first.', { action: 'Settings', onAction: openSettings });
      return;
    }
    const r = await mutate(api('/api/planner/sync', { method: 'POST' }));
    if (r.ok) toast(`Planner synced: ${r.created} new in the basket, ${r.updated} updated`);
    else toast(`Planner sync failed: ${r.error}`, { type: 'error', timeout: 8000 });
  } catch (e) { toastError(e); } finally { btn.classList.remove('syncing'); }
}
