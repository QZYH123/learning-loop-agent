/**
 * Primary Navigation Header Component
 * Aligned with Issue 18, 19, 22:
 * 4 Primary Workspaces: 学习 (learn), 资料 (sources), 组卷 (quiz_gen), 作答 (attempts)
 * Clean, concise, single "模型配置" modal entrance, accessible dropdowns.
 */

import { icons } from '../icons.js';

export function renderNavbar(state, container, handlers) {
  const { workspace, activeSubjectId, models, currentModelId, activeNavTab, activeOperations, theme } = state;
  const activeSubject = workspace.subjects?.find((s) => s.id === activeSubjectId) || null;
  const subjects = workspace.subjects || [];

  const activeModelId = currentModelId || state.chat?.active_model_id;
  const activeModel = models?.find((m) => m.id === activeModelId) || models?.[0] || null;

  const runningOps = Array.from(activeOperations.values()).filter(
    (op) => op.status === 'queued' || op.status === 'running'
  );
  const isRunning = runningOps.length > 0;

  // 4 Primary Workspaces (2-4 characters each)
  const navTabs = [
    { id: 'learn', label: '学习', icon: icons.book(15) },
    { id: 'sources', label: '资料', icon: icons.layers(15) },
    { id: 'quiz_gen', label: '组卷', icon: icons.compass(15) },
    { id: 'attempts', label: '作答', icon: icons.target(15) }
  ];

  container.innerHTML = `
    <header class="app-header-navbar" role="banner" data-testid="app-navbar">
      <!-- Left: Brand & Subject Space Switcher -->
      <div class="nav-left">
        <div class="brand-item" id="brand-home-btn" role="button" tabindex="0" title="学习工作台">
          <div class="brand-icon">${icons.feather(18)}</div>
          <span class="brand-title">Learning Loop</span>
        </div>

        <div class="nav-divider"></div>

        <!-- Subject Switcher Dropdown Anchor -->
        <div class="dropdown-anchor" id="subject-dropdown-anchor">
          <button
            type="button"
            class="btn-dropdown-trigger"
            id="btn-subject-dropdown"
            aria-haspopup="true"
            aria-expanded="false"
            title="切换或管理科目"
          >
            ${icons.book(14)}
            <span class="dropdown-trigger-label" style="max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
              ${escapeHtml(activeSubject?.name || '选择科目')}
            </span>
            ${icons.chevronDown(13)}
          </button>

          <div class="dropdown-popup" id="subject-popup-menu" role="menu" style="display: none;">
            <div class="dropdown-header">
              <span class="dropdown-header-title">科目空间</span>
              <button type="button" class="btn-text-action" id="btn-create-subject-trigger">
                ${icons.plus(13)} 新建
              </button>
            </div>

            <div class="dropdown-items-list" role="presentation">
              ${
                subjects.length === 0
                  ? `<div class="dropdown-empty-hint">暂无科目空间</div>`
                  : subjects
                      .map(
                        (subj) => `
                    <div
                      class="dropdown-menu-item ${subj.id === activeSubjectId ? 'is-active' : ''}"
                      data-subject-id="${subj.id}"
                      role="menuitem"
                      tabindex="0"
                    >
                      <div class="item-main-info">
                        <span class="item-title">${escapeHtml(subj.name)}</span>
                      </div>
                      <div class="item-actions">
                        <button
                          type="button"
                          class="btn-icon-subtle btn-rename-subject-trigger"
                          data-subject-id="${subj.id}"
                          data-subject-name="${escapeHtml(subj.name)}"
                          title="重命名"
                        >
                          ${icons.edit(12)}
                        </button>
                        ${
                          subjects.length > 1
                            ? `
                          <button
                            type="button"
                            class="btn-icon-subtle btn-delete-subject-trigger"
                            data-subject-id="${subj.id}"
                            title="删除"
                          >
                            ${icons.trash(12)}
                          </button>
                        `
                            : ''
                        }
                      </div>
                    </div>
                  `
                      )
                      .join('')
              }
            </div>
          </div>
        </div>
      </div>

      <!-- Center: 4 Primary Workspace Tabs -->
      <nav class="nav-center-tabs" role="navigation" aria-label="工作区导航">
        ${navTabs
          .map(
            (tab) => `
          <button
            type="button"
            class="nav-tab-item ${activeNavTab === tab.id ? 'is-active' : ''}"
            data-tab-id="${tab.id}"
            role="tab"
            aria-selected="${activeNavTab === tab.id}"
            title="${tab.label}"
          >
            <span class="nav-tab-icon">${tab.icon}</span>
            <span class="nav-tab-label">${tab.label}</span>
          </button>
        `
          )
          .join('')}
      </nav>

      <!-- Right: Model Config, Theme, Tools -->
      <div class="nav-right">
        ${
          isRunning
            ? `
          <div class="nav-ops-badge" title="${runningOps.length} 项后台任务正在执行">
            <span class="spinner-inline"></span>
            <span class="ops-count">${runningOps.length}</span>
          </div>
        `
            : ''
        }

        <!-- Single Model Configuration Button -->
        <button
          type="button"
          class="btn-nav-control"
          id="btn-open-model-config"
          title="模型配置 (${escapeHtml(activeModel?.name || activeModel?.provider || '未配置')})"
        >
          ${icons.cpu(14)}
          <span class="nav-control-label" style="max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
            ${escapeHtml(activeModel?.name || activeModel?.provider || '模型配置')}
          </span>
        </button>

        <!-- Command Palette Trigger -->
        <button
          type="button"
          class="btn-nav-control btn-icon-only"
          id="btn-nav-search"
          title="命令面板 (Ctrl+K)"
        >
          ${icons.search(14)}
        </button>

        <!-- Theme Toggle -->
        <button
          type="button"
          class="btn-nav-control btn-icon-only"
          id="btn-theme-toggle"
          title="${theme === 'paper' ? '切换暗色主题' : '切换亮色主题'}"
        >
          ${theme === 'paper' ? icons.moon(14) : icons.sun(14)}
        </button>
      </div>
    </header>
  `;

  // Attach Event Listeners
  const brandBtn = container.querySelector('#brand-home-btn');
  if (brandBtn) {
    brandBtn.onclick = () => handlers.onSelectNavTab?.('learn');
  }

  // Workspace Nav Tabs
  container.querySelectorAll('.nav-tab-item').forEach((btn) => {
    btn.onclick = () => {
      const tabId = btn.getAttribute('data-tab-id');
      handlers.onSelectNavTab?.(tabId);
    };
  });

  // Subject Dropdown Trigger & Popup
  const subjectBtn = container.querySelector('#btn-subject-dropdown');
  const subjectMenu = container.querySelector('#subject-popup-menu');
  if (subjectBtn && subjectMenu) {
    subjectBtn.onclick = (e) => {
      e.stopPropagation();
      const isExpanded = subjectBtn.getAttribute('aria-expanded') === 'true';
      subjectBtn.setAttribute('aria-expanded', !isExpanded);
      subjectMenu.style.display = isExpanded ? 'none' : 'block';
    };

    // Close on outside click
    const handleOutsideClick = (e) => {
      if (!subjectMenu.contains(e.target) && e.target !== subjectBtn) {
        subjectBtn.setAttribute('aria-expanded', 'false');
        subjectMenu.style.display = 'none';
        document.removeEventListener('click', handleOutsideClick);
      }
    };
    document.addEventListener('click', handleOutsideClick);
  }

  // Create Subject Trigger
  const createSubjBtn = container.querySelector('#btn-create-subject-trigger');
  if (createSubjBtn) {
    createSubjBtn.onclick = (e) => {
      e.stopPropagation();
      if (subjectMenu) subjectMenu.style.display = 'none';
      handlers.onOpenSubjectModal?.('create');
    };
  }

  // Switch Subject Items
  container.querySelectorAll('.dropdown-menu-item').forEach((item) => {
    item.onclick = (e) => {
      if (e.target.closest('.btn-rename-subject-trigger') || e.target.closest('.btn-delete-subject-trigger')) {
        return;
      }
      const sid = item.getAttribute('data-subject-id');
      if (sid && sid !== activeSubjectId) {
        if (subjectMenu) subjectMenu.style.display = 'none';
        handlers.onSwitchSubject?.(sid);
      }
    };
  });

  // Rename Subject
  container.querySelectorAll('.btn-rename-subject-trigger').forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const sid = btn.getAttribute('data-subject-id');
      const sname = btn.getAttribute('data-subject-name');
      if (subjectMenu) subjectMenu.style.display = 'none';
      handlers.onOpenRenameSubjectModal?.({ id: sid, name: sname });
    };
  });

  // Delete Subject
  container.querySelectorAll('.btn-delete-subject-trigger').forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const sid = btn.getAttribute('data-subject-id');
      if (subjectMenu) subjectMenu.style.display = 'none';
      handlers.onDeleteSubject?.(sid);
    };
  });

  // Open Model Config Modal
  const modelBtn = container.querySelector('#btn-open-model-config');
  if (modelBtn) {
    modelBtn.onclick = () => handlers.onOpenModelModal?.();
  }

  // Command Palette
  const searchBtn = container.querySelector('#btn-nav-search');
  if (searchBtn) {
    searchBtn.onclick = () => handlers.onToggleCommandPalette?.();
  }

  // Theme Toggle
  const themeBtn = container.querySelector('#btn-theme-toggle');
  if (themeBtn) {
    themeBtn.onclick = () => handlers.onToggleTheme?.();
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
