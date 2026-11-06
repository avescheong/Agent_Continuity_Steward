/**
 * Sleek Desktop Dialog Modals (Replaces blocking window.prompt / confirm).
 */

const getContainer = () => document.getElementById('dialog-modal-container');

export function showPromptDialog({
  title = 'Input Required',
  label = 'Value',
  defaultValue = '',
  placeholder = '',
  confirmText = 'OK',
  onConfirm,
}) {
  const container = getContainer();
  if (!container) return;

  container.innerHTML = `
    <div class="modal-overlay">
      <div class="modal-box" style="max-width: 380px;">
        <div class="modal-header">
          <span>${escapeHtml(title)}</span>
          <button id="dlg-close" class="btn btn-sm">✕</button>
        </div>
        <div class="modal-body" style="display: flex; flex-direction: column; gap: 8px;">
          <label style="font-size: 11px; color: var(--text-muted); text-transform: uppercase;">
            ${escapeHtml(label)}
          </label>
          <input
            id="dlg-input"
            type="text"
            class="mission-input"
            style="width: 100%; background: var(--bg-input); border: 1px solid var(--border);"
            value="${escapeHtml(defaultValue)}"
            placeholder="${escapeHtml(placeholder)}"
          />
        </div>
        <div class="modal-footer">
          <button id="dlg-cancel" class="btn">Cancel</button>
          <button id="dlg-confirm" class="btn btn-primary">${escapeHtml(confirmText)}</button>
        </div>
      </div>
    </div>
  `;

  const input = container.querySelector('#dlg-input');
  input?.focus();
  input?.select();

  const close = () => {
    container.innerHTML = '';
  };

  const submit = () => {
    const val = input?.value || '';
    close();
    if (onConfirm) onConfirm(val);
  };

  container.querySelector('#dlg-close')?.addEventListener('click', close);
  container.querySelector('#dlg-cancel')?.addEventListener('click', close);
  container.querySelector('#dlg-confirm')?.addEventListener('click', submit);

  input?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      submit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      close();
    }
  });
}

export function showProjectDialog({ onConfirm }) {
  const container = getContainer();
  if (!container) return;

  container.innerHTML = `
    <div class="modal-overlay">
      <div class="modal-box" style="max-width: 400px;">
        <div class="modal-header">
          <span>Create New Project</span>
          <button id="dlg-close" class="btn btn-sm">✕</button>
        </div>
        <div class="modal-body" style="display: flex; flex-direction: column; gap: 10px;">
          <div>
            <label style="font-size: 10px; color: var(--text-muted); text-transform: uppercase;">
              Project Code (Unique Identifier)
            </label>
            <input
              id="dlg-proj-code"
              type="text"
              class="mission-input"
              style="width: 100%; background: var(--bg-input); border: 1px solid var(--border); text-transform: uppercase;"
              placeholder="e.g. PRJ_BETA"
            />
          </div>
          <div>
            <label style="font-size: 10px; color: var(--text-muted); text-transform: uppercase;">
              Project Name / Title
            </label>
            <input
              id="dlg-proj-name"
              type="text"
              class="mission-input"
              style="width: 100%; background: var(--bg-input); border: 1px solid var(--border);"
              placeholder="e.g. Production Beta Launch"
            />
          </div>
        </div>
        <div class="modal-footer">
          <button id="dlg-cancel" class="btn">Cancel</button>
          <button id="dlg-create" class="btn btn-primary">Create Project</button>
        </div>
      </div>
    </div>
  `;

  const codeInput = container.querySelector('#dlg-proj-code');
  const nameInput = container.querySelector('#dlg-proj-name');
  codeInput?.focus();

  const close = () => {
    container.innerHTML = '';
  };

  const submit = () => {
    const code = codeInput?.value.trim().toUpperCase() || '';
    const name = nameInput?.value.trim() || '';
    if (!code || !name) return;
    close();
    if (onConfirm) onConfirm({ code, name });
  };

  container.querySelector('#dlg-close')?.addEventListener('click', close);
  container.querySelector('#dlg-cancel')?.addEventListener('click', close);
  container.querySelector('#dlg-create')?.addEventListener('click', submit);

  const handleKey = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      submit();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      close();
    }
  };
  codeInput?.addEventListener('keydown', handleKey);
  nameInput?.addEventListener('keydown', handleKey);
}

export function showConfirmDialog({
  title = 'Confirm Action',
  message = 'Are you sure you want to proceed?',
  confirmText = 'Delete',
  onConfirm,
}) {
  const container = getContainer();
  if (!container) return;

  container.innerHTML = `
    <div class="modal-overlay">
      <div class="modal-box" style="max-width: 360px;">
        <div class="modal-header">
          <span>${escapeHtml(title)}</span>
          <button id="dlg-close" class="btn btn-sm">✕</button>
        </div>
        <div class="modal-body">
          <p style="font-size: 12px; color: var(--text-secondary); margin: 0;">
            ${escapeHtml(message)}
          </p>
        </div>
        <div class="modal-footer">
          <button id="dlg-cancel" class="btn">Cancel</button>
          <button id="dlg-confirm" class="btn" style="background: rgba(244, 63, 94, 0.2); color: var(--color-missing); border: 1px solid var(--color-missing);">
            ${escapeHtml(confirmText)}
          </button>
        </div>
      </div>
    </div>
  `;

  const close = () => {
    container.innerHTML = '';
  };

  const submit = () => {
    close();
    if (onConfirm) onConfirm();
  };

  container.querySelector('#dlg-close')?.addEventListener('click', close);
  container.querySelector('#dlg-cancel')?.addEventListener('click', close);
  container.querySelector('#dlg-confirm')?.addEventListener('click', submit);
}

function escapeHtml(text) {
  return String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
