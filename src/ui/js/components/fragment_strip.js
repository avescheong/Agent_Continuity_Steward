/**
 * Session Action Bar Component (Session -> Continuity MD -> Handover).
 *
 * Implements the 3 primary actions matching the operator's real workflow:
 * 1. 📋 Paste Session (adds raw AI conversation evidence to temporary processing buffer)
 * 2. ⚡ Generate Continuity MD (runs Caveman on pending sessions to produce unsealed draft)
 * 3. 📦 Create AI Handover Package (merges approved chapters into master handover package)
 */

import { state } from '../state.js';
import { invoke } from '../bridge.js';

export function renderFragmentStrip(container) {
  const p = state.dashboard?.active_project;
  if (!p) {
    container.innerHTML = '';
    return;
  }

  const d = state.dashboard || {};
  const pending = d.pending_sessions ?? d.fragment_count ?? 0;
  const total = d.total_sessions ?? pending;
  const processed = d.processed_sessions ?? (total - pending);
  const mdCount = d.continuity_md_count ?? 0;

  container.innerHTML = `
    <div class="session-bar">
      <!-- Row 1: Primary Action & Session Telemetry -->
      <div class="session-primary-row">
        <button id="btn-paste-session" class="btn btn-primary btn-paste" title="Paste complete raw AI conversation session from clipboard (Ctrl+Shift+V)">
          📋 Paste Session
        </button>
        <div class="session-telemetry" title="Total Sessions: ${total} | Processed: ${processed} | Pending: ${pending}">
          <span class="session-pill ${pending > 0 ? 'has-pending' : ''}">
            ${pending} pending
          </span>
          <span class="session-total">(${total} total${mdCount > 0 ? ` • ${mdCount} MD` : ''})</span>
        </div>
      </div>

      <!-- Row 2: Secondary Continuity Actions -->
      <div class="session-actions-row">
        <button id="btn-gen-continuity" class="btn btn-continuity ${pending > 0 ? 'btn-active-gen' : ''}" ${pending === 0 ? 'disabled' : ''} title="Run Caveman extraction on pending sessions to draft Continuity MD chapter">
          ⚡ Generate Continuity MD ${pending >= 10 ? '★' : ''}
        </button>
        <button id="btn-create-handover" class="btn btn-handover" title="Combine approved Continuity MD chapters into AI_HANDOVER_PACKAGE.md">
          📦 AI Handover Package
        </button>
        ${pending > 0 ? `
          <button id="btn-clear-sessions" class="btn btn-sm btn-icon" title="Clear unapproved pending session buffer">✕</button>
        ` : ''}
      </div>
    </div>
  `;

  // Action 1: 📋 Paste Session
  const handlePasteSession = async () => {
    try {
      const clipRes = await invoke('window_control', { action: 'read_clipboard' });
      const text = clipRes?.text || '';
      if (!text || !text.trim()) {
        state.showToast('Clipboard is empty. Copy complete AI conversation first.', 'error');
        return;
      }

      const res = await invoke('add_chat_fragment', {
        project_id: p.id,
        text: text.trim(),
        source: 'CLIPBOARD',
        prevent_duplicate: true,
      });

      state.showToast(`Saved raw session ${res.session_code} (${res.word_count.toLocaleString()} words). ${res.pending_sessions} pending.`);
      await state.refreshDashboard();
    } catch (err) {
      state.showToast(err.message, 'error');
    }
  };

  // Action 2: ⚡ Generate Continuity MD
  const handleGenerateContinuity = async () => {
    if (pending === 0) return;
    try {
      state.showToast('Extracting continuity context with Caveman Engine...');
      const res = await invoke('generate_checkpoint', { project_id: p.id });
      window.__openCheckpointModal && window.__openCheckpointModal(res);
      await state.refreshDashboard();
    } catch (err) {
      state.showToast(err.message, 'error');
    }
  };

  // Action 3: 📦 Create AI Handover Package
  const handleCreateHandover = () => {
    window.__openHandoverModal && window.__openHandoverModal();
  };

  // Clear unapproved session buffer
  const handleClearSessions = async () => {
    try {
      const res = await invoke('clear_chat_fragments', { project_id: p.id });
      state.showToast(`Cleared ${res.count} pending session(s) from buffer`);
      await state.refreshDashboard();
    } catch (err) {
      state.showToast(err.message, 'error');
    }
  };

  // Attach event listeners
  container.querySelector('#btn-paste-session')?.addEventListener('click', handlePasteSession);
  container.querySelector('#btn-gen-continuity')?.addEventListener('click', handleGenerateContinuity);
  container.querySelector('#btn-create-handover')?.addEventListener('click', handleCreateHandover);
  container.querySelector('#btn-clear-sessions')?.addEventListener('click', handleClearSessions);

  // Global handle for keyboard shortcut Ctrl+Shift+V
  window.__handleQuickPasteSession = handlePasteSession;
  window.__handleQuickPasteFragment = handlePasteSession; // backward-compat
}
