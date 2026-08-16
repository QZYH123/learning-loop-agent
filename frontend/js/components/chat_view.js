/**
 * Learning Workspace Component (Chat, Socratic Tutor & Multi-Session Management)
 * Strictly aligned with Issue 17 & 18:
 * - Left Pane: Collapsible session list, search, create, switch, inline rename, delete.
 * - Right Pane: Session conversation, session sources manager dropdown,
 *   @source mention popup, temporary attachments with vision capability checks,
 *   content block rendering, real model snapshot badges, and Socratic stepping.
 */

import { icons } from '../icons.js';

export function renderChatView(state, container, handlers) {
  const {
    sessions = [],
    activeSessionId,
    sessionSearchQuery = '',
    sidebarCollapsed = {},
    chat = {},
    chatAttachments = [],
    selectionContext = null,
    sources = [],
    models = [],
    currentModelId
  } = state;

  const isCollapsed = !!sidebarCollapsed.learn;
  const activeSession = sessions.find((s) => s.id === activeSessionId) || sessions[0] || null;

  // Filter sessions by search query
  const filteredSessions = sessions.filter((s) =>
    (s.title || '学习会话').toLowerCase().includes((sessionSearchQuery || '').toLowerCase())
  );

  const messages = (activeSession?.messages || chat?.messages || []);
  const learningMode = activeSession?.learning_mode || chat?.learning_mode || 'chat';
  const groundingMode = activeSession?.grounding_mode || chat?.grounding_mode || 'general-knowledge';
  const socraticState = activeSession?.socratic_state || chat?.socratic_state || null;

  const activeModelId = activeSession?.model_id || currentModelId || chat?.active_model_id;
  const activeModel = models.find((m) => m.id === activeModelId) || models[0] || null;
  const hasVision = !!activeModel?.capabilities?.vision;

  // Pinned session sources
  const sessionSourceVersionIds = activeSession?.source_version_ids || chat?.source_version_ids || [];
  const pinnedSources = sources.filter((src) =>
    (src.versions || []).some((v) => sessionSourceVersionIds.includes(v.id)) ||
    sessionSourceVersionIds.includes(src.id)
  );

  container.innerHTML = `
    <div class="learning-workspace-layout ${isCollapsed ? 'is-sidebar-collapsed' : ''}" data-testid="learning-workspace">
      <!-- Left Sidebar: Multi-Session Drawer -->
      <aside class="workspace-sidebar" id="learn-session-sidebar">
        <div class="sidebar-header-row">
          <div class="sidebar-title-block">
            ${icons.messageSquare(15)}
            <span class="sidebar-title-text">学习会话 (${sessions.length})</span>
          </div>
          <div class="sidebar-actions-block">
            <button
              type="button"
              class="btn-icon-sidebar"
              id="btn-create-session"
              title="新建学习会话"
            >
              ${icons.plus(15)}
            </button>
            <button
              type="button"
              class="btn-icon-sidebar"
              id="btn-toggle-learn-sidebar"
              title="${isCollapsed ? '展开侧栏' : '收起侧栏'}"
            >
              ${isCollapsed ? icons.panelLeftOpen(15) : icons.panelLeftClose(15)}
            </button>
          </div>
        </div>

        <!-- Search Box -->
        <div class="sidebar-search-box">
          <div class="search-input-wrapper">
            ${icons.search(13)}
            <input
              type="text"
              class="sidebar-search-input"
              id="input-search-sessions"
              placeholder="搜索会话..."
              value="${escapeHtml(sessionSearchQuery)}"
            />
            ${
              sessionSearchQuery
                ? `<button type="button" class="btn-clear-search" id="btn-clear-session-search">${icons.x(12)}</button>`
                : ''
            }
          </div>
        </div>

        <!-- Session Items List -->
        <div class="sidebar-scrollable-list" id="session-items-scroll">
          ${
            filteredSessions.length === 0
              ? `
            <div class="sidebar-empty-state">
              <div class="sidebar-empty-icon">${icons.messageSquare(22)}</div>
              <div class="sidebar-empty-text">${sessionSearchQuery ? '未找到匹配的会话' : '暂无学习会话'}</div>
              <button type="button" class="btn-secondary btn-sm" id="btn-empty-create-session" style="margin-top: 8px;">
                ${icons.plus(13)} 新建会话
              </button>
            </div>
          `
              : filteredSessions
                  .map((sess) => {
                    const isSelected = sess.id === activeSessionId;
                    const modeLabel =
                      sess.learning_mode === 'socratic'
                        ? '苏格拉底'
                        : sess.learning_mode === 'crash-course'
                        ? '速成'
                        : '问答';
                    const srcCount = sess.source_version_ids?.length || 0;

                    return `
              <div
                class="session-list-item ${isSelected ? 'is-selected' : ''}"
                data-action="select-session"
                data-session-id="${sess.id}"
                role="button"
                tabindex="0"
              >
                <div class="session-item-main">
                  <div class="session-item-title-row">
                    <span class="session-item-title" title="${escapeHtml(sess.title || '学习会话')}">
                      ${escapeHtml(sess.title || '学习会话')}
                    </span>
                  </div>
                  <div class="session-item-meta-row">
                    <span class="session-mode-badge">${modeLabel}</span>
                    ${srcCount > 0 ? `<span class="session-sources-badge">${icons.folder(10)} ${srcCount} 份资料</span>` : ''}
                    <span class="session-time-text">${formatTimestamp(sess.updated_at || sess.created_at)}</span>
                  </div>
                </div>

                <!-- Session Action Menu Trigger -->
                <div class="session-item-actions">
                  <button
                    type="button"
                    class="btn-icon-subtle"
                    data-action="rename-session"
                    data-session-id="${sess.id}"
                    data-session-title="${escapeHtml(sess.title || '')}"
                    title="重命名会话"
                  >
                    ${icons.edit3(12)}
                  </button>
                  <button
                    type="button"
                    class="btn-icon-subtle btn-delete-subtle"
                    data-action="delete-session"
                    data-session-id="${sess.id}"
                    title="删除会话"
                  >
                    ${icons.trash2(12)}
                  </button>
                </div>
              </div>
            `;
                  })
                  .join('')
          }
        </div>
      </aside>

      <!-- Main Conversation Body -->
      <main class="workspace-main-content" id="learn-conversation-main">
        <!-- Floating Expand Toggle Button (Visible when sidebar collapsed) -->
        ${
          isCollapsed
            ? `
          <button
            type="button"
            class="btn-sidebar-floating-expand"
            id="btn-floating-expand-learn"
            title="展开会话侧栏"
          >
            ${icons.panelLeftOpen(15)}
            <span>会话 (${sessions.length})</span>
          </button>
        `
            : ''
        }

        <!-- Conversation Header Bar (Issue 18: Title, Sources Dropdown, Mode & Grounding) -->
        <header class="conversation-header-bar">
          <div class="conv-header-left">
            <h1 class="conv-session-title" title="${escapeHtml(activeSession?.title || '学习与问答')}">
              ${escapeHtml(activeSession?.title || '学习与问答')}
            </h1>

            <!-- Session Sources Dropdown Anchor -->
            <div class="dropdown-anchor" id="session-sources-dropdown-anchor">
              <button
                type="button"
                class="btn-session-sources-chip"
                id="btn-session-sources-dropdown"
                aria-haspopup="true"
                aria-expanded="false"
                title="管理当前会话固定的资料范围"
              >
                ${icons.folder(13)}
                <span>固定资料: ${sessionSourceVersionIds.length > 0 ? `${sessionSourceVersionIds.length} 份` : '未绑定'}</span>
                ${icons.chevronDown(12)}
              </button>

              <div class="dropdown-popup dropdown-sources-popup" id="session-sources-popup-menu" style="display: none;">
                <div class="dropdown-section-title">当前会话固定资料版本</div>
                ${
                  sessionSourceVersionIds.length === 0
                    ? `<div class="dropdown-empty-note">当前会话未绑定资料，默认使用通用常识回答。</div>`
                    : pinnedSources
                        .map(
                          (src) => `
                    <div class="dropdown-source-row">
                      <div class="dropdown-source-info">
                        ${icons.fileText(14)}
                        <span class="dropdown-source-name" title="${escapeHtml(src.display_name || src.name)}">
                          ${escapeHtml(src.display_name || src.name)}
                        </span>
                      </div>
                      <button
                        type="button"
                        class="btn-icon-subtle"
                        data-action="remove-session-source"
                        data-source-id="${src.id}"
                        title="从当前会话移除"
                      >
                        ${icons.x(12)}
                      </button>
                    </div>
                  `
                        )
                        .join('')
                }
                <div class="dropdown-divider"></div>
                <!-- Add from Subject Library -->
                <div class="dropdown-section-title">从科目资料库加入会话</div>
                ${
                  sources.length === 0
                    ? `<div class="dropdown-empty-note">科目库暂无资料，请先前往「资料」上传。</div>`
                    : sources
                        .filter((s) => !sessionSourceVersionIds.includes(s.id) && !sessionSourceVersionIds.includes(s.versions?.[0]?.id))
                        .map(
                          (src) => `
                    <div
                      class="dropdown-item"
                      data-action="add-source-to-session"
                      data-source-id="${src.id}"
                      data-version-id="${src.versions?.[0]?.id || src.id}"
                    >
                      ${icons.plus(13)}
                      <span>${escapeHtml(src.display_name || src.name)}</span>
                    </div>
                  `
                        )
                        .join('')
                }
              </div>
            </div>
          </div>

          <!-- Header Sub-controls: Mode Switcher & Grounding Mode -->
          <div class="conv-header-right">
            <!-- Learning Mode Switcher -->
            <div class="chat-mode-switch-group">
              <button
                type="button"
                class="chat-mode-btn ${learningMode === 'chat' ? 'is-active' : ''}"
                data-learning-mode="chat"
                title="普通自由问答"
              >
                ${icons.messageSquare(13)}
                <span>问答</span>
              </button>
              <button
                type="button"
                class="chat-mode-btn ${learningMode === 'socratic' ? 'is-active' : ''}"
                data-learning-mode="socratic"
                title="苏格拉底阶梯式启发导师"
              >
                ${icons.brain(13)}
                <span>苏格拉底</span>
              </button>
              <button
                type="button"
                class="chat-mode-btn ${learningMode === 'crash-course' ? 'is-active' : ''}"
                data-learning-mode="crash-course"
                title="章节速成大纲提炼"
              >
                ${icons.zap(13)}
                <span>章节速成</span>
              </button>
            </div>

            <!-- Grounding Mode Dropdown -->
            <div class="grounding-select-wrapper">
              <label for="select-grounding-mode" class="sr-only">知识依据模式</label>
              <select class="select-grounding-control" id="select-grounding-mode" aria-label="知识依据模式">
                <option value="strict" ${groundingMode === 'strict' ? 'selected' : ''}>严格资料模式</option>
                <option value="general-knowledge" ${groundingMode === 'general-knowledge' ? 'selected' : ''}>通用常识模式</option>
                <option value="supplemental" ${groundingMode === 'supplemental' ? 'selected' : ''}>补充扩展模式</option>
              </select>
            </div>

            <button
              type="button"
              class="btn-icon-subtle"
              id="btn-clear-chat"
              title="清空当前对话记录"
            >
              ${icons.trash2(14)}
            </button>
          </div>
        </header>

        <!-- Socratic State HUD Banner (When in Socratic Mode) -->
        ${
          learningMode === 'socratic' && socraticState
            ? `
          <div class="socratic-indicator-banner">
            <div class="socratic-banner-left">
              ${icons.sparkles(14)}
              <span class="socratic-banner-step">启发阶梯: 第 ${socraticState.current_level || 1} / ${socraticState.total_levels || 3} 层</span>
              <span class="socratic-banner-phase">阶段: ${escapeHtml(socraticState.phase || '引导探究')}</span>
            </div>
            ${
              socraticState.answer_revealed
                ? `<span class="socratic-answer-revealed-tag">${icons.eye(12)} 答案已揭示</span>`
                : `<span class="socratic-answer-hidden-tag">${icons.eyeOff(12)} 启发中 (答案保密)</span>`
            }
          </div>
        `
            : ''
        }

        <!-- Pinned Selection Banner -->
        ${
          selectionContext
            ? `
          <div class="selection-pinned-banner">
            <div class="selection-pinned-content">
              ${icons.tag(13)}
              <span class="selection-pinned-label">已固定选区:</span>
              <span class="selection-pinned-text">"${escapeHtml(selectionContext.text?.slice(0, 60) || '所选段落')}..."</span>
            </div>
            <button
              type="button"
              class="btn-icon-subtle"
              id="btn-unpin-selection"
              title="取消固定选区"
            >
              ${icons.x(12)}
            </button>
          </div>
        `
            : ''
        }

        <!-- Message History Stream Viewport -->
        <div class="chat-stream-viewport" id="chat-messages-scroll">
          ${
            messages.length === 0
              ? renderEmptyChatState(learningMode, sessionSourceVersionIds.length > 0)
              : messages.map((msg) => renderChatMessage(msg, models)).join('')
          }
        </div>

        <!-- Socratic Dynamic Intent Action Bar -->
        ${
          learningMode === 'socratic'
            ? `
          <div class="socratic-intents-bar">
            <button type="button" class="btn-intent-action" data-intent="request-hint" title="请求获取下一步线索提示">
              ${icons.helpCircle(13)} 请求提示
            </button>
            <button type="button" class="btn-intent-action" data-intent="restate" title="用自己的话重述理解">
              ${icons.edit3(13)} 重述理解
            </button>
            <button type="button" class="btn-intent-action" data-intent="request-explanation" title="查看完整详细解析与原委">
              ${icons.fileText(13)} 完整解释
            </button>
            <button type="button" class="btn-intent-action btn-quick-prompt" data-prompt="请出几道核心易错题自测我对刚才知识点的掌握情况。">
              ${icons.target(13)} 易错点自测
            </button>
          </div>
        `
            : ''
        }

        <!-- Chat Composer Area -->
        <div class="chat-composer-container">
          <!-- Temporary Attachments Tray (Issue 17) -->
          ${
            chatAttachments.length > 0
              ? `
            <div class="attachments-preview-tray">
              ${chatAttachments
                .map(
                  (att, idx) => `
                <div class="attachment-preview-chip ${att.status === 'error' ? 'is-error' : ''}">
                  ${
                    att.preview_url
                      ? `<img src="${att.preview_url}" class="attachment-thumb-img" alt="附件缩略图" />`
                      : icons.file(14)
                  }
                  <span class="attachment-file-name" title="${escapeHtml(att.name)}">${escapeHtml(att.name)}</span>
                  <span class="attachment-file-size">(${formatBytes(att.size_bytes || 0)})</span>
                  <button
                    type="button"
                    class="btn-remove-attachment"
                    data-action="remove-attachment"
                    data-index="${idx}"
                    title="移除此附件"
                  >
                    ${icons.x(11)}
                  </button>
                </div>
              `
                )
                .join('')}
            </div>
          `
              : ''
          }

          <!-- Vision Capability Warning (Issue 17) -->
          ${
            chatAttachments.some((a) => a.is_image) && !hasVision
              ? `
            <div class="vision-unsupported-banner">
              ${icons.alertTriangle(13)}
              <span>当前选定模型 (${escapeHtml(activeModel?.model || '未知')}) 不支持图片视觉分析，请前往顶部配置切换具备 Vision 的多模态模型。</span>
            </div>
          `
              : ''
          }

          <!-- Hidden Attachment Input -->
          <input
            type="file"
            id="chat-attachment-file-input"
            multiple
            style="display: none;"
            accept=".png,.jpg,.jpeg,.webp,.pdf,.txt,.md"
          />

          <!-- @Sources Autocomplete Menu Popup -->
          <div class="at-sources-menu" id="at-sources-menu-popup" style="display: none;">
            <div class="at-sources-header">选择要重点引用的资料 (@资料)</div>
            <div class="at-sources-list" id="at-sources-list-container">
              ${
                pinnedSources.length === 0
                  ? `<div class="dropdown-empty-note">当前会话未绑定资料，无法使用 @ 重点检索。</div>`
                  : pinnedSources
                      .map(
                        (src) => `
                  <div
                    class="at-source-item"
                    data-action="insert-at-source"
                    data-source-name="${escapeHtml(src.display_name || src.name)}"
                    data-version-id="${src.versions?.[0]?.id || src.id}"
                  >
                    ${icons.fileText(13)}
                    <span>${escapeHtml(src.display_name || src.name)}</span>
                  </div>
                `
                      )
                      .join('')
              }
            </div>
          </div>

          <!-- Composer Form Row -->
          <form class="composer-form-row" id="chat-composer-form">
            <!-- Attach File Button -->
            <button
              type="button"
              class="btn-composer-tool"
              id="btn-trigger-attachment"
              title="添加临时图片或文档附件 (仅供本轮消息使用)"
            >
              ${icons.paperclip(16)}
            </button>

            <!-- Text Input Field -->
            <textarea
              class="composer-textarea"
              id="chat-input-field"
              placeholder="${
                learningMode === 'socratic'
                  ? '输入你的思考与推导解答 (Enter 发送, Shift+Enter 换行, 输入 @ 引用资料)...'
                  : '输入学科疑问、概念推导或习题剖析 (Enter 发送, 输入 @ 引用资料)...'
              }"
              rows="1"
              required
            ></textarea>

            <!-- Send Button -->
            <button
              type="submit"
              class="btn-send-primary"
              id="btn-send-chat"
              title="发送消息 (Enter)"
            >
              ${icons.send(15)}
            </button>
          </form>
        </div>
      </main>
    </div>
  `;

  // Attach Event Handlers
  attachLearnEvents(container, state, handlers);
}

function attachLearnEvents(container, state, handlers) {
  const { activeSessionId, sessions, sidebarCollapsed } = state;

  // Sidebar Collapse Toggle
  const toggleBtn = container.querySelector('#btn-toggle-learn-sidebar');
  if (toggleBtn) {
    toggleBtn.onclick = () => {
      handlers.onToggleSidebar?.('learn');
    };
  }

  const floatingExpandBtn = container.querySelector('#btn-floating-expand-learn');
  if (floatingExpandBtn) {
    floatingExpandBtn.onclick = () => {
      handlers.onToggleSidebar?.('learn');
    };
  }

  // Create Session Triggers
  const createBtn = container.querySelector('#btn-create-session');
  if (createBtn) {
    createBtn.onclick = () => handlers.onOpenCreateSessionModal?.();
  }

  const emptyCreateBtn = container.querySelector('#btn-empty-create-session');
  if (emptyCreateBtn) {
    emptyCreateBtn.onclick = () => handlers.onOpenCreateSessionModal?.();
  }

  // Search Sessions
  const searchInput = container.querySelector('#input-search-sessions');
  if (searchInput) {
    searchInput.oninput = () => {
      handlers.onSearchSessions?.(searchInput.value);
    };
  }

  const clearSearchBtn = container.querySelector('#btn-clear-session-search');
  if (clearSearchBtn) {
    clearSearchBtn.onclick = () => {
      handlers.onSearchSessions?.('');
    };
  }

  // Session Item Selection & Actions
  container.querySelectorAll('[data-action="select-session"]').forEach((item) => {
    item.onclick = (e) => {
      if (e.target.closest('[data-action="rename-session"]') || e.target.closest('[data-action="delete-session"]')) {
        return;
      }
      const sId = item.getAttribute('data-session-id');
      handlers.onSelectSession?.(sId);
    };
  });

  container.querySelectorAll('[data-action="rename-session"]').forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const sId = btn.getAttribute('data-session-id');
      const currentTitle = btn.getAttribute('data-session-title');
      const newTitle = prompt('请输入会话新名称:', currentTitle);
      if (newTitle && newTitle.trim() && newTitle.trim() !== currentTitle) {
        handlers.onRenameSession?.(sId, newTitle.trim());
      }
    };
  });

  container.querySelectorAll('[data-action="delete-session"]').forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const sId = btn.getAttribute('data-session-id');
      if (confirm('确定要删除此学习会话及其聊天记录吗？（项目资料库不会被删除）')) {
        handlers.onDeleteSession?.(sId);
      }
    };
  });

  // Session Sources Dropdown
  const sourcesAnchor = container.querySelector('#session-sources-dropdown-anchor');
  const sourcesBtn = container.querySelector('#btn-session-sources-dropdown');
  const sourcesMenu = container.querySelector('#session-sources-popup-menu');

  if (sourcesBtn && sourcesMenu) {
    sourcesBtn.onclick = (e) => {
      e.stopPropagation();
      const isVisible = sourcesMenu.style.display === 'block';
      sourcesMenu.style.display = isVisible ? 'none' : 'block';
      sourcesBtn.setAttribute('aria-expanded', String(!isVisible));
    };
  }

  // Add source to session
  container.querySelectorAll('[data-action="add-source-to-session"]').forEach((item) => {
    item.onclick = () => {
      const versionId = item.getAttribute('data-version-id');
      if (sourcesMenu) sourcesMenu.style.display = 'none';
      handlers.onAddSessionSource?.(activeSessionId, versionId);
    };
  });

  // Remove source from session
  container.querySelectorAll('[data-action="remove-session-source"]').forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const sId = btn.getAttribute('data-source-id');
      handlers.onRemoveSessionSource?.(activeSessionId, sId);
    };
  });

  // Learning Mode Buttons
  container.querySelectorAll('[data-learning-mode]').forEach((btn) => {
    btn.onclick = () => {
      const mode = btn.getAttribute('data-learning-mode');
      handlers.onSwitchLearningMode?.(mode);
    };
  });

  // Grounding Mode Dropdown
  const groundingSelect = container.querySelector('#select-grounding-mode');
  if (groundingSelect) {
    groundingSelect.onchange = () => {
      handlers.onUpdateGroundingMode?.(groundingSelect.value);
    };
  }

  // Clear Chat Button
  const clearBtn = container.querySelector('#btn-clear-chat');
  if (clearBtn) {
    clearBtn.onclick = () => handlers.onClearChat?.();
  }

  // Unpin Selection Button
  const unpinBtn = container.querySelector('#btn-unpin-selection');
  if (unpinBtn) {
    unpinBtn.onclick = () => handlers.onClearSelection?.();
  }

  // Quick Prompt Buttons
  container.querySelectorAll('.btn-quick-prompt').forEach((btn) => {
    btn.onclick = () => {
      const prompt = btn.getAttribute('data-prompt');
      handlers.onSendMessage?.({ content: prompt, intent: 'ask' });
    };
  });

  // Socratic Intent Action Buttons
  container.querySelectorAll('.btn-intent-action[data-intent]').forEach((btn) => {
    btn.onclick = () => {
      const intent = btn.getAttribute('data-intent');
      handlers.onSendIntentMessage?.(intent);
    };
  });

  // Citations Inspection
  container.querySelectorAll('[data-citation-id]').forEach((badge) => {
    badge.onclick = () => {
      const citationId = badge.getAttribute('data-citation-id');
      handlers.onInspectCitation?.({ citationId });
    };
  });

  // Attachments Handling
  const fileInput = container.querySelector('#chat-attachment-file-input');
  const attachBtn = container.querySelector('#btn-trigger-attachment');

  if (attachBtn && fileInput) {
    attachBtn.onclick = () => fileInput.click();
    fileInput.onchange = () => {
      if (fileInput.files && fileInput.files.length > 0) {
        handlers.onAddChatAttachments?.(Array.from(fileInput.files));
        fileInput.value = '';
      }
    };
  }

  container.querySelectorAll('[data-action="remove-attachment"]').forEach((btn) => {
    btn.onclick = () => {
      const idx = parseInt(btn.getAttribute('data-index'), 10);
      handlers.onRemoveChatAttachment?.(idx);
    };
  });

  // Composer Form & @Sources Autocomplete
  const form = container.querySelector('#chat-composer-form');
  const input = container.querySelector('#chat-input-field');
  const atMenu = container.querySelector('#at-sources-menu-popup');

  if (form && input) {
    // Auto-scroll messages stream to bottom
    const scrollBox = container.querySelector('#chat-messages-scroll');
    if (scrollBox) {
      scrollBox.scrollTop = scrollBox.scrollHeight;
    }

    input.addEventListener('input', () => {
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 140) + 'px';

      // Check if user just typed '@'
      const val = input.value;
      const cursorPos = input.selectionStart;
      const textBefore = val.slice(0, cursorPos);
      const atMatch = textBefore.match(/@([^\s@]*)$/);

      if (atMatch && atMenu) {
        atMenu.style.display = 'block';
      } else if (atMenu) {
        atMenu.style.display = 'none';
      }
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && atMenu && atMenu.style.display === 'block') {
        atMenu.style.display = 'none';
        e.preventDefault();
        return;
      }
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        form.dispatchEvent(new Event('submit'));
      }
    });

    // Insert @source tag
    container.querySelectorAll('[data-action="insert-at-source"]').forEach((item) => {
      item.onclick = () => {
        const srcName = item.getAttribute('data-source-name');
        const val = input.value;
        const cursorPos = input.selectionStart;
        const textBefore = val.slice(0, cursorPos).replace(/@([^\s@]*)$/, `@${srcName} `);
        const textAfter = val.slice(cursorPos);
        input.value = textBefore + textAfter;
        if (atMenu) atMenu.style.display = 'none';
        input.focus();
      };
    });

    form.onsubmit = (e) => {
      e.preventDefault();
      const content = input.value.trim();
      if (!content && state.chatAttachments.length === 0) return;

      input.value = '';
      input.style.height = 'auto';
      if (atMenu) atMenu.style.display = 'none';

      const learningMode = state.activeSession?.learning_mode || state.chat?.learning_mode || 'chat';
      const intent = learningMode === 'socratic' ? 'attempt' : 'ask';

      handlers.onSendMessage?.({
        content,
        intent,
        attachments: state.chatAttachments
      });
    };
  }
}

function renderChatMessage(msg, models = []) {
  const isUser = msg.role === 'user';
  const roleName = isUser ? '学习者' : 'AI 伴学导师';

  // Real Model Snapshot Badge
  let modelBadge = '';
  if (!isUser && msg.model) {
    modelBadge = `<span class="msg-model-snapshot-chip" title="实际生成模型">${escapeHtml(msg.model)}</span>`;
  }

  // Real Grounding Badge (Ticket 04, 17)
  let groundingBadge = '';
  if (msg.grounding_result) {
    if (msg.grounding_result === 'covered') {
      groundingBadge = `<span class="grounding-tag-chip grounding-covered">${icons.bookmark(11)} 严格源自资料</span>`;
    } else if (msg.grounding_result === 'not-covered') {
      groundingBadge = `<span class="grounding-tag-chip grounding-not-covered">${icons.alertTriangle(11)} 资料未覆盖</span>`;
    } else if (msg.grounding_result === 'supplemental') {
      groundingBadge = `<span class="grounding-tag-chip grounding-supplemental">${icons.sparkles(11)} 补充通用知识</span>`;
    } else if (msg.grounding_result === 'general-knowledge') {
      groundingBadge = `<span class="grounding-tag-chip">${icons.brain(11)} 通用常识</span>`;
    }
  }

  // Content blocks rendering (Ticket 16, 17)
  let bodyContentHtml = '';
  if (Array.isArray(msg.content_blocks) && msg.content_blocks.length > 0) {
    bodyContentHtml = msg.content_blocks
      .map((block) => {
        if (block.type === 'text') {
          return `<div class="msg-text-paragraph">${escapeHtml(block.text || '')}</div>`;
        } else if (block.type === 'quote') {
          return `<blockquote class="msg-quote-block">${escapeHtml(block.text || '')}</blockquote>`;
        } else if (block.type === 'image' && block.image_url) {
          return `<div class="msg-image-block"><img src="${block.image_url}" alt="附图" class="msg-embedded-img" /></div>`;
        }
        return `<div>${escapeHtml(typeof block === 'string' ? block : JSON.stringify(block))}</div>`;
      })
      .join('');
  } else {
    bodyContentHtml = `<div class="msg-text-paragraph">${escapeHtml(msg.content || '')}</div>`;
  }

  return `
    <div class="chat-msg ${isUser ? 'chat-msg-user' : 'chat-msg-assistant'}" data-testid="chat-message">
      <div class="msg-meta-row">
        <span class="msg-role-label">${roleName}</span>
        ${modelBadge}
        ${groundingBadge}
        <span class="msg-timestamp">${formatTimestamp(msg.timestamp || msg.created_at)}</span>
      </div>

      <div class="msg-bubble">
        <div class="msg-body-wrapper">${bodyContentHtml}</div>

        <!-- Citation References (Ticket 04) -->
        ${
          msg.citations?.length
            ? `
          <div class="citations-badges-tray">
            <div class="citations-tray-label">${icons.bookmark(12)} 来源依据:</div>
            ${msg.citations
              .map(
                (c, idx) => `
              <button
                type="button"
                class="citation-badge-btn"
                data-citation-id="${c.id}"
                title="${escapeHtml(c.quote || '点击查看资料定位与锚点')}"
              >
                <span>[${idx + 1}] ${escapeHtml(c.source_name || c.anchor_id || '讲义依据')}</span>
              </button>
            `
              )
              .join('')}
          </div>
        `
            : ''
        }
      </div>
    </div>
  `;
}

function renderEmptyChatState(learningMode, hasSources) {
  const isSocratic = learningMode === 'socratic';
  const isCrashCourse = learningMode === 'crash-course';

  return `
    <div class="empty-chat-state-card" data-testid="chat-empty-state">
      <div class="empty-state-icon-circle">
        ${isSocratic ? icons.brain(24) : isCrashCourse ? icons.zap(24) : icons.sparkles(24)}
      </div>
      <div class="empty-state-title">
        ${
          isSocratic
            ? '苏格拉底式启发学习已就绪'
            : isCrashCourse
            ? '章节速成知识提炼已就绪'
            : 'AI 伴学导师与学科问答就绪'
        }
      </div>
      <div class="empty-state-desc">
        ${
          hasSources
            ? '当前会话已绑定学科资料。AI 将优先依据资料回答，支持段落选区推演与 @资料 重点检索。'
            : '当前会话未绑定资料，默认采用通用常识模式回答。可在上方添加资料建立严格依据。'
        }
      </div>
      <div class="empty-starters-tray">
        ${
          isSocratic
            ? `
          <button type="button" class="btn-intent-action btn-quick-prompt" data-prompt="我想深入理解这门学科中最核心的基本定理及其推导逻辑。">核心定理推导</button>
          <button type="button" class="btn-intent-action btn-quick-prompt" data-prompt="请通过阶梯式提问引导我理解易错概念的本质区别。">易错辨析启发</button>
        `
            : isCrashCourse
            ? `
          <button type="button" class="btn-intent-action btn-quick-prompt" data-prompt="请为我系统提炼当前资料的章节知识脉络与速成提纲。">章节考点脉络提炼</button>
        `
            : `
          <button type="button" class="btn-intent-action btn-quick-prompt" data-prompt="请为我系统梳理当前学科的知识结构与核心考点分布。">学科知识图谱梳理</button>
          <button type="button" class="btn-intent-action btn-quick-prompt" data-prompt="这门学科有哪些最容易混淆的考点？请结合实例剖析。">高频易错考点分析</button>
        `
        }
      </div>
    </div>
  `;
}

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatTimestamp(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
