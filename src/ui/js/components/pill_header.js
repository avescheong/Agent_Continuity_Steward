/**
 * Pill Header Component (Mode 1 & Compact Companion Controls).
 */

import { state } from '../state.js';
import { invoke } from '../bridge.js';
import { showProjectDialog } from './dialog_modal.js';

export function renderPillHeader(container) {
  const d = state.dashboard;
  const p = d?.active_project;
  const summary = d?.reconcile_summary || {};

  const isCompact = state.viewMode === 'pill' || state.viewMode === 'compact';

  container.innerHTML = `
    <div class="hud-pill">
      <div class="pill-left">
        <span class="brand-badge" title="SCS HUD Lite">⚡ SCS</span>
        <select id="project-select" class="project-select" title="Active Project">
          ${(d?.all_projects || []).map(proj => `
            <option value="${proj.id}" ${proj.id === p?.id ? 'selected' : ''}>
              ${proj.code}
            </option>
          `).join('')}
        </select>
        <button id="btn-new-project" class="btn btn-sm" title="Create New Project">+</button>
      </div>

      <div class="pill-center">
        <div class="status-dots" title="Artifact Reality: ${summary.verified_match || 0} Verified, ${summary.local_file_exists || 0} Local, ${summary.modified || 0} Modified, ${summary.missing || 0} Missing">
          <span class="dot dot-verified"></span><span>${summary.verified_match || 0}</span>
          <span class="dot dot-local"></span><span>${summary.local_file_exists || 0}</span>
          <span class="dot dot-modified"></span><span>${summary.modified || 0}</span>
          <span class="dot dot-missing"></span><span>${summary.missing || 0}</span>
        </div>
      </div>

      <div class="pill-right">
        <button id="btn-copy-bootstrap" class="btn btn-sm btn-icon" title="Copy Bootstrap Rehydration Prompt (Ctrl+Shift+B)">
          📋
        </button>
        <button id="btn-toggle-pin" class="btn btn-icon ${state.isPinned ? 'active' : ''}" title="Always on Top">
          📌
        </button>
        <button id="btn-toggle-ghost" class="btn btn-icon ${state.isGhost ? 'active' : ''}" title="Ghost Opacity">
          👁
        </button>
        <button id="btn-toggle-mode" class="btn btn-icon ${isCompact ? 'active' : ''}" title="${isCompact ? 'Expand to Full HUD (Normal Mode)' : 'Collapse to Compact HUD'}">
          ${isCompact ? '🗖' : '🗕'}
        </button>
      </div>
    </div>
  `;

  // Bind events
  container.querySelector('#project-select')?.addEventListener('change', (e) => {
    state.switchProject(e.target.value);
  });

  container.querySelector('#btn-new-project')?.addEventListener('click', () => {
    showProjectDialog({
      onConfirm: ({ code, name }) => {
        invoke('create_project', { code, name }).then(newProj => {
          state.refreshDashboard(newProj.id);
          state.showToast(`Created project ${newProj.code}`);
        }).catch(err => state.showToast(err.message, 'error'));
      },
    });
  });

  container.querySelector('#btn-copy-bootstrap')?.addEventListener('click', () => {
    if (!p) return;
    window.__openBootstrapModal && window.__openBootstrapModal();
  });

  container.querySelector('#btn-toggle-pin')?.addEventListener('click', () => {
    state.togglePin();
  });

  container.querySelector('#btn-toggle-ghost')?.addEventListener('click', () => {
    state.toggleGhost();
  });

  container.querySelector('#btn-toggle-mode')?.addEventListener('click', () => {
    const isCompact = state.viewMode === 'pill' || state.viewMode === 'compact';
    state.setViewMode(isCompact ? 'drawer' : 'compact');
  });
}
