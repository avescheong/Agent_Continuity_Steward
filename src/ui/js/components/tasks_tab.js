/**
 * Tasks Tab Component (Reasoning-bound execution checklist).
 */

import { state } from '../state.js';
import { invoke } from '../bridge.js';
import { showConfirmDialog } from './dialog_modal.js';

export function renderTasksTab(container) {
  const d = state.dashboard;
  const tasks = d?.tasks || [];

  if (tasks.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 24px 10px; color: var(--text-muted); font-size: 11px;">
        No tasks tracked yet. Use <strong>+ Capture</strong> or paste AI discussion to stage tasks.
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 6px;">
      ${tasks.map(t => {
        const isDone = t.status === 'COMPLETED';
        const isBlocked = t.status === 'BLOCKED';
        const statusIcon = isDone ? '✓' : (isBlocked ? '⚠' : (t.status === 'IN_PROGRESS' ? '▶' : '○'));
        const statusColor = isDone ? 'var(--color-verified)' : (isBlocked ? 'var(--color-missing)' : (t.status === 'IN_PROGRESS' ? 'var(--color-local)' : 'var(--text-muted)'));

        return `
          <div class="hud-card" data-id="${t.id}">
            <div class="card-row">
              <button class="btn btn-sm btn-cycle" data-id="${t.id}" style="color: ${statusColor}; font-weight: bold; width: 22px; padding: 2px 0;">
                ${statusIcon}
              </button>
              <span class="card-code">[${t.code}]</span>
              <span class="card-title" style="text-decoration: ${isDone ? 'line-through' : 'none'}; color: ${isDone ? 'var(--text-muted)' : 'var(--text-primary)'};">
                ${t.title}
              </span>
              <button class="btn btn-sm btn-del-task" data-id="${t.id}" style="padding: 1px 4px; color: var(--text-muted);" title="Delete">✕</button>
            </div>
            ${t.why_it_matters ? `
              <div class="chip-why" title="${t.why_it_matters}">
                Why: ${t.why_it_matters}
              </div>
            ` : ''}
            ${t.blocker_reason ? `
              <div style="font-size: 10px; color: var(--color-missing); padding-left: 26px;">
                Blocker: ${t.blocker_reason}
              </div>
            ` : ''}
          </div>
        `;
      }).join('')}
    </div>
  `;

  // Status cycling
  container.querySelectorAll('.btn-cycle').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.getAttribute('data-id');
      try {
        await invoke('cycle_task_status', { task_id: id });
        state.refreshDashboard();
      } catch (err) {
        state.showToast(err.message, 'error');
      }
    });
  });

  // Deletion
  container.querySelectorAll('.btn-del-task').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const id = btn.getAttribute('data-id');
      showConfirmDialog({
        title: 'Delete Task',
        message: 'Are you sure you want to delete this task item?',
        confirmText: 'Delete',
        onConfirm: async () => {
          try {
            await invoke('delete_task', { task_id: id });
            state.refreshDashboard();
          } catch (err) {
            state.showToast(err.message, 'error');
          }
        },
      });
    });
  });
}
