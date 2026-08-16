/**
 * Command Palette Component (Ctrl+K)
 * Real-time filter search, keyboard Arrow Up/Down & Enter execution.
 */

import { icons } from '../icons.js';

export function renderCommandPalette(state, container, handlers) {
  const { commandPaletteOpen, workspace, activeSubjectId } = state;
  if (!commandPaletteOpen) {
    container.innerHTML = '';
    return;
  }

  const activeSubject = workspace.subjects?.find((s) => s.id === activeSubjectId);

  const allCommands = [
    {
      id: 'cmd-learn',
      title: '进入学习与导师问答',
      category: '工作区导航',
      icon: 'messageSquare',
      action: () => handlers.onSelectNavTab?.('learn')
    },
    {
      id: 'cmd-sources',
      title: '打开资料金库与讲义管理',
      category: '工作区导航',
      icon: 'folder',
      action: () => handlers.onSelectNavTab?.('sources')
    },
    {
      id: 'cmd-studio-bp',
      title: '设计新试卷蓝图',
      category: '组卷工坊',
      icon: 'compass',
      action: () => {
        handlers.onSelectNavTab?.('exam_studio');
        handlers.onOpenBlueprintModal?.();
      }
    },
    {
      id: 'cmd-studio-draft',
      title: '查看试题编辑草稿',
      category: '组卷工坊',
      icon: 'edit3',
      action: () => {
        handlers.onSelectNavTab?.('exam_studio');
        handlers.onSelectExamStudioSubTab?.('draft');
      }
    },
    {
      id: 'cmd-practice',
      title: '开启试卷自由练习模式',
      category: '作答中心',
      icon: 'bookOpen',
      action: () => {
        handlers.onSelectNavTab?.('practice_exam');
        if (state.activeExamId) handlers.onStartAttempt?.(state.activeExamId, 'practice');
      }
    },
    {
      id: 'cmd-exam',
      title: '开启全真考场计时模式',
      category: '作答中心',
      icon: 'play',
      action: () => {
        handlers.onSelectNavTab?.('practice_exam');
        if (state.activeExamId) handlers.onStartAttempt?.(state.activeExamId, 'exam');
      }
    },
    {
      id: 'cmd-revision',
      title: '提出 AI 试卷结构化修改建议',
      category: '试卷工具',
      icon: 'sparkles',
      action: () => {
        handlers.onSelectNavTab?.('practice_exam');
        handlers.onOpenRevisionModal?.();
      }
    },
    {
      id: 'cmd-models',
      title: '配置与注册 AI 模型服务',
      category: '系统设置',
      icon: 'sliders',
      action: () => handlers.onOpenModelModal?.()
    },
    {
      id: 'cmd-rename-sub',
      title: `重命名科目空间 (${activeSubject?.name || '当前科目'})`,
      category: '空间管理',
      icon: 'edit3',
      action: () => handlers.onOpenRenameSubjectModal?.(activeSubject)
    },
    {
      id: 'cmd-create-sub',
      title: '新建科目空间',
      category: '空间管理',
      icon: 'plus',
      action: () => handlers.onOpenSubjectModal?.('create')
    },
    {
      id: 'cmd-theme',
      title: '切换纸张/暗调黑板视觉主题',
      category: '个性化',
      icon: 'sun',
      action: () => handlers.onToggleTheme?.()
    }
  ];

  let selectedIndex = 0;
  let filteredCommands = [...allCommands];

  container.innerHTML = `
    <div class="modal-overlay" id="cmd-modal-overlay">
      <div class="cmd-palette-box" id="cmd-palette-box">
        <div class="cmd-input-bar">
          ${icons.search(18)}
          <input type="text" class="cmd-input-field" id="cmd-search-input" placeholder="键入指令、搜索页面或快速操作 (↑↓ 选择，Enter 执行，Esc 退出)..." autofocus />
          <span class="brand-tag">ESC</span>
        </div>

        <div style="padding: 10px; max-height: 380px; overflow-y: auto; display: flex; flex-direction: column; gap: 4px;" id="cmd-results-list">
          ${renderCommandListHtml(filteredCommands, selectedIndex)}
        </div>
      </div>
    </div>
  `;

  const input = container.querySelector('#cmd-search-input');
  const resultsContainer = container.querySelector('#cmd-results-list');
  const overlay = container.querySelector('#cmd-modal-overlay');

  if (overlay) {
    overlay.onclick = (e) => {
      if (e.target === overlay) handlers.onCloseCommandPalette?.();
    };
  }

  if (input) {
    input.focus();

    // Input filter
    input.oninput = () => {
      const query = input.value.trim().toLowerCase();
      filteredCommands = allCommands.filter((cmd) => {
        return cmd.title.toLowerCase().includes(query) || cmd.category.toLowerCase().includes(query);
      });
      selectedIndex = 0;
      updateResults();
    };

    // Keyboard navigation
    input.onkeydown = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        handlers.onCloseCommandPalette?.();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (filteredCommands.length > 0) {
          selectedIndex = (selectedIndex + 1) % filteredCommands.length;
          updateResults();
        }
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (filteredCommands.length > 0) {
          selectedIndex = (selectedIndex - 1 + filteredCommands.length) % filteredCommands.length;
          updateResults();
        }
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const target = filteredCommands[selectedIndex];
        if (target) {
          handlers.onCloseCommandPalette?.();
          target.action();
        }
      }
    };
  }

  function updateResults() {
    if (resultsContainer) {
      resultsContainer.innerHTML = renderCommandListHtml(filteredCommands, selectedIndex);
      attachItemClicks();
    }
  }

  function attachItemClicks() {
    container.querySelectorAll('.cmd-item-row').forEach((row, idx) => {
      row.onclick = () => {
        const cmd = filteredCommands[idx];
        if (cmd) {
          handlers.onCloseCommandPalette?.();
          cmd.action();
        }
      };
    });
  }

  attachItemClicks();
}

function renderCommandListHtml(commands, activeIndex) {
  if (commands.length === 0) {
    return `<div style="padding: 24px; text-align: center; color: var(--ink-muted); font-size: 13px;">无匹配的指令</div>`;
  }

  return commands
    .map((cmd, idx) => {
      const isAct = idx === activeIndex;
      const iconFn = icons[cmd.icon] || icons.command;
      return `
      <div class="cmd-item-row ${isAct ? 'is-keyboard-active' : ''}" data-cmd-index="${idx}">
        <div style="display: flex; align-items: center; gap: 10px;">
          ${iconFn(16)}
          <span style="font-weight: 600; font-size: 13px;">${escapeHtml(cmd.title)}</span>
        </div>
        <span style="font-size: 11px; font-weight: 700; color: var(--ink-muted);">${escapeHtml(cmd.category)}</span>
      </div>
    `;
    })
    .join('');
}

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
