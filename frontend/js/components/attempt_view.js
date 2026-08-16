import { icons } from '../icons.js';

export function renderAttemptView(state, container, handlers) {
  const exams = state.exams || [];
  const activeExamId = state.activeExamId;
  const activeExam = exams.find((e) => e.id === activeExamId) || exams[0] || null;
  const activeAttempt = state.activeAttempt;
  const review = state.activeAttemptReview;

  container.innerHTML = `
    <div class="studio-pane-layout">
      <!-- Left Sidebar: Exam List & Attempts -->
      <aside class="studio-pane-sidebar">
        <div class="pane-sidebar-header" style="display: flex; align-items: center; justify-content: space-between;">
          <h3 class="pane-title">
            <span>${icons.target(18)}</span>
            <span>试卷与作答</span>
          </h3>
          <span class="count-pill">${exams.length} 卷</span>
        </div>

        <div class="exam-items-list">
          ${
            exams.length === 0
              ? `<div style="text-align: center; padding: 24px 8px; color: var(--ink-muted); font-size: 12px;">暂无已发布试卷</div>`
              : exams
                  .map(
                    (e) => `
                <div class="exam-item-card ${activeExam?.id === e.id ? 'is-selected' : ''}" data-exam-id="${e.id}">
                  <div style="display: flex; align-items: center; justify-content: space-between;">
                    <span style="font-weight: 700; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 140px;">
                      ${escapeHtml(e.document?.title || e.title || '期末自测卷')}
                    </span>
                    <span class="version-tag">v${e.version_count || 1}</span>
                  </div>
                  <div style="display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: var(--ink-muted); margin-top: 4px;">
                    <span>总分: ${e.document?.total_score || 20} 分</span>
                    <span>题数: ${e.document?.questions?.length || 0} 题</span>
                  </div>
                </div>
              `
                  )
                  .join('')
          }
        </div>
      </aside>

      <!-- Right Main Content: Attempt Interface / Review Report -->
      <main class="studio-pane-content">
        ${
          review
            ? renderReviewReport(review, handlers)
            : activeAttempt
              ? renderActiveAttemptPaper(activeAttempt, handlers)
              : activeExam
                ? renderExamLaunchpad(activeExam, handlers)
                : `
              <div class="copilot-empty-state">
                <div class="empty-glow-icon">${icons.target(28)}</div>
                <h3 style="font-family: var(--font-hand); font-size: 22px;">暂无已发布的试卷</h3>
                <p style="font-size: 13px; color: var(--ink-muted); max-width: 320px;">
                  请先在「组卷蓝图」生成题目草稿，并在「题目工坊」中点击"发布为正式试卷"。
                </p>
              </div>
            `
        }
      </main>
    </div>
  `;

  // Attach handlers
  container.querySelectorAll('.exam-item-card').forEach((card) => {
    card.onclick = () => {
      const examId = card.getAttribute('data-exam-id');
      handlers.onSelectExam?.(examId);
    };
  });

  const btnPractice = container.querySelector('#btn-launch-practice-mode');
  if (btnPractice && activeExam) {
    btnPractice.onclick = () => handlers.onStartAttempt?.(activeExam.id, 'practice');
  }

  const btnExam = container.querySelector('#btn-launch-exam-mode');
  if (btnExam && activeExam) {
    btnExam.onclick = () => handlers.onStartAttempt?.(activeExam.id, 'exam');
  }

  const btnSubmit = container.querySelector('#btn-submit-attempt');
  if (btnSubmit && activeAttempt) {
    btnSubmit.onclick = () => handlers.onSubmitAttempt?.(activeAttempt.id);
  }

  const btnPause = container.querySelector('#btn-pause-attempt');
  if (btnPause && activeAttempt) {
    btnPause.onclick = () => handlers.onPauseAttempt?.(activeAttempt.id);
  }

  const btnResume = container.querySelector('#btn-resume-attempt');
  if (btnResume && activeAttempt) {
    btnResume.onclick = () => handlers.onResumeAttempt?.(activeAttempt.id);
  }

  // Answer inputs & Feedback triggers
  container.querySelectorAll('.btn-option-choice').forEach((btn) => {
    btn.onclick = () => {
      const qId = btn.getAttribute('data-q-id');
      const optId = btn.getAttribute('data-opt-id');
      handlers.onSaveAnswer?.(activeAttempt.id, qId, { kind: 'choice', option_ids: [optId] });
    };
  });

  container.querySelectorAll('.input-answer-text').forEach((inp) => {
    inp.onblur = () => {
      const qId = inp.getAttribute('data-q-id');
      const text = inp.value.trim();
      if (text) {
        handlers.onSaveAnswer?.(activeAttempt.id, qId, { kind: 'text', text });
      }
    };
  });

  container.querySelectorAll('.btn-request-feedback').forEach((btn) => {
    btn.onclick = () => {
      const qId = btn.getAttribute('data-q-id');
      handlers.onRequestFeedback?.(activeAttempt.id, qId);
    };
  });

  const btnBackLaunchpad = container.querySelector('#btn-back-to-launchpad');
  if (btnBackLaunchpad) {
    btnBackLaunchpad.onclick = () => handlers.onResetAttemptView?.();
  }
}

function renderExamLaunchpad(exam, handlers) {
  const doc = exam.document || {};
  const questions = doc.questions || [];

  return `
    <div class="exam-launchpad-container">
      <div class="launchpad-header">
        <div class="title-row">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="padding: 6px; background: var(--marker-yellow); border: var(--sketch-border-thin); border-radius: var(--sketch-radius-sm);">
              ${icons.target(18)}
            </span>
            <div>
              <h2>${escapeHtml(doc.title || '试卷全景')}</h2>
              <span style="font-size: 12px; color: var(--ink-muted);">总分: ${doc.total_score || 20} 分 · 包含 ${questions.length} 道精选试题</span>
            </div>
          </div>
        </div>

        <div class="action-buttons-row" style="display: flex; align-items: center; gap: 8px;">
          <button class="btn-secondary-glow" id="btn-launch-practice-mode">
            <span>${icons.edit3(14)}</span>
            <span>练习模式 (即时AI批改)</span>
          </button>
          <button class="btn-primary-glow" id="btn-launch-exam-mode">
            <span>${icons.play(14)}</span>
            <span>考试模式 (全卷计时)</span>
          </button>
        </div>
      </div>

      <!-- Outline List -->
      <div class="exam-outline-list" style="display: grid; gap: 12px;">
        ${questions
          .map(
            (q, idx) => `
          <div class="outline-q-card">
            <div style="display: flex; align-items: center; justify-content: space-between;">
              <div style="display: flex; align-items: center; gap: 6px;">
                <span class="score-pill">第 ${idx + 1} 题</span>
                <span class="type-pill">${formatQuestionType(q.type)}</span>
              </div>
              <span class="score-pill" style="background: var(--marker-yellow);">${q.score || 5} 分</span>
            </div>
            <div style="font-weight: 700; font-size: 14px; margin-top: 4px;">
              ${escapeHtml(renderStem(q.stem))}
            </div>
          </div>
        `
          )
          .join('')}
      </div>
    </div>
  `;
}

function renderActiveAttemptPaper(attempt, handlers) {
  const paper = attempt.paper || {};
  const questions = paper.questions || [];
  const answers = attempt.answers || {};
  const feedbackList = attempt.feedback || [];
  const isPractice = attempt.mode === 'practice';
  const isPaused = attempt.status === 'paused';

  return `
    <div class="attempt-paper-container" style="display: flex; flex-direction: column; gap: 16px;">
      <div class="attempt-header-bar" style="display: flex; align-items: center; justify-content: space-between; padding-bottom: 14px; border-bottom: var(--sketch-border);">
        <div style="display: flex; align-items: center; gap: 10px;">
          <h2 style="font-family: var(--font-hand); font-size: 24px; font-weight: 700;">
            ${escapeHtml(paper.title || '作答试卷')}
          </h2>
          <span class="type-pill" style="background: ${isPractice ? 'var(--marker-green)' : 'var(--marker-yellow)'};">
            ${isPractice ? '练习模式 · 即时批改' : '考试模式 · 全真模拟'}
          </span>
        </div>

        <div style="display: flex; align-items: center; gap: 8px;">
          <div class="timer-display">
            <span>${icons.clock(15)}</span>
            <span>${formatTimer(attempt.elapsed_seconds || 0)}</span>
          </div>

          ${
            isPaused
              ? `
            <button class="btn-secondary-glow" id="btn-resume-attempt">
              <span>${icons.play(14)}</span>
              <span>继续作答</span>
            </button>
          `
              : `
            <button class="btn-secondary-glow" id="btn-pause-attempt">
              <span>${icons.pause(14)}</span>
              <span>暂停</span>
            </button>
          `
          }

          <button class="btn-primary-glow" id="btn-submit-attempt">
            <span>${icons.check(14)}</span>
            <span>交卷并查看分析</span>
          </button>
        </div>
      </div>

      <!-- Question Palette -->
      <div class="question-palette-bar" style="display: flex; gap: 6px; padding: 8px 12px; background: var(--bg-paper-alt); border: var(--sketch-border-thin); border-radius: var(--sketch-radius);">
        <span style="font-family: var(--font-hand); font-size: 14px; font-weight: 700; align-self: center;">题号导航:</span>
        ${questions
          .map((q, idx) => {
            const hasAns = answers[q.id] !== undefined;
            return `
            <button class="palette-slot ${hasAns ? 'is-answered' : ''}" style="width: 32px; height: 32px;" title="跳转至第 ${idx + 1} 题">
              ${idx + 1}
            </button>
          `;
          })
          .join('')}
      </div>

      <!-- Question List -->
      <div class="attempt-questions-stream" style="display: grid; gap: 16px;">
        ${questions
          .map((q, idx) => {
            const userAns = answers[q.id]?.answer;
            const qFeedback = feedbackList.find((f) => f.question_id === q.id);

            return `
            <div class="outline-q-card" id="q-card-${q.id}">
              <div style="display: flex; align-items: center; justify-content: space-between;">
                <div style="display: flex; align-items: center; gap: 6px;">
                  <span class="score-pill">第 ${idx + 1} 题</span>
                  <span class="type-pill">${formatQuestionType(q.type)}</span>
                </div>
                <span class="score-pill" style="background: var(--marker-yellow);">${q.score || 5} 分</span>
              </div>

              <!-- Stem -->
              <div style="font-weight: 700; font-size: 14px; margin-top: 4px; line-height: 1.5;">
                ${escapeHtml(renderStem(q.stem))}
              </div>

              <!-- Options for Choices -->
              ${
                q.options && q.options.length > 0
                  ? `
                <div class="options-container" style="display: grid; gap: 6px; margin-top: 8px;">
                  ${q.options
                    .map((opt) => {
                      const isChecked = userAns?.option_ids?.includes(opt.id);
                      return `
                      <button class="choice-option-label btn-option-choice ${isChecked ? 'is-checked' : ''}" data-q-id="${q.id}" data-opt-id="${opt.id}">
                        <span class="opt-key-circle">${opt.id}</span>
                        <span>${escapeHtml(opt.text)}</span>
                      </button>
                    `;
                    })
                    .join('')}
                </div>
              `
                  : `
                <div class="text-answer-container" style="margin-top: 8px;">
                  <textarea 
                    class="form-textarea input-answer-text" 
                    data-q-id="${q.id}" 
                    rows="3" 
                    placeholder="在此输入您的作答内容..."
                  >${escapeHtml(userAns?.text || '')}</textarea>
                </div>
              `
              }

              <!-- Practice Mode Instant Feedback Button -->
              ${
                isPractice
                  ? `
                <div style="display: flex; align-items: center; justify-content: flex-end; margin-top: 6px;">
                  <button class="btn-secondary-glow btn-request-feedback" data-q-id="${q.id}" style="padding: 4px 10px; font-size: 12px;">
                    <span>${icons.zap(13)}</span>
                    <span>请求即时 AI 批改</span>
                  </button>
                </div>
              `
                  : ''
              }

              <!-- Instant Feedback Result -->
              ${
                qFeedback
                  ? `
                <div class="instant-feedback-card" style="margin-top: 8px;">
                  <div style="display: flex; align-items: center; justify-content: space-between;">
                    <span style="font-weight: 700; color: ${qFeedback.correct ? 'var(--accent-emerald)' : 'var(--accent-amber)'};">
                      ${qFeedback.correct ? icons.check(14) + ' 回答正确' : icons.alertTriangle(14) + ' 采分点分析'}
                    </span>
                    ${qFeedback.suggested_score !== undefined && qFeedback.suggested_score !== null ? `<span class="score-pill">预估得分: ${qFeedback.suggested_score}分</span>` : ''}
                  </div>

                  ${
                    qFeedback.matched_points && qFeedback.matched_points.length > 0
                      ? `
                    <div style="color: var(--accent-emerald); font-size: 12px;">
                      <b>命中采分点:</b> ${qFeedback.matched_points.map((p) => p.description || p.id).join('；')}
                    </div>
                  `
                      : ''
                  }

                  ${
                    qFeedback.missed_points && qFeedback.missed_points.length > 0
                      ? `
                    <div style="color: var(--accent-crimson); font-size: 12px;">
                      <b>遗漏采分点:</b> ${qFeedback.missed_points.map((p) => p.description || p.id).join('；')}
                    </div>
                  `
                      : ''
                  }

                  ${
                    qFeedback.suggestions && qFeedback.suggestions.length > 0
                      ? `
                    <div style="color: var(--ink-secondary); font-size: 12px; margin-top: 4px;">
                      <b>改进建议:</b> ${qFeedback.suggestions.join(' ')}
                    </div>
                  `
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

function renderReviewReport(review, handlers) {
  const items = review.items || [];
  const score = review.score ?? 0;
  const totalScore = review.total_score ?? 20;

  return `
    <div class="attempt-review-container">
      <div class="review-header">
        <div class="title-row">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="padding: 6px; background: var(--marker-yellow); border: var(--sketch-border-thin); border-radius: var(--sketch-radius-sm);">
              ${icons.target(18)}
            </span>
            <div>
              <h2>试卷复盘与成绩单</h2>
              <span style="font-size: 12px; color: var(--ink-muted);">作答时长: ${formatTimer(review.elapsed_seconds || 0)}</span>
            </div>
          </div>
        </div>

        <div style="display: flex; align-items: center; gap: 12px;">
          <div style="padding: 6px 14px; background: var(--marker-green); border: var(--sketch-border); border-radius: var(--sketch-radius); font-family: var(--font-mono); font-size: 18px; font-weight: 800; color: #000;">
            最终得分: ${score} / ${totalScore} 分
          </div>
          <button class="btn-secondary-glow" id="btn-back-to-launchpad">
            <span>${icons.rotateCw(14)}</span>
            <span>返回试卷中心</span>
          </button>
        </div>
      </div>

      <!-- Items Stream -->
      <div class="review-items-stream" style="display: grid; gap: 16px;">
        ${items
          .map((item, idx) => {
            const q = item.question || {};
            const userAns = item.user_answer;
            const isCorrect = item.correct;

            return `
            <div class="review-q-card" style="border-left: 6px solid ${isCorrect ? 'var(--accent-emerald)' : 'var(--accent-crimson)'};">
              <div style="display: flex; align-items: center; justify-content: space-between;">
                <div style="display: flex; align-items: center; gap: 6px;">
                  <span class="score-pill">第 ${idx + 1} 题</span>
                  <span class="type-pill">${formatQuestionType(q.type)}</span>
                  <span style="font-weight: 700; color: ${isCorrect ? 'var(--accent-emerald)' : 'var(--accent-crimson)'};">
                    ${isCorrect ? icons.check(14) + ' 正确' : icons.x(14) + ' 错误'}
                  </span>
                </div>
                <span class="score-pill">得分: ${item.score || (isCorrect ? q.score : 0)} / ${q.score || 5} 分</span>
              </div>

              <div style="font-weight: 700; font-size: 14px; margin-top: 4px;">
                ${escapeHtml(renderStem(q.stem))}
              </div>

              <div style="padding: 8px 12px; background: var(--bg-paper); border: 1px dashed var(--ink-light); border-radius: var(--sketch-radius-sm); font-size: 13px; margin-top: 6px;">
                <div><b>你的作答:</b> ${escapeHtml(formatAnswer(userAns))}</div>
                <div style="color: var(--accent-emerald); margin-top: 4px;"><b>标准答案:</b> ${escapeHtml(formatAnswer(q.answer))}</div>
              </div>

              ${
                q.explanation
                  ? `
                <div class="q-explanation-box" style="margin-top: 6px;">
                  <span class="box-tag" style="color: var(--accent-primary);">${icons.info(13)} 考点精析:</span>
                  <div>${escapeHtml(q.explanation)}</div>
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

function formatQuestionType(t) {
  switch (t) {
    case 'single-choice':
      return '单选题';
    case 'multiple-choice':
      return '多选题';
    case 'fill-blank':
      return '填空题';
    case 'true-false':
      return '判断题';
    case 'short-answer':
      return '简答题';
    default:
      return '题目';
  }
}

function renderStem(stem) {
  if (Array.isArray(stem)) {
    return stem.map((s) => s.text || '').join('\n');
  }
  return typeof stem === 'string' ? stem : '';
}

function formatAnswer(ans) {
  if (!ans) return '未作答';
  if (ans.kind === 'choice') return ans.option_ids?.join(', ') || '未作答';
  if (ans.kind === 'fill-blank') return ans.blanks?.map((b) => b.value).join(', ') || '未作答';
  if (ans.kind === 'text') return ans.text || '未作答';
  return JSON.stringify(ans);
}

function formatTimer(totalSecs = 0) {
  const m = Math.floor(totalSecs / 60);
  const s = totalSecs % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
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
