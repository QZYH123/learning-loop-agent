/**
 * Practice & Exam Workspace Component
 * Strictly aligned with Tickets 10, 11, 21:
 * - Left Pane: Collapsible exams list & past attempts history
 * - Right Pane: Exam launcher, interactive worksheet (Attempt.paper with 7 question types, auto-save),
 *   instant practice feedback, decoupled Complete & Grade actions, Continue answering unlocking,
 *   and full review scorecard.
 */

import { icons } from '../icons.js';

export function renderPracticeExamView(state, container, handlers) {
  const {
    exams = [],
    activeExamId,
    activeAttempt,
    activeAttemptReview,
    attempts = [],
    sidebarCollapsed = {}
  } = state;

  const isCollapsed = !!sidebarCollapsed.practice_exam;
  const activeExam = exams.find((e) => e.id === activeExamId) || exams[0] || null;

  container.innerHTML = `
    <div class="learning-workspace-layout ${isCollapsed ? 'is-sidebar-collapsed' : ''}" data-testid="practice-exam-workspace">
      <!-- Left Sidebar: Exams & Attempts History -->
      <aside class="workspace-sidebar" id="practice-exam-sidebar">
        <div class="sidebar-header-row">
          <div class="sidebar-title-block">
            ${icons.target(15)}
            <span class="sidebar-title-text">作答中心</span>
          </div>
          <div class="sidebar-actions-block">
            <button
              type="button"
              class="btn-icon-sidebar"
              id="btn-toggle-practice-sidebar"
              title="${isCollapsed ? '展开侧栏' : '收起侧栏'}"
            >
              ${isCollapsed ? icons.panelLeftOpen(15) : icons.panelLeftClose(15)}
            </button>
          </div>
        </div>

        <div class="sidebar-scrollable-list" id="practice-items-scroll">
          <div class="dropdown-section-title">可作答试卷 (${exams.length})</div>
          ${
            exams.length === 0
              ? `<div class="sidebar-empty-state"><div class="sidebar-empty-text">暂无已发布试卷</div></div>`
              : exams
                  .map((ex) => {
                    const isSelected = ex.id === activeExamId && !activeAttempt && !activeAttemptReview;
                    return `
              <div
                class="standard-card-item ${isSelected ? 'is-selected' : ''}"
                data-action="select-exam-for-practice"
                data-exam-id="${ex.id}"
                role="button"
                tabindex="0"
              >
                <div class="source-card-header">
                  <div class="source-title-row">
                    ${icons.target(14)}
                    <span class="source-card-title" title="${escapeHtml(ex.title || '试卷')}">${escapeHtml(ex.title || '试卷')}</span>
                  </div>
                  <span class="grounding-tag-chip grounding-covered">${ex.total_score || 100} 分</span>
                </div>
                <div class="source-card-meta">
                  <span>${ex.questions?.length || 0} 道题</span>
                  <span>${formatTimestamp(ex.created_at)}</span>
                </div>
              </div>
            `;
                  })
                  .join('')
          }

          ${
            attempts.length > 0
              ? `
            <div class="dropdown-divider" style="margin: 12px 0;"></div>
            <div class="dropdown-section-title">作答历史记录 (${attempts.length})</div>
            ${attempts
              .map((att) => {
                const isSelected = activeAttempt?.id === att.id;
                const isCompleted = att.status === 'completed' || att.is_completed;
                const isGraded = att.grading_status === 'graded';
                return `
                <div
                  class="standard-card-item ${isSelected ? 'is-selected' : ''}"
                  data-action="select-attempt-history"
                  data-attempt-id="${att.id}"
                  role="button"
                  tabindex="0"
                >
                  <div class="source-card-header">
                    <div class="source-title-row">
                      ${att.mode === 'practice' ? icons.bookOpen(14) : icons.shield(14)}
                      <span class="source-card-title">${att.mode === 'practice' ? '练习作答' : '正式考试'}</span>
                    </div>
                    <span class="grounding-tag-chip ${isGraded ? 'grounding-covered' : isCompleted ? 'grounding-supplemental' : ''}">
                      ${isGraded ? '已批改' : isCompleted ? '已完成' : '作答中'}
                    </span>
                  </div>
                  <div class="source-card-meta">
                    <span>${formatTimestamp(att.created_at)}</span>
                    ${att.score !== undefined && att.score !== null ? `<span>得分: <strong>${att.score}</strong></span>` : ''}
                  </div>
                </div>
              `;
              })
              .join('')}
          `
              : ''
          }
        </div>
      </aside>

      <!-- Main Worksheet / Launcher / Review Area -->
      <main class="workspace-main-content" id="practice-exam-main">
        ${
          isCollapsed
            ? `
          <button
            type="button"
            class="btn-sidebar-floating-expand"
            id="btn-floating-expand-practice"
            title="展开作答侧栏"
          >
            ${icons.panelLeftOpen(15)}
            <span>试卷与作答记录</span>
          </button>
        `
            : ''
        }

        ${
          activeAttemptReview
            ? renderAttemptReview(activeAttemptReview, state, handlers)
            : activeAttempt
            ? renderAttemptSheet(activeAttempt, activeExam, state, handlers)
            : renderExamLauncher(activeExam, state, handlers)
        }
      </main>
    </div>
  `;

  // Attach Event Handlers
  attachPracticeEvents(container, state, handlers);
}

function renderExamLauncher(exam, state, handlers) {
  if (!exam) {
    return `
      <div class="detail-empty-container">
        <div class="empty-state-icon-circle">${icons.target(24)}</div>
        <div class="empty-state-title">未选择试卷</div>
        <div class="empty-state-desc">请在左侧列表中选择一套试卷开始练习或正式考试。</div>
      </div>
    `;
  }

  const questions = exam.questions || [];

  return `
    <div class="practice-launcher-container" data-testid="exam-launcher">
      <div class="launcher-hero-card">
        <div class="launcher-header-row">
          <div class="launcher-title-block">
            <span class="launcher-badge">正式试卷</span>
            <h1 class="launcher-title">${escapeHtml(exam.title || '试卷作答')}</h1>
            <div class="launcher-meta-row">
              <span>共 ${questions.length} 道试题</span>
              <span>满分 ${exam.total_score || 100} 分</span>
              <span>创建于 ${formatTimestamp(exam.created_at)}</span>
            </div>
          </div>

          <button
            type="button"
            class="btn-secondary btn-sm"
            id="btn-preview-render-doc"
            data-exam-id="${exam.id}"
            title="查看统一试卷排版与导出"
          >
            ${icons.printer(14)} 排版与导出...
          </button>
        </div>

        <div class="launcher-modes-grid">
          <!-- Practice Mode Card -->
          <div class="launcher-mode-card">
            <div class="mode-card-icon-circle mode-practice">${icons.bookOpen(22)}</div>
            <div class="mode-card-title">练习模式 (Practice)</div>
            <div class="mode-card-desc">
              在作答过程中可实时获取单题 AI 批改、得分点与改进建议，答案与解析按需可见。
            </div>
            <div class="mode-card-option-row">
              <label class="checkbox-control-label">
                <input type="checkbox" id="check-practice-suggested-score" />
                <span>同时输出参考建议分数</span>
              </label>
            </div>
            <button
              type="button"
              class="btn-primary btn-block"
              id="btn-start-practice-mode"
              data-exam-id="${exam.id}"
            >
              ${icons.play(14)} 开启练习作答
            </button>
          </div>

          <!-- Exam Mode Card -->
          <div class="launcher-mode-card">
            <div class="mode-card-icon-circle mode-exam">${icons.shield(22)}</div>
            <div class="mode-card-title">正式考试模式 (Exam)</div>
            <div class="mode-card-desc">
              全程严格防作弊与防泄漏。作答完成前答案、解析与反馈完全隐藏，提交后统一批改。
            </div>
            <div class="mode-card-option-row">
              <label class="checkbox-control-label">
                <input type="checkbox" id="check-exam-suggested-score" checked />
                <span>完成批改后显示全卷建议分数</span>
              </label>
            </div>
            <button
              type="button"
              class="btn-primary btn-block"
              id="btn-start-exam-mode"
              data-exam-id="${exam.id}"
            >
              ${icons.shield(14)} 开启正式考试
            </button>
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderAttemptSheet(attempt, exam, state, handlers) {
  const paper = attempt.paper || exam || {};
  const questions = paper.questions || [];
  const isCompleted = attempt.status === 'completed' || attempt.is_completed;
  const isPractice = attempt.mode === 'practice';
  const elapsed = attempt.elapsed_seconds || 0;

  return `
    <div class="attempt-worksheet-container" data-testid="attempt-worksheet">
      <!-- Worksheet Top Action Bar -->
      <header class="worksheet-header-bar">
        <div class="worksheet-header-left">
          <span class="worksheet-mode-chip ${isPractice ? 'mode-practice' : 'mode-exam'}">
            ${isPractice ? icons.bookOpen(13) : icons.shield(13)}
            <span>${isPractice ? '练习模式' : '正式考试'}</span>
          </span>
          <h2 class="worksheet-title" title="${escapeHtml(paper.title || '试卷')}">${escapeHtml(paper.title || '试卷')}</h2>
          <span class="worksheet-status-tag ${isCompleted ? 'grounding-covered' : ''}">
            ${isCompleted ? '已标记完成作答 (只读)' : '作答中'}
          </span>
        </div>

        <div class="worksheet-header-right">
          <!-- Timer & Pause / Resume -->
          <div class="attempt-timer-chip">
            ${icons.clock(14)}
            <span id="attempt-timer-display">${formatTimer(elapsed)}</span>
            ${
              attempt.status === 'paused'
                ? `
              <button type="button" class="btn-icon-subtle" id="btn-resume-attempt" data-attempt-id="${attempt.id}" title="恢复作答">
                ${icons.play(13)}
              </button>
            `
                : !isCompleted
                ? `
              <button type="button" class="btn-icon-subtle" id="btn-pause-attempt" data-attempt-id="${attempt.id}" title="暂停作答">
                ${icons.pause(13)}
              </button>
            `
                : ''
            }
          </div>

          <!-- Ticket 21: Decoupled Complete & Grade Actions -->
          ${
            !isCompleted
              ? `
            <button
              type="button"
              class="btn-primary btn-sm"
              id="btn-complete-attempt"
              data-attempt-id="${attempt.id}"
              title="标记已完成答题，锁定答案进入待批改状态"
            >
              ${icons.check(13)} 完成作答
            </button>
          `
              : `
            <button
              type="button"
              class="btn-secondary btn-sm"
              id="btn-continue-attempt"
              data-attempt-id="${attempt.id}"
              title="撤销完成标记，继续修改作答答案"
            >
              ${icons.edit3(13)} 继续作答 (解锁)
            </button>

            <button
              type="button"
              class="btn-primary btn-sm"
              id="btn-submit-grading"
              data-attempt-id="${attempt.id}"
              title="提交全卷 AI 批改与反馈生成"
            >
              ${icons.sparkles(13)} 提交批改...
            </button>
          `
          }

          <button
            type="button"
            class="btn-secondary btn-sm"
            id="btn-exit-attempt"
            title="退出当前作答"
          >
            ${icons.x(13)}
          </button>
        </div>
      </header>

      <!-- Questions List Stream (7 Question Types) -->
      <div class="worksheet-questions-scroll">
        ${questions
          .map((q, idx) => {
            const userAnswer = state.getAttemptAnswer(attempt, q.id);
            const feedback = state.getAttemptFeedback(attempt, q.id);

            return `
            <div class="worksheet-question-card" id="q-card-${q.id}">
              <div class="worksheet-q-header">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span class="slot-num-badge">${idx + 1}</span>
                  <span class="slot-type-badge">${formatQuestionType(q.type)}</span>
                  <span class="slot-points-badge">${q.points || 2} 分</span>
                </div>

                ${
                  isPractice && !isCompleted
                    ? `
                  <button
                    type="button"
                    class="btn-secondary btn-sm"
                    data-action="request-single-feedback"
                    data-attempt-id="${attempt.id}"
                    data-question-id="${q.id}"
                    title="获取本题 AI 即时评分与改进反馈"
                  >
                    ${icons.sparkles(12)} 获取本题即时反馈
                  </button>
                `
                    : ''
                }
              </div>

              <div class="worksheet-q-prompt">${escapeHtml(q.prompt || '')}</div>

              <!-- Answering Input Control -->
              <div class="worksheet-q-input-area">
                ${renderQuestionInputControl(q, userAnswer, isCompleted, attempt.id)}
              </div>

              <!-- Practice Mode Instant Feedback Display (Ticket 11) -->
              ${
                feedback
                  ? `
                <div class="single-q-feedback-card">
                  <div class="feedback-card-header">
                    <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; color: #1e40af;">
                      ${icons.sparkles(14)}
                      <span>AI 即时作答反馈</span>
                    </div>
                    ${feedback.suggested_score !== undefined && feedback.suggested_score !== null ? `<span class="feedback-score-chip">建议得分: ${feedback.suggested_score} / ${q.points || 2} 分</span>` : ''}
                  </div>
                  ${
                    feedback.key_points?.length
                      ? `<div class="feedback-point-item"><strong>得分要点:</strong> ${escapeHtml(feedback.key_points.join('; '))}</div>`
                      : ''
                  }
                  ${
                    feedback.missing_points?.length
                      ? `<div class="feedback-point-item missing"><strong>遗漏薄弱点:</strong> ${escapeHtml(feedback.missing_points.join('; '))}</div>`
                      : ''
                  }
                  ${
                    feedback.improvement_advice
                      ? `<div class="feedback-point-item advice"><strong>改进建议:</strong> ${escapeHtml(feedback.improvement_advice)}</div>`
                      : ''
                  }
                </div>
              `
                  : ''
              }
            </div>
          `;
          })
          .join('')}
      </div>
    </div>
  `;
}

function renderQuestionInputControl(q, userAnswer, isReadOnly, attemptId) {
  const type = String(q.type || '').toLowerCase();

  // 1. Single Choice
  if (type === 'single-choice' || type === 'single_choice') {
    const options = q.options || [];
    return `
      <div class="question-options-group">
        ${options
          .map((opt, idx) => {
            const letter = String.fromCharCode(65 + idx);
            const isChecked = userAnswer === letter || userAnswer === opt.text;
            return `
            <label class="radio-option-item ${isChecked ? 'is-checked' : ''}">
              <input
                type="radio"
                name="q_${q.id}"
                value="${letter}"
                ${isChecked ? 'checked' : ''}
                ${isReadOnly ? 'disabled' : ''}
                data-action="save-answer"
                data-attempt-id="${attemptId}"
                data-question-id="${q.id}"
              />
              <span class="option-letter-badge">${letter}</span>
              <span class="option-label-text">${escapeHtml(typeof opt === 'string' ? opt : opt.text || opt.content || '')}</span>
            </label>
          `;
          })
          .join('')}
      </div>
    `;
  }

  // 2. Multi Choice
  if (type === 'multi-choice' || type === 'multiple_choice') {
    const options = q.options || [];
    const selectedLetters = Array.isArray(userAnswer) ? userAnswer : (userAnswer || '').split('');
    return `
      <div class="question-options-group">
        ${options
          .map((opt, idx) => {
            const letter = String.fromCharCode(65 + idx);
            const isChecked = selectedLetters.includes(letter);
            return `
            <label class="checkbox-option-item ${isChecked ? 'is-checked' : ''}">
              <input
                type="checkbox"
                name="q_${q.id}"
                value="${letter}"
                ${isChecked ? 'checked' : ''}
                ${isReadOnly ? 'disabled' : ''}
                data-action="save-multi-answer"
                data-attempt-id="${attemptId}"
                data-question-id="${q.id}"
              />
              <span class="option-letter-badge">${letter}</span>
              <span class="option-label-text">${escapeHtml(typeof opt === 'string' ? opt : opt.text || opt.content || '')}</span>
            </label>
          `;
          })
          .join('')}
      </div>
    `;
  }

  // 3. True / False
  if (type === 'true-false' || type === 'true_false') {
    const isTrue = userAnswer === 'true' || userAnswer === true || userAnswer === '正确';
    const isFalse = userAnswer === 'false' || userAnswer === false || userAnswer === '错误';

    return `
      <div class="question-tf-group">
        <label class="tf-option-item ${isTrue ? 'is-checked' : ''}">
          <input
            type="radio"
            name="q_${q.id}"
            value="true"
            ${isTrue ? 'checked' : ''}
            ${isReadOnly ? 'disabled' : ''}
            data-action="save-answer"
            data-attempt-id="${attemptId}"
            data-question-id="${q.id}"
          />
          <span>${icons.check(14)} 正确</span>
        </label>
        <label class="tf-option-item ${isFalse ? 'is-checked' : ''}">
          <input
            type="radio"
            name="q_${q.id}"
            value="false"
            ${isFalse ? 'checked' : ''}
            ${isReadOnly ? 'disabled' : ''}
            data-action="save-answer"
            data-attempt-id="${attemptId}"
            data-question-id="${q.id}"
          />
          <span>${icons.x(14)} 错误</span>
        </label>
      </div>
    `;
  }

  // 4. Fill in the blank
  if (type === 'fill-in' || type === 'fill_in') {
    return `
      <div class="question-fillin-control">
        <input
          type="text"
          class="form-input-control"
          placeholder="在此输入填空答案..."
          value="${escapeHtml(userAnswer || '')}"
          ${isReadOnly ? 'readonly' : ''}
          data-action="save-text-answer"
          data-attempt-id="${attemptId}"
          data-question-id="${q.id}"
        />
      </div>
    `;
  }

  // 5. Short Answer, Analysis, Essay
  return `
    <div class="question-textarea-control">
      <textarea
        class="form-textarea-control"
        rows="3"
        placeholder="在此详细书写你的推演步骤、论述与解答..."
        ${isReadOnly ? 'readonly' : ''}
        data-action="save-text-answer"
        data-attempt-id="${attemptId}"
        data-question-id="${q.id}"
      >${escapeHtml(userAnswer || '')}</textarea>
    </div>
  `;
}

function renderAttemptReview(review, state, handlers) {
  const { attempt = {}, score, total_score = 100, results = [] } = review;

  return `
    <div class="attempt-review-container" data-testid="attempt-review-scorecard">
      <header class="review-scorecard-hero">
        <div class="scorecard-hero-left">
          <div class="scorecard-title-row">
            ${icons.target(20)}
            <h1 class="scorecard-title">作答批改成绩报告</h1>
          </div>
          <div class="scorecard-meta-row">
            <span>作答模式: ${attempt.mode === 'practice' ? '练习模式' : '正式考试'}</span>
            <span>耗时: ${formatTimer(attempt.elapsed_seconds || 0)}</span>
          </div>
        </div>

        <div class="scorecard-hero-right">
          <div class="score-display-box">
            <span class="score-num">${score !== undefined && score !== null ? score : '--'}</span>
            <span class="score-total">/ ${total_score} 分</span>
          </div>
        </div>
      </header>

      <div class="review-questions-scroll">
        ${results
          .map(
            (res, idx) => `
          <div class="review-question-card ${res.is_correct ? 'is-correct' : 'is-wrong'}">
            <div class="worksheet-q-header">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span class="slot-num-badge">${idx + 1}</span>
                <span class="slot-type-badge">${formatQuestionType(res.type)}</span>
                <span class="slot-points-badge">得分: ${res.score !== undefined ? res.score : '--'} / ${res.points || 2} 分</span>
              </div>
              <span class="grounding-tag-chip ${res.is_correct ? 'grounding-covered' : 'grounding-not-covered'}">
                ${res.is_correct ? '回答正确' : '存在失分 / 需改进'}
              </span>
            </div>

            <div class="worksheet-q-prompt">${escapeHtml(res.prompt || '')}</div>

            <div class="review-comparison-block">
              <div class="comparison-row">
                <span class="comparison-label">我的作答:</span>
                <span class="comparison-val user-val">${escapeHtml(res.user_answer || '（未作答）')}</span>
              </div>
              <div class="comparison-row">
                <span class="comparison-label">标准答案:</span>
                <span class="comparison-val standard-val">${escapeHtml(res.standard_answer || res.answer || '')}</span>
              </div>
            </div>

            ${
              res.explanation
                ? `
              <div class="review-explanation-card">
                <strong>详细考点解析:</strong>
                <div>${escapeHtml(res.explanation)}</div>
              </div>
            `
                : ''
            }
          </div>
        `
          )
          .join('')}
      </div>
    </div>
  `;
}

function attachPracticeEvents(container, state, handlers) {
  // Sidebar Collapse Toggle
  const toggleBtn = container.querySelector('#btn-toggle-practice-sidebar');
  if (toggleBtn) toggleBtn.onclick = () => handlers.onToggleSidebar?.('practice_exam');

  const floatingBtn = container.querySelector('#btn-floating-expand-practice');
  if (floatingBtn) floatingBtn.onclick = () => handlers.onToggleSidebar?.('practice_exam');

  // Select Exam for Practice
  container.querySelectorAll('[data-action="select-exam-for-practice"]').forEach((card) => {
    card.onclick = () => {
      const id = card.getAttribute('data-exam-id');
      handlers.onSelectExamForPractice?.(id);
    };
  });

  // Select Past Attempt History
  container.querySelectorAll('[data-action="select-attempt-history"]').forEach((card) => {
    card.onclick = () => {
      const id = card.getAttribute('data-attempt-id');
      handlers.onSelectAttemptHistory?.(id);
    };
  });

  // Start Practice Mode Button
  const startPracticeBtn = container.querySelector('#btn-start-practice-mode');
  if (startPracticeBtn) {
    startPracticeBtn.onclick = () => {
      const examId = startPracticeBtn.getAttribute('data-exam-id');
      const showScore = container.querySelector('#check-practice-suggested-score')?.checked || false;
      handlers.onStartAttempt?.(examId, 'practice', showScore);
    };
  }

  // Start Exam Mode Button
  const startExamBtn = container.querySelector('#btn-start-exam-mode');
  if (startExamBtn) {
    startExamBtn.onclick = () => {
      const examId = startExamBtn.getAttribute('data-exam-id');
      const showScore = container.querySelector('#check-exam-suggested-score')?.checked || true;
      handlers.onStartAttempt?.(examId, 'exam', showScore);
    };
  }

  // Preview Render Doc Button
  const previewDocBtn = container.querySelector('#btn-preview-render-doc');
  if (previewDocBtn) {
    previewDocBtn.onclick = () => {
      const examId = previewDocBtn.getAttribute('data-exam-id');
      handlers.onSelectExamStudioSubTab?.('preview_export');
    };
  }

  // Save Radio / TF Answer on Change
  container.querySelectorAll('input[data-action="save-answer"]').forEach((input) => {
    input.onchange = () => {
      const attemptId = input.getAttribute('data-attempt-id');
      const questionId = input.getAttribute('data-question-id');
      handlers.onSaveAttemptAnswer?.(attemptId, questionId, input.value);
    };
  });

  // Save Multi-Choice Checkboxes
  container.querySelectorAll('input[data-action="save-multi-answer"]').forEach((input) => {
    input.onchange = () => {
      const attemptId = input.getAttribute('data-attempt-id');
      const questionId = input.getAttribute('data-question-id');
      const parentCard = input.closest('.worksheet-question-card');
      const checkedVals = Array.from(parentCard.querySelectorAll(`input[name="q_${questionId}"]:checked`)).map(
        (el) => el.value
      );
      handlers.onSaveAttemptAnswer?.(attemptId, questionId, checkedVals.sort().join(''));
    };
  });

  // Save Text / Textarea Answer on Blur / Input
  container.querySelectorAll('[data-action="save-text-answer"]').forEach((el) => {
    el.onchange = () => {
      const attemptId = el.getAttribute('data-attempt-id');
      const questionId = el.getAttribute('data-question-id');
      handlers.onSaveAttemptAnswer?.(attemptId, questionId, el.value);
    };
  });

  // Request Single Question Feedback (Practice Mode)
  container.querySelectorAll('[data-action="request-single-feedback"]').forEach((btn) => {
    btn.onclick = () => {
      const attemptId = btn.getAttribute('data-attempt-id');
      const questionId = btn.getAttribute('data-question-id');
      handlers.onRequestQuestionFeedback?.(attemptId, questionId);
    };
  });

  // Pause / Resume Attempt
  const pauseBtn = container.querySelector('#btn-pause-attempt');
  if (pauseBtn) {
    pauseBtn.onclick = () => {
      const aId = pauseBtn.getAttribute('data-attempt-id');
      handlers.onPauseAttempt?.(aId);
    };
  }

  const resumeBtn = container.querySelector('#btn-resume-attempt');
  if (resumeBtn) {
    resumeBtn.onclick = () => {
      const aId = resumeBtn.getAttribute('data-attempt-id');
      handlers.onResumeAttempt?.(aId);
    };
  }

  // Complete Attempt (Ticket 21)
  const completeBtn = container.querySelector('#btn-complete-attempt');
  if (completeBtn) {
    completeBtn.onclick = () => {
      const aId = completeBtn.getAttribute('data-attempt-id');
      if (confirm('确认标记已完成作答吗？（完成后题目将进入只读状态，可随后提交批改或解锁继续作答）')) {
        handlers.onCompleteAttempt?.(aId);
      }
    };
  }

  // Continue Attempt (Unlock) (Ticket 21)
  const continueBtn = container.querySelector('#btn-continue-attempt');
  if (continueBtn) {
    continueBtn.onclick = () => {
      const aId = continueBtn.getAttribute('data-attempt-id');
      handlers.onContinueAttempt?.(aId);
    };
  }

  // Submit Grading (Ticket 21)
  const gradeBtn = container.querySelector('#btn-submit-grading');
  if (gradeBtn) {
    gradeBtn.onclick = () => {
      const aId = gradeBtn.getAttribute('data-attempt-id');
      handlers.onSubmitAttemptGrading?.(aId);
    };
  }

  // Exit Attempt
  const exitBtn = container.querySelector('#btn-exit-attempt');
  if (exitBtn) {
    exitBtn.onclick = () => {
      handlers.onExitAttempt?.();
    };
  }
}

function formatQuestionType(type) {
  const t = String(type || '').toLowerCase();
  if (t === 'single-choice' || t === 'single_choice') return '单选题';
  if (t === 'multi-choice' || t === 'multiple_choice') return '多选题';
  if (t === 'true-false' || t === 'true_false') return '判断题';
  if (t === 'fill-in' || t === 'fill_in') return '填空题';
  if (t === 'short-answer' || t === 'short_answer') return '简答题';
  if (t === 'analysis') return '辨析题';
  if (t === 'essay') return '大题/综合推导';
  return '试题';
}

function formatTimer(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
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
