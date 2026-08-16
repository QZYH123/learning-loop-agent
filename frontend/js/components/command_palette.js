/**
 * Command Palette Component (Ctrl+K)
 */

import { icons } from '../icons.js';

export function renderCommandPalette(state, container, handlers) {
  if (!state.commandPaletteOpen) {
    container.innerHTML = '';
    return;
  }

  const { activeNavTab, workspace, activeSubjectId, models, currentModelId } = state;
  const activeSubject = workspace.subjects?.find((s) => s.id === activeSubjectId);
  const activeModel = models?.find((m) => m.id === currentModelId) || models?.[0];

  const commands = [
    { id: 'nav-learn', label: '切换到「学习」工作区', category: '导航', icon: icons.book(15), action: () => handlers.onSelectNavTab?.('learn') },
    { id: 'nav-sources', label: '切换到「资料」工作区', category: '导航', icon: icons.layers(15), action: () => handlers.onSelectNavTab?.('sources') },
    { id: 'nav-quiz_gen', label: '切换到「组卷」工作区', category: '导航', icon: icons.compass(15), action: () => handlers.onSelectNavTab?.('quiz_gen') },
    { id: 'nav-attempts', label: '切换到「作答」工作区', category: '导航', icon: icons.target(15), action: () => handlers.onSelectNavTab?.('attempts') },
    { id: 'act-model-config', label: '打开模型配置', category: '模型', icon: icons.cpu(15), action: () => handlers.onOpenModelModal?.() },
    { id: 'act-create-session', label: '新建学习会话', category: '学习', icon: icons.plus(15), action: () => handlers.onOpenCreateSessionModal?.() },
    { id: 'act-create-subject', label: '新建科目空间', category: '科目', icon: icons.plus(15), action: () => handlers.onOpenSubjectModal?.('create') },
    { id: 'act-create-aidoc', label: '新建 AI 资料文档', category: '资料', icon: icons.fileText(15), action: () => handlers.onOpenCreateAiDocModal?.() },
    { id: 'act-create-blueprint', label: '新建组卷蓝图', category: '组卷', icon: icons.plus(15), action: () => handlers.onOpenBlueprintModal?.() },
    { id: 'act-toggle-theme', label: '切换浅色/暗色主题', category: '视图', icon: icons.sun(15), action: () => handlers.onToggleTheme?.() }
  ];

  container.innerHTML = `
    <div class="cmd-palette-backdrop" id="cmd-backdrop">
      <div class="cmd-palette-modal" role="dialog" aria-modal="true" aria-label="快捷命令">
        <div class="cmd-input-row">
          <span class="cmd-search-icon">${icons.search(16)}</span>
          <input
            type="text"
            class="cmd-search-input"
            id="cmd-palette-input"
            placeholder="搜索命令或工作区... (Esc 退出)"
            autocomplete="off"
            autofocus
          />
          <button type="button" class="btn-icon-subtle" id="cmd-close-btn" title="关闭">${icons.x(14)}</button>
        </div>

        <div class="cmd-results-list" id="cmd-results">
          ${commands
            .map(
              (cmd, idx) => `
            <div class="cmd-item ${idx === 0 ? 'is-focused' : ''}" data-cmd-id="${cmd.id}" role="button" tabindex="0">
              <span class="cmd-item-icon">${cmd.icon}</span>
              <span class="cmd-item-title">${escapeHtml(cmd.label)}</span>
              <span class="cmd-item-category">${escapeHtml(cmd.category)}</span>
            </div>
          `
            )
            .join('')}
        </div>
      </div>
    </div>
  `;

  const input = container.querySelector('#cmd-palette-input');
  if (input) {
    input.focus();
    input.oninput = () => {
      const q = input.value.toLowerCase().trim();
      const filtered = commands.filter((c) => c.label.toLowerCase().includes(q) || c.category.toLowerCase().includes(q));
      const resultsContainer = container.querySelector('#cmd-results');
      if (resultsContainer) {
        resultsContainer.innerHTML = filtered.length === 0
          ? `<div class="cmd-empty-hint">未找到匹配命令</div>`
          : filtered
              .map(
                (cmd, idx) => `
              <div class="cmd-item ${idx === 0 ? 'is-focused' : ''}" data-cmd-id="${cmd.id}" role="button" tabindex="0">
                <span class="cmd-item-icon">${cmd.icon}</span>
                <span class="cmd-item-title">${escapeHtml(cmd.label)}</span>
                <span class="cmd-item-category">${escapeHtml(cmd.category)}</span>
              </div>
            `
              )
              .join('');

        attachCmdItemEvents();
      }
    };
  }

  function attachCmdItemEvents() {
    container.querySelectorAll('.cmd-item').forEach((el) => {
      el.onclick = () => {
        const cid = el.getAttribute('data-cmd-id');
        const found = commands.find((c) => c.id === cid);
        if (found) {
          handlers.onCloseCommandPalette?.();
          found.action();
        }
      };
    });
  }

  attachCmdItemEvents();

  const backdrop = container.querySelector('#cmd-backdrop');
  if (backdrop) {
    backdrop.onclick = (e) => {
      if (e.target === backdrop) handlers.onCloseCommandPalette?.();
    };
  }

  const closeBtn = container.querySelector('#cmd-close-btn');
  if (closeBtn) {
    closeBtn.onclick = () => handlers.onCloseCommandPalette?.();
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
