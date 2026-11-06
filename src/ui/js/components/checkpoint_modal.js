/**
 * Continuity MD Review & Snapshot Approval Modal Component.
 *
 * Enforces the Custody Boundary:
 * Raw Evidence -> Caveman Processing -> Human Approval -> Sealed Snapshot
 */

import { state } from '../state.js';
import { invoke } from '../bridge.js';

export function renderCheckpointModal(container) {
  function openCheckpointModal(data) {
    if (!data) return;

    const chapterCode = data.chapter_code || 'Continuity_MD';
    const sessionRange = data.session_range || '';
    const fileName = data.file_name || `${chapterCode}.md`;
    const snapCode = data.snapshot_code || 'PENDING_APPROVAL';
    const isPending = snapCode === 'PENDING_APPROVAL';
    const sha = (data.checksum_sha256 || '').substring(0, 12);
    const content = data.markdown_content || '';
    const filePath = data.file_path || '';
    const projId = state.dashboard?.active_project?.id;
    const summary = data.extracted_summary || {};

    // Extract bootstrap block for quick copy
    let bootstrapBlock = '';
    const m = content.match(/```scs-bootstrap\s*([\s\S]*?)\s*```/);
    if (m) {
      bootstrapBlock = m[1].trim();
    } else {
      bootstrapBlock = content;
    }

    container.innerHTML = `
      <div class="modal-overlay">
        <div class="modal-box" style="max-width: 680px;">
          <div class="modal-header">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span>⚡ ${escapeHtml(chapterCode)} ${sessionRange ? `(${escapeHtml(sessionRange)})` : ''}</span>
              <span style="font-size: 10px; font-weight: 700; color: ${isPending ? 'var(--color-pending)' : 'var(--color-verified)'}; background: ${isPending ? 'rgba(99, 102, 241, 0.15)' : 'rgba(16, 185, 129, 0.15)'}; padding: 2px 6px; border-radius: var(--radius-sm);">
                ${isPending ? '🔒 DRAFT (UNSEALED)' : escapeHtml(snapCode)}
              </span>
              <span style="font-size: 10px; font-family: var(--font-mono); color: var(--text-muted);">
                SHA: ${escapeHtml(sha)}
              </span>
            </div>
            <button id="modal-close-cp" class="btn btn-sm">✕</button>
          </div>

          <div class="modal-body" style="display: flex; flex-direction: column; gap: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center; font-size: 11px; color: var(--text-secondary);">
              <span>
                Caveman Engine extraction: <strong>Accuracy > Compression</strong>. Decisions: ${summary.decisions_count || 0} | Constraints: ${summary.constraints_count || 0} | Tasks: ${summary.tasks_count || 0} | Artifacts: ${summary.artifacts_count || 0}
              </span>
              ${filePath ? `
                <button id="btn-copy-path" class="btn btn-sm" title="Copy saved file path">📁 Copy Path</button>
              ` : ''}
            </div>

            <textarea
              id="checkpoint-text"
              style="width: 100%; height: 260px; background: var(--bg-input); color: var(--text-primary); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px; font-family: var(--font-mono); font-size: 11px; line-height: 1.4; resize: vertical;"
              readonly
            >${escapeHtml(content)}</textarea>
          </div>

          <div class="modal-footer" style="display: flex; justify-content: space-between; align-items: center;">
            <button id="btn-close-cp" class="btn">Dismiss</button>
            <div style="display: flex; gap: 6px;">
              <button id="btn-copy-bootstrap-only" class="btn" title="Copy ready-to-use bootstrap prompt to paste into next AI chat">
                📋 Copy Bootstrap
              </button>
              ${isPending ? `
                <button id="btn-approve-checkpoint" class="btn btn-primary" style="background: rgba(16, 185, 129, 0.25); color: var(--color-verified); border: 1px solid var(--color-verified); font-weight: 700;">
                  🔒 Approve & Seal Snapshot
                </button>
              ` : `
                <button id="btn-copy-full-md" class="btn btn-primary">
                  📋 Copy Chapter MD
                </button>
              `}
            </div>
          </div>
        </div>
      </div>
    `;

    const close = () => {
      container.innerHTML = '';
    };

    container.querySelector('#modal-close-cp')?.addEventListener('click', close);
    container.querySelector('#btn-close-cp')?.addEventListener('click', close);

    container.querySelector('#btn-copy-path')?.addEventListener('click', async () => {
      try {
        await invoke('window_control', { action: 'copy_clipboard', text: filePath });
        state.showToast('Copied file path to clipboard');
      } catch (_) {}
    });

    container.querySelector('#btn-copy-bootstrap-only')?.addEventListener('click', async () => {
      try {
        await invoke('window_control', { action: 'copy_clipboard', text: bootstrapBlock });
        state.showToast('Copied Next Session Bootstrap to clipboard!');
      } catch (err) {
        state.showToast(err.message, 'error');
      }
    });

    container.querySelector('#btn-copy-full-md')?.addEventListener('click', async () => {
      try {
        await invoke('window_control', { action: 'copy_clipboard', text: content });
        state.showToast('Copied Continuity MD chapter to clipboard!');
      } catch (err) {
        state.showToast(err.message, 'error');
      }
    });

    container.querySelector('#btn-approve-checkpoint')?.addEventListener('click', async () => {
      try {
        const res = await invoke('approve_checkpoint', {
          project_id: projId,
          session_id: data.session_id,
        });
        state.showToast(`Sealed Snapshot ${res.snapshot_code}! Promoted ${res.promoted_decisions} decisions, ${res.promoted_tasks} tasks, ${res.promoted_artifacts} artifacts`);
        await state.refreshDashboard();
        close();
      } catch (err) {
        state.showToast(err.message, 'error');
      }
    });
  }

  window.__openCheckpointModal = openCheckpointModal;
}

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
