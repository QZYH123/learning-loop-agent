import { icons } from '../icons.js';
import {
  CHAT_STYLES,
  GROUNDING_MODES,
  sessionVisible,
  blocksToText,
  escapeHtml,
  formatTime,
  groundingLabel,
  renderBlocks,
  statusLabel,
  styleLabel,
  truncate,
} from '../util.js';

export function renderChatPane(state, handlers, options = {}) {
  const session = state.sessions.find((item) => item.id === state.activeSessionId) || null;
  const model = state.models.find((item) => item.id === state.currentModelId) || state.models[0] || null;
  const messages = session?.messages || [];
  const generating = state.chatOp && ['queued', 'running', 'canceling'].includes(state.chatOp.status);
  const placeholder = options.placeholder || '想学点什么？';
  const style = session?.chat_style || state.draftStyle || 'default';
  const canCompose = !!model && !!state.activeSubjectId;
  const collapsed = !!state.sidebarCollapsed[state.workspace === 'learn' ? 'learn' : state.workspace];
  const isBlank = options.variant === 'learn' && !generating && (!session || messages.length === 0);

  return `
    <section class="chat ${isBlank ? 'is-blank' : ''}" data-testid="${options.testId || 'chat-pane'}">
      <div class="pane-head">
        <div class="head-meta">
          ${
            options.variant === 'learn' && collapsed
              ? `<button type="button" class="icon-btn" data-action="collapse-left" title="展开">${icons.panelLeftOpen(15)}</button>`
              : ''
          }
          ${
            options.variant === 'task'
              ? `<div class="dropdown">
                  <button type="button" class="chip-btn" data-action="toggle-menu" data-menu="session" title="切换会话" aria-expanded="${state.openMenu === 'session'}">
                    ${icons.messageSquare(14)}
                    <span class="chip-label">${escapeHtml(session && sessionVisible(session) ? session.title : '新对话')}</span>
                    ${icons.chevronDown(14)}
                  </button>
                  ${state.openMenu === 'session' ? sessionMenu(state) : ''}
                </div>`
              : `<div class="pane-title"><span title="${escapeHtml(session && sessionVisible(session) ? session.title : '新对话')}">${escapeHtml(session && sessionVisible(session) ? session.title : '新对话')}</span></div>`
          }
        </div>
        <div class="pane-actions">
          ${
            options.variant === 'learn'
              ? `<button type="button" class="icon-btn ${state.openMenu === 'sources' ? 'is-active' : ''}" data-action="toggle-menu" data-menu="sources" title="资料">${icons.folder(15)}</button>`
              : ''
          }
          <div class="dropdown">
            <button type="button" class="chip-btn" data-action="toggle-menu" data-menu="style" title="对话风格" aria-expanded="${state.openMenu === 'style'}">
              ${icons.sparkles(14)}
              <span class="chip-label">${styleLabel(style)}</span>
            </button>
            ${state.openMenu === 'style' ? styleMenu(style) : ''}
          </div>
          ${
            options.variant === 'learn'
              ? `<div class="dropdown">
                  <button type="button" class="chip-btn" data-action="toggle-menu" data-menu="model" title="模型" aria-expanded="${state.openMenu === 'model'}">
                    ${icons.cpu(14)}
                    <span class="chip-label">${escapeHtml(model?.model || '模型')}</span>
                  </button>
                  ${state.openMenu === 'model' ? modelMenu(state) : ''}
                </div>`
              : ''
          }
          ${
            options.variant === 'learn' && !collapsed
              ? `<button type="button" class="icon-btn" data-action="collapse-left" title="收起">${icons.panelLeftClose(15)}</button>`
              : options.variant === 'task' && !collapsed
                ? `<button type="button" class="icon-btn" data-action="collapse-left" title="收起">${icons.panelLeftClose(15)}</button>`
                : ''
          }
        </div>
      </div>
      ${state.openMenu === 'sources' && options.variant === 'learn' ? sourcesDrawer(state) : ''}
      <div class="chat-main">
      <div class="chat-stream" id="chat-stream">
        ${
          messages.length === 0
            ? emptyChat(options)
            : messages.map((msg) => renderMessage(msg)).join('')
        }
        ${generating ? `<div class="msg msg-assistant"><div class="bubble">${icons.rotateCw(14, 'spin')} 生成中</div></div>` : ''}
      </div>
      <div class="composer">
        ${state.selection ? `<div class="sel-chip">${icons.bookmark(13)}<span title="${escapeHtml(state.selection.selected_text)}">${escapeHtml(truncate(state.selection.selected_text, 42))}</span><button type="button" class="ghost-icon" data-action="clear-selection" title="去掉选区">${icons.x(12)}</button></div>` : ''}
        ${
          (state.attachments || []).length
            ? `<div class="att-row">${state.attachments
                .map(
                  (att, index) =>
                    `<span class="att-name">${escapeHtml(att.name)}</span><button type="button" class="ghost-icon" data-action="remove-att" data-index="${index}" title="移除">${icons.x(12)}</button>`,
                )
                .join('')}</div>`
            : ''
        }
        <div class="composer-box">
          <textarea id="composer-input" rows="2" placeholder="${escapeHtml(placeholder)}" ${canCompose ? '' : 'disabled'}>${escapeHtml(state.composerText)}</textarea>
          <div class="composer-tools">
            <button type="button" class="icon-btn" data-action="toggle-menu" data-menu="grounding" title="依据：${groundingLabel(state.groundingMode)}">${icons.shield(15)}</button>
            <button type="button" class="icon-btn" data-action="pick-attach" title="附件" ${canCompose ? '' : 'disabled'}>${icons.paperclip(15)}</button>
            ${
              generating
                ? `<button type="button" class="icon-btn" data-action="stop-chat" title="停止">${icons.square(15)}</button>`
                : `<button type="button" class="icon-btn" data-action="send" title="发送" ${canCompose ? '' : 'disabled'}>${icons.send(15)}</button>`
            }
          </div>
        </div>
        ${state.openMenu === 'grounding' ? groundingMenu(state.groundingMode) : ''}
        <input type="file" id="chat-attach-input" hidden multiple />
      </div>
      </div>
    </section>
  `;
}

export function bindChatPane(root, handlers) {
  const textarea = root.querySelector('#composer-input');
  if (textarea) {
    textarea.oninput = (event) => handlers.onComposerInput(event.target.value);
    textarea.onkeydown = (event) => {
      if (event.key !== 'Enter' || event.shiftKey) return;
      if (event.isComposing || event.keyCode === 229) return;
      event.preventDefault();
      handlers.onSend();
    };
  }
  root.querySelector('#chat-attach-input')?.addEventListener('change', (event) => {
    handlers.onAddAttachments([...event.target.files]);
    event.target.value = '';
  });
}

function emptyChat(options) {
  return `<div class="empty"><h3>${escapeHtml(options.emptyTitle || '开始新对话')}</h3></div>`;
}

function renderMessage(msg) {
  const role = msg.role === 'user' ? 'user' : msg.role === 'assistant' ? 'assistant' : 'system';
  const text = renderBlocks(msg.content);
  const status = statusLabel('message', msg.status);
  const grounding = msg.grounding_result
    ? { covered: '依据资料', 'not-covered': '未覆盖', 'general-knowledge': '常识', supplemental: '补充' }[msg.grounding_result]
    : '';
  const cites = (msg.citations || [])
    .map((cite) => `<span class="cite" title="${escapeHtml(cite.excerpt || cite.location?.label || '')}">${escapeHtml(cite.source_name || '资料')}${cite.location?.label ? ` · ${escapeHtml(cite.location.label)}` : ''}</span>`)
    .join('');
  return `
    <article class="msg msg-${role}">
      <div class="msg-meta">
        <span>${role === 'user' ? '我' : 'AI'}</span>
        ${msg.model?.model ? `<span class="model-chip">${escapeHtml(msg.model.model)}</span>` : ''}
        ${grounding ? `<span>${grounding}</span>` : ''}
        ${status ? `<span>${status}</span>` : ''}
        <span>${formatTime(msg.created_at)}</span>
      </div>
      <div class="bubble">${text || escapeHtml(blocksToText(msg.content))}${cites ? `<div class="cite-row">${cites}</div>` : ''}</div>
    </article>
  `;
}

function sessionMenu(state) {
  return `
    <div class="menu">
      ${(state.sessions || [])
        .filter((item) => sessionVisible(item))
        .map(
          (item) => `
        <button type="button" class="menu-item ${item.id === state.activeSessionId ? 'is-active' : ''}" data-action="select-session" data-id="${item.id}">
          <span>${escapeHtml(item.title || '学习会话')}</span>
        </button>
      `,
        )
        .join('')}
      <div class="menu-split"></div>
      <button type="button" class="menu-item" data-action="create-session">${icons.plus(14)}<span>新建</span></button>
    </div>
  `;
}

function styleMenu(current) {
  return `
    <div class="menu menu-right">
      ${CHAT_STYLES.map(
        (item) => `
        <button type="button" class="menu-item ${item.id === current ? 'is-active' : ''}" data-action="set-style" data-id="${item.id}">
          <span>${item.label}</span>
        </button>
      `,
      ).join('')}
    </div>
  `;
}

function modelMenu(state) {
  return `
    <div class="menu menu-right">
      ${(state.models || [])
        .map(
          (item) => `
        <button type="button" class="menu-item ${item.id === state.currentModelId ? 'is-active' : ''}" data-action="select-model" data-id="${item.id}">
          <span>${escapeHtml(item.model)}</span>
        </button>
      `,
        )
        .join('')}
      <div class="menu-split"></div>
      <button type="button" class="menu-item" data-action="open-models">${icons.sliders(14)}<span>配置</span></button>
    </div>
  `;
}

function groundingMenu(current) {
  return `
    <div class="menu menu-right" style="bottom: 58px; top: auto; right: 54px;">
      ${GROUNDING_MODES.map(
        (item) => `
        <button type="button" class="menu-item ${item.id === current ? 'is-active' : ''}" data-action="set-grounding" data-id="${item.id}">
          <span>${item.label}</span>
        </button>
      `,
      ).join('')}
    </div>
  `;
}

function sourcesDrawer(state) {
  const session = state.sessions.find((item) => item.id === state.activeSessionId);
  const pinned = new Set(session?.source_version_ids || []);
  const ready = (state.sources || []).filter((src) => src.current_version?.id);
  return `
    <div class="menu" style="position:absolute;top:48px;right:12px;z-index:20;">
      <div class="menu-title">会话资料</div>
      ${
        ready.length
          ? ready
              .map((src) => {
                const versionId = src.current_version.id;
                const on = pinned.has(versionId);
                return `<button type="button" class="menu-item ${on ? 'is-active' : ''}" data-action="${on ? 'unpin-source' : 'pin-source'}" data-id="${versionId}">
                  <span>${escapeHtml(src.display_name)}</span>${on ? icons.check(14) : ''}
                </button>`;
              })
              .join('')
          : '<div class="menu-title">还没有可用资料</div>'
      }
    </div>
  `;
}
