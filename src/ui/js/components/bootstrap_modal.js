/**
 * Bootstrap Prompt Preview & Copy Component.
 */

import { state } from '../state.js';
import { invoke } from '../bridge.js';

export function renderBootstrapModal(container) {
  async function openBootstrapModal() {
    const p = state.dashboard?.active_project;
    if (!p) return;

    try {
      const res = await invoke('generate_bootstrap', { project_id: p.id });
      const promptText = res.prompt_text || '';
      const tokens = res.approx_tokens || 0;

      container.innerHTML = `
        <div class="modal-overlay">
          <div class="modal-box" style="max-width: 680px;">
            <div class="modal-header">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span>Continuity Bootstrap Prompt</span>
                <span style="font-size: 10px; font-weight: 700; color: var(--color-local); background: rgba(56, 189, 248, 0.15); padding: 2px 6px; border-radius: var(--radius-sm);">
                  ~${tokens} tokens
                </span>
              </div>
              <button id="modal-close-b" class="btn btn-sm">✕</button>
            </div>

            <div class="modal-body" style="display: flex; flex-direction: column; gap: 6px;">
              <p style="font-size: 11px; color: var(--text-secondary); margin: 0;">
                Review the rehydration prompt below before copying to your AI chat. All keys and secrets are automatically scrubbed.
              </p>
              <textarea
                id="bootstrap-preview-text"
                style="width: 100%; height: 260px; background: var(--bg-input); color: var(--text-primary); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px; font-family: var(--font-mono); font-size: 11px; line-height: 1.4; resize: vertical;"
                readonly
              >${escapeHtml(promptText)}</textarea>
            </div>

            <div class="modal-footer">
              <button id="btn-close-b" class="btn">Close</button>
              <button id="btn-copy-b" class="btn btn-primary">📋 Copy Prompt</button>
            </div>
          </div>
        </div>
      `;

      const close = () => {
        container.innerHTML = '';
      };

      container.querySelector('#modal-close-b')?.addEventListener('click', close);
      container.querySelector('#btn-close-b')?.addEventListener('click', close);

      container.querySelector('#btn-copy-b')?.addEventListener('click', async () => {
        try {
          await invoke('window_control', { action: 'copy_clipboard', text: promptText });
          state.showToast(`Copied Bootstrap prompt (~${tokens} tokens)`);
          close();
        } catch (err) {
          state.showToast(err.message, 'error');
        }
      });
    } catch (err) {
      state.showToast(err.message, 'error');
    }
  }

  window.__openBootstrapModal = openBootstrapModal;
}

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
