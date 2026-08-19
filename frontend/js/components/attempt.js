import { icons } from '../icons.js';
import {
  QUESTION_TYPES,
  answerForQuestion,
  buildAnswerPayload,
  countBlanks,
  escapeHtml,
  feedbackForQuestion,
  renderBlocks,
  statusLabel,
} from '../util.js';
import { bindChatPane, renderChatPane } from './chat.js';
import { renderReview, renderSolution } from './solution.js';

const SUBJECTIVE_TYPES = new Set(['short-answer', 'argumentation', 'extended-response']);

export function renderAttempt(state, root, handlers) {
  const collapsed = !!state.sidebarCollapsed.attempt;
  const exam = state.exams.find((item) => item.id === state.activeExamId) || null;
  const attempt = state.activeAttempt;

  root.innerHTML = `
    <div class="ws ws-task ${collapsed ? 'is-collapsed' : ''}" data-mobile="${state.mobilePane.attempt}" data-testid="attempt-workspace">
      <div class="mobile-switch">
        <button type="button" class="seg ${state.mobilePane.attempt === 'ai' ? 'is-active' : ''}" data-action="mobile-pane" data-pane="ai">AI</button>
        <button type="button" class="seg ${state.mobilePane.attempt === 'content' ? 'is-active' : ''}" data-action="mobile-pane" data-pane="content">内容</button>
      </div>
      <aside class="pane pane-ai">
        ${
          collapsed
            ? ''
            : renderChatPane(state, handlers, {
                variant: 'task',
                placeholder: '要解释哪一题？',
                emptyTitle: '开始新对话',
              })
        }
      </aside>
      <main class="pane pane-content">
        <div class="task">
          ${renderHeader(exam, attempt, collapsed)}
          <div class="task-body" id="task-scroll" data-select-root="attempt">
            ${renderBody(state, exam, attempt)}
          </div>
        </div>
      </main>
    </div>
  `;
  bindChatPane(root, handlers);
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

function renderHeader(exam, attempt, collapsed) {
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
        <div class="pane-title"><span>${escapeHtml(title)}</span></div>
        ${attempt ? `<span class="status ${attempt.status === 'submitted' ? 'status-ok' : 'status-info'}">${statusLabel('attempt', attempt.status)}</span>` : ''}
      </div>
      <div class="pane-actions">
        ${primary}
        ${
          attempt?.status === 'in-progress'
            ? `<button type="button" class="icon-btn" data-action="pause-attempt" data-id="${attempt.id}" title="暂停">${icons.pause(15)}</button>`
            : attempt?.status === 'paused'
              ? `<button type="button" class="icon-btn" data-action="resume-attempt" data-id="${attempt.id}" title="继续">${icons.play(15)}</button>`
              : ''
        }
      </div>
    </div>`;
}

function attemptPrimary(attempt) {
  if (!attempt) return '';
  if (attempt.completion_status !== 'completed') {
    return `<button type="button" class="btn btn-primary btn-sm" data-action="complete-attempt" data-id="${attempt.id}">完成作答</button>`;
  }
  if (attempt.grading_status === 'completed') {
    return `<button type="button" class="btn btn-ghost btn-sm" data-action="continue-attempt" data-id="${attempt.id}">继续作答</button>`;
  }
  return `
    <button type="button" class="btn btn-ghost btn-sm" data-action="continue-attempt" data-id="${attempt.id}">继续作答</button>
    <button type="button" class="btn btn-primary btn-sm" data-action="grade-attempt" data-id="${attempt.id}" ${attempt.grading_status === 'grading' || attempt.grading_status === 'queued' ? 'disabled' : ''}>提交批改</button>
  `;
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
        exam
          ? `<div class="empty">
              <h3>${escapeHtml(exam.document?.title || '试卷')}</h3>
              <div class="pane-actions">
                <button type="button" class="btn btn-primary" data-action="start-attempt" data-id="${exam.id}" data-mode="practice">开始练习</button>
                <button type="button" class="btn btn-ghost" data-action="start-attempt" data-id="${exam.id}" data-mode="exam">开始考试</button>
              </div>
            </div>`
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
          ? `<button type="button" class="btn btn-ghost btn-sm" style="margin-top:8px" data-action="ask-feedback" data-attempt-id="${attempt.id}" data-id="${question.id}">本题反馈</button>`
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
    const count = countBlanks(question);
    const blanks = answer?.blanks || [];
    return `<div class="fb">${Array.from({ length: count }, (_, index) => {
      const current = blanks[index]?.value || '';
      return `<input class="input" name="q-${question.id}-b${index}" value="${escapeHtml(current)}" ${locked ? 'disabled' : ''} placeholder="空 ${index + 1}" />`;
    }).join('')}</div>`;
  }
  const lines = Math.max(3, question.answer_area?.lines || 6);
  return `<textarea class="textarea" name="q-${question.id}" rows="${lines}" ${locked ? 'disabled' : ''}>${escapeHtml(answer?.text || '')}</textarea>`;
}

