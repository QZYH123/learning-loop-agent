/**
 * Right Content Panel for 「作答」 (Attempts / Practice & Exam) Workspace
 * Strictly aligned with Issue 10, 11, 21, ADR 0003:
 * - Interactive exam paper (single-choice, multiple-choice, true-false, fill-in, essay)
 * - Practice vs Exam mode toggle
 * - Floating "问 AI" button on text selection
 * - Practice mode instant explanation & scoring points
 * - Independent actions: 完成作答 (locks answers) & 提交批改 (submits for grading) & 继续作答 (unlocks answers)
 * - Expired feedback warning when graded answers are modified
 * - Full review scorecard
 */

import { icons } from '../icons.js';

export function renderAttemptsView(state, container, handlers) {
  const {
    exams = [],
    activeExamId,
    activeExam,
    activeAttempt,
    activeAttemptReview,
    attempts = [],
    sidebarCollapsed = {}
  } = state;

  const isRightCollapsed = !!sidebarCollapsed.right;

  container.innerHTML = `
    <div class="workspace-right-pane ${isRightCollapsed ? 'is-collapsed' : ''}" data-testid="attempts-workspace-right">
      <!-- Right Content Header -->
      <div class="workspace-right-header">
        <div class="header-object-info">
          <span class="object-icon">${icons.target(16)}</span>
          <h3 class="object-title" title="${escapeHtml(activeExam?.document?.title || activeExam?.title || '试卷作答')}">
            ${escapeHtml(activeExam?.document?.title || activeExam?.title || '试卷作答')}
          </h3>
          ${
            activeAttempt
              ? `
            <span class="status-pill status-pill-${activeAttempt.is_completed ? 'completed' : 'in-progress'}">
              ${activeAttempt.is_completed ? '已完成' : '作答中'}
            </span>
          `
              : ''
          }
        </div>

        <div class="header-actions">
          ${renderAttemptHeaderActions(state)}
        </div>
      </div>

      <!-- Right Content Body -->
      <div class="workspace-right-body" id="attempt-worksheet-body">
        ${renderAttemptBody(state)}
      </div>

      <!-- Floating "问 AI" Tooltip on Text Selection -->
      <div class="floating-ask-ai-bubble" id="floating-ask-ai-btn" style="display: none;">
        ${icons.messageSquare(13)} 问 AI
      </div>

      <!-- Drawer for Picking Exams & Past Attempts -->
      <div class="workspace-drawer-backdrop" id="attempts-drawer-backdrop" style="display: none;">
        <div class="workspace-drawer-panel" role="dialog" aria-modal="true" aria-label="试卷与答卷列表">
          <div class="drawer-header">
            <h4 class="drawer-title">${icons.target(16)} 试卷与答卷列表</h4>
            <button type="button" class="btn-icon-subtle" id="btn-close-attempts-drawer" title="关闭">${icons.x(14)}</button>
          </div>

          <div class="drawer-body">
            <!-- Published Exams List -->
            <div class="drawer-section">
              <div class="drawer-section-header">
                <span class="section-title">可作答试卷 (${exams.length})</span>
              </div>
              <div class="drawer-items-list">
                ${
                  exams.length === 0
                    ? `<div class="drawer-empty-hint">暂无已发试卷，请先去组卷</div>`
                    : exams
                        .map(
                          (e) => `
                      <div
                        class="drawer-item ${activeExam?.id === e.id ? 'is-selected' : ''}"
                        data-type="exam"
                        data-id="${e.id}"
                        role="button"
                        tabindex="0"
                      >
                        <span class="item-icon">${icons.target(14)}</span>
                        <div class="item-info">
                          <span class="item-name">${escapeHtml(e.document?.title || e.title || '期末自测卷')}</span>
                          <span class="item-meta">${(e.document?.questions || []).length} 题 · ${e.document?.duration_minutes || 60} 分钟</span>
                        </div>
                      </div>
                    `
                        )
                        .join('')
                }
              </div>
            </div>

            <!-- Past Attempts List -->
            <div class="drawer-section">
              <div class="drawer-section-header">
                <span class="section-title">历史作答记录 (${attempts.length})</span>
              </div>
              <div class="drawer-items-list">
                ${
                  attempts.length === 0
                    ? `<div class="drawer-empty-hint">暂无历史作答记录</div>`
                    : attempts
                        .map(
                          (att) => `
                      <div
                        class="drawer-item ${activeAttempt?.id === att.id ? 'is-selected' : ''}"
                        data-type="attempt"
                        data-id="${att.id}"
                        role="button"
                        tabindex="0"
                      >
                        <span class="item-icon">${icons.fileText(14)}</span>
                        <div class="item-info">
                          <span class="item-name">${att.mode === 'practice' ? '练习答卷' : '考试答卷'}</span>
                          <span class="item-meta">${att.is_completed ? '已完成' : '作答中'} · ${formatElapsed(att.elapsed_seconds)}</span>
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
  attachAttemptsEvents(container, state, handlers);
}

function renderAttemptHeaderActions(state) {
  const { activeExam, activeAttempt, activeAttemptReview } = state;

  if (!activeAttempt) {
    if (!activeExam) {
      return `
        <button type="button" class="btn-primary-action" id="btn-goto-quiz-gen" title="前往组卷">
          ${icons.compass(14)} 去组卷
        </button>
      `;
    }

    return `
      <button type="button" class="btn-primary-action" id="btn-start-practice-mode" title="开启练习模式 (可随时查看解析)">
        ${icons.play(14)} 练习模式
      </button>
      <button type="button" class="btn-outline-action" id="btn-start-exam-mode" title="开启正式考试模式 (提交前隐藏答案)">
        ${icons.clock(14)} 考试模式
      </button>
      <button type="button" class="btn-icon-action" id="btn-open-attempts-drawer" title="选择试卷">
        ${icons.list(14)}
      </button>
    `;
  }

  const isCompleted = activeAttempt.is_completed || activeAttempt.status === 'completed';

  return `
    ${
      !isCompleted
        ? `
      <button type="button" class="btn-primary-action" id="btn-complete-attempt-action" title="标记完成作答 (锁定答案为只读)">
        ${icons.check(14)} 完成作答
      </button>
    `
        : `
      <button type="button" class="btn-outline-action" id="btn-continue-attempt-action" title="解锁答卷，继续修改答案">
        ${icons.edit(14)} 继续作答
      </button>
    `
    }

    <button
      type="button"
      class="btn-primary-action btn-grading-action"
      id="btn-submit-grading-action"
      title="提交全卷智能批改与薄弱点分析"
    >
      ${icons.checkCircle(14)} 提交批改
    </button>

    <button type="button" class="btn-icon-action" id="btn-open-attempts-drawer" title="切换试卷/记录">
      ${icons.list(14)}
    </button>
  `;
}

function renderAttemptBody(state) {
  const { activeExam, activeAttempt, activeAttemptReview, exams = [] } = state;

  if (!activeAttempt) {
    if (!activeExam && exams.length === 0) {
      return `
        <div class="workspace-empty-state">
          <div class="empty-icon">${icons.target(28)}</div>
          <h4 class="empty-title">还没有可作答的试卷</h4>
          <p class="empty-subtitle">请先在「组卷」工作区通过自然语言生成一套试卷。</p>
          <div class="empty-actions-row">
            <button type="button" class="btn-primary-glow" id="btn-empty-goto-quiz-gen">
              ${icons.compass(14)} 去组卷
            </button>
          </div>
        </div>
      `;
    }

    const currentExam = activeExam || exams[0];
    const doc = currentExam?.document || currentExam;
    const questions = doc?.questions || [];

    return `
      <div class="attempt-launcher-container">
        <div class="launcher-hero-card">
          <div class="launcher-icon-wrap">${icons.target(28)}</div>
          <h3 class="launcher-title">${escapeHtml(doc?.title || currentExam?.title || '试卷自测')}</h3>
          <p class="launcher-desc">满分 ${doc?.total_score || 100} 分 · 共 ${questions.length} 题 · 建议时长 ${doc?.duration_minutes || 60} 分钟</p>
          <div class="launcher-modes-row">
            <button type="button" class="btn-mode-card" id="btn-hero-start-practice" data-exam-id="${currentExam?.id}">
              <span class="mode-card-icon">${icons.sparkles(20)}</span>
              <span class="mode-card-title">练习模式</span>
              <span class="mode-card-desc">答题时可随时查看单题 AI 解析与要点提示</span>
            </button>
            <button type="button" class="btn-mode-card" id="btn-hero-start-exam" data-exam-id="${currentExam?.id}">
              <span class="mode-card-icon">${icons.clock(20)}</span>
              <span class="mode-card-title">考试模式</span>
              <span class="mode-card-desc">计时作答，提交批改前严格隐藏参考答案</span>
            </button>
          </div>
        </div>
      </div>
    `;
  }

  // Active Worksheet
  const doc = activeAttempt.paper || activeExam?.document || activeExam || {};
  const questions = doc.questions || [];
  const isCompleted = activeAttempt.is_completed || activeAttempt.status === 'completed';
  const isPractice = activeAttempt.mode === 'practice';
  const answers = activeAttempt.answers || [];
  const feedbacks = activeAttempt.feedback || [];

  return `
    <div class="attempt-worksheet-container">
      <!-- Attempt HUD Bar -->
      <div class="attempt-hud-bar">
        <div class="hud-left">
          <span class="hud-tag hud-mode">${isPractice ? '练习模式' : '考试模式'}</span>
          <span class="hud-timer">${icons.clock(13)} ${formatElapsed(activeAttempt.elapsed_seconds)}</span>
          <span class="hud-progress">进度: ${answers.filter((a) => a.answer !== null && a.answer !== '').length}/${questions.length} 题</span>
        </div>
        <div class="hud-right">
          ${isCompleted ? `<span class="hud-tag hud-locked">${icons.lock(12)} 答案只读</span>` : `<span class="hud-tag hud-editable">${icons.edit(12)} 可编辑</span>`}
        </div>
      </div>

      <!-- Scorecard Review (if graded) -->
      ${
        activeAttemptReview
          ? `
        <div class="attempt-scorecard-card">
          <div class="scorecard-header">
            <div class="score-number-block">
              <span class="score-val">${activeAttemptReview.total_score || 0}</span>
              <span class="score-max">/ ${doc.total_score || 100} 分</span>
            </div>
            <div class="scorecard-summary">
              <h4 class="summary-title">${escapeHtml(activeAttemptReview.summary || '批改完毕')}</h4>
              <p class="summary-text">${escapeHtml(activeAttemptReview.weakness_analysis || '请查看各题具体得分与反馈要点。')}</p>
            </div>
          </div>
        </div>
      `
          : ''
      }

      <!-- Questions List -->
      <div class="attempt-questions-list">
        ${questions
          .map((q, idx) => {
            const curAnswer = answers.find((a) => a.question_id === q.id)?.answer;
            const curFb = feedbacks.find((f) => f.question_id === q.id);

            return `
              <div class="attempt-question-block" data-question-id="${q.id}">
                <div class="q-block-header">
                  <span class="q-block-num">第 ${idx + 1} 题</span>
                  <span class="q-block-type">${formatQuestionType(q.type)}</span>
                  <span class="q-block-points">${q.points || 5} 分</span>
                </div>

                <div class="q-block-stem selectable-text">${escapeHtml(q.stem || '')}</div>

                <!-- Input Sheet according to Question Type -->
                <div class="q-block-input-area">
                  ${renderQuestionInputArea(q, curAnswer, isCompleted, isPractice)}
                </div>

                <!-- Single Question Feedback / Explanation (Practice Mode or Graded) -->
                ${
                  isPractice || curFb
                    ? `
                  <div class="q-feedback-drawer">
                    ${
                      curFb
                        ? `
                      <div class="q-feedback-card ${curFb.is_correct ? 'is-correct' : 'is-incorrect'}">
                        <div class="fb-header">
                          <span class="fb-status">${curFb.is_correct ? icons.checkCircle(14) + ' 得分: ' + (curFb.score || q.points || 5) : icons.xCircle(14) + ' 得分: ' + (curFb.score || 0)}</span>
                          ${curFb.is_expired ? `<span class="badge-expired">批改已过期</span>` : ''}
                        </div>
                        <div class="fb-comment">${escapeHtml(curFb.feedback || curFb.comment || '')}</div>
                        ${
                          curFb.key_points && curFb.key_points.length > 0
                            ? `
                          <div class="fb-keypoints">
                            <span class="kp-title">得分要点:</span>
                            <ul>${curFb.key_points.map((kp) => `<li>${escapeHtml(kp)}</li>`).join('')}</ul>
                          </div>
                        `
                            : ''
                        }
                      </div>
                    `
                        : `
                      <button
                        type="button"
                        class="btn-text-action btn-request-single-feedback"
                        data-attempt-id="${activeAttempt.id}"
                        data-question-id="${q.id}"
                        title="查看本题 AI 解析与要点"
                      >
                        ${icons.sparkles(13)} 查看本题解析
                      </button>
                    `
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

function renderQuestionInputArea(q, curAnswer, isCompleted, isPractice) {
  const type = q.type || 'single-choice';
  const disabledAttr = isCompleted ? 'disabled' : '';

  if (type === 'single-choice' || type === 'true-false') {
    const options = q.options && q.options.length > 0
      ? q.options
      : type === 'true-false'
      ? [{ key: 'true', text: '正确' }, { key: 'false', text: '错误' }]
      : [];

    return `
      <div class="options-radio-group" data-question-id="${q.id}">
        ${options
          .map((opt, oIdx) => {
            const optVal = opt.key || String.fromCharCode(65 + oIdx);
            const isChecked = String(curAnswer) === String(optVal) || (type === 'true-false' && String(curAnswer) === String(opt.key));

            return `
              <label class="option-radio-label ${isChecked ? 'is-selected' : ''} ${isCompleted ? 'is-disabled' : ''}">
                <input
                  type="radio"
                  name="q_${q.id}"
                  value="${optVal}"
                  ${isChecked ? 'checked' : ''}
                  ${disabledAttr}
                  class="q-input-radio"
                  data-question-id="${q.id}"
                />
                <span class="opt-indicator">${String.fromCharCode(65 + oIdx)}</span>
                <span class="opt-label-text selectable-text">${escapeHtml(opt.text || opt)}</span>
              </label>
            `;
          })
          .join('')}
      </div>
    `;
  }

  if (type === 'multiple-choice') {
    const selectedArr = Array.isArray(curAnswer) ? curAnswer : typeof curAnswer === 'string' ? curAnswer.split(',') : [];

    return `
      <div class="options-checkbox-group" data-question-id="${q.id}">
        ${(q.options || [])
          .map((opt, oIdx) => {
            const optVal = opt.key || String.fromCharCode(65 + oIdx);
            const isChecked = selectedArr.includes(optVal);

            return `
              <label class="option-checkbox-label ${isChecked ? 'is-selected' : ''} ${isCompleted ? 'is-disabled' : ''}">
                <input
                  type="checkbox"
                  value="${optVal}"
                  ${isChecked ? 'checked' : ''}
                  ${disabledAttr}
                  class="q-input-checkbox"
                  data-question-id="${q.id}"
                />
                <span class="opt-indicator">${String.fromCharCode(65 + oIdx)}</span>
                <span class="opt-label-text selectable-text">${escapeHtml(opt.text || opt)}</span>
              </label>
            `;
          })
          .join('')}
      </div>
    `;
  }

  // Essay / Fill-in / Coding
  return `
    <div class="text-answer-box">
      <textarea
        class="q-input-textarea ${isCompleted ? 'is-disabled' : ''}"
        data-question-id="${q.id}"
        rows="4"
        placeholder="${isCompleted ? '（作答已标记完成）' : '在此输入作答内容...'}"
        ${disabledAttr}
      >${escapeHtml(curAnswer || '')}</textarea>
    </div>
  `;
}

function attachAttemptsEvents(container, state, handlers) {
  // Drawer
  const drawerBackdrop = container.querySelector('#attempts-drawer-backdrop');
  const openDrawerBtn = container.querySelector('#btn-open-attempts-drawer');
  const closeDrawerBtn = container.querySelector('#btn-close-attempts-drawer');

  const openDrawer = () => {
    if (drawerBackdrop) drawerBackdrop.style.display = 'block';
  };
  const closeDrawer = () => {
    if (drawerBackdrop) drawerBackdrop.style.display = 'none';
  };

  if (openDrawerBtn) openDrawerBtn.onclick = openDrawer;
  if (closeDrawerBtn) closeDrawerBtn.onclick = closeDrawer;
  if (drawerBackdrop) {
    drawerBackdrop.onclick = (e) => {
      if (e.target === drawerBackdrop) closeDrawer();
    };
  }

  // Go to Quiz Gen
  const gotoQuizGenBtn = container.querySelector('#btn-goto-quiz-gen') || container.querySelector('#btn-empty-goto-quiz-gen');
  if (gotoQuizGenBtn) {
    gotoQuizGenBtn.onclick = () => handlers.onSelectNavTab?.('quiz_gen');
  }

  // Start Modes
  const startPracticeBtn = container.querySelector('#btn-start-practice-mode') || container.querySelector('#btn-hero-start-practice');
  const startExamBtn = container.querySelector('#btn-start-exam-mode') || container.querySelector('#btn-hero-start-exam');

  if (startPracticeBtn) {
    startPracticeBtn.onclick = () => {
      const eid = startPracticeBtn.getAttribute('data-exam-id') || state.activeExam?.id;
      if (eid) handlers.onStartAttempt?.(eid, 'practice');
    };
  }

  if (startExamBtn) {
    startExamBtn.onclick = () => {
      const eid = startExamBtn.getAttribute('data-exam-id') || state.activeExam?.id;
      if (eid) handlers.onStartAttempt?.(eid, 'exam');
    };
  }

  // Complete Attempt
  const completeBtn = container.querySelector('#btn-complete-attempt-action');
  if (completeBtn) {
    completeBtn.onclick = () => {
      const attId = state.activeAttempt?.id;
      if (attId) handlers.onCompleteAttempt?.(attId);
    };
  }

  // Continue Attempt
  const continueBtn = container.querySelector('#btn-continue-attempt-action');
  if (continueBtn) {
    continueBtn.onclick = () => {
      const attId = state.activeAttempt?.id;
      if (attId) handlers.onContinueAttempt?.(attId);
    };
  }

  // Submit Grading
  const gradingBtn = container.querySelector('#btn-submit-grading-action');
  if (gradingBtn) {
    gradingBtn.onclick = () => {
      const attId = state.activeAttempt?.id;
      if (attId) handlers.onSubmitAttemptGrading?.(attId);
    };
  }

  // Request Single Question Feedback
  container.querySelectorAll('.btn-request-single-feedback').forEach((btn) => {
    btn.onclick = () => {
      const attId = btn.getAttribute('data-attempt-id');
      const qid = btn.getAttribute('data-question-id');
      handlers.onRequestQuestionFeedback?.(attId, qid);
    };
  });

  // Inputs: Auto-save Answers
  container.querySelectorAll('.q-input-radio').forEach((input) => {
    input.onchange = () => {
      const qid = input.getAttribute('data-question-id');
      const val = input.value;
      const attId = state.activeAttempt?.id;
      if (attId && qid) handlers.onSaveAttemptAnswer?.(attId, qid, val);
    };
  });

  container.querySelectorAll('.q-input-checkbox').forEach((input) => {
    input.onchange = () => {
      const qid = input.getAttribute('data-question-id');
      const group = container.querySelectorAll(`.q-input-checkbox[data-question-id="${qid}"]:checked`);
      const val = Array.from(group).map((cb) => cb.value);
      const attId = state.activeAttempt?.id;
      if (attId && qid) handlers.onSaveAttemptAnswer?.(attId, qid, val);
    };
  });

  container.querySelectorAll('.q-input-textarea').forEach((textarea) => {
    let timeout = null;
    textarea.oninput = () => {
      clearTimeout(timeout);
      timeout = setTimeout(() => {
        const qid = textarea.getAttribute('data-question-id');
        const val = textarea.value;
        const attId = state.activeAttempt?.id;
        if (attId && qid) handlers.onSaveAttemptAnswer?.(attId, qid, val);
      }, 500);
    };
  });

  // Select Item from Drawer
  container.querySelectorAll('.drawer-item').forEach((el) => {
    el.onclick = () => {
      const type = el.getAttribute('data-type');
      const id = el.getAttribute('data-id');
      closeDrawer();
      if (type === 'exam') {
        handlers.onSelectExam?.(id);
      } else if (type === 'attempt') {
        handlers.onSelectAttempt?.(id);
      }
    };
  });

  // Floating "问 AI" on Text Selection
  setupFloatingSelectionMenu(container, handlers);
}

function setupFloatingSelectionMenu(container, handlers) {
  const askBtn = container.querySelector('#floating-ask-ai-btn');
  const worksheetBody = container.querySelector('#attempt-worksheet-body');
  if (!askBtn || !worksheetBody) return;

  document.addEventListener('selectionchange', () => {
    const selection = window.getSelection();
    const selectedText = selection?.toString().trim();

    if (!selectedText || selectedText.length < 2 || !worksheetBody.contains(selection.anchorNode)) {
      askBtn.style.display = 'none';
      return;
    }

    try {
      const range = selection.getRangeAt(0);
      const rect = range.getBoundingClientRect();
      askBtn.style.top = `${rect.top - 36 + window.scrollY}px`;
      askBtn.style.left = `${rect.left + rect.width / 2 - 36 + window.scrollX}px`;
      askBtn.style.display = 'flex';

      askBtn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        askBtn.style.display = 'none';
        handlers.onSelectTextForQuestion?.(selectedText);
      };
    } catch (err) {
      askBtn.style.display = 'none';
    }
  });
}

function formatElapsed(seconds = 0) {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

function formatQuestionType(type) {
  const map = {
    'single-choice': '单选题',
    'multiple-choice': '多选题',
    'true-false': '判断题',
    'fill-in-the-blank': '填空题',
    'essay': '问答题',
    'coding': '编程题',
    'reading-comprehension': '阅读理解'
  };
  return map[type] || type || '单选题';
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
