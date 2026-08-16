import { icons } from '../icons.js';

export function renderDraftView(state, container, handlers) {
  const drafts = state.drafts || [];
  const activeDraftId = state.activeDraftId;
  const activeDraft = drafts.find((d) => d.id === activeDraftId) || drafts[0] || null;

  container.innerHTML = `
    <div class="studio-pane-layout">
      <!-- Left Sidebar: Drafts List -->
      <aside class="studio-pane-sidebar">
        <div class="pane-sidebar-header" style="display: flex; align-items: center; justify-content: space-between;">
          <h3 class="pane-title">
            <span>${icons.sparkles(18)}</span>
            <span>题目工坊</span>
          </h3>
          <span class="count-pill">${drafts.length} 组</span>
        </div>

        <div class="draft-items-list">
          ${
            drafts.length === 0
              ? `<div style="text-align: center; padding: 24px 8px; color: var(--ink-muted); font-size: 12px;">暂无生成中的题目草稿</div>`
              : drafts
                  .map(
                    (d) => `
                <div class="draft-item-card ${activeDraft?.id === d.id ? 'is-selected' : ''}" data-draft-id="${d.id}">
                  <div style="display: flex; align-items: center; justify-content: space-between;">
                    <span style="font-weight: 700; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 140px;">
                      ${escapeHtml(d.title || '试题草稿')}
                    </span>
                    <span class="status-pill status-pill-${d.status || 'draft'}">${formatDraftStatus(d.status)}</span>
                  </div>
                  <div style="display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: var(--ink-muted); margin-top: 4px;">
                    <span>完成度: ${countCompletedQuestions(d.questions)}/${d.questions?.length || 0} 题</span>
                    <span>${formatDate(d.created_at)}</span>
                  </div>
                </div>
              `
                  )
                  .join('')
          }
        </div>
      </aside>

      <!-- Right Main Content: Draft Questions List -->
      <main class="studio-pane-content">
        ${
          activeDraft
            ? `
          <div class="draft-detail-container">
            <div class="draft-detail-header">
              <div class="title-row">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="padding: 6px; background: var(--marker-yellow); border: var(--sketch-border-thin); border-radius: var(--sketch-radius-sm);">
                    ${icons.sparkles(18)}
                  </span>
                  <div>
                    <h2>${escapeHtml(activeDraft.title || '试卷题目生成工坊')}</h2>
                    <span style="font-size: 12px; color: var(--ink-muted);">
                      草稿 ID: ${activeDraft.id} · 就绪: ${countCompletedQuestions(activeDraft.questions)}/${activeDraft.questions?.length || 0}
                    </span>
                  </div>
                </div>
              </div>

              <div class="action-buttons-row" style="display: flex; align-items: center; gap: 8px;">
                <button class="btn-primary-glow" id="btn-publish-draft-to-exam" title="将所有就绪题目发布为正式试卷">
                  <span>${icons.printer(14)}</span>
                  <span>发布为正式试卷</span>
                </button>
              </div>
            </div>

            <!-- Draft Question Slot Cards -->
            <div class="draft-questions-list">
              ${(activeDraft.questions || [])
                .map((q, idx) => {
                  const isNeedsReview = q.status === 'needs-review';
                  return `
                <div class="draft-q-card" data-question-id="${q.id}" style="${isNeedsReview ? 'border-color: var(--accent-crimson);' : ''}">
                  <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                      <span class="score-pill">第 ${idx + 1} 题</span>
                      <span class="type-pill">${formatQuestionType(q.type)}</span>
                      <span class="score-pill" style="background: var(--marker-yellow);">${q.score || 5} 分</span>
                    </div>

                    <div style="display: flex; align-items: center; gap: 6px;">
                      <span class="status-pill status-pill-${q.status || 'complete'}">${formatQStatus(q.status)}</span>
                      <button class="btn-icon-hud btn-retry-question" data-draft-id="${activeDraft.id}" data-question-id="${q.id}" title="重新生成此题">
                        ${icons.rotateCw(13)}
                      </button>
                    </div>
                  </div>

                  <!-- Stem -->
                  <div style="font-weight: 700; font-size: 14px; margin-top: 4px; line-height: 1.5;">
                    ${escapeHtml(renderStem(q.stem))}
                  </div>

                  <!-- Options (for choice questions) -->
                  ${
                    q.options && q.options.length > 0
                      ? `
                    <div class="options-container" style="display: grid; gap: 6px; margin-top: 6px;">
                      ${q.options
                        .map(
                          (opt) => `
                        <div class="choice-option-label" style="background: var(--bg-paper);">
                          <span class="opt-key-circle">${opt.id}</span>
                          <span>${escapeHtml(opt.text)}</span>
                        </div>
                      `
                        )
                        .join('')}
                    </div>
                  `
                      : ''
                  }

                  <!-- Answer & Explanation -->
                  <div class="q-explanation-box">
                    <span class="box-tag" style="color: var(--accent-emerald);">${icons.check(13)} 参考答案与解析:</span>
                    <div style="font-weight: 700;">答案: ${escapeHtml(formatAnswer(q.answer))}</div>
                    <div style="color: var(--ink-secondary); margin-top: 2px;">${escapeHtml(q.explanation || '')}</div>
                  </div>

                  <!-- Scoring Points (for subjective questions) -->
                  ${
                    q.scoring_points && q.scoring_points.length > 0
                      ? `
                    <div class="q-scoring-points-box">
                      <span class="box-tag" style="color: var(--accent-primary);">${icons.target(13)} 采分要点 (Scoring Points):</span>
                      <ul style="padding-left: 18px; margin-top: 2px; color: var(--ink-secondary);">
                        ${q.scoring_points
                          .map(
                            (sp) => `
                          <li><span style="font-weight: 700;">[+${sp.points}分]</span> ${escapeHtml(sp.description)}</li>
                        `
                          )
                          .join('')}
                      </ul>
                    </div>
                  `
                      : ''
                  }

                  <!-- Evidence / Citations -->
                  ${
                    q.evidence && q.evidence.citations && q.evidence.citations.length > 0
                      ? `
                    <div class="q-evidence-box">
                      <span class="box-tag" style="color: var(--ink-muted);">${icons.tag(13)} 出题依据 (Evidence):</span>
                      <div style="font-size: 11px; color: var(--ink-muted);">
                        ${q.evidence.citations.map((c) => `<span>§ 依据引用 [${escapeHtml(c.quote || c.id)}]</span>`).join(' · ')}
                      </div>
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
        `
            : `
          <div class="copilot-empty-state">
            <div class="empty-glow-icon">${icons.sparkles(28)}</div>
            <h3 style="font-family: var(--font-hand); font-size: 22px;">暂无题目工坊任务</h3>
            <p style="font-size: 13px; color: var(--ink-muted); max-width: 320px;">
              请前往「组卷蓝图」标签页，设计并确认蓝图后点击"生成试卷草稿"。
            </p>
          </div>
        `
        }
      </main>
    </div>
  `;

  // Attach handlers
  container.querySelectorAll('.draft-item-card').forEach((card) => {
    card.onclick = () => {
      const draftId = card.getAttribute('data-draft-id');
      handlers.onSelectDraft?.(draftId);
    };
  });

  const btnPublish = container.querySelector('#btn-publish-draft-to-exam');
  if (btnPublish && activeDraft) {
    btnPublish.onclick = () => handlers.onPublishDraft?.(activeDraft.id);
  }

  container.querySelectorAll('.btn-retry-question').forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const draftId = btn.getAttribute('data-draft-id');
      const questionId = btn.getAttribute('data-question-id');
      handlers.onRetryQuestion?.(draftId, questionId);
    };
  });
}

function countCompletedQuestions(questions = []) {
  return questions.filter((q) => q.status === 'complete').length;
}

function formatDraftStatus(s) {
  switch (s) {
    case 'generating':
      return '生成中';
    case 'complete':
      return '生成完毕';
    case 'needs-review':
      return '部分待复核';
    case 'published':
      return '已发布';
    default:
      return '就绪';
  }
}

function formatQStatus(s) {
  switch (s) {
    case 'complete':
      return '就绪';
    case 'needs-review':
      return '待复核';
    case 'generating':
      return '生成中';
    default:
      return '就绪';
  }
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
  if (!ans) return '暂无';
  if (ans.kind === 'choice') return ans.option_ids?.join(', ') || '未设置';
  if (ans.kind === 'fill-blank') return ans.blanks?.map((b) => b.value).join(', ') || '未设置';
  if (ans.kind === 'text') return ans.text || '未设置';
  return JSON.stringify(ans);
}

function formatDate(timestamp) {
  if (!timestamp) return '';
  const d = new Date(timestamp);
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
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
