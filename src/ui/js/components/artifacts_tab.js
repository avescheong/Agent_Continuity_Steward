/**
 * Artifact Reality Awareness & Read-Only Reconciliation Tab.
 */

import { state } from '../state.js';
import { invoke } from '../bridge.js';
import { showPromptDialog, showConfirmDialog } from './dialog_modal.js';

export function renderArtifactsTab(container) {
  const d = state.dashboard;
  const p = d?.active_project;
  const artifacts = d?.artifacts || [];

  const rootPath = p?.root_paths && p.root_paths.length > 0 ? p.root_paths[0] : '(No folder selected)';

  container.innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 8px;">
      <!-- Project Root Watcher Header -->
      <div style="background: var(--bg-card); padding: 8px 10px; border-radius: var(--radius-sm); border: 1px solid var(--border); display: flex; flex-direction: column; gap: 4px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <span style="font-size: 10px; color: var(--text-muted); text-transform: uppercase;">Watched Read-Only Folder:</span>
          <div style="display: flex; gap: 4px;">
            <button id="btn-pick-folder" class="btn btn-sm">📁 Set Folder</button>
            <button id="btn-reconcile" class="btn btn-sm btn-primary">🔄 Reconcile Now</button>
          </div>
        </div>
        <div style="font-size: 11px; font-family: var(--font-mono); color: var(--text-secondary); word-break: break-all;">
          ${rootPath}
        </div>
      </div>

      <!-- Artifact List -->
      ${artifacts.length === 0 ? `
        <div style="text-align: center; padding: 20px 10px; color: var(--text-muted); font-size: 11px;">
          No artifacts tracked yet. Use <strong>+ Capture</strong> to track a file discussed in AI chat.
        </div>
      ` : `
        <div style="display: flex; flex-direction: column; gap: 6px;">
          ${artifacts.map(a => {
            let badgeClass = 'tag-TASK';
            let badgeText = a.custody_state;
            let badgeStyle = 'background: rgba(100, 116, 139, 0.2); color: var(--text-muted);';

            if (a.custody_state === 'VERIFIED_MATCH') {
              badgeText = '🟢 Verified Match';
              badgeStyle = 'background: rgba(16, 185, 129, 0.2); color: var(--color-verified);';
            } else if (a.custody_state === 'LOCAL_FILE_EXISTS') {
              badgeText = '🔵 Local File Exists';
              badgeStyle = 'background: rgba(56, 189, 248, 0.2); color: var(--color-local);';
            } else if (a.custody_state === 'MODIFIED') {
              badgeText = '🟠 Modified / Drift';
              badgeStyle = 'background: rgba(245, 158, 11, 0.2); color: var(--color-modified);';
            } else if (a.custody_state === 'MISSING') {
              badgeText = '🔴 Missing on Disk';
              badgeStyle = 'background: rgba(244, 63, 94, 0.2); color: var(--color-missing);';
            } else if (a.custody_state === 'CONVERSATION_ONLY') {
              badgeText = '💬 Chat-Only';
              badgeStyle = 'background: rgba(168, 85, 247, 0.2); color: var(--color-chat);';
            }

            const canLock = a.observed_sha256 && a.custody_state !== 'VERIFIED_MATCH';

            return `
              <div class="hud-card" data-id="${a.id}">
                <div class="card-row">
                  <span class="card-title">${a.name}</span>
                  <span style="font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: var(--radius-sm); ${badgeStyle}">
                    ${badgeText}
                  </span>
                </div>
                <div style="font-size: 10px; font-family: var(--font-mono); color: var(--text-muted);">
                  Rel Path: ${a.relative_path || '(Chat only - not saved to disk)'}
                </div>
                ${a.observed_sha256 ? `
                  <div style="font-size: 10px; font-family: var(--font-mono); color: var(--text-muted);">
                    SHA: ${a.observed_sha256.substring(0, 16)}...
                  </div>
                ` : ''}
                <div style="display: flex; justify-content: flex-end; gap: 4px; margin-top: 4px;">
                  <button class="btn btn-sm btn-bind-path" data-id="${a.id}" data-path="${a.relative_path || ''}">
                    🔗 Bind Path
                  </button>
                  ${canLock ? `
                    <button class="btn btn-sm btn-primary btn-lock-hash" data-id="${a.id}" title="Lock current file hash as baseline">
                      🔒 Lock Baseline
                    </button>
                  ` : ''}
                  <button class="btn btn-sm btn-del-art" data-id="${a.id}">✕</button>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      `}
    </div>
  `;

  // Bindings
  container.querySelector('#btn-pick-folder')?.addEventListener('click', async () => {
    if (!p) return;
    try {
      const res = await invoke('window_control', { action: 'pick_folder' });
      if (res.folder) {
        await invoke('update_project_session', {
          project_id: p.id,
          root_paths: [res.folder],
        });
        state.showToast('Updated project root folder');
        state.refreshDashboard();
      }
    } catch (err) {
      state.showToast(err.message, 'error');
    }
  });

  container.querySelector('#btn-reconcile')?.addEventListener('click', async () => {
    if (!p) return;
    try {
      const res = await invoke('reconcile_project_artifacts', { project_id: p.id });
      state.showToast(`Reconciled ${res.summary.total} artifacts`);
      state.refreshDashboard();
    } catch (err) {
      state.showToast(err.message, 'error');
    }
  });

  container.querySelectorAll('.btn-bind-path').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.getAttribute('data-id');
      const current = btn.getAttribute('data-path') || '';
      showPromptDialog({
        title: 'Bind Relative Path',
        label: 'Relative Path Inside Project Root',
        defaultValue: current,
        placeholder: 'e.g. src/index.js or docs/spec.md',
        confirmText: 'Bind Path',
        onConfirm: async (newPath) => {
          if (!newPath.trim()) return;
          try {
            await invoke('bind_artifact_path', { artifact_id: id, relative_path: newPath.trim() });
            state.showToast('Bound relative path');
            state.refreshDashboard();
          } catch (err) {
            state.showToast(err.message, 'error');
          }
        },
      });
    });
  });

  container.querySelectorAll('.btn-lock-hash').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.getAttribute('data-id');
      try {
        await invoke('lock_artifact_baseline', { artifact_id: id });
        state.showToast('Locked baseline SHA-256');
        state.refreshDashboard();
      } catch (err) {
        state.showToast(err.message, 'error');
      }
    });
  });

  container.querySelectorAll('.btn-del-art').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.getAttribute('data-id');
      showConfirmDialog({
        title: 'Delete Artifact',
        message: 'Are you sure you want to remove this artifact tracking record?',
        confirmText: 'Delete',
        onConfirm: async () => {
          try {
            await invoke('delete_artifact', { artifact_id: id });
            state.refreshDashboard();
          } catch (err) {
            state.showToast(err.message, 'error');
          }
        },
      });
    });
  });
}
