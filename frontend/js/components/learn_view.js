/**
 * Right Content Panel for 「学习」 (Learning) Workspace
 * Displays active source excerpt, AI learning document, or citation location.
 * Provides compact contextual actions: 切换资料, 查看原文位置, 加入会话, 编辑, 导出.
 */

import { icons } from '../icons.js';

export function renderLearnView(state, container, handlers) {
  const {
    sources = [],
    aiDocuments = [],
    activeSourceId,
    activeSource,
    activeAiDocumentId,
    activeAiDocument,
    activeAnchor,
    sidebarCollapsed = {},
    sessions = [],
    activeSessionId
  } = state;

  const isRightCollapsed = !!sidebarCollapsed.right;
  const activeSession = sessions.find((s) => s.id === activeSessionId) || sessions[0] || null;
  const sessionSourceVersionIds = activeSession?.source_version_ids || [];

  // Determine current active content (AI document or uploaded source)
  const isAiDoc = !!activeAiDocument;
  const currentItem = activeAiDocument || activeSource || null;
  const hasItem = !!currentItem;

  // Check if pinned to session
  const isPinned = currentItem && (
    sessionSourceVersionIds.includes(currentItem.id) ||
    (currentItem.versions || []).some((v) => sessionSourceVersionIds.includes(v.id))
  );

  container.innerHTML = `
    <div class="workspace-right-pane ${isRightCollapsed ? 'is-collapsed' : ''}" data-testid="learn-workspace-right">
      <!-- Right Content Header -->
      <div class="workspace-right-header">
        <div class="header-object-info">
          <span class="object-icon">${isAiDoc ? icons.fileText(16) : icons.book(16)}</span>
          <h3 class="object-title" title="${escapeHtml(currentItem?.title || currentItem?.name || '学习内容')}">
            ${escapeHtml(currentItem?.title || currentItem?.name || '学习内容')}
          </h3>
          ${
            hasItem
              ? `
            <span class="object-badge ${isAiDoc ? 'badge-ai' : 'badge-source'}">
              ${isAiDoc ? 'AI 笔记' : '资料'}
            </span>
          `
              : ''
          }
        </div>

        <div class="header-actions">
          <!-- Primary Action: 选资料 / 切换资料 -->
          <button type="button" class="btn-primary-action" id="btn-open-learn-drawer" title="选择或切换资料与文档">
            ${icons.list(14)} 选资料
          </button>

          ${
            hasItem
              ? `
            <!-- Context Icon Actions (Max 3) -->
            ${
              !isAiDoc
                ? `
              <button
                type="button"
                class="btn-icon-action ${isPinned ? 'is-active' : ''}"
                id="btn-pin-learn-source"
                title="${isPinned ? '已加入当前会话资料范围' : '加入当前会话资料范围'}"
              >
                ${icons.link(14)}
              </button>
            `
                : `
              <button
                type="button"
                class="btn-icon-action"
                id="btn-edit-learn-doc"
                title="修改此 AI 笔记"
              >
                ${icons.edit(14)}
              </button>
            `
            }

            <button
              type="button"
              class="btn-icon-action"
              id="btn-export-learn-content"
              title="导出当前内容"
            >
              ${icons.download(14)}
            </button>
          `
              : `
            <button type="button" class="btn-secondary-action" id="btn-create-note-learn" title="新建 AI 笔记">
              ${icons.plus(13)} 新建笔记
            </button>
          `
          }
        </div>
      </div>

      <!-- Right Content Body -->
      <div class="workspace-right-body">
        ${
          !hasItem
            ? `
          <div class="workspace-empty-state">
            <div class="empty-icon">${icons.book(28)}</div>
            <h4 class="empty-title">选份资料开始</h4>
            <p class="empty-subtitle">选择一份资料或新建笔记，随时查看重点与原文。</p>
            <div class="empty-actions-row">
              <button type="button" class="btn-primary-glow" id="btn-empty-select-source">
                ${icons.list(14)} 选资料
              </button>
              <button type="button" class="btn-outline-action" id="btn-empty-create-note">
                ${icons.plus(14)} 新建笔记
              </button>
            </div>
          </div>
        `
            : `
          <div class="document-viewer-container">
            ${
              activeAnchor
                ? `
              <div class="active-anchor-callout">
                <div class="anchor-callout-header">
                  <span class="callout-icon">${icons.tag(13)}</span>
                  <span class="callout-title">原文位置: ${escapeHtml(activeAnchor.title || activeAnchor.id || '锚点')}</span>
                  <button type="button" class="btn-icon-subtle" id="btn-close-anchor-callout" title="关闭位置标记">
                    ${icons.x(12)}
                  </button>
                </div>
                <div class="anchor-callout-text">
                  ${escapeHtml(activeAnchor.text_content || activeAnchor.content || '')}
                </div>
              </div>
            `
                : ''
            }

            <article class="document-article-body markdown-rendered-body">
              ${renderDocumentBody(currentItem)}
            </article>
          </div>
        `
        }
      </div>

      <!-- Slide-out Drawer for Selecting Materials -->
      <div class="workspace-drawer-backdrop" id="learn-drawer-backdrop" style="display: none;">
        <div class="workspace-drawer-panel" role="dialog" aria-modal="true" aria-label="资料与文档库">
          <div class="drawer-header">
            <h4 class="drawer-title">${icons.layers(16)} 资料与文档</h4>
            <button type="button" class="btn-icon-subtle" id="btn-close-learn-drawer" title="关闭">${icons.x(14)}</button>
          </div>

          <div class="drawer-body">
            <!-- Uploaded Sources Section -->
            <div class="drawer-section">
              <div class="drawer-section-header">
                <span class="section-title">用户资料 (${sources.length})</span>
                <button type="button" class="btn-text-action" id="btn-drawer-upload-source">
                  ${icons.upload(12)} 上传
                </button>
              </div>
              <div class="drawer-items-list">
                ${
                  sources.length === 0
                    ? `<div class="drawer-empty-hint">暂无上传资料</div>`
                    : sources
                        .map(
                          (src) => `
                      <div
                        class="drawer-item ${!isAiDoc && activeSource?.id === src.id ? 'is-selected' : ''}"
                        data-type="source"
                        data-id="${src.id}"
                        role="button"
                        tabindex="0"
                      >
                        <span class="item-icon">${icons.fileText(14)}</span>
                        <div class="item-info">
                          <span class="item-name">${escapeHtml(src.name || '资料')}</span>
                          <span class="item-meta">${(src.versions || []).length} 个版本</span>
                        </div>
                      </div>
                    `
                        )
                        .join('')
                }
              </div>
            </div>

            <!-- AI Documents Section -->
            <div class="drawer-section">
              <div class="drawer-section-header">
                <span class="section-title">AI 笔记文档 (${aiDocuments.length})</span>
                <button type="button" class="btn-text-action" id="btn-drawer-create-aidoc">
                  ${icons.plus(12)} 新建
                </button>
              </div>
              <div class="drawer-items-list">
                ${
                  aiDocuments.length === 0
                    ? `<div class="drawer-empty-hint">暂无 AI 笔记</div>`
                    : aiDocuments
                        .map(
                          (doc) => `
                      <div
                        class="drawer-item ${isAiDoc && activeAiDocument?.id === doc.id ? 'is-selected' : ''}"
                        data-type="aidoc"
                        data-id="${doc.id}"
                        role="button"
                        tabindex="0"
                      >
                        <span class="item-icon">${icons.sparkles(14)}</span>
                        <div class="item-info">
                          <span class="item-name">${escapeHtml(doc.title || 'AI 笔记')}</span>
                          <span class="item-meta">${(doc.versions || []).length || 1} 个版本</span>
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
      </div>
    </div>
  `;

  // Attach Event Listeners
  attachLearnEvents(container, state, handlers);
}

function renderDocumentBody(item) {
  if (!item) return '';
  const text = item.content || item.text_content || item.extracted_text || item.summary || '（此文档暂无正文内容）';
  return escapeHtml(text).replace(/\n/g, '<br/>');
}

function attachLearnEvents(container, state, handlers) {
  const drawerBackdrop = container.querySelector('#learn-drawer-backdrop');
  const openDrawerBtn = container.querySelector('#btn-open-learn-drawer');
  const closeDrawerBtn = container.querySelector('#btn-close-learn-drawer');
  const emptySelectBtn = container.querySelector('#btn-empty-select-source');

  const openDrawer = () => {
    if (drawerBackdrop) drawerBackdrop.style.display = 'block';
  };
  const closeDrawer = () => {
    if (drawerBackdrop) drawerBackdrop.style.display = 'none';
  };

  if (openDrawerBtn) openDrawerBtn.onclick = openDrawer;
  if (emptySelectBtn) emptySelectBtn.onclick = openDrawer;
  if (closeDrawerBtn) closeDrawerBtn.onclick = closeDrawer;
  if (drawerBackdrop) {
    drawerBackdrop.onclick = (e) => {
      if (e.target === drawerBackdrop) closeDrawer();
    };
  }

  // Create Note Triggers
  const createNoteBtn = container.querySelector('#btn-create-note-learn');
  const emptyCreateNoteBtn = container.querySelector('#btn-empty-create-note');
  const drawerCreateAiDocBtn = container.querySelector('#btn-drawer-create-aidoc');

  const triggerCreateNote = () => {
    closeDrawer();
    handlers.onOpenCreateAiDocModal?.();
  };

  if (createNoteBtn) createNoteBtn.onclick = triggerCreateNote;
  if (emptyCreateNoteBtn) emptyCreateNoteBtn.onclick = triggerCreateNote;
  if (drawerCreateAiDocBtn) drawerCreateAiDocBtn.onclick = triggerCreateNote;

  // Drawer Upload Source Trigger
  const drawerUploadBtn = container.querySelector('#btn-drawer-upload-source');
  if (drawerUploadBtn) {
    drawerUploadBtn.onclick = () => {
      closeDrawer();
      handlers.onSelectNavTab?.('sources');
    };
  }

  // Select Item from Drawer
  container.querySelectorAll('.drawer-item').forEach((el) => {
    el.onclick = () => {
      const type = el.getAttribute('data-type');
      const id = el.getAttribute('data-id');
      closeDrawer();
      if (type === 'source') {
        handlers.onSelectSource?.(id);
      } else if (type === 'aidoc') {
        handlers.onSelectAiDocument?.(id);
      }
    };
  });

  // Pin Source to Session
  const pinBtn = container.querySelector('#btn-pin-learn-source');
  if (pinBtn) {
    pinBtn.onclick = () => {
      const srcId = state.activeSource?.id;
      if (srcId) handlers.onTogglePinSource?.(srcId);
    };
  }

  // Edit AI Doc
  const editDocBtn = container.querySelector('#btn-edit-learn-doc');
  if (editDocBtn) {
    editDocBtn.onclick = () => {
      const docId = state.activeAiDocument?.id;
      if (docId) handlers.onOpenAiDocRevisionModal?.(docId);
    };
  }

  // Export Content
  const exportBtn = container.querySelector('#btn-export-learn-content');
  if (exportBtn) {
    exportBtn.onclick = () => {
      handlers.onExportCurrentDocument?.();
    };
  }

  // Close Anchor Callout
  const closeAnchorBtn = container.querySelector('#btn-close-anchor-callout');
  if (closeAnchorBtn) {
    closeAnchorBtn.onclick = () => {
      handlers.onClearActiveAnchor?.();
    };
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
