import { icons } from '../icons.js';
import { COMMANDS } from '../commands.js';
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
  sanitizeErrorMessage,
} from '../util.js';

export function renderChatPane(state, handlers, options = {}) {
  const session = state.sessions.find((item) => item.id === state.activeSessionId) || null;
  const model = state.models.find((item) => item.id === state.currentModelId) || state.models[0] || null;
  const messages = session?.messages || [];
  const lastMessage = messages[messages.length - 1];
  const lastAssistantGenerating = lastMessage?.role === 'assistant'
    && ['queued', 'generating'].includes(lastMessage?.status);
  const generating = (state.chatOp && ['queued', 'running', 'canceling'].includes(state.chatOp.status))
    || lastAssistantGenerating;
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
              ? `<div class="dropdown">
                  <button type="button" class="icon-btn ${state.openMenu === 'sources' ? 'is-active' : ''}" data-action="toggle-menu" data-menu="sources" title="资料" aria-expanded="${state.openMenu === 'sources'}">${icons.folder(15)}</button>
                  ${state.openMenu === 'sources' ? sourcesDrawer(state) : ''}
                </div>`
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
      <div class="chat-main">
      <div class="chat-stream" id="chat-stream">
        ${
          messages.length === 0
            ? emptyChat(options)
            : messages.map((msg) => renderMessage(msg)).join('')
        }
        ${commandBusyRow(state, session)}
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
            <div class="dropdown composer-grounding">
              <button type="button" class="icon-btn" data-action="toggle-menu" data-menu="grounding" title="依据：${groundingLabel(state.groundingMode)}" aria-expanded="${state.openMenu === 'grounding'}">${icons.shield(15)}</button>
              ${state.openMenu === 'grounding' ? groundingMenu(state.groundingMode) : ''}
            </div>
            <button type="button" class="icon-btn" data-action="pick-attach" title="附件" ${canCompose ? '' : 'disabled'}>${icons.paperclip(15)}</button>
            ${
              generating
                ? `<button type="button" class="icon-btn" data-action="stop-chat" title="停止">${icons.square(15)}</button>`
                : `<button type="button" class="icon-btn" data-action="send" title="发送" ${canCompose ? '' : 'disabled'}>${icons.send(15)}</button>`
            }
          </div>
        </div>
        <input type="file" id="chat-attach-input" hidden multiple />
      </div>
      </div>
    </section>
  `;
}

export function bindChatPane(root, handlers) {
  const textarea = root.querySelector('#composer-input');
  const composer = root.querySelector('.composer');
  if (!textarea || !composer) return;

  let menuEl = null;

  const hideMenu = () => {
    if (!menuEl) return;
    menuEl.remove();
    menuEl = null;
  };

  const selectableItems = () => (menuEl ? [...menuEl.querySelectorAll('.cmd-item:not(:disabled)')] : []);

  const setActive = (index) => {
    if (!menuEl) return;
    const buttons = [...menuEl.querySelectorAll('.cmd-item')];
    const selectable = selectableItems();
    buttons.forEach((btn) => btn.classList.remove('is-active'));
    if (!selectable.length) {
      if (buttons[0]) buttons[0].classList.add('is-active');
      return;
    }
    const next = ((index % selectable.length) + selectable.length) % selectable.length;
    selectable[next].classList.add('is-active');
  };

  const activeIndex = () => {
    const selectable = selectableItems();
    const current = selectable.findIndex((btn) => btn.classList.contains('is-active'));
    return current < 0 ? 0 : current;
  };

  const applyMention = (source) => {
    const token = lastMentionToken(textarea.value);
    if (!token) return;
    const start = textarea.value.lastIndexOf(token);
    const next = `${textarea.value.slice(0, start)}@${source.display_name} `;
    textarea.value = next;
    handlers.onComposerInput(next);
    textarea.focus();
    handlers.onMentionSource?.(source);
    hideMenu();
  };

  const showMenu = (items) => {
    hideMenu();
    if (!items.length) return;
    menuEl = document.createElement('div');
    menuEl.className = 'cmd-menu';
    menuEl.innerHTML = items
      .map((item, index) => {
        const active = index === 0 ? ' is-active' : '';
        const disabled = item.disabled ? ' disabled' : '';
        return `<button type="button" class="cmd-item${active}"${disabled}${item.attrs || ''}>${item.html}</button>`;
      })
      .join('');
    menuEl.addEventListener('click', (event) => {
      const btn = event.target.closest('.cmd-item');
      if (!btn || btn.disabled) return;
      const cmd = btn.getAttribute('data-cmd');
      const sourceId = btn.getAttribute('data-source-id');
      if (cmd) {
        textarea.value = `${cmd} `;
        handlers.onComposerInput(textarea.value);
        textarea.focus();
        hideMenu();
        return;
      }
      if (sourceId) {
        const source = (handlers.onGetMentionSources?.() || []).find((item) => item.id === sourceId);
        if (source) applyMention(source);
      }
    });
    menuEl.addEventListener('mouseover', (event) => {
      const btn = event.target.closest('.cmd-item');
      if (!btn || btn.disabled || !menuEl.contains(btn)) return;
      const selectable = selectableItems();
      setActive(selectable.indexOf(btn));
    });
    const box = composer.querySelector('.composer-box');
    composer.insertBefore(menuEl, box);
  };

  const updateMenu = (value) => {
    if (value.startsWith('/') && !value.includes(' ')) {
      const seen = new Set();
      const items = [];
      const needs = handlers.onCommandNeeds?.() || {};
      const hasExam = !!needs.exam;
      const hasDraft = !!needs.draft;
      const hasDoc = !!needs.aiDocument;
      for (const def of COMMANDS) {
        for (const name of [def.name, ...def.aliases]) {
          if (!name.startsWith(value) || seen.has(def.name)) continue;
          seen.add(def.name);
          const disabled = (def.needs === 'examOrDraft' && !hasExam && !hasDraft)
            || (def.needs === 'exam' && !hasExam)
            || (def.needs === 'aiDocument' && !hasDoc);
          items.push({
            disabled,
            attrs: ` data-cmd="${escapeHtml(name)}"`,
            html: `<b>${escapeHtml(name)}</b><span>${escapeHtml(disabled ? `${def.hint}（当前不可用）` : def.hint)}</span>`,
          });
        }
      }
      showMenu(items);
      return;
    }
    const token = lastMentionToken(value);
    if (!token) {
      hideMenu();
      return;
    }
    const query = token.slice(1);
    const sources = (handlers.onGetMentionSources?.() || []).filter((src) =>
      String(src.display_name || '').toLowerCase().startsWith(query.toLowerCase()),
    );
    if (!sources.length) {
      showMenu([{ disabled: true, html: '<span>无可用资料</span>' }]);
      return;
    }
    showMenu(
      sources.map((src) => ({
        attrs: ` data-source-id="${escapeHtml(src.id)}"`,
        html: `<b>@${escapeHtml(src.display_name)}</b>`,
      })),
    );
  };

  textarea.oninput = (event) => {
    handlers.onComposerInput(event.target.value);
    updateMenu(event.target.value);
  };
  textarea.onkeydown = (event) => {
    if (menuEl) {
      if (event.key === 'Escape') {
        event.preventDefault();
        hideMenu();
        return;
      }
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        setActive(activeIndex() + 1);
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        setActive(activeIndex() - 1);
        return;
      }
      if (event.key === 'Enter' && !event.shiftKey) {
        if (event.isComposing || event.keyCode === 229) return;
        event.preventDefault();
        selectableItems()[activeIndex()]?.click();
        return;
      }
    }
    if (event.key === 'Escape') {
      hideMenu();
      return;
    }
    if (event.key !== 'Enter' || event.shiftKey) return;
    if (event.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    handlers.onSend();
  };
  root.querySelector('#chat-attach-input')?.addEventListener('change', (event) => {
    handlers.onAddAttachments([...event.target.files]);
    event.target.value = '';
  });
}

function lastMentionToken(value) {
  const match = String(value || '').match(/(?:^|\s)(@[^\s]*)$/);
  return match ? match[1] : null;
}

function commandBusyRow(state, session) {
  const busy = state.commandBusy;
  if (!busy || !session || busy.sessionId !== session.id) return '';
  return `
    <article class="msg msg-system">
      <div class="bubble">${icons.rotateCw(14, 'spin')} ${escapeHtml(busy.label || '正在执行')}</div>
    </article>
  `;
}

function emptyChat(options) {
  return `<div class="empty"><h3>${escapeHtml(options.emptyTitle || '开始新对话')}</h3></div>`;
}

function renderMessage(msg) {
  const role = msg.role === 'user' ? 'user' : msg.role === 'assistant' ? 'assistant' : 'system';
  const isGenerating = role === 'assistant' && ['queued', 'generating'].includes(msg.status);
  const text = renderBlocks(msg.content);
  const plainText = blocksToText(msg.content);
  const status = statusLabel('message', msg.status);
  const grounding = msg.grounding_result
    ? { covered: '依据资料', 'not-covered': '未覆盖', 'general-knowledge': '常识', supplemental: '补充' }[msg.grounding_result]
    : '';
  const cites = (msg.citations || [])
    .slice(0, 3)
    .map((cite) => {
      const location = shortLocation(cite.location?.label);
      const label = location ? `${cite.source_name || '资料'} · ${location}` : (cite.source_name || '资料');
      return `<span class="cite" title="${escapeHtml(cite.excerpt || cite.location?.label || label)}">${escapeHtml(label)}</span>`;
    })
    .join('');
  const bubbleBody = isGenerating && !text && !plainText
    ? `${icons.rotateCw(14, 'spin')} 生成中`
    : `${text || escapeHtml(plainText)}${cites ? `<div class="cite-row">${cites}</div>` : ''}`;
  const retryable = role === 'assistant' && ['error', 'stopped'].includes(msg.status);
  const errorBlock = retryable
    ? `<div class="msg-error">${escapeHtml(sanitizeErrorMessage(msg.error?.message || '生成失败'))}</div>
       <button type="button" class="btn btn-ghost btn-sm" data-action="retry-message" data-id="${msg.id}">重试</button>`
    : '';
  return `
    <article class="msg msg-${role}">
      <div class="msg-meta">
        <span>${role === 'user' ? '我' : 'AI'}</span>
        ${msg.model?.model ? `<span class="model-chip">${escapeHtml(msg.model.model)}</span>` : ''}
        ${grounding ? `<span>${grounding}</span>` : ''}
        ${status ? `<span>${status}</span>` : ''}
        <span>${formatTime(msg.created_at)}</span>
      </div>
      <div class="bubble">${bubbleBody}</div>
      ${errorBlock}
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
    <div class="menu">
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

function shortLocation(label) {
  const text = String(label || '').trim();
  if (!text) return '';
  const parts = text.split('/').map((part) => part.trim()).filter(Boolean);
  return parts[parts.length - 1] || text;
}

function sourcesDrawer(state) {
  const session = state.sessions.find((item) => item.id === state.activeSessionId);
  const pinned = new Set(session?.source_version_ids || []);
  const ready = (state.sources || []).filter((src) => src.current_version?.id);
  const seen = new Map();
  ready.forEach((src) => {
    const key = src.display_name || src.id;
    seen.set(key, (seen.get(key) || 0) + 1);
  });
  const counts = new Map();
  return `
    <div class="menu menu-right">
      <div class="menu-title">会话资料</div>
      ${
        ready.length
          ? ready
              .map((src) => {
                const versionId = src.current_version.id;
                const on = pinned.has(versionId);
                const key = src.display_name || src.id;
                const dup = (seen.get(key) || 0) > 1;
                const n = dup ? (counts.set(key, (counts.get(key) || 0) + 1), counts.get(key)) : 0;
                const extra = dup ? ` · v${src.current_version?.number || n}` : (src.current_version?.number > 1 ? ` · v${src.current_version.number}` : '');
                return `<button type="button" class="menu-item ${on ? 'is-active' : ''}" data-action="${on ? 'unpin-source' : 'pin-source'}" data-id="${versionId}" title="${escapeHtml(src.display_name)}">
                  <span>${escapeHtml(src.display_name)}${extra}</span>${on ? icons.check(14) : ''}
                </button>`;
              })
              .join('')
          : '<div class="menu-title">还没有可用资料</div>'
      }
    </div>
  `;
}
