import { icons } from '../icons.js';

export function expandBtn(collapsed) {
  return collapsed
    ? `<button type="button" class="icon-btn" data-action="collapse-left" title="展开">${icons.panelLeftOpen(15)}</button>`
    : '';
}

export function taskWorkspaceShell({ testId, collapsed, mobilePane }) {
  return `
    <div class="ws ws-task ${collapsed ? 'is-collapsed' : ''}" data-mobile="${mobilePane}" data-testid="${testId}">
      <div class="mobile-switch">
        <button type="button" class="seg ${mobilePane === 'ai' ? 'is-active' : ''}" data-action="mobile-pane" data-pane="ai">AI</button>
        <button type="button" class="seg ${mobilePane === 'content' ? 'is-active' : ''}" data-action="mobile-pane" data-pane="content">内容</button>
      </div>
      <aside class="pane pane-ai"></aside>
      <main class="pane pane-content"></main>
    </div>
  `;
}
