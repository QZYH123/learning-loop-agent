/**
 * Sources & AI Documents Workspace Component
 * Strictly aligned with Tickets 03, 04, 05, 18, 20:
 * - Collapsible sidebar with dual tabs: "用户上传资料" & "AI 资料文档"
 * - Multi-format support: PDF, DOCX, PPTX, Markdown, TXT, Images
 * - Source version history, anchor list / section inspection, pin to chat selection
 * - AI Document creation, version restore, and AI revision proposals diff review (Apply/Discard)
 */

import { icons } from '../icons.js';

export function renderSourcesView(state, container, handlers) {
  const {
    sources = [],
    activeSourceId,
    activeSourceVersions = [],
    activeSourceAnchors = [],
    aiDocuments = [],
    activeAiDocumentId,
    activeAiDocument,
    aiDocumentVersions = [],
    aiDocumentProposals = [],
    activeAiDocProposalId,
    sourcesTab = 'user_sources',
    sidebarCollapsed = {}
  } = state;

  const isCollapsed = !!sidebarCollapsed.sources;
  const isUserSourcesTab = sourcesTab === 'user_sources';

  const activeSource = sources.find((s) => s.id === activeSourceId) || sources[0] || null;
  const activeAiDoc = aiDocuments.find((d) => d.id === activeAiDocumentId) || aiDocuments[0] || null;
  const activeAiProposal = aiDocumentProposals.find((p) => p.id === activeAiDocProposalId) || aiDocumentProposals[0] || null;

  container.innerHTML = `
    <div class="learning-workspace-layout ${isCollapsed ? 'is-sidebar-collapsed' : ''}" data-testid="sources-workspace">
      <!-- Left Sidebar: Sources & AI Documents List -->
      <aside class="workspace-sidebar" id="sources-sidebar">
        <!-- Sidebar Header with Tabs & Collapse Button -->
        <div class="sidebar-header-row">
          <div class="sidebar-tabs-group">
            <button
              type="button"
              class="sidebar-tab-btn ${isUserSourcesTab ? 'is-active' : ''}"
              data-sources-tab="user_sources"
              title="用户上传讲义与文件"
            >
              ${icons.fileText(14)}
              <span>资料库 (${sources.length})</span>
            </button>
            <button
              type="button"
              class="sidebar-tab-btn ${!isUserSourcesTab ? 'is-active' : ''}"
              data-sources-tab="ai_documents"
              title="AI 生成的系统资料文档"
            >
              ${icons.sparkles(14)}
              <span>AI 文档 (${aiDocuments.length})</span>
            </button>
          </div>

          <div class="sidebar-actions-block">
            <button
              type="button"
              class="btn-icon-sidebar"
              id="btn-toggle-sources-sidebar"
              title="${isCollapsed ? '展开侧栏' : '收起侧栏'}"
            >
              ${isCollapsed ? icons.panelLeftOpen(15) : icons.panelLeftClose(15)}
            </button>
          </div>
        </div>

        <!-- Action Bar: Upload File or Create AI Doc -->
        <div class="sidebar-top-action-bar">
          ${
            isUserSourcesTab
              ? `
            <button type="button" class="btn-primary btn-sm btn-block" id="btn-trigger-upload-source">
              ${icons.upload(14)}
              <span>上传学习资料...</span>
            </button>
            <input
              type="file"
              id="source-file-upload-input"
              multiple
              style="display: none;"
              accept=".pdf,.docx,.pptx,.md,.markdown,.txt,.png,.jpg,.jpeg,.webp"
            />
          `
              : `
            <button type="button" class="btn-primary btn-sm btn-block" id="btn-open-create-ai-doc">
              ${icons.plus(14)}
              <span>创建 AI 资料文档...</span>
            </button>
          `
          }
        </div>

        <!-- Scrollable Card List -->
        <div class="sidebar-scrollable-list" id="sources-items-scroll">
          ${
            isUserSourcesTab
              ? renderUserSourcesList(sources, activeSourceId)
              : renderAiDocumentsList(aiDocuments, activeAiDocumentId)
          }
        </div>
      </aside>

      <!-- Main Detail & Anchor Inspector Content Area -->
      <main class="workspace-main-content" id="sources-detail-main">
        ${
          isCollapsed
            ? `
          <button
            type="button"
            class="btn-sidebar-floating-expand"
            id="btn-floating-expand-sources"
            title="展开资料侧栏"
          >
            ${icons.panelLeftOpen(15)}
            <span>${isUserSourcesTab ? `资料库 (${sources.length})` : `AI 文档 (${aiDocuments.length})`}</span>
          </button>
        `
            : ''
        }

        ${
          isUserSourcesTab
            ? renderUserSourceDetail(activeSource, activeSourceVersions, activeSourceAnchors, state)
            : renderAiDocumentDetail(activeAiDoc, aiDocumentVersions, aiDocumentProposals, activeAiProposal, state)
        }
      </main>
    </div>
  `;

  // Attach Event Handlers
  attachSourcesEvents(container, state, handlers);
}

function renderUserSourcesList(sources, activeSourceId) {
  if (!sources || sources.length === 0) {
    return `
      <div class="sidebar-empty-state">
        <div class="sidebar-empty-icon">${icons.folder(22)}</div>
        <div class="sidebar-empty-text">资料库暂无文件</div>
        <div class="sidebar-empty-subtext">支持 PDF, DOCX, PPTX, Markdown, TXT 及图片资料</div>
      </div>
    `;
  }

  return sources
    .map((src) => {
      const isSelected = src.id === activeSourceId;
      const formatExt = (src.filename || src.name || '').split('.').pop().toUpperCase() || 'DOC';
      const versionCount = src.version_count || src.versions_count || 1;
      const isReady = src.status === 'ready';

      return `
      <div
        class="standard-card-item ${isSelected ? 'is-selected' : ''}"
        data-action="select-source"
        data-source-id="${src.id}"
        role="button"
        tabindex="0"
      >
        <div class="source-card-header">
          <div class="source-title-row">
            ${getSourceFormatIcon(formatExt)}
            <span class="source-card-title" title="${escapeHtml(src.display_name || src.name || src.filename)}">
              ${escapeHtml(src.display_name || src.name || src.filename)}
            </span>
          </div>
          <span class="grounding-tag-chip ${isReady ? 'grounding-covered' : 'grounding-not-covered'}">
            ${isReady ? '已就绪' : src.status === 'parsing' ? '解析中' : '待处理'}
          </span>
        </div>
        <div class="source-card-meta">
          <span>${formatBytes(src.size_bytes || 0)}</span>
          <span>${versionCount} 个版本</span>
          <span>${formatTimestamp(src.updated_at || src.created_at)}</span>
        </div>
      </div>
    `;
    })
    .join('');
}

function renderAiDocumentsList(aiDocuments, activeAiDocumentId) {
  if (!aiDocuments || aiDocuments.length === 0) {
    return `
      <div class="sidebar-empty-state">
        <div class="sidebar-empty-icon">${icons.sparkles(22)}</div>
        <div class="sidebar-empty-text">暂无 AI 生成资料文档</div>
        <div class="sidebar-empty-subtext">可通过上方按钮明确指令 AI 生成专属结构化资料</div>
      </div>
    `;
  }

  return aiDocuments
    .map((doc) => {
      const isSelected = doc.id === activeAiDocumentId;
      const versionCount = doc.version_count || (doc.versions ? doc.versions.length : 1);

      return `
      <div
        class="standard-card-item ${isSelected ? 'is-selected' : ''}"
        data-action="select-ai-doc"
        data-doc-id="${doc.id}"
        role="button"
        tabindex="0"
      >
        <div class="source-card-header">
          <div class="source-title-row">
            ${icons.sparkles(14, 'color-accent-blue')}
            <span class="source-card-title" title="${escapeHtml(doc.title || 'AI 资料文档')}">
              ${escapeHtml(doc.title || 'AI 资料文档')}
            </span>
          </div>
          <span class="tag-chip-ai-authored">AI 生成</span>
        </div>
        <div class="source-card-meta">
          <span>${versionCount} 个版本</span>
          <span>${formatTimestamp(doc.updated_at || doc.created_at)}</span>
        </div>
      </div>
    `;
    })
    .join('');
}

function renderUserSourceDetail(source, versions = [], anchors = [], state) {
  if (!source) {
    return `
      <div class="detail-empty-container">
        <div class="empty-state-icon-circle">${icons.folder(24)}</div>
        <div class="empty-state-title">未选择任何资料</div>
        <div class="empty-state-desc">在左侧列表中选择资料查看解析锚点、历史版本，或点击上传新资料。</div>
      </div>
    `;
  }

  const formatExt = (source.filename || source.name || '').split('.').pop().toUpperCase() || 'DOC';
  const latestVersion = versions[0] || null;

  return `
    <div class="source-detail-container" data-testid="source-detail-view">
      <!-- Detail Header Bar -->
      <header class="detail-header-bar">
        <div class="detail-header-info">
          <div style="display: flex; align-items: center; gap: 8px;">
            ${getSourceFormatIcon(formatExt, 20)}
            <h2 class="detail-title-text" title="${escapeHtml(source.display_name || source.name)}">
              ${escapeHtml(source.display_name || source.name)}
            </h2>
            <span class="grounding-tag-chip ${source.status === 'ready' ? 'grounding-covered' : ''}">
              ${source.status === 'ready' ? '解析就绪' : source.status === 'parsing' ? '正在解析' : '待处理'}
            </span>
          </div>
          <div class="detail-meta-row">
            <span>格式: ${formatExt}</span>
            <span>大小: ${formatBytes(source.size_bytes || 0)}</span>
            <span>当前版本 ID: <code>${escapeHtml(latestVersion?.id?.slice(0, 8) || source.id?.slice(0, 8))}</code></span>
          </div>
        </div>

        <div class="detail-header-actions">
          <button
            type="button"
            class="btn-secondary btn-sm"
            id="btn-iterate-version"
            title="上传更新内容并建立新资料版本"
          >
            ${icons.upload(13)} 迭代新版本...
          </button>
          <input
            type="file"
            id="source-iterate-file-input"
            style="display: none;"
            accept=".pdf,.docx,.pptx,.md,.markdown,.txt,.png,.jpg,.jpeg,.webp"
          />

          <button
            type="button"
            class="btn-secondary btn-sm"
            id="btn-add-to-active-session"
            title="将此资料固定至当前学习会话"
          >
            ${icons.plus(13)} 加入当前会话
          </button>

          <button
            type="button"
            class="btn-icon-subtle btn-delete-subtle"
            id="btn-delete-source"
            title="从资料库删除此资料 (会提示引用的会话与试卷)"
          >
            ${icons.trash2(14)}
          </button>
        </div>
      </header>

      <!-- Main Body: Two Column (Left Anchors & Sections / Right Versions) -->
      <div class="source-detail-body-grid">
        <!-- Anchors & Content Section -->
        <section class="source-anchors-section">
          <div class="section-subheading-row">
            <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 13px;">
              ${icons.bookmark(14)}
              <span>解析来源锚点 (${anchors.length})</span>
            </div>
            <span style="font-size: 11px; color: var(--ink-muted);">点击锚点可将其段落固定到导师提问</span>
          </div>

          <div class="anchors-list-scroll">
            ${
              anchors.length === 0
                ? `
              <div class="empty-anchors-note">
                ${source.status === 'parsing' ? '资料正在后台解析中，请稍候...' : '暂无结构化锚点数据。'}
              </div>
            `
                : anchors
                    .map(
                      (anchor) => `
              <div class="anchor-item-card" data-action="pin-anchor" data-anchor-id="${anchor.id}" data-anchor-text="${escapeHtml(anchor.text || anchor.quote || '')}">
                <div class="anchor-card-top">
                  <span class="anchor-badge">${escapeHtml(anchor.section_title || anchor.anchor_id || '段落')}</span>
                  ${anchor.page ? `<span class="anchor-page-badge">第 ${anchor.page} 页</span>` : ''}
                  <button type="button" class="btn-pin-anchor" title="固定选区到对话">${icons.tag(11)} 固定提问</button>
                </div>
                <div class="anchor-quote-text">
                  ${escapeHtml(anchor.text || anchor.quote || '')}
                </div>
              </div>
            `
                    )
                    .join('')
            }
          </div>
        </section>

        <!-- Version History List -->
        <aside class="source-versions-aside">
          <div class="section-subheading-row">
            <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; font-size: 13px;">
              ${icons.gitCompare(14)}
              <span>版本历史 (${versions.length})</span>
            </div>
          </div>

          <div class="versions-list-scroll">
            ${
              versions.length === 0
                ? `<div class="empty-anchors-note">暂无历史版本记录</div>`
                : versions
                    .map(
                      (ver, idx) => `
              <div class="version-item-card ${idx === 0 ? 'is-latest' : ''}">
                <div class="version-card-header">
                  <span class="version-id-tag">v${versions.length - idx} · ${escapeHtml(ver.id?.slice(0, 8))}</span>
                  ${idx === 0 ? `<span class="version-latest-badge">最新</span>` : ''}
                </div>
                <div class="version-card-meta">
                  <span>${formatBytes(ver.size_bytes || 0)}</span>
                  <span>${formatTimestamp(ver.created_at)}</span>
                </div>
              </div>
            `
                    )
                    .join('')
            }
          </div>
        </aside>
      </div>
    </div>
  `;
}

function renderAiDocumentDetail(doc, versions = [], proposals = [], activeProposal, state) {
  if (!doc) {
    return `
      <div class="detail-empty-container">
        <div class="empty-state-icon-circle">${icons.sparkles(24)}</div>
        <div class="empty-state-title">未选择 AI 资料文档</div>
        <div class="empty-state-desc">在左侧列表中选择文档，或点击“创建 AI 资料文档”由 AI 生成专属讲义。</div>
      </div>
    `;
  }

  const latestVersion = versions[0] || null;

  return `
    <div class="source-detail-container" data-testid="ai-document-detail-view">
      <!-- Header -->
      <header class="detail-header-bar">
        <div class="detail-header-info">
          <div style="display: flex; align-items: center; gap: 8px;">
            ${icons.sparkles(18, 'color-accent-blue')}
            <h2 class="detail-title-text" title="${escapeHtml(doc.title || 'AI 资料文档')}">
              ${escapeHtml(doc.title || 'AI 资料文档')}
            </h2>
            <span class="tag-chip-ai-authored">AI 生成</span>
          </div>
          <div class="detail-meta-row">
            <span>当前版本 ID: <code>${escapeHtml(latestVersion?.id?.slice(0, 8) || doc.id?.slice(0, 8))}</code></span>
            <span>更新时间: ${formatTimestamp(doc.updated_at || doc.created_at)}</span>
          </div>
        </div>

        <div class="detail-header-actions">
          <button
            type="button"
            class="btn-primary btn-sm"
            id="btn-open-ai-doc-revision"
            title="向 AI 提出修改要求，生成并预览结构化差异提案"
          >
            ${icons.edit3(13)} AI 修改提案...
          </button>

          <button
            type="button"
            class="btn-secondary btn-sm"
            id="btn-add-ai-doc-to-session"
            title="将此 AI 文档加入当前学习会话并参与检索"
          >
            ${icons.plus(13)} 加入会话
          </button>
        </div>
      </header>

      <!-- Active Revision Proposal Diff Banner (Ticket 20) -->
      ${
        activeProposal && activeProposal.status === 'pending'
          ? `
        <div class="revision-proposal-diff-banner">
          <div class="diff-banner-header">
            <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; color: #1e40af;">
              ${icons.edit3(14)}
              <span>AI 修改建议提案 (待确认)</span>
            </div>
            <div style="display: flex; gap: 8px;">
              <button type="button" class="btn-primary btn-sm" id="btn-apply-ai-doc-proposal" data-proposal-id="${activeProposal.id}">
                ${icons.check(13)} 应用修改并创建新版本
              </button>
              <button type="button" class="btn-secondary btn-sm" id="btn-discard-ai-doc-proposal" data-proposal-id="${activeProposal.id}">
                ${icons.x(13)} 放弃提案
              </button>
            </div>
          </div>
          <div class="diff-instruction-quote">
            <strong>修改指令:</strong> "${escapeHtml(activeProposal.instruction || '优化与补充内容')}"
          </div>
          <div class="diff-comparison-grid">
            <div class="diff-pane diff-pane-original">
              <div class="diff-pane-label">原版本内容</div>
              <div class="diff-text-body">${escapeHtml(activeProposal.original_content || doc.content || '')}</div>
            </div>
            <div class="diff-pane diff-pane-proposed">
              <div class="diff-pane-label">建议修改内容</div>
              <div class="diff-text-body">${escapeHtml(activeProposal.proposed_content || '')}</div>
            </div>
          </div>
        </div>
      `
          : ''
      }

      <!-- Main Document Content -->
      <div class="source-detail-body-grid">
        <section class="source-anchors-section">
          <div class="section-subheading-row">
            <div style="font-weight: 700; font-size: 13px;">文档完整正文</div>
          </div>
          <div class="ai-doc-content-viewer">
            <div class="markdown-rendered-body">
              ${escapeHtml(doc.content || latestVersion?.content || '（正文内容加载中）')}
            </div>
          </div>
        </section>

        <!-- Version History with Restore Action (Ticket 20) -->
        <aside class="source-versions-aside">
          <div class="section-subheading-row">
            <div style="font-weight: 700; font-size: 13px;">版本记录与恢复</div>
          </div>
          <div class="versions-list-scroll">
            ${
              versions.length === 0
                ? `<div class="empty-anchors-note">暂无版本历史</div>`
                : versions
                    .map(
                      (ver, idx) => `
              <div class="version-item-card ${idx === 0 ? 'is-latest' : ''}">
                <div class="version-card-header">
                  <span class="version-id-tag">v${versions.length - idx}</span>
                  ${
                    idx > 0
                      ? `
                    <button
                      type="button"
                      class="btn-subtle-restore"
                      data-action="restore-ai-doc-version"
                      data-version-id="${ver.id}"
                      title="恢复此版本为当前最新版本"
                    >
                      ${icons.undo(12)} 恢复此版本
                    </button>
                  `
                      : `<span class="version-latest-badge">当前</span>`
                  }
                </div>
                <div class="version-card-meta">
                  <span>${formatTimestamp(ver.created_at)}</span>
                </div>
              </div>
            `
                    )
                    .join('')
            }
          </div>
        </aside>
      </div>
    </div>
  `;
}

function attachSourcesEvents(container, state, handlers) {
  const { activeSourceId, activeAiDocumentId, activeSessionId } = state;

  // Sidebar Collapse Toggle
  const toggleBtn = container.querySelector('#btn-toggle-sources-sidebar');
  if (toggleBtn) {
    toggleBtn.onclick = () => handlers.onToggleSidebar?.('sources');
  }

  const floatingBtn = container.querySelector('#btn-floating-expand-sources');
  if (floatingBtn) {
    floatingBtn.onclick = () => handlers.onToggleSidebar?.('sources');
  }

  // Tabs Switch (User Sources vs AI Docs)
  container.querySelectorAll('[data-sources-tab]').forEach((btn) => {
    btn.onclick = () => {
      const tab = btn.getAttribute('data-sources-tab');
      handlers.onSwitchSourcesTab?.(tab);
    };
  });

  // Upload Source Files
  const fileInput = container.querySelector('#source-file-upload-input');
  const uploadBtn = container.querySelector('#btn-trigger-upload-source');

  if (uploadBtn && fileInput) {
    uploadBtn.onclick = () => fileInput.click();
    fileInput.onchange = () => {
      if (fileInput.files && fileInput.files.length > 0) {
        handlers.onUploadFiles?.(Array.from(fileInput.files));
        fileInput.value = '';
      }
    };
  }

  // Iterate Source Version
  const iterateInput = container.querySelector('#source-iterate-file-input');
  const iterateBtn = container.querySelector('#btn-iterate-version');

  if (iterateBtn && iterateInput) {
    iterateBtn.onclick = () => iterateInput.click();
    iterateInput.onchange = () => {
      if (iterateInput.files && iterateInput.files[0] && activeSourceId) {
        handlers.onIterateSourceVersion?.(activeSourceId, iterateInput.files[0]);
        iterateInput.value = '';
      }
    };
  }

  // Create AI Doc Modal Trigger
  const createAiDocBtn = container.querySelector('#btn-open-create-ai-doc');
  if (createAiDocBtn) {
    createAiDocBtn.onclick = () => handlers.onOpenCreateAiDocModal?.();
  }

  // AI Doc Revision Modal Trigger
  const aiDocRevisionBtn = container.querySelector('#btn-open-ai-doc-revision');
  if (aiDocRevisionBtn) {
    aiDocRevisionBtn.onclick = () => handlers.onOpenAiDocRevisionModal?.(activeAiDocumentId);
  }

  // Apply / Discard AI Doc Proposals
  const applyAiProposalBtn = container.querySelector('#btn-apply-ai-doc-proposal');
  if (applyAiProposalBtn) {
    applyAiProposalBtn.onclick = () => {
      const pId = applyAiProposalBtn.getAttribute('data-proposal-id');
      handlers.onApplyAiDocProposal?.(pId);
    };
  }

  const discardAiProposalBtn = container.querySelector('#btn-discard-ai-doc-proposal');
  if (discardAiProposalBtn) {
    discardAiProposalBtn.onclick = () => {
      const pId = discardAiProposalBtn.getAttribute('data-proposal-id');
      handlers.onDiscardAiDocProposal?.(pId);
    };
  }

  // Restore AI Doc Version
  container.querySelectorAll('[data-action="restore-ai-doc-version"]').forEach((btn) => {
    btn.onclick = () => {
      const vId = btn.getAttribute('data-version-id');
      if (confirm('确定要恢复此历史版本吗？')) {
        handlers.onRestoreAiDocVersion?.(activeAiDocumentId, vId);
      }
    };
  });

  // Select Source Item
  container.querySelectorAll('[data-action="select-source"]').forEach((card) => {
    card.onclick = () => {
      const id = card.getAttribute('data-source-id');
      handlers.onSelectSource?.(id);
    };
  });

  // Select AI Doc Item
  container.querySelectorAll('[data-action="select-ai-doc"]').forEach((card) => {
    card.onclick = () => {
      const id = card.getAttribute('data-doc-id');
      handlers.onSelectAiDoc?.(id);
    };
  });

  // Add Source / AI Doc to Current Session
  const addToSessionBtn = container.querySelector('#btn-add-to-active-session');
  if (addToSessionBtn && activeSourceId && activeSessionId) {
    addToSessionBtn.onclick = () => {
      const source = state.sources.find((s) => s.id === activeSourceId);
      const vId = source?.versions?.[0]?.id || activeSourceId;
      handlers.onAddSessionSource?.(activeSessionId, vId);
    };
  }

  const addAiDocToSessionBtn = container.querySelector('#btn-add-ai-doc-to-session');
  if (addAiDocToSessionBtn && activeAiDocumentId && activeSessionId) {
    addAiDocToSessionBtn.onclick = () => {
      handlers.onAddSessionSource?.(activeSessionId, activeAiDocumentId);
    };
  }

  // Delete Source
  const deleteSourceBtn = container.querySelector('#btn-delete-source');
  if (deleteSourceBtn && activeSourceId) {
    deleteSourceBtn.onclick = () => handlers.onDeleteSource?.(activeSourceId);
  }

  // Pin Anchor Selection to Chat
  container.querySelectorAll('[data-action="pin-anchor"]').forEach((card) => {
    card.onclick = () => {
      const anchorId = card.getAttribute('data-anchor-id');
      const text = card.getAttribute('data-anchor-text');
      handlers.onPinSelection?.({
        source_id: activeSourceId,
        anchor_id: anchorId,
        text
      });
    };
  });
}

function getSourceFormatIcon(ext, size = 15) {
  const e = ext.toUpperCase();
  if (e === 'PDF') return icons.fileText(size, 'color-accent-amber');
  if (e === 'DOCX' || e === 'DOC') return icons.fileText(size, 'color-accent-blue');
  if (e === 'PPTX' || e === 'PPT') return icons.layers(size, 'color-accent-amber');
  if (['PNG', 'JPG', 'JPEG', 'WEBP'].includes(e)) return icons.image(size, 'color-accent-emerald');
  return icons.file(size);
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
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
