/**
 * Decisions & Rejected Options Tab Component.
 */

import { state } from '../state.js';
import { invoke } from '../bridge.js';
import { showConfirmDialog } from './dialog_modal.js';

function formatDecisionBadge(kind) {
  switch (kind) {
    case 'REJECTED_OPTION':
      return { text: '⛔ Do Not Repeat', color: 'var(--color-missing)', bg: 'rgba(244, 63, 94, 0.15)' };
    case 'CONSTRAINT':
      return { text: '🔒 Constraint', color: 'var(--color-modified)', bg: 'rgba(245, 158, 11, 0.15)' };
    case 'IDEA':
      return { text: '💡 Idea', color: 'var(--color-chat)', bg: 'rgba(168, 85, 247, 0.15)' };
    case 'DECISION':
    default:
      return { text: '⚡ Decision', color: 'var(--color-verified)', bg: 'rgba(16, 185, 129, 0.15)' };
  }
}

export function renderDecisionsTab(container) {
  const d = state.dashboard;
  const decs = d?.decisions || [];

  if (decs.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 24px 10px; color: var(--text-muted); font-size: 11px;">
        No decisions, constraints, or rejected options recorded yet.
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 6px;">
      ${decs.map(dec => {
        const badge = formatDecisionBadge(dec.record_kind);

        return `
          <div class="hud-card" style="border-left: 3px solid ${badge.color}; opacity: ${dec.is_active ? '1.0' : '0.5'};">
            <div class="card-row">
              <span class="card-code" style="color: ${badge.color}; font-weight: 700;">
                [${dec.code}]
              </span>
              <span style="font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: var(--radius-sm); color: ${badge.color}; background: ${badge.bg}; white-space: nowrap;">
                ${badge.text}
              </span>
              <span class="card-title" style="text-decoration: ${dec.is_active ? 'none' : 'line-through'};">
                ${dec.statement}
              </span>
              <div style="display: flex; gap: 4px;">
                <button class="btn btn-sm btn-toggle-dec" data-id="${dec.id}" title="Toggle Active">
                  ${dec.is_active ? 'Active' : 'Superseded'}
                </button>
                <button class="btn btn-sm btn-del-dec" data-id="${dec.id}" title="Delete">✕</button>
              </div>
            </div>
            ${dec.rationale_why ? `
              <div class="chip-why" title="${dec.rationale_why}">
                Why: ${dec.rationale_why}
              </div>
            ` : ''}
          </div>
        `;
      }).join('')}
    </div>
  `;

  // Toggle active
  container.querySelectorAll('.btn-toggle-dec').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.getAttribute('data-id');
      try {
        await invoke('toggle_decision_active', { decision_id: id });
        state.refreshDashboard();
      } catch (err) {
        state.showToast(err.message, 'error');
      }
    });
  });

  // Delete
  container.querySelectorAll('.btn-del-dec').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.getAttribute('data-id');
      showConfirmDialog({
        title: 'Delete Decision',
        message: 'Are you sure you want to delete this decision/constraint record?',
        confirmText: 'Delete',
        onConfirm: async () => {
          try {
            await invoke('delete_decision', { decision_id: id });
            state.refreshDashboard();
          } catch (err) {
            state.showToast(err.message, 'error');
          }
        },
      });
    });
  });
}
