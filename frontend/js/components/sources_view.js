/**
 * Right Content Panel for 「资料」 (Sources & AI Documents) Workspace
 * Strictly aligned with Issue 20 & ADR 0003:
 * - Sub-tabs: 用户资料 (User Uploaded) vs AI 文档 (AI Generated)
 * - User Uploaded: Read-only, anchors viewer, upload source, pin to session
 * - AI Documents: Create doc, revision proposals diff view, apply/discard edits, restore version
 * - Clean empty states with direct actions
 */

import { icons } from '../icons.js';

export function renderSourcesView(state, container, handlers) {
  const {
    sources = [],
    activeSourceId,
    activeSource,
    activeSourceVersions = [],
    activeSourceAnchors = [],
    activeAnchor,
    aiDocuments = [],
    activeAiDocumentId,
    activeAiDocument,
    aiDocumentVersions = [],
    aiDocumentProposals = [],
    activeAiDocProposal,
    sourcesTab = 'user_sources', // 'user_sources' | 'ai_documents'
    sidebarCollapsed = {},
    sessions = [],
    activeSessionId
  } = state;

  const isRightCollapsed = !!sidebarCollapsed.right;
  const isUserSourcesTab = sourcesTab === 'user_sources';

  const activeSession = sessions.find((s) => s.id === activeSessionId) || sessions[0] || null;
  const sessionSourceVersionIds = activeSession?.source_version_ids || [];

  container.innerHTML = `
    <div class="workspace-right-pane ${isRightCollapsed ? 'is-collapsed' : ''}" data-testid="sources-workspace-right">
      <!-- Right Content Header -->
      <div class="workspace-right-header">
        <div class="header-object-info">
          <!-- Sub-tabs Switcher: 用户资料 | AI 文档 -->
          <div class="sources-subtab-switcher" role="tablist" aria-label="资料分类">
            <button
              type="button"
              class="subtab-btn ${isUserSourcesTab ? 'is-active' : ''}"
              id="btn-tab-user-sources"
              role="tab"
              aria-selected="${isUserSourcesTab}"
            >
              ${icons.layers(14)} 用户资料 (${sources.length})
            </button>
            <button
              type="button"
              class="subtab-btn ${!isUserSourcesTab ? 'is-active' : ''}"
              id="btn-tab-ai-docs"
              role="tab"
              aria-selected="${!isUserSourcesTab}"
            >
              ${icons.fileText(14)} AI 文档 (${aiDocuments.length})
            </button>
          </div>
        </div>

        <div class="header-actions">
          ${
            isUserSourcesTab
              ? `
            <!-- Upload Source Primary Action -->
            <button type="button" class="btn-primary-action" id="btn-trigger-upload-source" title="上传新的资料文件">
              ${icons.upload(14)} 上传资料
            </button>
            <input type="file" id="source-file-input" style="display: none;" accept=".pdf,.txt,.md,.docx,.pptx,image/*" />

            <button type="button" class="btn-icon-action" id="btn-toggle-sources-drawer" title="资料列表">
              ${icons.list(14)}
            </button>
          `
              : `
            <!-- Create AI Document Primary Action -->
            <button type="button" class="btn-primary-action" id="btn-trigger-create-aidoc" title="新建 AI 资料文档">
              ${icons.plus(14)} 创建文档
            </button>

            ${
              activeAiDocument
                ? `
              <button type="button" class="btn-icon-action" id="btn-trigger-propose-revision" title="修改此文档">
                ${icons.edit(14)}
              </button>
            `
                : ''
            }

            <button type="button" class="btn-icon-action" id="btn-toggle-aidocs-drawer" title="文档列表">
              ${icons.list(14)}
            </button>
          `
          }
        </div>
      </div>

      <!-- Right Content Body -->
      <div class="workspace-right-body">
        ${
          isUserSourcesTab
            ? renderUserSourcesContent(state)
            : renderAiDocumentsContent(state)
        }
      </div>

      <!-- Item Switcher Drawer -->
      <div class="workspace-drawer-backdrop" id="sources-drawer-backdrop" style="display: none;">
        <div class="workspace-drawer-panel" role="dialog" aria-modal="true" aria-label="${isUserSourcesTab ? '资料列表' : 'AI 文档列表'}">
          <div class="drawer-header">
            <h4 class="drawer-title">${isUserSourcesTab ? icons.layers(16) : icons.fileText(16)} ${isUserSourcesTab ? '资料列表' : 'AI 文档列表'}</h4>
            <button type="button" class="btn-icon-subtle" id="btn-close-sources-drawer" title="关闭">${icons.x(14)}</button>
          </div>

          <div class="drawer-body">
            <div class="drawer-items-list">
              ${
                isUserSourcesTab
                  ? (sources.length === 0
                      ? `<div class="drawer-empty-hint">暂无上传资料，请点击上方上传</div>`
                      : sources
                          .map(
                            (s) => `
                        <div
                          class="drawer-item ${activeSource?.id === s.id ? 'is-selected' : ''}"
                          data-type="source"
                          data-id="${s.id}"
                          role="button"
                          tabindex="0"
                        >
                          <span class="item-icon">${icons.fileText(14)}</span>
                          <div class="item-info">
                            <span class="item-name">${escapeHtml(s.name || '资料')}</span>
                            <span class="item-meta">${(s.versions || []).length} 个版本</span>
                          </div>
                          <button type="button" class="btn-icon-subtle btn-delete-source" data-id="${s.id}" title="删除资料">
                            ${icons.trash(12)}
                          </button>
                        </div>
                      `
                          )
                          .join(''))
                  : (aiDocuments.length === 0
                      ? `<div class="drawer-empty-hint">暂无 AI 文档，请点击新建</div>`
                      : aiDocuments
                          .map(
                            (d) => `
                        <div
                          class="drawer-item ${activeAiDocument?.id === d.id ? 'is-selected' : ''}"
                          data-type="aidoc"
                          data-id="${d.id}"
                          role="button"
                          tabindex="0"
                        >
                          <span class="item-icon">${icons.sparkles(14)}</span>
                          <div class="item-info">
                            <span class="item-name">${escapeHtml(d.title || 'AI 文档')}</span>
                            <span class="item-meta">${(d.versions || []).length || 1} 个版本</span>
                          </div>
                        </div>
                      `
                          )
                          .join(''))
              }
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  // Attach Event Listeners
  attachSourcesEvents(container, state, handlers);
}

function renderUserSourcesContent(state) {
  const { activeSource, activeSourceVersions = [], activeSourceAnchors = [] } = state;

  if (!activeSource) {
    return `
      <div class="workspace-empty-state">
        <div class="empty-icon">${icons.layers(28)}</div>
        <h4 class="empty-title">还没有资料</h4>
        <p class="empty-subtitle">上传教材、课件或笔记，支持 PDF、Word、PPT 与文本格式。</p>
        <div class="empty-actions-row">
          <button type="button" class="btn-primary-glow" id="btn-empty-upload-source">
            ${icons.upload(14)} 上传资料
          </button>
        </div>
      </div>
    `;
  }

  const latestVersion = activeSourceVersions[0] || (activeSource.versions || [])[0] || null;

  return `
    <div class="source-detail-container">
      <div class="source-detail-header-card">
        <div class="source-header-top">
          <div class="source-title-row">
            <span class="source-icon">${icons.fileText(18)}</span>
            <h3 class="source-name">${escapeHtml(activeSource.name || '资料')}</h3>
            <span class="status-pill status-pill-ready">只读资料</span>
          </div>
          <div class="source-meta-row">
            <span>大小: ${formatBytes(latestVersion?.byte_size || activeSource.byte_size || 0)}</span>
            <span>·</span>
            <span>格式: ${escapeHtml(latestVersion?.mime_type || activeSource.mime_type || 'text/plain')}</span>
            <span>·</span>
            <span>版本: v${activeSourceVersions.length || 1}</span>
          </div>
        </div>

        <div class="source-banner-hint">
          ${icons.info(13)}
          <span>用户上传资料为只读。如需修改，AI 会自动为您创建一份可编辑的 AI 文档副本。</span>
        </div>
      </div>

      <!-- Anchors / Locations in Source -->
      ${
        activeSourceAnchors.length > 0
          ? `
        <div class="source-anchors-section">
          <h4 class="anchors-section-title">${icons.tag(14)} 原文位置与解析锚点 (${activeSourceAnchors.length})</h4>
          <div class="anchors-grid">
            ${activeSourceAnchors
              .map(
                (anc) => `
              <div class="anchor-card-item" data-anchor-id="${anc.id}">
                <div class="anchor-header">
                  <span class="anchor-title">${escapeHtml(anc.title || anc.id)}</span>
                  <span class="anchor-loc">第 ${anc.page_number || 1} 页</span>
                </div>
                <div class="anchor-excerpt">${escapeHtml(anc.text_content || anc.content || '')}</div>
              </div>
            `
              )
              .join('')}
          </div>
        </div>
      `
          : ''
      }

      <!-- Source Text Preview -->
      <div class="source-content-preview-box">
        <h4 class="preview-box-title">${icons.book(14)} 正文预览</h4>
        <div class="source-text-body">
          ${escapeHtml(activeSource.text_content || activeSource.extracted_text || latestVersion?.text_content || '（暂无解析文本）').replace(/\n/g, '<br/>')}
        </div>
      </div>
    </div>
  `;
}

function renderAiDocumentsContent(state) {
  const { activeAiDocument, aiDocumentVersions = [], aiDocumentProposals = [], activeAiDocProposal } = state;

  if (!activeAiDocument) {
    return `
      <div class="workspace-empty-state">
        <div class="empty-icon">${icons.fileText(28)}</div>
        <h4 class="empty-title">还没有 AI 文档</h4>
        <p class="empty-subtitle">让 AI 根据资料梳理重点、生成笔记，或直接创建新文档。</p>
        <div class="empty-actions-row">
          <button type="button" class="btn-primary-glow" id="btn-empty-create-aidoc">
            ${icons.plus(14)} 创建文档
          </button>
        </div>
      </div>
    `;
  }

  const latestProposal = activeAiDocProposal || aiDocumentProposals[0] || null;

  return `
    <div class="aidoc-detail-container">
      <!-- AI Doc Header Info -->
      <div class="aidoc-header-card">
        <div class="aidoc-title-row">
          <span class="aidoc-icon">${icons.sparkles(18)}</span>
          <h3 class="aidoc-title">${escapeHtml(activeAiDocument.title || 'AI 文档')}</h3>
          <span class="status-pill status-pill-ai">AI 生成</span>
        </div>
        <div class="aidoc-meta-row">
          <span>版本: v${(activeAiDocument.versions || []).length || aiDocumentVersions.length || 1}</span>
          <span>·</span>
          <span>修改提案: ${aiDocumentProposals.length} 个</span>
        </div>
      </div>

      <!-- Revision Proposal / Diff Preview (if any active proposal) -->
      ${
        latestProposal
          ? `
        <div class="aidoc-proposal-diff-card">
          <div class="proposal-diff-header">
            <div class="diff-header-left">
              <span class="diff-icon">${icons.gitCompare(15)}</span>
              <span class="diff-title">修改预览: ${escapeHtml(latestProposal.summary || 'AI 润色提案')}</span>
            </div>
            <div class="diff-header-actions">
              <button
                type="button"
                class="btn-primary-sm btn-apply-proposal"
                data-proposal-id="${latestProposal.id}"
                title="确认并应用修改"
              >
                ${icons.check(13)} 应用修改
              </button>
              <button
                type="button"
                class="btn-outline-sm btn-discard-proposal"
                data-proposal-id="${latestProposal.id}"
                title="放弃此提案"
              >
                ${icons.x(13)} 放弃
              </button>
            </div>
          </div>

          <div class="proposal-diff-view">
            <div class="diff-column diff-before">
              <div class="diff-column-header">修改前</div>
              <div class="diff-text">${escapeHtml(latestProposal.before_content || activeAiDocument.content || '').replace(/\n/g, '<br/>')}</div>
            </div>
            <div class="diff-column diff-after">
              <div class="diff-column-header">修改后</div>
              <div class="diff-text">${escapeHtml(latestProposal.after_content || latestProposal.proposed_content || '').replace(/\n/g, '<br/>')}</div>
            </div>
          </div>
        </div>
      `
          : ''
      }

      <!-- AI Document Current Body -->
      <article class="aidoc-article-body markdown-rendered-body">
        ${escapeHtml(activeAiDocument.content || '（暂无正文）').replace(/\n/g, '<br/>')}
      </article>

      <!-- Version History Section -->
      ${
        aiDocumentVersions.length > 1
          ? `
        <div class="aidoc-versions-section">
          <h4 class="versions-section-title">${icons.clock(14)} 版本历史</h4>
          <div class="versions-list">
            ${aiDocumentVersions
              .map(
                (v, vIdx) => `
              <div class="version-item-card">
                <div class="version-card-left">
                  <span class="version-name">版本 ${v.version_number || aiDocumentVersions.length - vIdx}</span>
                  <span class="version-time">${v.created_at ? new Date(v.created_at).toLocaleString() : ''}</span>
                </div>
                <button
                  type="button"
                  class="btn-outline-sm btn-restore-aidoc-version"
                  data-version-id="${v.id}"
                  title="恢复此版本"
                >
                  ${icons.undo(12)} 恢复此版
                </button>
              </div>
            `
              )
              .join('')}
          </div>
        </div>
      `
          : ''
      }
    </div>
  `;
}

function attachSourcesEvents(container, state, handlers) {
  // Sub-tabs switch
  const tabUserSources = container.querySelector('#btn-tab-user-sources');
  const tabAiDocs = container.querySelector('#btn-tab-ai-docs');

  if (tabUserSources) tabUserSources.onclick = () => handlers.onSwitchSourcesTab?.('user_sources');
  if (tabAiDocs) tabAiDocs.onclick = () => handlers.onSwitchSourcesTab?.('ai_documents');

  // Drawer open / close
  const drawerBackdrop = container.querySelector('#sources-drawer-backdrop');
  const toggleSourcesDrawerBtn = container.querySelector('#btn-toggle-sources-drawer');
  const toggleAiDocsDrawerBtn = container.querySelector('#btn-toggle-aidocs-drawer');
  const closeDrawerBtn = container.querySelector('#btn-close-sources-drawer');

  const openDrawer = () => {
    if (drawerBackdrop) drawerBackdrop.style.display = 'block';
  };
  const closeDrawer = () => {
    if (drawerBackdrop) drawerBackdrop.style.display = 'none';
  };

  if (toggleSourcesDrawerBtn) toggleSourcesDrawerBtn.onclick = openDrawer;
  if (toggleAiDocsDrawerBtn) toggleAiDocsDrawerBtn.onclick = openDrawer;
  if (closeDrawerBtn) closeDrawerBtn.onclick = closeDrawer;
  if (drawerBackdrop) {
    drawerBackdrop.onclick = (e) => {
      if (e.target === drawerBackdrop) closeDrawer();
    };
  }

  // Upload Source Trigger
  const triggerUploadBtn = container.querySelector('#btn-trigger-upload-source');
  const emptyUploadBtn = container.querySelector('#btn-empty-upload-source');
  const fileInput = container.querySelector('#source-file-input');

  const triggerUpload = () => {
    if (fileInput) fileInput.click();
  };

  if (triggerUploadBtn) triggerUploadBtn.onclick = triggerUpload;
  if (emptyUploadBtn) emptyUploadBtn.onclick = triggerUpload;
  if (fileInput) {
    fileInput.onchange = (e) => {
      const file = e.target.files?.[0];
      if (file) {
        handlers.onUploadSource?.(file);
        fileInput.value = '';
      }
    };
  }

  // Create AI Doc Trigger
  const createAiDocBtn = container.querySelector('#btn-trigger-create-aidoc');
  const emptyCreateAiDocBtn = container.querySelector('#btn-empty-create-aidoc');

  const triggerCreateDoc = () => {
    handlers.onOpenCreateAiDocModal?.();
  };

  if (createAiDocBtn) createAiDocBtn.onclick = triggerCreateDoc;
  if (emptyCreateAiDocBtn) emptyCreateAiDocBtn.onclick = triggerCreateDoc;

  // Propose Revision
  const proposeRevBtn = container.querySelector('#btn-trigger-propose-revision');
  if (proposeRevBtn) {
    proposeRevBtn.onclick = () => {
      const docId = state.activeAiDocument?.id;
      if (docId) handlers.onOpenAiDocRevisionModal?.(docId);
    };
  }

  // Select Item from Drawer
  container.querySelectorAll('.drawer-item').forEach((el) => {
    el.onclick = (e) => {
      if (e.target.closest('.btn-delete-source')) return;
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

  // Delete Source
  container.querySelectorAll('.btn-delete-source').forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const id = btn.getAttribute('data-id');
      if (id) handlers.onDeleteSource?.(id);
    };
  });

  // Apply / Discard Proposal
  container.querySelectorAll('.btn-apply-proposal').forEach((btn) => {
    btn.onclick = () => {
      const pid = btn.getAttribute('data-proposal-id');
      handlers.onApplyAiDocProposal?.(pid);
    };
  });

  container.querySelectorAll('.btn-discard-proposal').forEach((btn) => {
    btn.onclick = () => {
      const pid = btn.getAttribute('data-proposal-id');
      handlers.onDiscardAiDocProposal?.(pid);
    };
  });

  // Restore AI Doc Version
  container.querySelectorAll('.btn-restore-aidoc-version').forEach((btn) => {
    btn.onclick = () => {
      const vid = btn.getAttribute('data-version-id');
      const docId = state.activeAiDocument?.id;
      if (docId && vid) handlers.onRestoreAiDocVersion?.(docId, vid);
    };
  });
}

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
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
