import { icons } from '../icons.js';
import {
  QUESTION_TYPES,
  answerForQuestion,
  blankIdsForQuestion,
  buildAnswerPayload,
  escapeHtml,
  feedbackForQuestion,
  formatTime,
  renderBlocks,
  statusLabel,
} from '../util.js';
import { attemptElapsedMs, attemptLimitMs, attemptRemainingMs, attemptTimerRunning, examDurationMinutes, formatElapsed } from '../attempt-timer.js';
import { bindChatPane, renderChatPane } from './chat.js';
import { renderMiniCard } from './exam.js';
import { renderReview, renderSolution } from './solution.js';
import { taskWorkspaceShell } from './workspace-shell.js';

const SUBJECTIVE_TYPES = new Set(['short-answer', 'argumentation', 'extended-response']);

export function attemptShellHtml(state) {
  return taskWorkspaceShell({
    testId: 'attempt-workspace',
    collapsed: !!state.sidebarCollapsed.attempt,
    mobilePane: state.mobilePane.attempt,
  });
}

export function attemptLeftHtml(state, handlers) {
  const collapsed = !!state.sidebarCollapsed.attempt;
  return collapsed
    ? ''
    : renderChatPane(state, handlers, {
        variant: 'task',
        placeholder: '要解释哪一题？',
        emptyTitle: '开始新对话',
      });
}

export function attemptRightHtml(state) {
  const collapsed = !!state.sidebarCollapsed.attempt;
  const tab = state.attemptTab || 'exams';
  const exam = state.exams.find((item) => item.id === state.activeExamId) || null;
  const attempt = state.activeAttempt;
  return `
        <div class="task">
          ${tab === 'missed' ? renderMissedHeader(state, collapsed) : renderHeader(state, exam, attempt, collapsed)}
          <div class="local-nav">
            <button type="button" class="seg ${tab === 'exams' ? 'is-active' : ''}" data-action="attempt-tab" data-tab="exams">试卷</button>
            <button type="button" class="seg ${tab === 'missed' ? 'is-active' : ''}" data-action="attempt-tab" data-tab="missed">错题</button>
          </div>
          <div class="task-body" id="task-scroll" data-select-root="attempt">
            ${tab === 'missed' ? renderMissed(state) : renderBody(state, exam, attempt)}
          </div>
        </div>
  `;
}

export function bindAttemptLeft(root, handlers) {
  bindChatPane(root, handlers);
}

export function bindAttemptRight(root, handlers, attempt) {
  const form = root.querySelector('#attempt-form');
  if (form && attempt && attempt.completion_status !== 'completed') {
    form.onchange = () => {
      const questionEl = document.activeElement?.closest?.('[data-question-id]');
      const questionId = questionEl?.dataset.questionId;
      if (!questionId) return;
      const question = attempt.paper?.questions?.find((item) => item.id === questionId);
      if (!question) return;
      const payload = buildAnswerPayload(question, new FormData(form));
      if (payload) handlers.onSaveAnswer(attempt.id, questionId, payload);
    };
  }
}

function renderHeader(state, exam, attempt, collapsed) {
  const expand = collapsed
    ? `<button type="button" class="icon-btn" data-action="collapse-left" title="展开">${icons.panelLeftOpen(15)}</button>`
    : '';
  if (!exam && !attempt) {
    return `
      <div class="pane-head">
        <div class="head-meta">${expand}<div class="pane-title"><span>作答</span></div></div>
        <div class="pane-actions"><button type="button" class="btn btn-primary btn-sm" data-action="go-exam">去组卷</button></div>
      </div>`;
  }
  const title = attempt?.paper?.title || exam?.document?.title || '试卷';
  const primary = attemptPrimary(attempt);
  return `
    <div class="pane-head">
      <div class="head-meta">
        ${expand}
        ${attempt ? `<button type="button" class="icon-btn" data-action="close-attempt" title="返回试卷">${icons.chevronLeft(15)}</button>` : ''}
        <div class="pane-title"><span>${escapeHtml(title)}</span></div>
        ${attempt ? attemptStatusPill(attempt) : ''}
      </div>
      <div class="pane-actions">
        ${primary}
        ${attemptTimerHtml(state, exam, attempt)}
        ${attemptMoreMenu(state, attempt)}
      </div>
    </div>`;
}

function renderMissedHeader(state, collapsed) {
  const expand = collapsed
    ? `<button type="button" class="icon-btn" data-action="collapse-left" title="展开">${icons.panelLeftOpen(15)}</button>`
    : '';
  const hasMissed = (state.missedQuestions || []).length > 0;
  return `
    <div class="pane-head">
      <div class="head-meta">${expand}<div class="pane-title"><span>错题</span></div></div>
      <div class="pane-actions">
        ${hasMissed ? '<button type="button" class="btn btn-primary btn-sm" data-action="practice-missed-set">再练一套</button>' : ''}
      </div>
    </div>`;
}

function attemptMoreMenu(state, attempt) {
  if (!attempt) return '';
  const items = [];
  if (attempt.mode === 'practice' && attempt.completion_status !== 'completed') {
    items.push(`<button type="button" class="menu-item" role="menuitem" data-action="toggle-suggested-score" data-id="${attempt.id}">${icons.tag(14)}<span>${attempt.show_suggested_score ? '隐藏建议分' : '显示建议分'}</span></button>`);
  }
  if (attempt.status === 'in-progress' && attempt.completion_status !== 'completed') {
    items.push(`<button type="button" class="menu-item" role="menuitem" data-action="pause-attempt" data-id="${attempt.id}">${icons.pause(14)}<span>暂停</span></button>`);
  } else if (attempt.status === 'paused') {
    items.push(`<button type="button" class="menu-item" role="menuitem" data-action="resume-attempt" data-id="${attempt.id}">${icons.play(14)}<span>继续</span></button>`);
  }
  if (attempt.completion_status === 'completed' && attempt.grading_status !== 'completed') {
    items.push(`<button type="button" class="menu-item" role="menuitem" data-action="continue-attempt" data-id="${attempt.id}">${icons.play(14)}<span>继续作答</span></button>`);
  }
  if (!items.length) return '';
  return `
    <div class="dropdown">
      <button type="button" class="icon-btn" data-action="toggle-menu" data-menu="attempt-more" title="更多" aria-expanded="${state.openMenu === 'attempt-more'}">${icons.moreHorizontal(15)}</button>
      ${state.openMenu === 'attempt-more' ? `<div class="menu menu-right" role="menu">${items.join('')}</div>` : ''}
    </div>`;
}

function renderMissed(state) {
  const groups = state.missedQuestions || [];
  if (!groups.length) {
    return `<div class="empty"><h3>还没有错题</h3><button type="button" class="btn btn-primary" data-action="attempt-tab" data-tab="exams">去作答</button></div>`;
  }
  const selected = new Set(state.missedSelectedPoints || []);
  return groups
    .map((group) => {
      const point = group.knowledge_point;
      const checked = selected.has(point) ? 'checked' : '';
      const rows = (group.questions || [])
        .map((item) => {
          const type = QUESTION_TYPES[item.question_type] || item.question_type;
          return `
        <button type="button" class="item" data-action="open-missed-question" data-attempt-id="${escapeHtml(item.attempt_id || '')}" data-question-id="${escapeHtml(item.question_id || '')}">
          <div class="item-main">
            <div class="item-title">${escapeHtml(type)} · ${escapeHtml(item.stem_preview || '')}</div>
            <div class="item-sub">
              <span>${escapeHtml(item.exam_title || '试卷')}</span>
              <span>${formatTime(item.missed_at)}</span>
            </div>
          </div>
        </button>`;
        })
        .join('');
      return `
      <section class="missed-group">
        <label class="missed-head">
          <input type="checkbox" data-action="toggle-missed-point" data-point="${escapeHtml(point)}" ${checked} />
          <span class="missed-head-title">${escapeHtml(point)}</span>
          <span class="item-sub">${group.miss_count} 题</span>
        </label>
        <div class="list">${rows}</div>
      </section>`;
    })
    .join('');
}

function attemptTimerHtml(state, exam, attempt) {
  if (!attempt) return '';
  const running = attemptTimerRunning(attempt);
  const minutes = examDurationMinutes(exam || state.exams.find((item) => item.id === attempt.exam_id), state.blueprints);
  const limitMs = attempt.mode === 'exam' ? attemptLimitMs(minutes) : 0;
  const remaining = limitMs ? attemptRemainingMs(attempt, limitMs) : null;
  const display = remaining == null ? formatElapsed(attemptElapsedMs(attempt)) : formatElapsed(remaining);
  const title = remaining == null ? '作答用时' : '剩余时间';
  const hint = attempt.mode === 'practice' && minutes ? `<span class="item-sub">建议 ${minutes} 分钟</span>` : '';
  return `<span class="attempt-timer ${limitMs ? 'is-countdown' : ''}" data-attempt-timer data-elapsed-ms="${Number(attempt.elapsed_ms) || 0}" data-timing-started-at="${attempt.timing_started_at || ''}" data-running="${running ? '1' : '0'}" data-limit-ms="${limitMs || ''}" title="${title}">${display}</span>${hint}`;
}

function isOpenAttempt(item) {
  return item?.completion_status === 'in-progress' && (item.status === 'in-progress' || item.status === 'paused');
}

function renderStartActions(state, exam) {
  const openAttempt = (state.examAttempts || []).find(isOpenAttempt);
  if (!openAttempt) {
    return `
      <button type="button" class="btn btn-primary" data-action="start-attempt" data-id="${exam.id}" data-mode="practice">开始练习</button>
      <button type="button" class="btn btn-ghost" data-action="start-attempt" data-id="${exam.id}" data-mode="exam">开始考试</button>
    `;
  }
  return `
    <button type="button" class="btn btn-primary" data-action="open-attempt" data-id="${openAttempt.id}">继续作答</button>
    <button type="button" class="btn btn-ghost" data-action="start-another" data-id="${exam.id}">再做一份</button>
    ${
      state.startAnotherOpen
        ? `<button type="button" class="btn btn-ghost" data-action="start-attempt" data-id="${exam.id}" data-mode="practice">开始练习</button>
           <button type="button" class="btn btn-ghost" data-action="start-attempt" data-id="${exam.id}" data-mode="exam">开始考试</button>`
        : ''
    }
  `;
}

function renderAttemptList(state) {
  const items = (state.examAttempts || []).slice(0, 10);
  if (!items.length) return '';
  return `
    <div class="list">
      ${items
        .map((item) => {
          const mode = item.mode === 'exam' ? '考试' : '练习';
          const status = item.completion_status === 'completed' ? '已完成' : statusLabel('attempt', item.status);
          return `
        <button type="button" class="item" data-action="open-attempt" data-id="${item.id}">
          <div class="item-main">
            <div class="item-title">${mode} · ${item.answered_count}/${item.question_count}</div>
            <div class="item-sub">
              <span>${status}</span>
              <span>${formatTime(item.updated_at)}</span>
            </div>
          </div>
        </button>`;
        })
        .join('')}
    </div>
  `;
}

function attemptStatusPill(attempt) {
  if (attempt.completion_status === 'completed') {
    if (attempt.grading_status === 'completed') return '<span class="status status-ok">已批改</span>';
    if (attempt.grading_status === 'failed') return '<span class="status status-bad">批改失败</span>';
    if (attempt.grading_status === 'grading' || attempt.grading_status === 'queued') {
      return '<span class="status status-info">批改中</span>';
    }
    return '<span class="status status-ok">已完成</span>';
  }
  const kind = attempt.status === 'paused' ? 'status-warn' : 'status-info';
  return `<span class="status ${kind}">${statusLabel('attempt', attempt.status)}</span>`;
}

function attemptPrimary(attempt) {
  if (!attempt) return '';
  if (attempt.completion_status !== 'completed') {
    return `<button type="button" class="btn btn-primary btn-sm" data-action="complete-attempt" data-id="${attempt.id}">完成作答</button>`;
  }
  if (attempt.grading_status === 'completed') {
    return `<button type="button" class="btn btn-ghost btn-sm" data-action="continue-attempt" data-id="${attempt.id}">继续作答</button>`;
  }
  return `<button type="button" class="btn btn-primary btn-sm" data-action="grade-attempt" data-id="${attempt.id}" ${attempt.grading_status === 'grading' || attempt.grading_status === 'queued' ? 'disabled' : ''}>提交批改</button>`;
}

function renderBody(state, exam, attempt) {
  const exams = state.exams || [];
  if (!exams.length) {
    return `<div class="empty"><h3>还没有试卷</h3><button type="button" class="btn btn-primary" data-action="go-exam">去组卷</button></div>`;
  }
  if (!attempt) {
    return `
      <div class="resource-row">
        ${exams
          .map((item) =>
            renderMiniCard({
              active: item.id === state.activeExamId,
              renaming: state.renamingExamId === item.id,
              action: 'select-exam',
              id: item.id,
              title: item.document?.title || '试卷',
              sub: `${item.total_score} 分`,
              renameKind: 'exam',
            }),
          )
          .join('')}
      </div>
      ${
        exam
          ? `<div class="empty">
              <h3>${escapeHtml(exam.document?.title || '试卷')}</h3>
              <div class="pane-actions">
                ${renderStartActions(state, exam)}
              </div>
            </div>
            ${renderAttemptList(state)}`
          : `<div class="empty"><h3>选择一份试卷</h3></div>`
      }
    `;
  }

  const locked = attempt.completion_status === 'completed';
  const hideFeedback = attempt.mode === 'exam' && attempt.completion_status !== 'completed';
  const reviewed = Object.fromEntries((state.review?.items || []).map((item) => [item.question.id, item.question]));
  return `
    <form id="attempt-form">
      ${(attempt.paper?.questions || [])
        .map((question) => renderQuestion(question, attempt, locked, hideFeedback, reviewed[question.id]))
        .join('')}
    </form>
  `;
}

function renderQuestion(question, attempt, locked, hideFeedback, reviewedQuestion) {
  const saved = answerForQuestion(attempt, question.id);
  const feedback = hideFeedback ? null : feedbackForQuestion(attempt, question.id);
  return `
    <article class="q" data-question-id="${question.id}">
      <div class="q-head">
        <span>${question.ordinal}.</span>
        <span>${QUESTION_TYPES[question.type] || question.type}</span>
        <span>${question.score} 分</span>
      </div>
      ${renderBlocks(question.stem)}
      ${renderInput(question, saved, locked)}
      ${
        attempt.mode === 'practice' && !locked && SUBJECTIVE_TYPES.has(question.type)
          ? `<button type="button" class="btn btn-ghost btn-sm q-feedback-btn" data-action="ask-feedback" data-attempt-id="${attempt.id}" data-id="${question.id}">本题反馈</button>`
          : ''
      }
      ${reviewedQuestion ? renderSolution(reviewedQuestion, { showAnswer: true }) : ''}
      ${feedback ? renderReview(feedback, { showSuggestedScore: !!attempt.show_suggested_score }) : ''}
    </article>
  `;
}

function renderInput(question, saved, locked) {
  const answer = saved?.answer;
  if (question.type === 'single-choice' || question.type === 'multiple-choice') {
    const selected = new Set(answer?.option_ids || []);
    const type = question.type === 'single-choice' ? 'radio' : 'checkbox';
    return (question.options || [])
      .map(
        (opt) => `
        <label class="option">
          <input type="${type}" name="q-${question.id}" value="${escapeHtml(opt.id)}" ${selected.has(opt.id) ? 'checked' : ''} ${locked ? 'disabled' : ''} />
          <div>${renderBlocks(opt.content)}</div>
        </label>
      `,
      )
      .join('');
  }
  if (question.type === 'true-false') {
    const value = answer && answer.kind === 'true-false' ? String(answer.value) : '';
    return `
      <label class="option"><input type="radio" name="q-${question.id}" value="true" ${value === 'true' ? 'checked' : ''} ${locked ? 'disabled' : ''} /><span>对</span></label>
      <label class="option"><input type="radio" name="q-${question.id}" value="false" ${value === 'false' ? 'checked' : ''} ${locked ? 'disabled' : ''} /><span>错</span></label>
    `;
  }
  if (question.type === 'fill-blank') {
    const ids = blankIdsForQuestion(question);
    const blanks = answer?.blanks || [];
    return `<div class="fb">${ids.map((blankId, index) => {
      const current = blanks.find((item) => item.blank_id === blankId)?.value || blanks[index]?.value || '';
      return `<input class="input" name="q-${question.id}-b${index}" value="${escapeHtml(current)}" ${locked ? 'disabled' : ''} placeholder="空 ${index + 1}" />`;
    }).join('')}</div>`;
  }
  const lines = Math.max(3, question.answer_area?.lines || 6);
  return `<textarea class="textarea" name="q-${question.id}" rows="${lines}" ${locked ? 'disabled' : ''}>${escapeHtml(answer?.text || '')}</textarea>`;
}
