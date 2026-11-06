/**
 * Central Reactive Store & State Controller for SCS-HUD UI.
 */

import { invoke } from './bridge.js';

export const state = {
  dashboard: null,
  activeTab: 'tasks',       // 'tasks' | 'decisions' | 'artifacts' | 'snapshots'
  viewMode: 'drawer',       // 'pill' | 'drawer' | 'inspector'
  isPinned: true,
  isGhost: false,
  inboxExpanded: false,
  listeners: [],

  subscribe(listener) {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter(l => l !== listener);
    };
  },

  notify() {
    for (const listener of this.listeners) {
      listener(this);
    }
  },

  async refreshDashboard(projectId = null) {
    try {
      const pId = projectId || (this.dashboard?.active_project?.id);
      const data = await invoke('get_dashboard_state', { project_id: pId });
      this.dashboard = data;
      this.notify();
    } catch (err) {
      this.showToast(`Failed to load state: ${err.message}`, 'error');
    }
  },

  async switchProject(projectId) {
    await this.refreshDashboard(projectId);
  },

  setTab(tab) {
    this.activeTab = tab;
    this.notify();
  },

  async setViewMode(mode) {
    this.viewMode = mode;
    this.notify();
    try {
      await invoke('window_control', { action: 'set_view_mode', mode });
    } catch (_) {}
    try {
      if (mode === 'compact' || mode === 'pill') {
        window.resizeTo(430, 220);
      } else {
        window.resizeTo(430, 680);
      }
    } catch (_) {}
  },

  async togglePin() {
    this.isPinned = !this.isPinned;
    this.notify();
    try {
      await invoke('window_control', { action: 'toggle_pin', topmost: this.isPinned });
    } catch (_) {}
  },

  async toggleGhost() {
    this.isGhost = !this.isGhost;
    this.notify();
    try {
      await invoke('window_control', { action: 'toggle_ghost', ghost: this.isGhost });
    } catch (_) {}
  },

  toggleInbox() {
    this.inboxExpanded = !this.inboxExpanded;
    this.notify();
  },

  showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    if (type === 'error') {
      toast.style.borderLeftColor = 'var(--color-missing)';
    }
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      setTimeout(() => toast.remove(), 200);
    }, 2800);
  }
};
