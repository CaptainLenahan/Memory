// Drag tasks from lists/queue onto synapses, and drag synapses back off the brain.
import { Tasks } from './api.js';
import { mutate, store } from './store.js';
import { confirmDialog, toast, toastError } from './ui.js';

let brain;
let dragTaskId = null;
const ghost = () => document.getElementById('drag-ghost');
const stage = () => document.getElementById('brain-stage');

export function initDragDrop(brainInstance) {
  brain = brainInstance;

  // ---- HTML5 drag from task rows and queue chips ----
  document.addEventListener('dragstart', e => {
    const src = e.target.closest?.('[data-task-id][draggable="true"]');
    if (!src) return;
    dragTaskId = Number(src.dataset.taskId);
    e.dataTransfer.setData('text/plain', String(dragTaskId));
    e.dataTransfer.effectAllowed = 'move';
    src.classList.add('dragging');
    document.body.classList.add('dragging');
  });
  document.addEventListener('dragend', e => {
    e.target.closest?.('[data-task-id]')?.classList.remove('dragging');
    endDrag();
  });

  document.addEventListener('dragover', e => {
    if (dragTaskId == null) return;
    const zone = e.target.closest?.('[data-drop]');
    setZoneHover(zone);
    if (zone) { e.preventDefault(); brain.highlight(null); return; }
    if (stage().contains(e.target) || e.target.closest?.('#brain-labels')) {
      e.preventDefault();
      const slot = brain.slotAt(e.clientX, e.clientY, dragTaskId);
      brain.highlight(slot);
      stage().classList.toggle('drop-active', slot != null);
    } else {
      brain.highlight(null);
    }
  });

  document.addEventListener('drop', e => {
    if (dragTaskId == null) return;
    e.preventDefault();
    const id = dragTaskId;
    const zone = e.target.closest?.('[data-drop]');
    const slot = zone ? null : brain.highlighted;
    endDrag();
    if (zone) dropOnZone(id, zone.dataset.drop);
    else if (slot != null) dropOnSlot(id, slot);
  });
}

function setZoneHover(zone) {
  document.querySelectorAll('[data-drop].drop-over').forEach(z => { if (z !== zone) z.classList.remove('drop-over'); });
  zone?.classList.add('drop-over');
}

function endDrag() {
  dragTaskId = null;
  document.body.classList.remove('dragging');
  stage().classList.remove('drop-active');
  setZoneHover(null);
  brain?.highlight(null);
  const g = ghost();
  g.style.display = 'none';
}

// ---- pointer drag that starts on a synapse ----
export function startSynapseDrag(task, ev) {
  dragTaskId = task.id;
  document.body.classList.add('dragging');
  const g = ghost();
  g.textContent = task.title;
  g.style.display = 'block';
  const move = e => {
    g.style.left = `${e.clientX + 14}px`;
    g.style.top = `${e.clientY + 10}px`;
    const under = document.elementFromPoint(e.clientX, e.clientY);
    const zone = under?.closest('[data-drop]');
    setZoneHover(zone);
    if (zone) brain.highlight(null);
    else {
      const slot = brain.slotAt(e.clientX, e.clientY, task.id);
      brain.highlight(slot !== task.slot_index ? slot : null);
    }
  };
  const up = e => {
    window.removeEventListener('pointermove', move);
    window.removeEventListener('pointerup', up);
    const under = document.elementFromPoint(e.clientX, e.clientY);
    const zone = under?.closest('[data-drop]');
    const slot = brain.highlighted;
    endDrag();
    if (zone) dropOnZone(task.id, zone.dataset.drop);
    else if (slot != null && slot !== task.slot_index) dropOnSlot(task.id, slot);
  };
  move(ev);
  window.addEventListener('pointermove', move);
  window.addEventListener('pointerup', up);
}

export async function dropOnSlot(taskId, slot) {
  const task = store.task(taskId);
  const occupant = brain.occupant(slot);
  try {
    if (occupant && occupant.id !== taskId && task?.status !== 'active') {
      const ok = await confirmDialog('Synapse occupied',
        `Synapse ${slot + 1} holds “${occupant.title}”. Swap it out to the backlog queue?`, 'Swap');
      if (!ok) return;
    }
    const before = task?.region;
    await mutate(Tasks.place(taskId, slot));
    brain.focusTask(taskId);
    const after = store.task(taskId)?.region;
    if (before && after && before !== after) toast(`“${task.title}” now counts as ${after} work, matching its hemisphere`);
    if (occupant && occupant.id !== taskId) {
      toast(task?.status === 'active' ? `Swapped with “${occupant.title}”` : `“${occupant.title}” moved to the queue`);
    }
  } catch (e) { toastError(e); }
}

async function dropOnZone(taskId, zone) {
  const task = store.task(taskId);
  if (!task) return;
  try {
    if (zone === 'done') {
      await mutate(Tasks.update(taskId, { status: 'done' }));
      toast(`Completed “${task.title}”`, { action: 'Undo', onAction: () => mutate(Tasks.update(taskId, { status: 'backlog' })) });
    } else if (zone !== task.status) {
      await mutate(Tasks.unplace(taskId, zone));
    }
  } catch (e) { toastError(e); }
}
