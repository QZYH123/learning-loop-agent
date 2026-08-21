import { icons } from '../icons.js';
import {
  currentAiVersion,
  escapeHtml,
  formatTime,
  pendingProposal,
  renderBlocks,
  sourceAnchorLabel,
  statusLabel,
} from '../util.js';
import { bindChatPane, renderChatPane } from './chat.js';

export function sourcesShellHtml(state) {
  const collapsed = !!state.sidebarCollapsed.sources;
  return `
    <div class="ws ws-task ${collapsed ? 'is-collapsed' : ''}" data-mobile="${state.mobilePane.sources}" data-testid="sources-workspace">
      <div class="mobile-switch">
        <button type="button" class="seg ${state.mobilePane.sources === 'ai' ? 'is-active' : ''}" data-action="mobile-pane" data-pane="ai">AI</button>
        <button type="button" class="seg ${state.mobilePane.sources === 'content' ? 'is-active' : ''}" data-action="mobile-pane" data-pane="content">内容</button>
      </div>
      <aside class="pane pane-ai"></aside>
      <main class="pane pane-content"></main>
    </div>
  `;
}

export function sourcesLeftHtml(state, handlers) {
  const collapsed = !!state.sidebarCollapsed.sources;
  return collapsed
    ? ''
    : renderChatPane(state, handlers, {
        variant: 'task',
        placeholder: '要整理或修改哪份资料？输入 / 用命令',
        emptyTitle: '开始新对话',
      });
}

export function sourcesRightHtml(state) {
  const collapsed = !!state.sidebarCollapsed.sources;
  const kind = state.sourceKind || 'files';
  const source = state.sources.find((item) => item.id === state.activeSourceId) || null;
  const doc = state.aiDocuments.find((item) => item.id === state.activeAiDocumentId) || null;
  const proposal = pendingProposal(state.aiDocumentProposals);
  return `
        <div class="task">
          ${renderHeader(kind, source, doc, proposal, collapsed)}
          <div class="local-nav">
            <button type="button" class="seg ${kind === 'files' ? 'is-active' : ''}" data-action="source-kind" data-kind="files">资料</button>
            <button type="button" class="seg ${kind === 'docs' ? 'is-active' : ''}" data-action="source-kind" data-kind="docs">AI 文档</button>
          </div>
          <div class="task-body" id="task-scroll" data-select-root="source">
            ${kind === 'files' ? renderFiles(state, source) : renderDocs(state, doc, proposal)}
          </div>
        </div>
        <input type="file" id="source-file-input" hidden multiple accept=".pdf,.docx,.pptx,.md,.markdown,.txt,.png,.jpg,.jpeg,.webp" />
  `;
}

export function bindSourcesLeft(root, handlers) {
  bindChatPane(root, handlers);
}

export function bindSourcesRight(root, handlers) {
  root.querySelector('#source-file-input')?.addEventListener('change', (event) => {
    handlers.onUploadSources([...event.target.files]);
    event.target.value = '';
  });
}

function expandBtn(collapsed) {
  return collapsed
    ? `<button type="button" class="icon-btn" data-action="collapse-left" title="展开">${icons.panelLeftOpen(15)}</button>`
    : '';
}

function renderHeader(kind, source, doc, proposal, collapsed) {
  if (kind === 'docs') {
    if (!doc) {
      return `
        <div class="pane-head">
          <div class="head-meta">${expandBtn(collapsed)}<div class="pane-title"><span>AI 文档</span></div></div>
          <div class="pane-actions">
            <button type="button" class="btn btn-primary btn-sm" data-action="create-ai-doc">生成文档</button>
          </div>
        </div>`;
    }
    return `
      <div class="pane-head">
        <div class="head-meta">
          ${expandBtn(collapsed)}
          <div class="pane-title"><span>${escapeHtml(doc.title)}</span></div>
          ${proposal ? `<span class="status status-warn">${statusLabel('proposal', proposal.status)}</span>` : ''}
        </div>
        <div class="pane-actions">
          ${
            proposal?.status === 'ready'
              ? `<button type="button" class="btn btn-primary btn-sm" data-action="apply-doc-proposal" data-id="${proposal.id}">应用修改</button>
                 <button type="button" class="icon-btn" data-action="discard-doc-proposal" data-id="${proposal.id}" title="放弃">${icons.x(15)}</button>`
              : `<button type="button" class="btn btn-primary btn-sm" data-action="create-ai-doc">生成文档</button>`
          }
        </div>
      </div>`;
  }
  if (!source) {
    return `
      <div class="pane-head">
        <div class="head-meta">${expandBtn(collapsed)}<div class="pane-title"><span>资料</span></div></div>
        <div class="pane-actions">
          <button type="button" class="btn btn-primary btn-sm" data-action="upload-source">${icons.upload(14)} 上传资料</button>
        </div>
      </div>`;
  }
  return `
    <div class="pane-head">
      <div class="head-meta">
        ${expandBtn(collapsed)}
        <div class="pane-title"><span>${escapeHtml(source.display_name)}</span></div>
        <span class="status ${source.status === 'ready' ? 'status-ok' : source.status === 'failed' ? 'status-bad' : 'status-warn'}">${statusLabel('source', source.status)}</span>
      </div>
      <div class="pane-actions">
        <button type="button" class="btn btn-primary btn-sm" data-action="upload-source">${icons.upload(14)} 上传资料</button>
        <button type="button" class="icon-btn" data-action="delete-source" data-id="${source.id}" title="删除">${icons.trash2(15)}</button>
      </div>
    </div>`;
}

function renderFiles(state, source) {
  const sources = state.sources || [];
  if (!sources.length) {
    return `<div class="empty"><h3>还没有资料</h3><button type="button" class="btn btn-primary" data-action="upload-source">${icons.upload(14)} 上传资料</button></div>`;
  }
  return `
    <div class="resource-row">
      ${sources
        .map(
          (item) => `
        <button type="button" class="mini ${item.id === state.activeSourceId ? 'is-active' : ''}" data-action="select-source" data-id="${item.id}" title="${escapeHtml(item.display_name)}">
          <div class="item-title">${escapeHtml(item.display_name)}</div>
          <div class="item-sub"><span>${statusLabel('source', item.status)}</span>${item.version_count > 1 ? `<span>v${item.current_version?.number || item.version_count}</span>` : ''}<span>${formatTime(item.updated_at)}</span></div>
        </button>
      `,
        )
        .join('')}
    </div>
    ${
      !source
        ? `<div class="empty"><h3>选择一份资料</h3></div>`
        : source.status === 'processing'
          ? `<div class="boot"><div>${icons.rotateCw(18, 'spin')}</div><h3>处理中</h3></div>`
          : source.status === 'failed'
            ? `<div class="fail"><h3>处理失败</h3><p>${escapeHtml(source.failure?.message || '')}</p><button type="button" class="btn btn-ghost" data-action="upload-source">重新上传</button></div>`
            : (state.sourceAnchors || []).length
              ? `${
                  (state.sourceVersions || []).length > 1
                    ? `<p class="item-sub" style="margin-bottom:10px">共 ${(state.sourceVersions || []).length} 个版本，当前 v${
                        (state.sourceVersions || []).find((item) => item.id === state.sourceViewVersionId)?.number
                        || source.current_version?.number
                        || 1
                      }</p>`
                    : ''
                }${state.sourceAnchors
                  .map(
                    (anchor, index) => `
          <section class="anchor" id="anchor-${anchor.id}" data-question-id="">
            <div class="anchor-label">${escapeHtml(sourceAnchorLabel(anchor, index))}</div>
            ${renderBlocks(anchor.content)}
          </section>
        `,
                  )
                  .join('')}`
              : `<div class="empty"><h3>暂无正文</h3></div>`
    }
  `;
}

function renderDocs(state, doc, proposal) {
  const docs = state.aiDocuments || [];
  if (!docs.length && !proposal) {
    return `<div class="empty"><h3>还没有文档</h3><button type="button" class="btn btn-primary" data-action="create-ai-doc">生成文档</button></div>`;
  }
  const version = currentAiVersion(doc);
  return `
    ${
      docs.length
        ? `<div class="resource-row">${docs
            .map(
              (item) => `
          <button type="button" class="mini ${item.id === state.activeAiDocumentId ? 'is-active' : ''}" data-action="select-ai-doc" data-id="${item.id}">
            <div class="item-title">${escapeHtml(item.title)}</div>
            <div class="item-sub">${formatTime(item.updated_at)}</div>
          </button>
        `,
            )
            .join('')}</div>`
        : ''
    }
    ${
      proposal?.status === 'ready'
        ? `<section class="diff">
            <div class="diff-col diff-before"><h4>当前</h4>${renderBlocks(proposal.changes?.[0]?.before || version?.content || [])}</div>
            <div class="diff-col diff-after"><h4>修改预览</h4>${renderBlocks(proposal.changes?.[0]?.after || [])}</div>
          </section>`
        : version
          ? renderBlocks(version.content)
          : `<div class="empty"><h3>选择一份文档</h3></div>`
    }
  `;
}
