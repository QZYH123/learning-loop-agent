import { icons } from '../icons.js';
import { escapeHtml, formatTime, sessionVisible, styleLabel } from '../util.js';
import { bindChatPane, renderChatPane } from './chat.js';

export function learnShellHtml(state) {
  const collapsed = !!state.sidebarCollapsed.learn;
  return `
    <div class="ws ws-learn ${collapsed ? 'is-collapsed' : ''}" data-mobile="${state.mobilePane.learn}" data-testid="learning-workspace">
      <div class="mobile-switch">
        <button type="button" class="seg ${state.mobilePane.learn === 'sessions' ? 'is-active' : ''}" data-action="mobile-pane" data-pane="sessions">会话</button>
        <button type="button" class="seg ${state.mobilePane.learn === 'chat' ? 'is-active' : ''}" data-action="mobile-pane" data-pane="chat">对话</button>
      </div>
      <aside class="pane pane-sessions"></aside>
      <main class="pane pane-chat"></main>
    </div>
  `;
}

export function learnLeftHtml(state) {
  const query = (state.sessionSearch || '').trim().toLowerCase();
  const sessions = (state.sessions || []).filter(
    (item) => sessionVisible(item) && (item.title || '').toLowerCase().includes(query),
  );
  return `
        <div class="pane-head">
          <div class="pane-title">${icons.messageSquare(15)}<span>会话</span></div>
          <div class="pane-actions">
            <button type="button" class="icon-btn" data-action="create-session" title="新建">${icons.plus(15)}</button>
            <button type="button" class="icon-btn" data-action="collapse-left" title="收起">${icons.panelLeftClose(15)}</button>
          </div>
        </div>
        <div class="search">${icons.search(13)}<input id="session-search" placeholder="搜索" value="${escapeHtml(state.sessionSearch)}" /></div>
        <div class="list">
          ${
            sessions.length === 0
              ? `<div class="empty">
                  <h3>${query ? '没有匹配会话' : '开始新对话'}</h3>
                  <button type="button" class="btn btn-primary btn-sm" data-action="create-session">${icons.plus(13)} 新建</button>
                </div>`
              : sessions.map((item) => sessionItem(item, state)).join('')
          }
        </div>
  `;
}

export function learnRightHtml(state, handlers) {
  return renderChatPane(state, handlers, { variant: 'learn', placeholder: '想学点什么？', emptyTitle: '开始新对话', testId: 'learn-chat' });
}

export function bindLearnLeft(root, handlers) {
  const search = root.querySelector('#session-search');
  if (search) search.oninput = (event) => handlers.onSearchSessions(event.target.value);
}

export function bindLearnRight(root, handlers) {
  bindChatPane(root, handlers);
}

function sessionItem(item, state) {
  const active = item.id === state.activeSessionId;
  const renaming = state.renamingSessionId === item.id;
  return `
    <div class="item ${active ? 'is-active' : ''}" data-action="select-session" data-id="${item.id}">
      <div class="item-main">
        ${
          renaming
            ? `<input class="input inline-rename" data-rename-session value="${escapeHtml(item.title || '')}" />`
            : `<div class="item-title">${escapeHtml(item.title || '学习会话')}</div>`
        }
        <div class="item-sub">
          <span>${styleLabel(item.chat_style)}</span>
          <span>${formatTime(item.updated_at || item.created_at)}</span>
        </div>
      </div>
      <div class="item-ops">
        <button type="button" class="ghost-icon" data-action="rename-session" data-id="${item.id}" title="重命名">${icons.edit3(13)}</button>
        <button type="button" class="ghost-icon is-danger" data-action="delete-session" data-id="${item.id}" title="删除">${icons.trash2(13)}</button>
      </div>
    </div>
  `;
}
