/**
 * Universal RPC Client Bridge for SCS-HUD.
 *
 * Supports:
 * 1. Local Starlette/Uvicorn HTTP RPC with per-session token (/api/invoke)
 * 2. pywebview JS API
 * 3. Future Tauri v2 core via window.__TAURI_INTERNALS__.invoke
 */

export async function invoke(command, payload = {}) {
  // 1. Future Tauri v2 check
  if (window.__TAURI_INTERNALS__ && typeof window.__TAURI_INTERNALS__.invoke === 'function') {
    return await window.__TAURI_INTERNALS__.invoke(command, payload);
  }

  // 2. pywebview check
  if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.invoke === 'function') {
    return await window.pywebview.api.invoke(command, payload);
  }

  // 3. Standard Local RPC Server fallback (/api/invoke)
  const token = window.__SCS_SESSION_TOKEN__ || '';
  const response = await fetch('/api/invoke', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-SCS-Token': token,
    },
    body: JSON.stringify({ command, payload }),
  });

  if (!response.ok) {
    const errText = await response.text();
    let errJson = null;
    try { errJson = JSON.parse(errText); } catch (_) {}
    throw new Error(errJson?.error?.message || `HTTP error ${response.status}: ${errText}`);
  }

  const envelope = await response.json();
  if (!envelope.ok) {
    throw new Error(envelope.error?.message || 'RPC Command Failed');
  }

  return envelope.data;
}
