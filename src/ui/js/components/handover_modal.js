/**
 * Master AI Handover Package & Human Operator Recovery Suite Component.
 *
 * Compiles approved canonical SQLite state into TWO specialized continuity deliverables:
 * 1. AI_HANDOVER_PACKAGE.md (Target: Fresh AI session rehydration)
 * 2. HUMAN_BRIEFING.md (Target: Human operator recovery briefing in ~3 minutes)
 */

import { state } from '../state.js';
import { invoke } from '../bridge.js';
import { showPromptDialog } from './dialog_modal.js';

export function renderHandoverModal(container) {
  function openHandoverModal() {
    const p = state.dashboard?.active_project;
    if (!p) return;

    const d = state.dashboard || {};
    const chapters = d.continuity_chapters || [];
    const totalSess = d.total_sessions || 0;
    const procSess = d.processed_sessions || 0;
    const pendSess = d.pending_sessions || 0;

    let activeTab = 'ai'; // 'ai' | 'human' | 'recovery'
    let aiContent = '';
    let humanContent = '';
    let recoveryContent = '';
    let aiFileName = `${p.code}_AI_HANDOVER_PACKAGE.md`;
    let humanFileName = `${p.code}_HUMAN_BRIEFING.md`;
    let recoveryFileName = `${p.code}_PROJECT_RECOVERY_CARD.md`;

    container.innerHTML = `
      <div class="modal-overlay">
        <div class="modal-box" style="max-width: 760px;">
          <div class="modal-header">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span>📦 Triple Continuity Suite — ${escapeHtml(p.name)} (${escapeHtml(p.code)})</span>
              <span style="font-size: 10px; background: rgba(99, 102, 241, 0.15); color: var(--color-pending); padding: 2px 6px; border-radius: var(--radius-sm); font-weight: 700;">
                ${chapters.length} Chapter(s)
              </span>
            </div>
            <button id="modal-close-h" class="btn btn-sm">✕</button>
          </div>

          <div class="modal-body" style="display: flex; flex-direction: column; gap: 10px;">
            <!-- Continuity Chapters Coverage -->
            <div>
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <span style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">
                  Archived Continuity Chapters (${procSess}/${totalSess} sessions sealed${pendSess > 0 ? `, ${pendSess} pending` : ''})
                </span>
                <button id="btn-create-snap" class="btn btn-sm" title="Seal standalone continuity snapshot">
                  📸 Quick Snapshot
                </button>
              </div>

              <div style="max-height: 90px; overflow-y: auto; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 6px;">
                ${chapters.length === 0 ? `
                  <div style="font-size: 11px; color: var(--text-muted); text-align: center; padding: 12px;">
                    No Continuity MD chapters generated yet. Use "⚡ Generate Continuity MD" on pending sessions first.
                  </div>
                ` : `
                  ${chapters.map(c => `
                    <div style="display: flex; justify-content: space-between; font-size: 11px; padding: 3px 0; border-bottom: 1px solid var(--border-subtle);">
                      <div>
                        <strong style="color: var(--color-verified);">${escapeHtml(c.chapter_code)}</strong>
                        <span style="color: var(--text-secondary); margin-left: 6px;">(${escapeHtml(c.session_range)})</span>
                      </div>
                      <div style="font-family: var(--font-mono); font-size: 10px; color: var(--text-muted);">
                        Seal: <span style="color: var(--color-local);">${escapeHtml(c.snapshot_code)}</span>
                      </div>
                    </div>
                  `).join('')}
                `}
              </div>
            </div>

            <!-- 3-Way View Switcher & Generate Action -->
            <div>
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap; gap: 6px;">
                <!-- Segmented Tabs for 3 Outputs -->
                <div style="display: flex; gap: 4px; background: var(--bg-input); padding: 2px; border-radius: var(--radius-sm); border: 1px solid var(--border);">
                  <button id="tab-view-ai" class="btn btn-sm" style="background: var(--color-pending); color: #fff; font-weight: 600;">
                    📦 AI Handover (Machine)
                  </button>
                  <button id="tab-view-human" class="btn btn-sm" style="background: transparent; color: var(--text-secondary); font-weight: 600;">
                    👤 Human Briefing (Detailed)
                  </button>
                  <button id="tab-view-recovery" class="btn btn-sm" style="background: transparent; color: var(--text-secondary); font-weight: 600;">
                    ✅ Recovery Card (Fast Checklist)
                  </button>
                </div>

                <button id="btn-gen-handover" class="btn btn-primary" style="font-weight: 700;">
                  ⚡ Generate Continuity Suite
                </button>
              </div>

              <textarea
                id="handover-text"
                style="width: 100%; height: 210px; background: var(--bg-input); color: var(--text-primary); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px; font-family: var(--font-mono); font-size: 10px; line-height: 1.4; resize: vertical;"
                readonly
                placeholder="Click 'Generate Continuity Suite' to produce AI Handover Package, Human Briefing, and Project Recovery Card..."
              ></textarea>
            </div>
          </div>

          <div class="modal-footer" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;">
            <button id="btn-close-h" class="btn">Close</button>
            <div style="display: flex; gap: 6px; flex-wrap: wrap;">
              <button id="btn-copy-recovery" class="btn" style="display: none; background: rgba(16, 185, 129, 0.15); color: var(--color-verified); border-color: rgba(16, 185, 129, 0.4); font-weight: 600;">
                ✅ Copy Recovery Card
              </button>
              <button id="btn-copy-human" class="btn" style="display: none; background: rgba(56, 189, 248, 0.15); color: var(--color-local); border-color: rgba(56, 189, 248, 0.4); font-weight: 600;">
                👤 Copy Human Briefing
              </button>
              <button id="btn-copy-ai" class="btn btn-primary" style="display: none; font-weight: 600;">
                📦 Copy AI Handover
              </button>
            </div>
          </div>
        </div>
      </div>
    `;

    const close = () => {
      container.innerHTML = '';
    };

    container.querySelector('#modal-close-h')?.addEventListener('click', close);
    container.querySelector('#btn-close-h')?.addEventListener('click', close);

    const ta = container.querySelector('#handover-text');
    const tabAi = container.querySelector('#tab-view-ai');
    const tabHuman = container.querySelector('#tab-view-human');
    const tabRecovery = container.querySelector('#tab-view-recovery');
    const btnCopyAi = container.querySelector('#btn-copy-ai');
    const btnCopyHuman = container.querySelector('#btn-copy-human');
    const btnCopyRecovery = container.querySelector('#btn-copy-recovery');

    const updateView = () => {
      [tabAi, tabHuman, tabRecovery].forEach(t => {
        if (t) {
          t.style.background = 'transparent';
          t.style.color = 'var(--text-secondary)';
        }
      });

      if (activeTab === 'ai') {
        if (tabAi) {
          tabAi.style.background = 'var(--color-pending)';
          tabAi.style.color = '#fff';
        }
        if (ta) ta.value = aiContent;
      } else if (activeTab === 'human') {
        if (tabHuman) {
          tabHuman.style.background = 'var(--color-local)';
          tabHuman.style.color = '#000';
        }
        if (ta) ta.value = humanContent;
      } else if (activeTab === 'recovery') {
        if (tabRecovery) {
          tabRecovery.style.background = 'var(--color-verified)';
          tabRecovery.style.color = '#000';
        }
        if (ta) ta.value = recoveryContent;
      }
    };

    tabAi?.addEventListener('click', () => {
      activeTab = 'ai';
      updateView();
    });

    tabHuman?.addEventListener('click', () => {
      activeTab = 'human';
      updateView();
    });

    tabRecovery?.addEventListener('click', () => {
      activeTab = 'recovery';
      updateView();
    });

    // Standalone quick snapshot
    container.querySelector('#btn-create-snap')?.addEventListener('click', () => {
      showPromptDialog({
        title: 'Seal Continuity Snapshot',
        label: 'Snapshot Label (Optional)',
        defaultValue: 'Milestone Snapshot',
        placeholder: 'e.g. Phase 5 Complete',
        confirmText: 'Seal Snapshot',
        onConfirm: async (label) => {
          try {
            const snp = await invoke('create_snapshot', { project_id: p.id, label: label || 'Milestone Snapshot' });
            state.showToast(`Sealed Snapshot ${snp.snapshot_code}`);
            await state.refreshDashboard();
            openHandoverModal();
          } catch (err) {
            state.showToast(err.message, 'error');
          }
        },
      });
    });

    // Generate Triple Continuity Suite (AI Handover + Human Briefing + Recovery Card)
    container.querySelector('#btn-gen-handover')?.addEventListener('click', async () => {
      try {
        state.showToast('Compiling continuity suite (AI Handover + Human Briefing + Recovery Card)...');
        const pkg = await invoke('generate_handover', { project_id: p.id, save_to_exports: true });
        aiContent = pkg.markdown_content || '';
        humanContent = pkg.human_briefing_content || '';
        recoveryContent = pkg.recovery_card_content || '';
        aiFileName = pkg.file_name || aiFileName;
        humanFileName = pkg.human_file_name || humanFileName;
        recoveryFileName = pkg.recovery_file_name || recoveryFileName;

        updateView();

        // Default copy: if viewing recovery tab copy recovery card; if human copy briefing; else copy AI handover
        let textToCopy = aiContent;
        if (activeTab === 'recovery') {
          textToCopy = recoveryContent;
        } else if (activeTab === 'human') {
          textToCopy = humanContent;
        }
        await invoke('window_control', { action: 'copy_clipboard', text: textToCopy });

        state.showToast(`Compiled & Saved AI Handover, Human Briefing & Recovery Card!`);
        await state.refreshDashboard();

        if (btnCopyAi) btnCopyAi.style.display = 'inline-flex';
        if (btnCopyHuman) btnCopyHuman.style.display = 'inline-flex';
        if (btnCopyRecovery) btnCopyRecovery.style.display = 'inline-flex';
      } catch (err) {
        state.showToast(err.message, 'error');
      }
    });

    // Copy Fast Project Recovery Card
    btnCopyRecovery?.addEventListener('click', async () => {
      if (recoveryContent) {
        await invoke('window_control', { action: 'copy_clipboard', text: recoveryContent });
        state.showToast(`Copied ${recoveryFileName} to clipboard`);
      }
    });

    // Copy Human Operator Briefing
    btnCopyHuman?.addEventListener('click', async () => {
      if (humanContent) {
        await invoke('window_control', { action: 'copy_clipboard', text: humanContent });
        state.showToast(`Copied ${humanFileName} to clipboard`);
      }
    });

    // Copy AI Handover Package
    btnCopyAi?.addEventListener('click', async () => {
      if (aiContent) {
        await invoke('window_control', { action: 'copy_clipboard', text: aiContent });
        state.showToast(`Copied ${aiFileName} to clipboard`);
      }
    });
  }

  window.__openHandoverModal = openHandoverModal;
}

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
