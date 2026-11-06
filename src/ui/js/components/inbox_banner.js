/**
 * Human Approval Inbox Component (Quarantine Gate).
 */

import { state } from '../state.js';
import { invoke } from '../bridge.js';

function formatProposalType(type) {
  switch (type) {
    case 'REJECTED_OPTION': return '⛔ Do Not Repeat';
    case 'CONSTRAINT': return '🔒 Constraint';
    case 'DECISION': return '⚡ Decision';
    case 'TASK': return '📋 Task';
    case 'ARTIFACT': return '📦 Artifact';
    case 'BLOCKER': return '🛑 Blocker';
    case 'IDEA': return '💡 Idea';
    default: return type;
  }
}

export function renderInboxBanner(container) {
  const d = state.dashboard;
  const pending = d?.proposals_pending || [];

  if (pending.length === 0) {
    container.innerHTML = '';
    return;
  }

  container.innerHTML = `
    <div class="inbox-banner" id="inbox-toggle-bar">
      <div style="display: flex; align-items: center;">
        <span class="inbox-badge">${pending.length}</span>
        <strong>Proposed Captures (Pending Human Review)</strong>
      </div>
      <div style="display: flex; gap: 6px; align-items: center;">
        <button id="btn-approve-all" class="btn btn-sm btn-primary">✓ Approve All</button>
        <span style="font-size: 11px; color: var(--text-muted);">${state.inboxExpanded ? '▲' : '▼'}</span>
      </div>
    </div>

    ${state.inboxExpanded ? `
      <div class="inbox-drawer">
        ${pending.map(prop => `
          <div class="proposal-card" data-id="${prop.id}">
            <div class="proposal-header">
              <span class="proposal-tag tag-${prop.proposal_type}">${formatProposalType(prop.proposal_type)}</span>
              <div style="display: flex; gap: 4px;">
                <button class="btn btn-sm btn-approve" data-id="${prop.id}" title="Approve">✓</button>
                <button class="btn btn-sm btn-reject" data-id="${prop.id}" title="Reject">✕</button>
              </div>
            </div>
            <div style="font-size: 11px; font-weight: 600; color: var(--text-primary);">
              ${prop.title}
            </div>
            ${prop.rationale_why ? `
              <div style="font-size: 10px; color: var(--text-secondary);">
                Why: ${prop.rationale_why}
              </div>
            ` : ''}
          </div>
        `).join('')}
      </div>
    ` : ''}
  `;

  // Bindings
  container.querySelector('#inbox-toggle-bar')?.addEventListener('click', (e) => {
    if (e.target.id === 'btn-approve-all') return;
    state.toggleInbox();
  });

  container.querySelector('#btn-approve-all')?.addEventListener('click', async (e) => {
    e.stopPropagation();
    const p = state.dashboard?.active_project;
    if (!p) return;
    try {
      const res = await invoke('approve_all_proposals', { project_id: p.id });
      state.showToast(`Approved ${res.approved_count} proposals`);
      state.refreshDashboard();
    } catch (err) {
      state.showToast(err.message, 'error');
    }
  });

  container.querySelectorAll('.btn-approve').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const id = btn.getAttribute('data-id');
      try {
        await invoke('approve_proposal', { proposal_id: id });
        state.showToast('Proposal approved');
        state.refreshDashboard();
      } catch (err) {
        state.showToast(err.message, 'error');
      }
    });
  });

  container.querySelectorAll('.btn-reject').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const id = btn.getAttribute('data-id');
      try {
        await invoke('reject_proposal', { proposal_id: id });
        state.showToast('Proposal dismissed');
        state.refreshDashboard();
      } catch (err) {
        state.showToast(err.message, 'error');
      }
    });
  });
}
