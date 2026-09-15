import { icons } from '../icons.js';
import {
  currentAiVersion,
  escapeHtml,
  formatTime,
  isUploadedSource,
  pendingProposal,
  renderBlocks,
  sourceAnchorLabel,
  statusLabel,
  uploadedSources,
} from '../util.js';
import { bindChatPane, renderChatPane } from './chat.js';
import { expandBtn, taskWorkspaceShell } from './workspace-shell.js';

export function sourcesShellHtml(state) {
  return taskWorkspaceShell({
    testId: 'sources-workspace',
    collapsed: !!state.sidebarCollapsed.sources,
    mobilePane: state.mobilePane.sources,
  });
}

export function sourcesLeftHtml(state, handlers) {
  const collapsed = !!state.sidebarCollapsed.sources;
  return collapsed
    ? ''
    : renderChatPane(state, handlers, {
        variant: 'task',
        placeholder: '要整理哪份资料？',
        emptyTitle: '开始新对话',
      });
}

export function sourcesRightHtml(state) {
  const collapsed = !!state.sidebarCollapsed.sources;
  const kind = state.sourceKind || 'files';
  const source = uploadedSources(state.sources).find((item) => item.id === state.activeSourceId)
    || uploadedSources(state.sources)[0]
    || null;
  const doc = state.aiDocuments.find((item) => item.id === state.activeAiDocumentId) || null;
  const proposal = pendingProposal(state.aiDocumentProposals);
  return `
        <div class="task">
          ${renderHeader(state, kind, source, doc, proposal, collapsed)}
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

function renderHeader(state, kind, source, doc, proposal, collapsed) {
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
              : `<button type="button" class="btn btn-primary btn-sm" data-action="revise-ai-doc">修改当前</button>
                 <button type="button" class="icon-btn" data-action="delete-ai-doc" data-id="${doc.id}" title="删除">${icons.trash2(15)}</button>
                 <div class="dropdown">
                   <button type="button" class="icon-btn" data-action="toggle-menu" data-menu="doc-more" title="更多" aria-expanded="${state.openMenu === 'doc-more'}">${icons.moreHorizontal(15)}</button>
                   ${state.openMenu === 'doc-more' ? docMoreMenu(doc, state) : ''}
                 </div>`
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
  const sources = uploadedSources(state.sources);
  const current = source && isUploadedSource(source) ? source : null;
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
      !current
        ? `<div class="empty"><h3>选择一份资料</h3></div>`
        : current.status === 'processing'
          ? `<div class="boot"><div>${icons.rotateCw(18, 'spin')}</div><h3>处理中</h3></div>`
          : current.status === 'failed'
            ? `<div class="fail"><h3>处理失败</h3><p>${escapeHtml(current.failure?.message || '')}</p><button type="button" class="btn btn-ghost" data-action="upload-source">重新上传</button></div>`
            : `${renderSourceVersions(state, current)}${
                (state.sourceAnchors || []).length
                  ? state.sourceAnchors
                      .map(
                        (anchor, index) => `
          <section class="anchor" id="anchor-${anchor.id}" data-question-id="">
            <div class="anchor-label">${escapeHtml(sourceAnchorLabel(anchor, index))}</div>
            ${renderBlocks(anchor.content)}
          </section>
        `,
                      )
                      .join('')
                  : `<div class="empty"><h3>暂无正文</h3></div>`
              }`
    }
  `;
}

function renderDocs(state, doc, proposal) {
  const docs = state.aiDocuments || [];
  if (!docs.length && !proposal) {
    return `<div class="empty"><h3>还没有文档</h3><button type="button" class="btn btn-primary" data-action="create-ai-doc">生成文档</button></div>`;
  }
  const version = viewedAiVersion(doc, state);
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
          ? `${renderAiDocumentVersions(doc, version)}${renderBlocks(version.content)}`
          : `<div class="empty"><h3>选择一份文档</h3></div>`
    }
  `;
}

function viewedAiVersion(doc, state) {
  const versions = doc?.versions || [];
  return versions.find((item) => item.id === state.aiDocumentViewVersionId) || currentAiVersion(doc);
}

function docMoreMenu(doc) {
  return `
    <div class="menu menu-right" role="menu">
      <button type="button" class="menu-item" data-action="create-ai-doc">${icons.plus(14)}<span>生成文档</span></button>
      ${doc ? `<button type="button" class="menu-item" data-action="delete-ai-doc" data-id="${doc.id}">${icons.trash2(14)}<span>删除</span></button>` : ''}
    </div>
  `;
}

function renderSourceVersions(state, source) {
  const versions = (state.sourceVersions || []).slice().sort((a, b) => (b.number || 0) - (a.number || 0));
  if (versions.length < 2) return '';
  const currentId = source.current_version?.id;
  const viewing = state.sourceViewVersionId || currentId;
  return `
    <div class="version-row">
      <span class="solution-label">版本</span>
      <div class="cite-row">
        ${versions
          .map((item) => {
            const current = item.id === currentId;
            const active = item.id === viewing;
            return `<button type="button" class="cite ${active ? 'is-active' : ''}" data-action="view-source-version" data-id="${source.id}" data-version-id="${item.id}">v${item.number}${current ? ' · 当前' : ''}</button>`;
          })
          .join('')}
      </div>
    </div>`;
}

function renderAiDocumentVersions(doc, viewing) {
  const versions = (doc?.versions || []).slice().sort((a, b) => (b.number || 0) - (a.number || 0));
  if (versions.length < 2) return '';
  return `
    <div class="version-row">
      <span class="solution-label">版本</span>
      <div class="cite-row">
        ${versions
          .map((item) => {
            const current = item.id === doc.current_version_id;
            const active = item.id === viewing?.id;
            return `<button type="button" class="cite ${active ? 'is-active' : ''}" data-action="view-ai-doc-version" data-id="${doc.id}" data-version-id="${item.id}">v${item.number}${current ? ' · 当前' : ''}</button>${
              !current && active
                ? `<button type="button" class="btn btn-ghost btn-sm" data-action="restore-ai-doc-version" data-id="${doc.id}" data-version-id="${item.id}">恢复此版</button>`
                : ''
            }`;
          })
          .join('')}
      </div>
    </div>`;
}
