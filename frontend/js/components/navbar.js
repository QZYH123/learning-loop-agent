/**
 * Primary Navigation Header Component
 * Aligned with Issue 18, 19, 22: Clean 4+1 navigation, single Model Configuration entrance,
 * accessible dropdowns with keyboard navigation, no emoji, subtle active indicator lines.
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

  container.innerHTML = `
    <header class="app-header-navbar" role="banner" data-testid="app-navbar">
      <!-- Left: Brand Logo & Subject Space Dropdown -->
      <div class="nav-left">
        <div class="brand-badge-item" id="brand-home-btn" role="button" tabindex="0" title="回到学习主页">
          <div class="brand-logo-icon">${icons.feather(18)}</div>
          <span class="brand-text-label">Learning Loop</span>
        </div>

        <div class="nav-divider-v"></div>

        <!-- Subject Switcher Dropdown Anchor -->
        <div class="dropdown-anchor" id="subject-dropdown-anchor">
          <button
            type="button"
            class="btn-dropdown-trigger"
            id="btn-subject-dropdown"
            aria-haspopup="true"
            aria-expanded="false"
            title="切换或管理科目空间"
          >
            ${icons.book(15)}
            <span class="dropdown-trigger-label" style="max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
              ${escapeHtml(activeSubject?.name || '选择科目空间')}
            </span>
            ${icons.chevronDown(14)}
          </button>

          <div class="dropdown-popup" id="subject-popup-menu" role="menu" style="display: none;">
            <div class="dropdown-section-title">我的科目空间</div>
            ${subjects.length === 0 ? `<div class="dropdown-empty-note">暂无科目空间</div>` : ''}
            ${subjects
              .map(
                (s) => `
              <div
                class="dropdown-item ${s.id === activeSubjectId ? 'is-selected' : ''}"
                role="menuitem"
                tabindex="0"
                data-action="switch-subject"
                data-subject-id="${s.id}"
              >
                <div class="dropdown-item-content">
                  <span class="dropdown-item-title">${escapeHtml(s.name)}</span>
                </div>
                ${s.id === activeSubjectId ? icons.check(14) : ''}
              </div>
            `
              )
              .join('')}
            <div class="dropdown-divider"></div>
            ${
              activeSubject
                ? `
              <div class="dropdown-item" role="menuitem" tabindex="0" data-action="open-rename-subject">
                ${icons.edit3(14)}
                <span>重命名当前科目</span>
              </div>
            `
                : ''
            }
            <div class="dropdown-item" role="menuitem" tabindex="0" data-action="open-create-subject" style="color: var(--accent-primary);">
              ${icons.plus(14)}
              <span>新建科目空间...</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Center: 4 Primary Core Workspaces -->
      <nav class="nav-center" role="navigation" aria-label="主工作区导航">
        <div class="primary-nav-tabs">
          <button
            type="button"
            class="nav-tab-btn nav-tab-learn ${activeNavTab === 'learn' ? 'is-active' : ''}"
            data-nav-tab="learn"
            title="学习工作区 (问答、启发式自测与会话)"
          >
            ${icons.messageSquare(16)}
            <span>学习</span>
          </button>
          <button
            type="button"
            class="nav-tab-btn nav-tab-sources ${activeNavTab === 'sources' ? 'is-active' : ''}"
            data-nav-tab="sources"
            title="资料库与 AI 生成文档"
          >
            ${icons.folder(16)}
            <span>资料</span>
            ${state.sources?.length ? `<span class="tab-badge">${state.sources.length}</span>` : ''}
          </button>
          <button
            type="button"
            class="nav-tab-btn nav-tab-studio ${activeNavTab === 'exam_studio' ? 'is-active' : ''}"
            data-nav-tab="exam_studio"
            title="组卷工坊 (蓝图构思、增量实验室与排版)"
          >
            ${icons.compass(16)}
            <span>组卷工坊</span>
          </button>
          <button
            type="button"
            class="nav-tab-btn nav-tab-practice ${activeNavTab === 'practice_exam' ? 'is-active' : ''}"
            data-nav-tab="practice_exam"
            title="作答中心 (练习/考试作答、批改与成绩复查)"
          >
            ${icons.target(16)}
            <span>作答中心</span>
            ${state.exams?.length ? `<span class="tab-badge">${state.exams.length}</span>` : ''}
          </button>
        </div>
      </nav>

      <!-- Right: Single Model Config Entrance, System Status & Dev Tools -->
      <div class="nav-right">
        <!-- Unified Model Configuration Button (Issue 19) -->
        <button
          type="button"
          class="btn-nav-model-config ${!activeModel ? 'is-unconfigured' : ''}"
          id="btn-nav-model-config"
          data-action="open-model-modal"
          title="模型服务配置与模型发现"
        >
          ${icons.cpu(15)}
          <span class="nav-model-label">${escapeHtml(activeModel?.model || '配置模型服务')}</span>
          ${activeModel?.capabilities?.vision ? `<span class="tag-chip-vision" title="具备视觉能力">Vision</span>` : ''}
        </button>

        <!-- Real Async Task Status Tracker -->
        ${
          isRunning
            ? `
          <div class="system-status-chip status-chip-running" title="后台正在执行异步任务">
            ${icons.rotateCw(13, 'spin')}
            <span>执行中 (${runningOps.length})</span>
          </div>
        `
            : `
          <div class="system-status-chip" title="所有系统就绪">
            <span class="status-dot status-dot-green"></span>
            <span>就绪</span>
          </div>
        `
        }

        <!-- Settings & Dev Tools -->
        <button
          type="button"
          class="btn-icon-nav ${activeNavTab === 'settings_dev' ? 'is-active' : ''}"
          data-nav-tab="settings_dev"
          title="观测分析与设置"
          aria-label="观测分析与设置"
        >
          ${icons.activity(16)}
        </button>

        <!-- Command Palette Shortcut (Ctrl+K) -->
        <button
          type="button"
          class="btn-icon-nav"
          id="btn-open-cmd"
          title="快捷指令面板 (Ctrl+K)"
          aria-label="快捷指令面板"
        >
          ${icons.command(16)}
        </button>

        <!-- Theme Switcher -->
        <button
          type="button"
          class="btn-icon-nav"
          id="btn-toggle-theme"
          title="切换纸张 / 暗调黑板主题"
          aria-label="切换主题"
        >
          ${theme === 'paper' ? icons.moon(16) : icons.sun(16)}
        </button>
      </div>
    </header>
  `;

  // Attach Event Listeners
  const subjectBtn = container.querySelector('#btn-subject-dropdown');
  const subjectMenu = container.querySelector('#subject-popup-menu');

  const closeSubjectMenu = () => {
    if (subjectMenu) {
      subjectMenu.style.display = 'none';
      if (subjectBtn) subjectBtn.setAttribute('aria-expanded', 'false');
    }
  };

  if (subjectBtn && subjectMenu) {
    subjectBtn.onclick = (e) => {
      e.stopPropagation();
      const isVisible = subjectMenu.style.display === 'block';
      subjectMenu.style.display = isVisible ? 'none' : 'block';
      subjectBtn.setAttribute('aria-expanded', String(!isVisible));
    };

    // Keyboard navigation inside dropdown
    subjectMenu.onkeydown = (e) => {
      if (e.key === 'Escape') {
        closeSubjectMenu();
        subjectBtn.focus();
      }
    };
  }

  // Global document click handler for closing dropdown
  const onDocClick = (e) => {
    if (!container.contains(e.target)) {
      closeSubjectMenu();
    }
  };
  document.removeEventListener('click', container._navbarDocClickHandler);
  container._navbarDocClickHandler = onDocClick;
  document.addEventListener('click', onDocClick);

  // Subject Actions
  container.querySelectorAll('[data-action="switch-subject"]').forEach((el) => {
    const handleSelect = () => {
      const subId = el.getAttribute('data-subject-id');
      closeSubjectMenu();
      handlers.onSwitchSubject?.(subId);
    };
    el.onclick = handleSelect;
    el.onkeydown = (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handleSelect();
      }
    };
  });

  container.querySelectorAll('[data-action="open-create-subject"]').forEach((el) => {
    el.onclick = () => {
      closeSubjectMenu();
      handlers.onOpenSubjectModal?.('create');
    };
  });

  container.querySelectorAll('[data-action="open-rename-subject"]').forEach((el) => {
    el.onclick = () => {
      closeSubjectMenu();
      handlers.onOpenRenameSubjectModal?.(activeSubject);
    };
  });

  // Model Modal Trigger
  const modelConfigBtn = container.querySelector('#btn-nav-model-config');
  if (modelConfigBtn) {
    modelConfigBtn.onclick = () => {
      handlers.onOpenModelModal?.();
    };
  }

  // Primary Navigation Tabs
  container.querySelectorAll('[data-nav-tab]').forEach((btn) => {
    btn.onclick = () => {
      const tab = btn.getAttribute('data-nav-tab');
      handlers.onSelectNavTab?.(tab);
    };
  });

  // Top Shortcuts
  const brandBtn = container.querySelector('#brand-home-btn');
  if (brandBtn) {
    brandBtn.onclick = () => handlers.onSelectNavTab?.('learn');
    brandBtn.onkeydown = (e) => {
      if (e.key === 'Enter') handlers.onSelectNavTab?.('learn');
    };
  }

  const cmdBtn = container.querySelector('#btn-open-cmd');
  if (cmdBtn) {
    cmdBtn.onclick = () => handlers.onToggleCommandPalette?.();
  }

  const themeBtn = container.querySelector('#btn-toggle-theme');
  if (themeBtn) {
    themeBtn.onclick = () => handlers.onToggleTheme?.();
  }
}

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
