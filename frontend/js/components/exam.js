import { icons } from '../icons.js';
import {
  DIFFICULTY,
  QUESTION_TYPE_ORDER,
  QUESTION_TYPES,
  blocksArePlainText,
  blocksToText,
  escapeHtml,
  formatTime,
  pendingProposal,
  renderBlocks,
  renderMarkdown,
  statusLabel,
  sanitizeErrorMessage,
  draftPublishState,
  textToMarkdownBlocks,
  truncate,
} from '../util.js';
import { bindChatPane, renderChatPane } from './chat.js';
import { formatKey, renderSolution } from './solution.js';

export function examShellHtml(state) {
  const collapsed = !!state.sidebarCollapsed.exam;
  return `
    <div class="ws ws-task ${collapsed ? 'is-collapsed' : ''}" data-mobile="${state.mobilePane.exam}" data-testid="exam-workspace">
      <div class="mobile-switch">
        <button type="button" class="seg ${state.mobilePane.exam === 'ai' ? 'is-active' : ''}" data-action="mobile-pane" data-pane="ai">AI</button>
        <button type="button" class="seg ${state.mobilePane.exam === 'content' ? 'is-active' : ''}" data-action="mobile-pane" data-pane="content">内容</button>
      </div>
      <aside class="pane pane-ai"></aside>
      <main class="pane pane-content"></main>
    </div>
  `;
}

export function examLeftHtml(state, handlers) {
  const collapsed = !!state.sidebarCollapsed.exam;
  return collapsed
    ? ''
    : renderChatPane(state, handlers, {
        variant: 'task',
        placeholder: '例如 /组卷 出一套简单计网小测',
        emptyTitle: '开始新对话',
      });
}

export function examRightHtml(state) {
  const collapsed = !!state.sidebarCollapsed.exam;
  const tab = state.examTab || 'blueprint';
  const blueprint = state.blueprints.find((item) => item.id === state.activeBlueprintId) || null;
  const draft = state.drafts.find((item) => item.id === state.activeDraftId) || null;
  const exam = state.exams.find((item) => item.id === state.activeExamId) || null;
  const proposal = pendingProposal(state.examProposals);
  const draftProposal = pendingProposal(state.draftProposals);
  return `
        <div class="task">
          ${renderHeader(tab, blueprint, draft, exam, tab === 'draft' ? draftProposal : proposal, collapsed, state)}
          <div class="local-nav">
            <button type="button" class="seg ${tab === 'blueprint' ? 'is-active' : ''}" data-action="exam-tab" data-tab="blueprint">蓝图</button>
            <button type="button" class="seg ${tab === 'draft' ? 'is-active' : ''}" data-action="exam-tab" data-tab="draft">草稿</button>
            <button type="button" class="seg ${tab === 'exam' ? 'is-active' : ''}" data-action="exam-tab" data-tab="exam">试卷</button>
          </div>
          <div class="task-body" id="task-scroll" data-select-root="exam">
            ${tab === 'blueprint' ? renderBlueprint(state, blueprint) : tab === 'draft' ? renderDraft(state, draft) : renderExamDoc(state, exam, proposal)}
          </div>
        </div>
  `;
}

export function bindExamLeft(root, handlers) {
  bindChatPane(root, handlers);
}

function expandBtn(collapsed) {
  return collapsed
    ? `<button type="button" class="icon-btn" data-action="collapse-left" title="展开">${icons.panelLeftOpen(15)}</button>`
    : '';
}

function renderHeader(tab, blueprint, draft, exam, proposal, collapsed, state = {}) {
  if (tab === 'blueprint') {
    return `
      <div class="pane-head">
        <div class="head-meta">
          ${expandBtn(collapsed)}
          <div class="pane-title"><span>${escapeHtml(blueprint?.title || '蓝图')}</span></div>
          ${blueprint ? `<span class="status ${blueprint.status === 'confirmed' ? 'status-ok' : blueprint.status === 'failed' ? 'status-bad' : 'status-warn'}">${statusLabel('blueprint', blueprint.status)}</span>` : ''}
        </div>
        <div class="pane-actions">
          ${
            blueprint?.status === 'draft'
              ? `<button type="button" class="btn btn-primary btn-sm" data-action="confirm-blueprint" data-id="${blueprint.id}">确认蓝图</button>`
              : blueprint?.status === 'confirmed'
                ? `<button type="button" class="btn btn-primary btn-sm" data-action="generate-draft" data-id="${blueprint.id}">开始组题</button>`
                : `<button type="button" class="btn btn-primary btn-sm" data-action="create-blueprint">新建蓝图</button>`
          }
        </div>
      </div>`;
  }
  if (tab === 'draft') {
    return `
      <div class="pane-head">
        <div class="head-meta">
          ${expandBtn(collapsed)}
          <div class="pane-title"><span>${escapeHtml(draft?.title || '草稿')}</span></div>
          ${draft ? `<span class="status ${draft.status === 'editable' ? 'status-ok' : draft.status === 'failed' ? 'status-bad' : 'status-warn'}">${statusLabel('draft', draft.status)}</span>` : ''}
        </div>
        <div class="pane-actions">
          ${
            proposal?.status === 'ready'
              ? `<button type="button" class="btn btn-primary btn-sm" data-action="apply-draft-proposal" data-id="${proposal.id}" ${state.draftProposalBusyId === proposal.id ? 'disabled' : ''}>${state.draftProposalBusyId === proposal.id ? '应用中' : '应用修改'}</button>
                 <button type="button" class="icon-btn" data-action="discard-draft-proposal" data-id="${proposal.id}" title="放弃" ${state.draftProposalBusyId === proposal.id ? 'disabled' : ''}>${icons.x(15)}</button>`
              : draft && (draft.status === 'editable' || draft.status === 'generating')
              ? `<button type="button" class="btn btn-primary btn-sm" data-action="publish-draft" data-id="${draft.id}" ${draft.status !== 'editable' || !draftPublishState(draft).canPublish ? 'disabled' : ''} title="${draftPublishState(draft).canPublish ? '发布试卷' : '先重试失败或待复查题目'}">发布试卷</button>`
              : `<button type="button" class="btn btn-primary btn-sm" data-action="focus-composer">用对话组卷</button>`
          }
        </div>
      </div>`;
  }
  return `
    <div class="pane-head">
      <div class="head-meta">
        ${expandBtn(collapsed)}
        <div class="pane-title"><span>${escapeHtml(exam?.document?.title || '试卷')}</span></div>
        ${proposal ? `<span class="status status-warn">${statusLabel('proposal', proposal.status)}</span>` : ''}
      </div>
      <div class="pane-actions">
        ${
          proposal?.status === 'ready'
            ? `<button type="button" class="btn btn-primary btn-sm" data-action="apply-exam-proposal" data-id="${proposal.id}" ${state.draftProposalBusyId === proposal.id ? 'disabled' : ''}>${state.draftProposalBusyId === proposal.id ? '应用中' : '应用修改'}</button>
               <button type="button" class="icon-btn" data-action="discard-exam-proposal" data-id="${proposal.id}" title="放弃" ${state.draftProposalBusyId === proposal.id ? 'disabled' : ''}>${icons.x(15)}</button>`
            : exam
              ? `<button type="button" class="btn btn-primary btn-sm" data-action="go-attempt" data-id="${exam.id}">去作答</button>`
              : `<button type="button" class="btn btn-primary btn-sm" data-action="focus-composer">用对话组卷</button>`
        }
        ${exam ? examMoreMenu(exam, state) : ''}
      </div>
    </div>`;
}

function examMoreMenu(exam, state) {
  return `
    <div class="dropdown">
      <button type="button" class="icon-btn" data-action="toggle-menu" data-menu="exam-more" title="更多" aria-expanded="${state.openMenu === 'exam-more'}">${icons.moreHorizontal(15)}</button>
      ${
        state.openMenu === 'exam-more'
          ? `<div class="menu menu-right" role="menu">
              <button type="button" class="menu-item" role="menuitem" data-action="print-exam" data-id="${exam.id}">${icons.printer(14)}<span>打印</span></button>
              <button type="button" class="menu-item" role="menuitem" data-action="export-exam-pdf" data-id="${exam.id}">${icons.download(14)}<span>导出 PDF</span></button>
              <button type="button" class="menu-item" role="menuitem" data-action="export-exam-markdown" data-id="${exam.id}">${icons.fileText(14)}<span>导出 Markdown</span></button>
              ${exam.can_undo || exam.can_redo ? '<div class="menu-split"></div>' : ''}
              ${exam.can_undo ? `<button type="button" class="menu-item" role="menuitem" data-action="undo-exam" data-id="${exam.id}">${icons.undo(14)}<span>撤销</span></button>` : ''}
              ${exam.can_redo ? `<button type="button" class="menu-item" role="menuitem" data-action="redo-exam" data-id="${exam.id}">${icons.redo(14)}<span>重做</span></button>` : ''}
              ${examVersionMenu(exam, state)}
            </div>`
          : ''
      }
    </div>`;
}

function renderBlueprint(state, blueprint) {
  const items = state.blueprints || [];
  if (!items.length) {
    return `<div class="empty"><h3>还没有蓝图</h3><p class="item-sub">可以先用默认题型，再改题量和分值</p><button type="button" class="btn btn-primary" data-action="create-blueprint">新建蓝图</button></div>`;
  }
  return `
    <div class="resource-row">
      ${items
        .map((item) =>
          renderMiniCard({
            active: item.id === state.activeBlueprintId,
            renaming: state.renamingBlueprintId === item.id,
            action: 'select-blueprint',
            id: item.id,
            title: item.title || '蓝图',
            sub: `<span>${statusLabel('blueprint', item.status)}</span><span>${formatTime(item.updated_at)}</span>`,
            renameKind: 'blueprint',
            deleteAction: 'delete-blueprint',
          }),
        )
        .join('')}
      <div class="mini-wrap">
        <button type="button" class="mini" data-action="create-blueprint">
          <div class="item-title">新建蓝图</div>
          <div class="item-sub">默认题型，可改</div>
        </button>
      </div>
    </div>
    ${
      !blueprint
        ? `<div class="empty"><h3>选择一份蓝图</h3></div>`
        : blueprint.status === 'parsing'
          ? `<div class="boot">${icons.rotateCw(18, 'spin')}<h3>解析中</h3></div>`
          : blueprint.status === 'failed'
            ? `<div class="fail"><h3>${escapeHtml(blueprint.issues?.[0]?.message || '解析失败')}</h3><button type="button" class="btn btn-primary" data-action="create-blueprint">新建蓝图</button></div>`
            : `<div>
                <p class="item-sub" style="margin-bottom:10px">${escapeHtml(truncate(blueprint.prompt || '', 160))}</p>
                ${(blueprint.issues || [])
                  .map((issue) => `<p class="item-sub">${escapeHtml(issue.message)}</p>`)
                  .join('')}
                ${renderSyllabus(blueprint)}
                <div class="plan">
                  ${(blueprint.question_plan || [])
                    .map((row, index) => renderPlanRow(blueprint, row, index))
                    .join('')}
                </div>
                ${
                  blueprint.status === 'draft'
                    ? `<button type="button" class="btn btn-ghost btn-sm" data-action="add-plan-row" data-id="${blueprint.id}" style="margin-top:8px">${icons.plus(14)} 题型</button>`
                    : ''
                }
                <p class="item-sub" style="margin-top:10px">总分 ${blueprint.total_score}</p>
                ${renderDurationField(blueprint)}
              </div>`
    }
  `;
}

function examVersionMenu(exam, state) {
  const versions = (state.examVersions || []).slice().sort((a, b) => (b.number || 0) - (a.number || 0));
  if (versions.length < 2) return '';
  const actor = { user: '人工', ai: 'AI', restore: '恢复', undo: '撤销', redo: '重做' };
  return `
    <div class="menu-split"></div>
    <div class="menu-title">版本</div>
    ${versions
      .map((item) => {
        const current = item.id === exam.current_version_id;
        return `<button type="button" class="menu-item ${current ? 'is-active' : ''}" role="menuitem" data-action="restore-exam-version" data-id="${exam.id}" data-version-id="${item.id}" ${current ? 'disabled' : ''} title="${escapeHtml(item.summary || '')}">
          <span>v${item.number} · ${actor[item.actor] || item.actor}${current ? ' · 当前' : ''}</span>
        </button>`;
      })
      .join('')}
  `;
}

function renderPlanRow(blueprint, row, index) {
  const draft = blueprint.status === 'draft';
  const canRemove = draft && (blueprint.question_plan || []).length > 1;
  if (!draft) {
    return `
      <div class="plan-row">
        <strong>${QUESTION_TYPES[row.type] || row.type}</strong>
        <span>${DIFFICULTY[row.difficulty] || row.difficulty}</span>
        <span>${row.count} 题</span>
        <span>${row.score_each} 分</span>
      </div>`;
  }
  return `
    <div class="plan-row is-editing">
      <select class="input" data-action="plan-type" data-id="${blueprint.id}" data-index="${index}" title="题型">
        ${QUESTION_TYPE_ORDER.map((type) => `<option value="${type}" ${row.type === type ? 'selected' : ''}>${QUESTION_TYPES[type]}</option>`).join('')}
      </select>
      <select class="input" data-action="plan-difficulty" data-id="${blueprint.id}" data-index="${index}" title="难度">
        ${Object.entries(DIFFICULTY).map(([id, label]) => `<option value="${id}" ${row.difficulty === id ? 'selected' : ''}>${label}</option>`).join('')}
      </select>
      <input class="input" type="number" min="1" value="${row.count}" data-action="plan-count" data-id="${blueprint.id}" data-index="${index}" title="题量" />
      <input class="input" type="number" min="1" step="0.5" value="${row.score_each}" data-action="plan-score" data-id="${blueprint.id}" data-index="${index}" title="每题分值" />
      ${
        canRemove
          ? `<button type="button" class="icon-btn" data-action="remove-plan-row" data-id="${blueprint.id}" data-index="${index}" title="删除题型">${icons.x(14)}</button>`
          : '<span></span>'
      }
    </div>`;
}

function renderDurationField(blueprint) {
  if (blueprint.status === 'draft') {
    return `
      <label class="field duration-field">
        <span class="field-label">建议用时</span>
        <input class="input" type="number" min="1" placeholder="分钟，可空" value="${blueprint.duration_minutes || ''}" data-action="plan-duration" data-id="${blueprint.id}" title="建议用时" />
        <span class="item-sub">分钟</span>
      </label>`;
  }
  return blueprint.duration_minutes
    ? `<p class="item-sub">建议用时 ${blueprint.duration_minutes} 分钟</p>`
    : '';
}

function renderSyllabus(blueprint) {
  const points = (blueprint.syllabus || []).filter(Boolean);
  if (!points.length) return '';
  const draft = blueprint.status === 'draft';
  return `
    <div class="syllabus-row">
      <span class="solution-label">考点</span>
      <div class="cite-row">
        ${points
          .map(
            (point, index) => `
          <span class="cite${draft ? ' is-editable' : ''}">
            ${escapeHtml(point)}
            ${
              draft
                ? `<button type="button" class="cite-remove" data-action="remove-blueprint-point" data-id="${blueprint.id}" data-index="${index}" title="删除">${icons.x(10)}</button>`
                : ''
            }
          </span>`,
          )
          .join('')}
      </div>
    </div>
  `;
}

function renderDraft(state, draft) {
  const items = state.drafts || [];
  const proposal = pendingProposal(state.draftProposals);
  if (!items.length) {
    return `<div class="empty"><h3>还没有草稿</h3><button type="button" class="btn btn-primary" data-action="focus-composer">用对话组卷</button></div>`;
  }
  return `
    <div class="resource-row">
      ${items
        .map((item) =>
          renderMiniCard({
            active: item.id === state.activeDraftId,
            renaming: false,
            action: 'select-draft',
            id: item.id,
            title: item.title || '草稿',
            sub: statusLabel('draft', item.status),
            deleteAction: 'delete-draft',
          }),
        )
        .join('')}
    </div>
    ${
      !draft
        ? `<div class="empty"><h3>选择一份草稿</h3></div>`
        : `${
            proposal?.status === 'ready' ? renderProposalDiff(proposal) : ''
          }${(draft.questions || [])
            .map((slot) => {
              const q = slot.question;
              const retryable = slot.status === 'failed' || slot.status === 'needs-review';
              const editing = state.draftHandEditId === slot.id;
              const canEdit = draft.status === 'editable' && q && !proposal;
              const slots = draft.questions || [];
              return `
          <article class="q" data-question-id="${slot.id}">
            <div class="q-head">
              <span>${slot.ordinal}.</span>
              <span>${QUESTION_TYPES[slot.planned_type] || slot.planned_type}</span>
              <span class="status ${slot.status === 'complete' ? 'status-ok' : slot.status === 'failed' ? 'status-bad' : 'status-warn'}">${statusLabel('draft', slot.status)}</span>
              ${
                canEdit
                  ? `<div class="q-ops">
                      <button type="button" class="icon-btn" data-action="move-question" data-draft-id="${draft.id}" data-id="${slot.id}" data-delta="-1" title="上移" ${slot.ordinal <= 1 ? 'disabled' : ''}>${icons.chevronUp(14)}</button>
                      <button type="button" class="icon-btn" data-action="move-question" data-draft-id="${draft.id}" data-id="${slot.id}" data-delta="1" title="下移" ${slot.ordinal >= slots.length ? 'disabled' : ''}>${icons.chevronDown(14)}</button>
                      ${retryable ? `<button type="button" class="icon-btn" data-action="retry-question" data-draft-id="${draft.id}" data-id="${slot.id}" title="重试" ${state.retryingQuestionId === slot.id || slot.status === 'generating' || slot.status === 'queued' ? 'disabled' : ''}>${icons.rotateCw(14)}</button>` : ''}
                      <button type="button" class="icon-btn ${editing ? 'is-active' : ''}" data-action="toggle-question-edit" data-id="${slot.id}" title="手改">${icons.edit3(14)}</button>
                      ${
                        slots.length > 1
                          ? `<button type="button" class="icon-btn" data-action="delete-question" data-draft-id="${draft.id}" data-id="${slot.id}" title="删题">${icons.trash2(14)}</button>`
                          : ''
                      }
                    </div>`
                  : retryable
                    ? `<button type="button" class="icon-btn" data-action="retry-question" data-draft-id="${draft.id}" data-id="${slot.id}" title="重试" ${state.retryingQuestionId === slot.id || slot.status === 'generating' || slot.status === 'queued' ? 'disabled' : ''}>${icons.rotateCw(14)}</button>`
                    : ''
              }
            </div>
            ${
              editing && q
                ? renderQuestionEditor(draft, slot, q)
                : q
                  ? `${renderBlocks(q.stem)}${renderOptions(q)}${q.answer ? `<div class="answer-key">${escapeHtml(formatKey(q.answer))}</div>` : ''}${renderSolution(q)}`
                  : `<p class="item-sub">${escapeHtml(sanitizeErrorMessage(slot.error?.message || (slot.status === 'generating' || slot.status === 'queued' ? '生成中' : '待生成')))}</p>`
            }
            ${editing ? '' : renderQuestionRevise(state, draft, slot, q, proposal)}
          </article>
        `;
            })
            .join('')}`
    }
  `;
}

function renderExamDoc(state, exam, proposal) {
  const items = state.exams || [];
  if (!items.length) {
    return `<div class="empty"><h3>还没有试卷</h3><button type="button" class="btn btn-primary" data-action="focus-composer">用对话组卷</button></div>`;
  }
  const questions = exam?.document?.questions || [];
  return `
    <div class="resource-row">
      ${items
        .map((item) =>
          renderMiniCard({
            active: item.id === state.activeExamId,
            renaming: state.renamingExamId === item.id,
            action: 'select-exam',
            id: item.id,
            title: item.document?.title || '试卷',
            sub: `${item.total_score} 分`,
            renameKind: 'exam',
            deleteAction: 'delete-exam',
          }),
        )
        .join('')}
    </div>
    ${
      proposal?.status === 'ready'
        ? renderProposalDiff(proposal)
        : !exam
          ? `<div class="empty"><h3>选择一份试卷</h3></div>`
          : questions.map((q, index) => renderExamQuestion(q, { index, showSolution: true })).join('')
    }
  `;
}

export function renderMiniCard({ active, renaming, action, id, title, sub, renameKind, deleteAction }) {
  const titleHtml = renaming
    ? `<input class="input inline-rename" data-rename-resource="${renameKind}" data-id="${id}" value="${escapeHtml(title)}" maxlength="200" />`
    : `<div class="item-title">${escapeHtml(title)}</div>`;
  const inner = renaming
    ? `<div class="mini is-active">${titleHtml}<div class="item-sub">${sub}</div></div>`
    : `<button type="button" class="mini ${active ? 'is-active' : ''}" data-action="${action}" data-id="${id}">${titleHtml}<div class="item-sub">${sub}</div></button>`;
  const ops = [];
  if (renameKind) {
    ops.push(`<button type="button" class="ghost-icon" data-action="rename-${renameKind}" data-id="${id}" title="重命名" aria-label="重命名">${icons.edit3(12)}</button>`);
  }
  if (deleteAction) {
    ops.push(`<button type="button" class="ghost-icon is-danger" data-action="${deleteAction}" data-id="${id}" title="删除" aria-label="删除">${icons.trash2(12)}</button>`);
  }
  return `
    <div class="mini-wrap ${active ? 'is-active' : ''} ${renaming ? 'is-renaming' : ''} ${ops.length > 1 ? 'has-two-ops' : ''}">
      ${inner}
      ${active && !renaming && ops.length ? `<div class="mini-ops">${ops.join('')}</div>` : ''}
    </div>
  `;
}

function renderQuestionRevise(state, draft, slot, question, proposal) {
  if (!question || draft.status !== 'editable' || proposal) return '';
  if (state.draftQuestionBusyId === slot.id) {
    return `<button type="button" class="btn btn-primary btn-sm q-revise-toggle" disabled>正在修改</button>`;
  }
  if (state.draftQuestionBusyId) return '';
  if (state.draftQuestionEditId === slot.id) {
    return `
      <div class="q-revise">
        <input id="question-revise-input" class="input" type="text" placeholder="写一句修改要求" value="${escapeHtml(state.draftQuestionPrompt || '')}" maxlength="10000" />
        <button type="button" class="btn btn-primary btn-sm" data-action="revise-question" data-id="${slot.id}">改这题</button>
        <button type="button" class="icon-btn" data-action="cancel-question-revise" title="取消">${icons.x(14)}</button>
      </div>`;
  }
  return `<button type="button" class="btn btn-ghost btn-sm q-revise-toggle" data-action="open-question-revise" data-id="${slot.id}">改这题</button>`;
}

export function renderOptions(question) {
  if (!question.options?.length) return '';
  return question.options
    .map((opt) => `<div class="option-view"><span>${escapeHtml(opt.id)}</span><div>${renderBlocks(opt.content)}</div></div>`)
    .join('');
}

export function renderExamQuestion(question, { index = 0, showSolution = false } = {}) {
  if (!question) return '';
  const ordinal = question.ordinal || index + 1;
  return `
    <article class="q" data-question-id="${question.id}">
      <div class="q-head"><span>${ordinal}.</span><span>${QUESTION_TYPES[question.type] || question.type}</span><span>${question.score} 分</span></div>
      ${renderBlocks(question.stem)}
      ${renderOptions(question)}
      ${showSolution && question.answer ? `<div class="answer-key">${escapeHtml(formatKey(question.answer))}</div>` : ''}
      ${showSolution ? renderSolution(question) : ''}
    </article>
  `;
}

export function renderExamPrintDocument(doc) {
  const showSolution = doc?.edition === 'solutions';
  const questions = (doc?.questions || [])
    .map((item, index) => {
      const question = item.question || item;
      const merged = showSolution && item.solution ? { ...question, ...item.solution } : question;
      return renderExamQuestion(merged, { index, showSolution });
    })
    .join('');
  return `
    <div class="print-exam">
      <h1>${escapeHtml(doc?.title || '试卷')}</h1>
      ${doc?.instructions?.length ? `<div class="print-instructions">${renderBlocks(doc.instructions)}</div>` : ''}
      ${questions}
    </div>
  `;
}

function renderProposalDiff(proposal) {
  return `
    <section class="diff">
      ${(proposal.changes || [])
        .map(
          (change) => `
        <div class="diff-col diff-before"><h4>当前</h4>${renderChangeSide(change.before)}</div>
        <div class="diff-col diff-after"><h4>修改预览${change.summary ? ` · ${escapeHtml(change.summary)}` : ''}</h4>${renderChangeSide(change.after)}</div>
      `,
        )
        .join('')}
    </section>`;
}

function renderChangeSide(value) {
  if (value == null || value === '') return '<p class="item-sub">无</p>';
  if (typeof value === 'string') return `<div class="prose">${renderMarkdown(value)}</div>`;
  if (Array.isArray(value)) {
    if (!value.length) return '<p class="item-sub">无</p>';
    if (value[0]?.type || value[0]?.text) return renderBlocks(value);
    if (value[0]?.stem) return value.map((item) => renderChangeSide(item)).join('');
  }
  if (typeof value === 'object') {
    if (value.stem) {
      return `${renderBlocks(value.stem)}${renderOptions(value)}${
        value.answer ? `<div class="answer-key">${escapeHtml(formatKey(value.answer))}</div>` : ''
      }${value.score != null ? `<p class="item-sub">${escapeHtml(String(value.score))} 分</p>` : ''}`;
    }
    if (value.text) return renderBlocks([{ type: 'markdown', id: value.id || 'block', text: value.text }]);
    const parts = [];
    if (value.title) parts.push(value.title);
    if (value.type) parts.push(QUESTION_TYPES[value.type] || value.type);
    if (value.score != null) parts.push(`${value.score} 分`);
    if (parts.length) return `<p>${escapeHtml(parts.join(' · '))}</p>`;
  }
  return '<p class="item-sub">结构化修改</p>';
}

function renderQuestionEditor(draft, slot, question) {
  const stemOk = blocksArePlainText(question.stem);
  const options = question.options || [];
  const selected = new Set(question.answer?.kind === 'choice' ? question.answer.option_ids || [] : []);
  const choice = question.type === 'single-choice' || question.type === 'multiple-choice';
  return `
    <form class="q-editor" data-question-edit="${slot.id}" data-draft-id="${draft.id}">
      ${
        stemOk
          ? `<label class="field"><span class="field-label">题干</span><textarea class="textarea" name="stem" rows="4">${escapeHtml(blocksToText(question.stem))}</textarea></label>`
          : `<p class="item-sub">本题含图片或表格，题干请用「改这题」</p>${renderBlocks(question.stem)}`
      }
      <label class="field"><span class="field-label">分值</span><input class="input" type="number" min="0.5" step="0.5" name="score" value="${question.score}" /></label>
      ${
        choice
          ? `<div class="q-options-edit">${options
              .map(
                (opt, index) => `
            <label class="option">
              <input type="${question.type === 'single-choice' ? 'radio' : 'checkbox'}" name="correct" value="${escapeHtml(opt.id)}" ${selected.has(opt.id) ? 'checked' : ''} />
              <span>${escapeHtml(opt.id)}</span>
              <input class="input" name="option-${index}" data-option-id="${escapeHtml(opt.id)}" value="${escapeHtml(blocksToText(opt.content))}" ${blocksArePlainText(opt.content) ? '' : 'disabled'} />
            </label>`,
              )
              .join('')}
            <button type="button" class="btn btn-ghost btn-sm" data-action="add-option" data-id="${slot.id}">加选项</button>
          </div>`
          : ''
      }
      ${
        question.type === 'true-false'
          ? `<div class="q-options-edit">
              <label class="option"><input type="radio" name="tf" value="true" ${question.answer?.value === true ? 'checked' : ''} /><span>对</span></label>
              <label class="option"><input type="radio" name="tf" value="false" ${question.answer?.value === false ? 'checked' : ''} /><span>错</span></label>
            </div>`
          : ''
      }
      ${
        question.type === 'fill-blank'
          ? (question.answer?.blanks || [])
              .map(
                (blank, index) => `
            <label class="field"><span class="field-label">空 ${index + 1} 答案</span>
              <input class="input" name="blank-${index}" value="${escapeHtml((blank.acceptable_answers || []).join(' / '))}" />
            </label>`,
              )
              .join('')
          : ''
      }
      <div class="q-revise">
        <button type="button" class="btn btn-primary btn-sm" data-action="save-question-edit" data-draft-id="${draft.id}" data-id="${slot.id}">保存</button>
        <button type="button" class="icon-btn" data-action="toggle-question-edit" data-id="${slot.id}" title="取消">${icons.x(14)}</button>
      </div>
    </form>`;
}

export function questionFromEditor(question, formEl) {
  const form = new FormData(formEl);
  const next = JSON.parse(JSON.stringify(question));
  const score = Number(form.get('score'));
  if (Number.isFinite(score) && score > 0) next.score = score;
  if (form.has('stem') && blocksArePlainText(question.stem)) {
    next.stem = textToMarkdownBlocks(form.get('stem'), question.stem);
  }
  if (next.type === 'single-choice' || next.type === 'multiple-choice') {
    next.options = (next.options || []).map((opt, index) => {
      const input = formEl.querySelector(`[name="option-${index}"]`);
      if (!input || input.disabled) return opt;
      return { ...opt, content: textToMarkdownBlocks(input.value, opt.content) };
    });
    const checked = form.getAll('correct');
    if (checked.length) next.answer = { kind: 'choice', option_ids: checked };
  }
  if (next.type === 'true-false') {
    const value = form.get('tf');
    if (value === 'true' || value === 'false') next.answer = { kind: 'true-false', value: value === 'true' };
  }
  if (next.type === 'fill-blank' && Array.isArray(next.answer?.blanks)) {
    next.answer = {
      ...next.answer,
      blanks: next.answer.blanks.map((blank, index) => {
        const raw = String(form.get(`blank-${index}`) || '');
        const answers = raw.split(/[/；;]+/).map((item) => item.trim()).filter(Boolean);
        return { ...blank, acceptable_answers: answers.length ? answers : blank.acceptable_answers };
      }),
    };
  }
  return next;
}
