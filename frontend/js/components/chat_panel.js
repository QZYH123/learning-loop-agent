/**
 * Unified AI Chat Panel Component (Left Column of All 4 Workspaces)
 * Strictly aligned with Issue 17, 18, ADR 0003, ADR 0004:
 * - Session title and session switcher dropdown (+ new session, switch, rename, delete)
 * - Pinned sources & active model snapshot
 * - Complete message history with markdown rendering & code blocks
 * - Citations with anchor preview popup
 * - Real model snapshot badges on AI messages
 * - Generating live status, stop button, error state & retry
 * - Context tags above input (selectionContext or current doc)
 * - Attachments with vision capability check
 * - Compact style switch: 普通 (default), 苏格拉底 (socratic), 章节速成 (crash-course)
 * - Workspace-aware placeholder
 */

import { icons } from '../icons.js';

export function renderChatPanel(state, container, handlers) {
  const {
    sessions = [],
    activeSessionId,
    sidebarCollapsed = {},
    chat = {},
    chatAttachments = [],
    selectionContext = null,
    sources = [],
    aiDocuments = [],
    activeSource = null,
    activeAiDocument = null,
    models = [],
    currentModelId,
    activeNavTab = 'learn',
    activeOperations = new Map()
  } = state;

  const isLeftCollapsed = !!sidebarCollapsed.left;
  const activeSession = sessions.find((s) => s.id === activeSessionId) || sessions[0] || null;

  // Active Model
  const activeModelId = activeSession?.model_id || currentModelId || chat?.active_model_id;
  const activeModel = models.find((m) => m.id === activeModelId) || models[0] || null;
  const hasVision = !!activeModel?.capabilities?.vision;

  // Pinned session sources
  const sessionSourceVersionIds = activeSession?.source_version_ids || chat?.source_version_ids || [];
  const pinnedSources = sources.filter((src) =>
    (src.versions || []).some((v) => sessionSourceVersionIds.includes(v.id)) ||
    sessionSourceVersionIds.includes(src.id)
  );

  // Messages
  const messages = activeSession?.messages || chat?.messages || [];

  // Active chat style
  const currentChatStyle = activeSession?.chat_style || chat?.chat_style || 'default';

  // Check if any generation is currently running for this session
  const isGenerating = Array.from(activeOperations.values()).some(
    (op) =>
      (op.status === 'queued' || op.status === 'running') &&
      (op.type === 'chat_generation' || op.type === 'session_message' || op.type === 'crash_course')
  );

  // Placeholder based on current workspace
  let inputPlaceholder = '想学点什么？';
  if (activeNavTab === 'sources') {
    inputPlaceholder = '输入要求，让 AI 整理或修改资料...';
  } else if (activeNavTab === 'quiz_gen') {
    inputPlaceholder = '想出一套什么卷？例如：高数期末10道单选题';
  } else if (activeNavTab === 'attempts') {
    inputPlaceholder = '选中题干或输入问题，向 AI 提问...';
  }

  // Current context chip text
  let contextChipText = null;
  let contextChipType = null;
  if (selectionContext && selectionContext.text) {
    contextChipText = selectionContext.text.slice(0, 30) + (selectionContext.text.length > 30 ? '...' : '');
    contextChipType = 'selection';
  } else if (activeNavTab === 'sources' && (activeAiDocument || activeSource)) {
    const docTitle = activeAiDocument?.title || activeSource?.name || '当前资料';
    contextChipText = docTitle.slice(0, 24) + (docTitle.length > 24 ? '...' : '');
    contextChipType = 'doc';
  }

  container.innerHTML = `
    <div class="chat-panel-container ${isLeftCollapsed ? 'is-collapsed' : ''}" data-testid="chat-panel">
      <!-- Chat Header -->
      <div class="chat-panel-header">
        <div class="chat-header-main">
          <!-- Session Switcher Dropdown Anchor -->
          <div class="dropdown-anchor" id="session-dropdown-anchor">
            <button
              type="button"
              class="btn-session-dropdown-trigger"
              id="btn-session-dropdown"
              aria-haspopup="true"
              aria-expanded="false"
              title="切换或管理学习会话"
            >
              ${icons.messageSquare(15)}
              <span class="session-trigger-title" style="max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                ${escapeHtml(activeSession?.title || '学习会话')}
              </span>
              ${icons.chevronDown(13)}
            </button>

            <div class="dropdown-popup session-popup-menu" id="session-popup-menu" role="menu" style="display: none;">
              <div class="dropdown-header">
                <span class="dropdown-header-title">会话列表</span>
                <button type="button" class="btn-text-action" id="btn-create-session-trigger">
                  ${icons.plus(13)} 新建
                </button>
              </div>

              <div class="session-dropdown-list" role="presentation">
                ${
                  sessions.length === 0
                    ? `<div class="dropdown-empty-hint">暂无会话，请点击新建</div>`
                    : sessions
                        .map(
                          (s) => `
                      <div
                        class="session-menu-item ${s.id === (activeSession?.id || activeSessionId) ? 'is-active' : ''}"
                        data-session-id="${s.id}"
                        role="menuitem"
                        tabindex="0"
                      >
                        <div class="session-item-content">
                          <span class="session-item-title">${escapeHtml(s.title || '学习会话')}</span>
                          <span class="session-item-meta">${(s.messages || []).length} 条对话</span>
                        </div>
                        <button
                          type="button"
                          class="btn-icon-subtle btn-delete-session"
                          data-session-id="${s.id}"
                          title="删除会话"
                        >
                          ${icons.trash(12)}
                        </button>
                      </div>
                    `
                        )
                        .join('')
                }
              </div>
            </div>
          </div>
        </div>

        <!-- Right Header Tools: Context Info & Collapse Sidebar Toggle -->
        <div class="chat-header-actions">
          <button
            type="button"
            class="btn-icon-subtle btn-collapse-left"
            id="btn-toggle-chat-collapse"
            title="${isLeftCollapsed ? '展开对话栏' : '收起对话栏'}"
          >
            ${isLeftCollapsed ? icons.chevronRight(15) : icons.chevronLeft(15)}
          </button>
        </div>
      </div>

      <!-- Collapsed Strip (when isLeftCollapsed is true) -->
      ${
        isLeftCollapsed
          ? `
        <div class="chat-collapsed-strip" id="chat-collapsed-expand-btn" role="button" tabindex="0" title="点击展开 AI 对话">
          <span class="collapsed-icon">${icons.messageSquare(18)}</span>
          <span class="collapsed-label">AI 对话</span>
        </div>
      `
          : `
        <!-- Compact Context Bar -->
        <div class="chat-context-bar">
          <div class="context-bar-left">
            <span class="context-pill" title="当前模型: ${escapeHtml(activeModel?.name || '默认模型')} (${formatApiFormat(activeModel?.api_format)})">
              ${icons.cpu(12)}
              <span class="pill-text">${escapeHtml(activeModel?.name || '默认模型')}</span>
            </span>
            ${
              pinnedSources.length > 0
                ? `
              <span class="context-pill" title="已固定 ${pinnedSources.length} 份资料作为上下文">
                ${icons.book(12)}
                <span class="pill-text">${pinnedSources.length} 份资料</span>
              </span>
            `
                : ''
            }
          </div>
          <div class="context-bar-right">
            <button type="button" class="btn-clear-chat" id="btn-clear-chat" title="清空当前会话记录">
              ${icons.trash(12)} 清空
            </button>
          </div>
        </div>

        <!-- Messages Scrollable Area -->
        <div class="chat-messages-scroll" id="chat-messages-container">
          ${
            messages.length === 0
              ? `
            <div class="chat-empty-state">
              <div class="empty-icon-wrap">${icons.sparkles(24)}</div>
              <h4 class="empty-title">开始聊聊</h4>
              <p class="empty-desc">随时提出问题，或输入指令让 AI 梳理重点、组卷出题或润色资料。</p>
              <div class="empty-quick-prompts">
                <button type="button" class="quick-prompt-btn" data-prompt="梳理当前资料的核心重点和知识脉络">
                  ${icons.compass(13)} 梳理重点
                </button>
                <button type="button" class="quick-prompt-btn" data-prompt="帮我出一套期末自测题，题型多样">
                  ${icons.target(13)} 出套自测题
                </button>
                <button type="button" class="quick-prompt-btn" data-prompt="用苏格拉底提问方式考考我">
                  ${icons.messageSquare(13)} 考考我
                </button>
              </div>
            </div>
          `
              : messages
                  .map((msg, idx) => renderChatMessage(msg, idx, activeModel))
                  .join('')
          }

          ${
            isGenerating
              ? `
            <div class="chat-generating-bubble">
              <div class="generating-dot-pulse">
                <span></span><span></span><span></span>
              </div>
              <span class="generating-text">正在生成回答...</span>
              <button type="button" class="btn-stop-generation" id="btn-stop-generation-inline" title="停止生成">
                ${icons.stopCircle(14)} 停止
              </button>
            </div>
          `
              : ''
          }
        </div>

        <!-- Chat Input Footer -->
        <div class="chat-input-footer">
          <!-- Context Chip (if selection or active document) -->
          ${
            contextChipText
              ? `
            <div class="chat-context-chip-row">
              <div class="chat-context-chip">
                <span class="chip-icon">${contextChipType === 'selection' ? icons.tag(12) : icons.fileText(12)}</span>
                <span class="chip-label">${contextChipType === 'selection' ? '选区' : '当前文档'}:</span>
                <span class="chip-content" title="${escapeHtml(contextChipText)}">${escapeHtml(contextChipText)}</span>
                <button type="button" class="btn-chip-remove" id="btn-clear-selection-context" title="移除上下文">
                  ${icons.x(12)}
                </button>
              </div>
            </div>
          `
              : ''
          }

          <!-- Attachments Preview Bar -->
          ${
            chatAttachments.length > 0
              ? `
            <div class="chat-attachments-row">
              ${chatAttachments
                .map(
                  (att) => `
                <div class="attachment-preview-chip">
                  <span class="att-icon">${att.is_image ? icons.eye(12) : icons.fileText(12)}</span>
                  <span class="att-filename">${escapeHtml(att.filename || '附件')}</span>
                  <button type="button" class="btn-remove-attachment" data-att-id="${att.id}" title="删除附件">
                    ${icons.x(12)}
                  </button>
                </div>
              `
                )
                .join('')}
            </div>
          `
              : ''
          }

          <!-- Style Switcher (Segmented Control: 普通 / 苏格拉底 / 章节速成) -->
          <div class="chat-style-switch-row">
            <div class="style-segmented-control" role="radiogroup" aria-label="对话风格">
              <button
                type="button"
                class="style-segment-btn ${currentChatStyle === 'default' ? 'is-active' : ''}"
                data-style="default"
                role="radio"
                aria-checked="${currentChatStyle === 'default'}"
                title="普通问答：直接解答问题与详细说明"
              >
                普通
              </button>
              <button
                type="button"
                class="style-segment-btn ${currentChatStyle === 'socratic' ? 'is-active' : ''}"
                data-style="socratic"
                role="radio"
                aria-checked="${currentChatStyle === 'socratic'}"
                title="苏格拉底：通过循序反问与引导启发思考"
              >
                苏格拉底
              </button>
              <button
                type="button"
                class="style-segment-btn ${currentChatStyle === 'crash-course' ? 'is-active' : ''}"
                data-style="crash-course"
                role="radio"
                aria-checked="${currentChatStyle === 'crash-course'}"
                title="章节速成：按章节提纲快速梳理重点"
              >
                章节速成
              </button>
            </div>
          </div>

          <!-- Input Textarea & Action Buttons -->
          <div class="chat-input-box">
            <textarea
              class="chat-textarea"
              id="chat-input-textarea"
              placeholder="${escapeHtml(inputPlaceholder)}"
              rows="2"
              autofocus
            ></textarea>

            <div class="chat-input-controls">
              <div class="input-controls-left">
                <!-- Attachment Button -->
                <button
                  type="button"
                  class="btn-icon-control"
                  id="btn-upload-chat-attachment"
                  title="${hasVision ? '上传图片或文档附件' : '上传文档附件 (当前模型不支持视觉输入)'}"
                >
                  ${icons.paperclip(15)}
                </button>
                <input type="file" id="chat-file-input" style="display: none;" accept="image/*,.pdf,.txt,.md,.docx,.pptx" />
              </div>

              <div class="input-controls-right">
                ${
                  isGenerating
                    ? `
                  <button type="button" class="btn-send-chat btn-stop" id="btn-stop-chat" title="停止生成">
                    ${icons.stopCircle(16)}
                  </button>
                `
                    : `
                  <button type="button" class="btn-send-chat" id="btn-send-chat" title="发送消息 (Enter)">
                    ${icons.send(16)}
                  </button>
                `
                }
              </div>
            </div>
          </div>
        </div>
      `
      }
    </div>
  `;

  // Attach Event Listeners
  attachChatEventListeners(container, state, handlers);
}

function renderChatMessage(msg, idx, activeModel) {
  const isUser = msg.role === 'user';
  const citations = msg.citations || [];
  const modelSnapshot = msg.model_id || activeModel?.name || '';
  const apiFormat = msg.api_format || activeModel?.api_format || '';

  return `
    <div class="chat-message-item ${isUser ? 'is-user-msg' : 'is-assistant-msg'}" data-msg-idx="${idx}">
      <div class="msg-bubble">
        <div class="msg-content markdown-rendered-body">
          ${renderMarkdown(msg.content || '')}
        </div>

        ${
          citations.length > 0
            ? `
          <div class="msg-citations-row">
            <span class="citations-label">${icons.link(12)} 来源:</span>
            ${citations
              .map(
                (c, cIdx) => `
              <button
                type="button"
                class="citation-pill"
                data-citation-id="${c.id || ''}"
                data-anchor-id="${c.anchor_id || ''}"
                data-version-id="${c.source_version_id || ''}"
                title="${escapeHtml(c.text_excerpt || '查看原文位置')}"
              >
                [${cIdx + 1}] ${escapeHtml(c.source_title || '资料')}
              </button>
            `
              )
              .join('')}
          </div>
        `
            : ''
        }

        ${
          !isUser && modelSnapshot
            ? `
          <div class="msg-footer-snapshot">
            <span class="model-badge-text">
              ${escapeHtml(modelSnapshot)}${apiFormat ? ` · ${formatApiFormat(apiFormat)}` : ''}
            </span>
          </div>
        `
            : ''
        }
      </div>
    </div>
  `;
}

function attachChatEventListeners(container, state, handlers) {
  const { activeSession, activeSessionId, sessions = [] } = state;

  // Toggle Collapse
  const toggleBtn = container.querySelector('#btn-toggle-chat-collapse');
  if (toggleBtn) {
    toggleBtn.onclick = () => handlers.onToggleSidebar?.('left');
  }

  const expandStrip = container.querySelector('#chat-collapsed-expand-btn');
  if (expandStrip) {
    expandStrip.onclick = () => handlers.onToggleSidebar?.('left');
  }

  // Session Dropdown
  const sessionBtn = container.querySelector('#btn-session-dropdown');
  const sessionMenu = container.querySelector('#session-popup-menu');
  if (sessionBtn && sessionMenu) {
    sessionBtn.onclick = (e) => {
      e.stopPropagation();
      const isExpanded = sessionBtn.getAttribute('aria-expanded') === 'true';
      sessionBtn.setAttribute('aria-expanded', !isExpanded);
      sessionMenu.style.display = isExpanded ? 'none' : 'block';
    };

    const handleOutsideClick = (e) => {
      if (!sessionMenu.contains(e.target) && e.target !== sessionBtn) {
        sessionBtn.setAttribute('aria-expanded', 'false');
        sessionMenu.style.display = 'none';
        document.removeEventListener('click', handleOutsideClick);
      }
    };
    document.addEventListener('click', handleOutsideClick);
  }

  // Create Session
  const createSessBtn = container.querySelector('#btn-create-session-trigger');
  if (createSessBtn) {
    createSessBtn.onclick = (e) => {
      e.stopPropagation();
      if (sessionMenu) sessionMenu.style.display = 'none';
      handlers.onOpenCreateSessionModal?.();
    };
  }

  // Switch Session
  container.querySelectorAll('.session-menu-item').forEach((item) => {
    item.onclick = (e) => {
      if (e.target.closest('.btn-delete-session')) return;
      const sid = item.getAttribute('data-session-id');
      if (sid && sid !== activeSessionId) {
        if (sessionMenu) sessionMenu.style.display = 'none';
        handlers.onSwitchSession?.(sid);
      }
    };
  });

  // Delete Session
  container.querySelectorAll('.btn-delete-session').forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const sid = btn.getAttribute('data-session-id');
      if (sid) {
        if (sessionMenu) sessionMenu.style.display = 'none';
        handlers.onDeleteSession?.(sid);
      }
    };
  });

  // Clear Chat
  const clearBtn = container.querySelector('#btn-clear-chat');
  if (clearBtn) {
    clearBtn.onclick = () => handlers.onClearChat?.();
  }

  // Quick Prompts
  container.querySelectorAll('.quick-prompt-btn').forEach((btn) => {
    btn.onclick = () => {
      const prompt = btn.getAttribute('data-prompt');
      if (prompt) {
        const textarea = container.querySelector('#chat-input-textarea');
        if (textarea) {
          textarea.value = prompt;
          textarea.focus();
        }
      }
    };
  });

  // Clear Selection Context
  const clearCtxBtn = container.querySelector('#btn-clear-selection-context');
  if (clearCtxBtn) {
    clearCtxBtn.onclick = () => handlers.onClearSelectionContext?.();
  }

  // Remove Attachment
  container.querySelectorAll('.btn-remove-attachment').forEach((btn) => {
    btn.onclick = () => {
      const aid = btn.getAttribute('data-att-id');
      handlers.onRemoveChatAttachment?.(aid);
    };
  });

  // Style Switcher
  container.querySelectorAll('.style-segment-btn').forEach((btn) => {
    btn.onclick = () => {
      const style = btn.getAttribute('data-style');
      handlers.onSwitchChatStyle?.(style);
    };
  });

  // File Upload Attachment Trigger
  const attBtn = container.querySelector('#btn-upload-chat-attachment');
  const fileInput = container.querySelector('#chat-file-input');
  if (attBtn && fileInput) {
    attBtn.onclick = () => fileInput.click();
    fileInput.onchange = (e) => {
      const file = e.target.files?.[0];
      if (file) {
        handlers.onUploadChatAttachment?.(file);
        fileInput.value = '';
      }
    };
  }

  // Textarea input and auto-resize
  const textarea = container.querySelector('#chat-input-textarea');
  if (textarea) {
    textarea.oninput = () => {
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 180) + 'px';
    };

    textarea.onkeydown = (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    };
  }

  // Send Button
  const sendBtn = container.querySelector('#btn-send-chat');
  if (sendBtn) {
    sendBtn.onclick = () => sendMessage();
  }

  // Stop Button
  const stopBtn = container.querySelector('#btn-stop-chat') || container.querySelector('#btn-stop-generation-inline');
  if (stopBtn) {
    stopBtn.onclick = () => handlers.onStopGeneration?.();
  }

  // Citation Pills Click (Anchor Inspector or jump to right view)
  container.querySelectorAll('.citation-pill').forEach((pill) => {
    pill.onclick = () => {
      const citationId = pill.getAttribute('data-citation-id');
      const anchorId = pill.getAttribute('data-anchor-id');
      const versionId = pill.getAttribute('data-version-id');
      handlers.onInspectCitation?.({ citationId, anchorId, versionId });
    };
  });

  function sendMessage() {
    if (!textarea) return;
    const text = textarea.value.trim();
    if (!text && state.chatAttachments.length === 0) return;

    handlers.onSendMessage?.(text);
    textarea.value = '';
    textarea.style.height = 'auto';
  }

  // Auto scroll messages to bottom
  const scrollArea = container.querySelector('#chat-messages-container');
  if (scrollArea) {
    scrollArea.scrollTop = scrollArea.scrollHeight;
  }
}

function renderMarkdown(md) {
  if (!md) return '';
  // Basic safe markdown parser for headings, bold, code blocks, lists, line breaks
  let html = escapeHtml(md);

  // Fenced Code blocks
  html = html.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre class="code-block" data-lang="${lang}"><code>${code}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

  // Headings
  html = html.replace(/^### (.*?)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.*?)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.*?)$/gm, '<h1>$1</h1>');

  // Bold & Italic
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

  // Unordered list items
  html = html.replace(/^\s*[-*]\s+(.*?)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

  // Paragraphs
  html = html.replace(/\n\n/g, '<br/><br/>');

  return html;
}

function formatApiFormat(fmt) {
  if (fmt === 'openai-chat-completions') return 'Chat Completions';
  if (fmt === 'openai-responses') return 'Responses';
  if (fmt === 'ollama') return 'Ollama';
  return fmt || 'Chat Completions';
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
