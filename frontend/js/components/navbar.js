import { icons } from '../icons.js';
import { escapeHtml } from '../util.js';

export function navbarHtml(state) {
  const subject = state.subjects.find((item) => item.id === state.activeSubjectId) || null;
  const model = state.models.find((item) => item.id === state.currentModelId) || state.models[0] || null;
  const busy = (state.operations || []).length;
  const menu = state.openMenu;

  return `
    <header class="nav" data-testid="app-navbar">
      <div class="nav-side">
        <button type="button" class="brand" data-action="go-learn" title="学习">
          <span class="brand-mark">${icons.feather(18)}</span>
          <span class="brand-name">Learning Loop</span>
        </button>
        <span class="v-split"></span>
        <div class="dropdown">
          <button type="button" class="chip-btn" data-action="toggle-menu" data-menu="subject" aria-expanded="${menu === 'subject'}" title="科目">
            ${icons.book(15)}
            <span class="chip-label">${escapeHtml(subject?.name || '选择科目')}</span>
            ${icons.chevronDown(14)}
          </button>
          ${menu === 'subject' ? subjectMenu(state) : ''}
        </div>
      </div>

      <nav class="tabs" aria-label="工作区">
        ${tab('learn', '学习', icons.messageSquare(16), state.workspace === 'learn')}
        ${tab('sources', '资料', icons.folder(16), state.workspace === 'sources')}
        ${tab('exam', '组卷', icons.compass(16), state.workspace === 'exam')}
        ${tab('attempt', '作答', icons.target(16), state.workspace === 'attempt')}
      </nav>

      <div class="nav-side">
        <button type="button" class="chip-btn ${model ? '' : 'is-warn'}" data-action="open-models" title="模型服务">
          ${icons.cpu(15)}
          <span class="chip-label">${escapeHtml(model?.model || '配置模型')}</span>
        </button>
        ${busy ? `<div class="busy">${icons.rotateCw(13, 'spin')}<span>${busy}</span></div>` : ''}
        <button type="button" class="icon-btn" data-action="toggle-theme" title="${state.theme === 'paper' ? '切换深色' : '切换浅色'}">
          ${state.theme === 'paper' ? icons.moon(16) : icons.sun(16)}
        </button>
      </div>
    </header>
  `;
}

export function renderNavbar(state, root, handlers) {
  root.innerHTML = navbarHtml(state);

  root.onclick = (event) => {
    const btn = event.target.closest('[data-action]');
    if (!btn) return;
    event.stopPropagation();
    const action = btn.dataset.action;
    if (action === 'go-learn') handlers.onSelectWorkspace('learn');
    if (action === 'select-workspace') handlers.onSelectWorkspace(btn.dataset.workspace);
    if (action === 'toggle-menu') handlers.onToggleMenu(btn.dataset.menu);
    if (action === 'switch-subject') handlers.onSwitchSubject(btn.dataset.id);
    if (action === 'create-subject') handlers.onOpenModal('subject');
    if (action === 'rename-subject') handlers.onOpenModal('rename-subject');
    if (action === 'delete-subject') handlers.onDeleteSubject();
    if (action === 'open-models') handlers.onOpenModal('models');
    if (action === 'toggle-theme') handlers.onToggleTheme();
  };
}

function tab(id, label, icon, active) {
  return `
    <button type="button" class="tab tab-${id} ${active ? 'is-active' : ''}" data-action="select-workspace" data-workspace="${id}">
      ${icon}<span>${label}</span>
    </button>
  `;
}

function subjectMenu(state) {
  const items = (state.subjects || [])
    .map(
      (item) => `
      <button type="button" class="menu-item ${item.id === state.activeSubjectId ? 'is-active' : ''}" data-action="switch-subject" data-id="${item.id}">
        <span>${escapeHtml(item.name)}</span>
        ${item.id === state.activeSubjectId ? icons.check(14) : ''}
      </button>
    `,
    )
    .join('');
  return `
    <div class="menu" role="menu">
      <div class="menu-title">科目</div>
      ${items || '<div class="menu-title">还没有科目</div>'}
      <div class="menu-split"></div>
      ${
        state.activeSubjectId
          ? `<button type="button" class="menu-item" data-action="rename-subject">${icons.edit3(14)}<span>重命名</span></button>
             <button type="button" class="menu-item" data-action="delete-subject">${icons.trash2(14)}<span>删除科目</span></button>`
          : ''
      }
      <button type="button" class="menu-item" data-action="create-subject">${icons.plus(14)}<span>新建科目</span></button>
    </div>
  `;
}
