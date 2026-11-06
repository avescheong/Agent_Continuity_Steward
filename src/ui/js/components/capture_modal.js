/**
 * Fast Capture & Paste AI Output Modal Component.
 */

import { state } from '../state.js';
import { invoke } from '../bridge.js';

export function renderCaptureModal(container) {
  let activeTab = 'paste'; // 'paste' | 'quick'

  function update() {
    container.innerHTML = `
      <div class="modal-overlay">
        <div class="modal-box">
          <div class="modal-header">
            <span>Fast Intelligence Capture</span>
            <button id="modal-close" class="btn btn-sm">✕</button>
          </div>

          <div class="tab-bar" style="padding: 0 14px;">
            <button id="cap-tab-paste" class="tab-btn ${activeTab === 'paste' ? 'active' : ''}">
              Paste AI Discussion / Delta
            </button>
            <button id="cap-tab-quick" class="tab-btn ${activeTab === 'quick' ? 'active' : ''}">
              Quick Item
            </button>
          </div>

          <div class="modal-body">
            ${activeTab === 'paste' ? `
              <p style="font-size: 11px; color: var(--text-secondary);">
                Paste conversation excerpt, checklists, or <code>scs-delta</code> block. Items will be staged to the Proposal Inbox.
              </p>
              <textarea id="paste-text" style="width: 100%; height: 140px; background: var(--bg-input); color: var(--text-primary); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px; font-family: var(--font-mono); font-size: 11px; resize: vertical;" placeholder="Paste AI chat response or decision block..."></textarea>
              <div style="display: flex; gap: 6px;">
                <button id="btn-paste-clipboard" class="btn btn-sm">📋 Paste from Clipboard</button>
              </div>
            ` : `
              <div style="display: flex; flex-direction: column; gap: 8px;">
                <div>
                  <label style="font-size: 10px; color: var(--text-muted); text-transform: uppercase;">Item Type</label>
                  <select id="quick-type" class="project-select" style="width: 100%; max-width: none;">
                    <option value="TASK">📋 Task (Action Item)</option>
                    <option value="DECISION">⚡ Decision (Architectural Choice)</option>
                    <option value="CONSTRAINT">🔒 Constraint (Hard Limit / Rule)</option>
                    <option value="REJECTED_OPTION">⛔ Do Not Repeat (Rejected Alternative)</option>
                    <option value="BLOCKER">🛑 Blocker (Blocking Issue)</option>
                    <option value="IDEA">💡 Idea (Future Consideration)</option>
                    <option value="ARTIFACT">📦 Artifact (File / Document Reference)</option>
                  </select>
                </div>
                <div>
                  <label style="font-size: 10px; color: var(--text-muted); text-transform: uppercase;">Title / Statement</label>
                  <input id="quick-title" type="text" class="mission-input" style="width: 100%; background: var(--bg-input); border: 1px solid var(--border);" placeholder="What was decided or needs to be done?" />
                </div>
                <div>
                  <label style="font-size: 10px; color: var(--text-muted); text-transform: uppercase;">Why it matters (Rationale)</label>
                  <input id="quick-why" type="text" class="mission-input" style="width: 100%; background: var(--bg-input); border: 1px solid var(--border);" placeholder="Architectural reason or justification..." />
                </div>
                <div id="quick-art-row" style="display: none;">
                  <label style="font-size: 10px; color: var(--text-muted); text-transform: uppercase;">Relative Path (Optional)</label>
                  <input id="quick-path" type="text" class="mission-input" style="width: 100%; background: var(--bg-input); border: 1px solid var(--border);" placeholder="e.g. src/index.js or docs/spec.md" />
                </div>
              </div>
            `}
          </div>

          <div class="modal-footer">
            <button id="btn-cancel" class="btn">Cancel</button>
            ${activeTab === 'paste' ? `
              <button id="btn-stage-paste" class="btn btn-primary">Stage to Proposal Inbox</button>
            ` : `
              <button id="btn-stage-quick" class="btn">Stage to Inbox</button>
              <button id="btn-direct-add" class="btn btn-primary">✓ Approve & Add</button>
            `}
          </div>
        </div>
      </div>
    `;

    // Bindings
    container.querySelector('#modal-close')?.addEventListener('click', close);
    container.querySelector('#btn-cancel')?.addEventListener('click', close);

    container.querySelector('#cap-tab-paste')?.addEventListener('click', () => { activeTab = 'paste'; update(); });
    container.querySelector('#cap-tab-quick')?.addEventListener('click', () => { activeTab = 'quick'; update(); });

    container.querySelector('#btn-paste-clipboard')?.addEventListener('click', async () => {
      try {
        const res = await invoke('window_control', { action: 'read_clipboard' });
        const ta = container.querySelector('#paste-text');
        if (ta && res.text) ta.value = res.text;
      } catch (_) {}
    });

    container.querySelector('#quick-type')?.addEventListener('change', (e) => {
      const artRow = container.querySelector('#quick-art-row');
      if (artRow) artRow.style.display = e.target.value === 'ARTIFACT' ? 'block' : 'none';
    });

    // Stage from Paste
    container.querySelector('#btn-stage-paste')?.addEventListener('click', async () => {
      const p = state.dashboard?.active_project;
      const text = container.querySelector('#paste-text')?.value || '';
      if (!p || !text.trim()) return;
      try {
        const staged = await invoke('stage_raw_capture', { project_id: p.id, raw_text: text });
        state.showToast(`Staged ${staged.length} items to Proposal Inbox`);
        close();
        state.refreshDashboard();
      } catch (err) {
        state.showToast(err.message, 'error');
      }
    });

    // Stage Quick
    container.querySelector('#btn-stage-quick')?.addEventListener('click', async () => {
      const p = state.dashboard?.active_project;
      const title = container.querySelector('#quick-title')?.value || '';
      const why = container.querySelector('#quick-why')?.value || '';
      const type = container.querySelector('#quick-type')?.value || 'TASK';
      const relPath = container.querySelector('#quick-path')?.value || '';
      if (!p || !title.trim()) return;
      try {
        await invoke('stage_proposal', {
          project_id: p.id,
          proposal_type: type,
          title: title.trim(),
          rationale_why: why.trim(),
          relative_path: relPath.trim(),
        });
        state.showToast('Staged to Proposal Inbox');
        close();
        state.refreshDashboard();
      } catch (err) {
        state.showToast(err.message, 'error');
      }
    });

    // Direct Add
    container.querySelector('#btn-direct-add')?.addEventListener('click', async () => {
      const p = state.dashboard?.active_project;
      const title = container.querySelector('#quick-title')?.value || '';
      const why = container.querySelector('#quick-why')?.value || '';
      const type = container.querySelector('#quick-type')?.value || 'TASK';
      const relPath = container.querySelector('#quick-path')?.value || '';
      if (!p || !title.trim()) return;
      try {
        await invoke('create_approved_item', {
          project_id: p.id,
          proposal_type: type,
          title,
          rationale_why: why,
          relative_path: relPath,
        });
        state.showToast(`Added ${type}`);
        close();
        state.refreshDashboard();
      } catch (err) {
        state.showToast(err.message, 'error');
      }
    });
  }

  function close() {
    container.innerHTML = '';
  }

  window.__openCaptureModal = () => {
    update();
  };
}
