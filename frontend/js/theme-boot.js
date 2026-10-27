// Re-applies the last colour theme before first paint, so a non-blue theme doesn't flash blue while modules load.
try {
  const saved = JSON.parse(localStorage.getItem('memoryTheme'));
  if (saved && saved.vars) {
    for (const k in saved.vars) document.documentElement.style.setProperty(k, saved.vars[k]);
    document.documentElement.dataset.theme = saved.id;
  }
} catch (e) { /* no saved theme */ }
