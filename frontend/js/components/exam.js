import { icons } from '../icons.js';
import {
  DIFFICULTY,
  QUESTION_TYPES,
  blocksToText,
  escapeHtml,
  formatTime,
  pendingProposal,
  renderBlocks,
  statusLabel,
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
        placeholder: '想出一套什么卷？输入 / 用命令',
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
  return `
        <div class="task">
          ${renderHeader(tab, blueprint, draft, exam, proposal, collapsed)}
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

function renderHeader(tab, blueprint, draft, exam, proposal, collapsed) {
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
                : `<button type="button" class="btn btn-primary btn-sm" data-action="focus-composer">用对话组卷</button>`
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
            draft && (draft.status === 'editable' || draft.status === 'generating')
              ? `<button type="button" class="btn btn-primary btn-sm" data-action="publish-draft" data-id="${draft.id}" ${draft.status !== 'editable' ? 'disabled' : ''}>发布试卷</button>`
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
            ? `<button type="button" class="btn btn-primary btn-sm" data-action="apply-exam-proposal" data-id="${proposal.id}">应用修改</button>
               <button type="button" class="icon-btn" data-action="discard-exam-proposal" data-id="${proposal.id}" title="放弃">${icons.x(15)}</button>`
            : exam
              ? `<button type="button" class="btn btn-primary btn-sm" data-action="go-attempt" data-id="${exam.id}">去作答</button>`
              : `<button type="button" class="btn btn-primary btn-sm" data-action="focus-composer">用对话组卷</button>`
        }
        ${exam?.can_undo ? `<button type="button" class="icon-btn" data-action="undo-exam" data-id="${exam.id}" title="撤销">${icons.undo(15)}</button>` : ''}
        ${exam?.can_redo ? `<button type="button" class="icon-btn" data-action="redo-exam" data-id="${exam.id}" title="重做">${icons.redo(15)}</button>` : ''}
      </div>
    </div>`;
}

function renderBlueprint(state, blueprint) {
  const items = state.blueprints || [];
  if (!items.length) {
    return `<div class="empty"><h3>还没有试卷</h3><button type="button" class="btn btn-primary" data-action="focus-composer">用对话组卷</button></div>`;
  }
  return `
    <div class="resource-row">
      ${items
        .map(
          (item) => `
        <button type="button" class="mini ${item.id === state.activeBlueprintId ? 'is-active' : ''}" data-action="select-blueprint" data-id="${item.id}">
          <div class="item-title">${escapeHtml(item.title || '蓝图')}</div>
          <div class="item-sub"><span>${statusLabel('blueprint', item.status)}</span><span>${formatTime(item.updated_at)}</span></div>
        </button>
      `,
        )
        .join('')}
    </div>
    ${
      !blueprint
        ? `<div class="empty"><h3>选择一份蓝图</h3></div>`
        : blueprint.status === 'parsing'
          ? `<div class="boot">${icons.rotateCw(18, 'spin')}<h3>解析中</h3></div>`
          : blueprint.status === 'failed'
            ? `<div class="fail"><h3>解析失败</h3><button type="button" class="btn btn-primary" data-action="focus-composer">重新组卷</button></div>`
            : `<div>
                <p class="item-sub" style="margin-bottom:10px">${escapeHtml(truncate(blueprint.prompt || '', 160))}</p>
                ${renderSyllabus(blueprint)}
                <div class="plan">
                  ${(blueprint.question_plan || [])
                    .map(
                      (row) => `
                    <div class="plan-row">
                      <strong>${QUESTION_TYPES[row.type] || row.type}</strong>
                      <span>${DIFFICULTY[row.difficulty] || row.difficulty}</span>
                      <span>${row.count} 题</span>
                      <span>${row.score_each} 分</span>
                    </div>
                  `,
                    )
                    .join('')}
                </div>
                <p class="item-sub" style="margin-top:10px">总分 ${blueprint.total_score}${blueprint.duration_minutes ? ` · ${blueprint.duration_minutes} 分钟` : ''}</p>
              </div>`
    }
  `;
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
  if (!items.length) {
    return `<div class="empty"><h3>还没有草稿</h3><button type="button" class="btn btn-primary" data-action="focus-composer">用对话组卷</button></div>`;
  }
  return `
    <div class="resource-row">
      ${items
        .map(
          (item) => `
        <button type="button" class="mini ${item.id === state.activeDraftId ? 'is-active' : ''}" data-action="select-draft" data-id="${item.id}">
          <div class="item-title">${escapeHtml(item.title || '草稿')}</div>
          <div class="item-sub">${statusLabel('draft', item.status)}</div>
        </button>
      `,
        )
        .join('')}
    </div>
    ${
      !draft
        ? `<div class="empty"><h3>选择一份草稿</h3></div>`
        : (draft.questions || [])
            .map((slot) => {
              const q = slot.question;
              return `
          <article class="q" data-question-id="${slot.id}">
            <div class="q-head">
              <span>${slot.ordinal}.</span>
              <span>${QUESTION_TYPES[slot.planned_type] || slot.planned_type}</span>
              <span class="status ${slot.status === 'complete' ? 'status-ok' : slot.status === 'failed' ? 'status-bad' : 'status-warn'}">${statusLabel('draft', slot.status)}</span>
              ${slot.status === 'failed' ? `<button type="button" class="icon-btn" data-action="retry-question" data-draft-id="${draft.id}" data-id="${slot.id}" title="重试">${icons.rotateCw(14)}</button>` : ''}
            </div>
            ${q ? `${renderBlocks(q.stem)}${renderOptions(q)}${q.answer ? `<div class="answer-key">${escapeHtml(formatKey(q.answer))}</div>` : ''}${renderSolution(q)}` : `<p class="item-sub">${slot.error?.message || '生成中'}</p>`}
          </article>
        `;
            })
            .join('')
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
        .map(
          (item) => `
        <button type="button" class="mini ${item.id === state.activeExamId ? 'is-active' : ''}" data-action="select-exam" data-id="${item.id}">
          <div class="item-title">${escapeHtml(item.document?.title || '试卷')}</div>
          <div class="item-sub">${item.total_score} 分</div>
        </button>
      `,
        )
        .join('')}
    </div>
    ${
      proposal?.status === 'ready'
        ? `<section class="diff">
            ${(proposal.changes || [])
              .map(
                (change) => `
              <div class="diff-col diff-before"><h4>当前</h4><p>${escapeHtml(stringifyChange(change.before))}</p></div>
              <div class="diff-col diff-after"><h4>修改预览${change.summary ? ` · ${escapeHtml(change.summary)}` : ''}</h4><p>${escapeHtml(stringifyChange(change.after))}</p></div>
            `,
              )
              .join('')}
          </section>`
        : !exam
          ? `<div class="empty"><h3>选择一份试卷</h3></div>`
          : questions
              .map(
                (q, index) => `
          <article class="q" data-question-id="${q.id}">
            <div class="q-head"><span>${index + 1}.</span><span>${QUESTION_TYPES[q.type] || q.type}</span><span>${q.score} 分</span></div>
            ${renderBlocks(q.stem)}
            ${renderOptions(q)}
            ${q.answer ? `<div class="answer-key">${escapeHtml(formatKey(q.answer))}</div>` : ''}
            ${renderSolution(q)}
          </article>
        `,
              )
              .join('')
    }
  `;
}

function renderOptions(question) {
  if (!question.options?.length) return '';
  return question.options
    .map((opt) => `<div class="option-view"><span>${escapeHtml(opt.id)}</span><div>${renderBlocks(opt.content)}</div></div>`)
    .join('');
}

function stringifyChange(value) {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return blocksToText(value) || JSON.stringify(value);
  if (value.stem) return blocksToText(value.stem);
  if (value.text) return value.text;
  return truncate(JSON.stringify(value), 240);
}
