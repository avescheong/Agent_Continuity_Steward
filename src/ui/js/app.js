/**
 * Main Application Bootstrap & Keyboard Navigation.
 */

import { state } from './state.js';
import { renderPillHeader } from './components/pill_header.js';
import { renderInboxBanner } from './components/inbox_banner.js';
import { renderTasksTab } from './components/tasks_tab.js';
import { renderDecisionsTab } from './components/decisions_tab.js';
import { renderArtifactsTab } from './components/artifacts_tab.js';
import { renderCaptureModal } from './components/capture_modal.js';
import { renderHandoverModal } from './components/handover_modal.js';
import { renderBootstrapModal } from './components/bootstrap_modal.js';
import { renderFragmentStrip } from './components/fragment_strip.js';
import { renderCheckpointModal } from './components/checkpoint_modal.js';
import { invoke } from './bridge.js';

async function initApp() {
  const pillContainer = document.getElementById('pill-container');
  const missionContainer = document.getElementById('mission-container');
  const fragmentContainer = document.getElementById('fragment-container');
  const inboxContainer = document.getElementById('inbox-container');
  const contentPane = document.getElementById('content-pane');
  const captureModalContainer = document.getElementById('capture-modal-container');
  const handoverModalContainer = document.getElementById('handover-modal-container');
  const bootstrapModalContainer = document.getElementById('bootstrap-modal-container');
  const checkpointModalContainer = document.getElementById('checkpoint-modal-container');

  // Initialize modals
  renderCaptureModal(captureModalContainer);
  renderHandoverModal(handoverModalContainer);
  renderBootstrapModal(bootstrapModalContainer);
  renderCheckpointModal(checkpointModalContainer);

  // Subscribe to state changes
  state.subscribe((s) => {
    renderPillHeader(pillContainer);
    renderMissionStrip(missionContainer);
    renderFragmentStrip(fragmentContainer);
    renderInboxBanner(inboxContainer);
    renderActiveTab(contentPane);

    // Apply view mode visibility (Compact Mode preserves Header, Mission & Session Action Bar)
    const isCompact = s.viewMode === 'pill' || s.viewMode === 'compact';
    document.body.classList.toggle('mode-compact', isCompact);
    document.body.classList.toggle('mode-drawer', !isCompact);

    const inboxArea = document.getElementById('inbox-container');
    const tabBar = document.querySelector('.tab-bar');
    const contentPaneEl = document.getElementById('content-pane');

    if (inboxArea) inboxArea.style.display = isCompact ? 'none' : 'block';
    if (tabBar) tabBar.style.display = isCompact ? 'none' : 'flex';
    if (contentPaneEl) contentPaneEl.style.display = isCompact ? 'none' : 'flex';
  });

  // Tab switching
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.setTab(btn.getAttribute('data-tab'));
    });
  });

  // Keyboard Shortcuts
  window.addEventListener('keydown', (e) => {
    // 1. Ctrl+Shift Shortcuts
    if (e.ctrlKey && e.shiftKey) {
      if (e.key === 'B' || e.key === 'b') {
        e.preventDefault();
        document.getElementById('btn-copy-bootstrap')?.click();
      } else if (e.key === 'N' || e.key === 'n') {
        e.preventDefault();
        window.__openCaptureModal && window.__openCaptureModal();
      } else if (e.key === 'R' || e.key === 'r') {
        e.preventDefault();
        const copyRecoveryBtn = document.getElementById('btn-copy-recovery');
        if (copyRecoveryBtn && copyRecoveryBtn.style.display !== 'none') {
          copyRecoveryBtn.click();
        } else {
          document.getElementById('btn-reconcile')?.click();
        }
      } else if (e.key === 'S' || e.key === 's') {
        e.preventDefault();
        const snapBtn = document.getElementById('btn-snapshot-quick');
        if (snapBtn) {
          snapBtn.click();
        } else {
          const p = state.dashboard?.active_project;
          if (p) {
            invoke('create_snapshot', { project_id: p.id, label: 'Quick Checkpoint' }).then(snp => {
              state.showToast(`Sealed Snapshot ${snp.snapshot_code}`);
              state.refreshDashboard();
            }).catch(err => state.showToast(err.message, 'error'));
          }
        }
      } else if (e.key === 'V' || e.key === 'v') {
        e.preventDefault();
        window.__handleQuickPasteSession ? window.__handleQuickPasteSession() : (window.__handleQuickPasteFragment && window.__handleQuickPasteFragment());
      }
    }
  });

  // Initial load
  await state.refreshDashboard();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}

function renderMissionStrip(container) {
  const p = state.dashboard?.active_project;
  if (!p) {
    container.innerHTML = '';
    return;
  }

  container.innerHTML = `
    <div class="mission-strip">
      <div class="mission-row">
        <span class="mission-label">Focus</span>
        <input id="input-focus" class="mission-input" value="${escapeHtml(p.current_focus || '')}" placeholder="What are you currently working on?" />
        <button id="btn-snapshot-quick" class="btn btn-sm" title="Take Continuity Snapshot">📸</button>
        <button id="btn-handover-open" class="btn btn-sm" title="Session Handover Package">📦</button>
      </div>
      <div class="mission-row">
        <span class="mission-label">Next</span>
        <input id="input-next" class="mission-input" value="${escapeHtml(p.next_action || '')}" placeholder="Immediate next concrete action..." />
      </div>
    </div>
  `;

  // Debounced auto-save on change
  const saveMission = async () => {
    const focusVal = container.querySelector('#input-focus')?.value || '';
    const nextVal = container.querySelector('#input-next')?.value || '';
    try {
      await invoke('update_project_session', {
        project_id: p.id,
        current_focus: focusVal,
        next_action: nextVal,
      });
    } catch (_) {}
  };

  container.querySelector('#input-focus')?.addEventListener('blur', saveMission);
  container.querySelector('#input-next')?.addEventListener('blur', saveMission);

  container.querySelector('#btn-snapshot-quick')?.addEventListener('click', async () => {
    try {
      const snp = await invoke('create_snapshot', { project_id: p.id, label: 'Quick Checkpoint' });
      state.showToast(`Sealed Snapshot ${snp.snapshot_code}`);
      state.refreshDashboard();
    } catch (err) {
      state.showToast(err.message, 'error');
    }
  });

  container.querySelector('#btn-handover-open')?.addEventListener('click', () => {
    window.__openHandoverModal && window.__openHandoverModal();
  });
}

function renderActiveTab(container) {
  if (state.activeTab === 'tasks') {
    renderTasksTab(container);
  } else if (state.activeTab === 'decisions') {
    renderDecisionsTab(container);
  } else if (state.activeTab === 'artifacts') {
    renderArtifactsTab(container);
  } else if (state.activeTab === 'snapshots') {
    renderSnapshotsTab(container);
  }
}

function renderSnapshotsTab(container) {
  const snapshots = state.dashboard?.recent_snapshots || [];
  const chapters = state.dashboard?.continuity_chapters || [];

  if (snapshots.length === 0 && chapters.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 24px 10px; color: var(--text-muted); font-size: 11px;">
        No continuity chapters or snapshots sealed yet.<br>
        Use "⚡ Generate Continuity MD" or "📦 AI Handover Package" to seal continuity.
      </div>
    `;
    return;
  }

  let chaptersHtml = '';
  if (chapters.length > 0) {
    chaptersHtml = `
      <div style="margin-bottom: 10px;">
        <div style="font-size: 10px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px;">
          Sealed Continuity Chapters (${chapters.length})
        </div>
        <div style="display: flex; flex-direction: column; gap: 4px;">
          ${chapters.map(c => `
            <div class="hud-card" style="border-left: 3px solid var(--color-verified);">
              <div class="card-row">
                <span class="card-code" style="color: var(--color-verified); font-weight: 700;">${escapeHtml(c.chapter_code)}</span>
                <span class="card-title">${escapeHtml(c.session_range || '')} (${c.session_count || 0} sessions)</span>
                <span style="font-size: 10px; color: var(--text-muted); font-family: var(--font-mono);">
                  ${(c.created_at || '').substring(0, 16).replace('T', ' ')}
                </span>
              </div>
              <div style="font-size: 10px; color: var(--text-secondary); margin-top: 2px;">
                Seal: <span style="font-family: var(--font-mono); color: var(--color-local);">${escapeHtml(c.snapshot_code || '')}</span>
                ${c.context_summary ? ` — ${escapeHtml(c.context_summary.substring(0, 80))}...` : ''}
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  let snapsHtml = '';
  if (snapshots.length > 0) {
    snapsHtml = `
      <div>
        <div style="font-size: 10px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px;">
          Immutable Snapshots (${snapshots.length})
        </div>
        <div style="display: flex; flex-direction: column; gap: 4px;">
          ${snapshots.map(s => `
            <div class="hud-card">
              <div class="card-row">
                <span class="card-code" style="color: var(--color-local); font-weight: 700;">${s.snapshot_code}</span>
                <span class="card-title">${s.label || 'Checkpoint'}</span>
                <span style="font-size: 10px; color: var(--text-muted); font-family: var(--font-mono);">
                  ${s.created_at.substring(0, 16).replace('T', ' ')}
                </span>
              </div>
              <div style="font-size: 10px; font-family: var(--font-mono); color: var(--text-secondary);">
                SHA: ${s.checksum_sha256.substring(0, 24)}...
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  container.innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 8px;">
      ${chaptersHtml}
      ${snapsHtml}
    </div>
  `;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
