/**
 * Right Content Panel for 「组卷」 (Quiz Generation) Workspace
 * Strictly aligned with Issue 08, 09, 13, ADR 0003:
 * - 3 Stages: 试卷设置 (Blueprints) | 题目草稿 (Drafts) | 已发试卷 (Published Exams)
 * - Plain terms: "试卷设置", "确认设置", "发布试卷"
 * - Blueprint parameters, per-question generation status & retry, draft publish, exam exports
 * - Direct natural language entry points
 */

import { icons } from '../icons.js';

export function renderQuizGenView(state, container, handlers) {
  const {
    blueprints = [],
    activeBlueprintId,
    activeBlueprint,
    drafts = [],
    activeDraftId,
    activeDraft,
    exams = [],
    activeExamId,
    activeExam,
    examVersions = [],
    examStudioSubTab = 'blueprint', // 'blueprint' | 'draft' | 'exams'
    sidebarCollapsed = {}
  } = state;

  const isRightCollapsed = !!sidebarCollapsed.right;

  container.innerHTML = `
    <div class="workspace-right-pane ${isRightCollapsed ? 'is-collapsed' : ''}" data-testid="quiz-gen-workspace-right">
      <!-- Right Content Header -->
      <div class="workspace-right-header">
        <div class="header-object-info">
          <!-- Stage Switcher: 试卷设置 | 题目草稿 | 已发试卷 -->
          <div class="quiz-stage-switcher" role="tablist" aria-label="组卷流程">
            <button
              type="button"
              class="subtab-btn ${examStudioSubTab === 'blueprint' ? 'is-active' : ''}"
              id="btn-tab-blueprints"
              role="tab"
              aria-selected="${examStudioSubTab === 'blueprint'}"
            >
              ${icons.compass(14)} 试卷设置 (${blueprints.length})
            </button>
            <button
              type="button"
              class="subtab-btn ${examStudioSubTab === 'draft' ? 'is-active' : ''}"
              id="btn-tab-drafts"
              role="tab"
              aria-selected="${examStudioSubTab === 'draft'}"
            >
              ${icons.sparkles(14)} 题目草稿 (${drafts.length})
            </button>
            <button
              type="button"
              class="subtab-btn ${examStudioSubTab === 'exams' ? 'is-active' : ''}"
              id="btn-tab-exams"
              role="tab"
              aria-selected="${examStudioSubTab === 'exams'}"
            >
              ${icons.target(14)} 已发试卷 (${exams.length})
            </button>
          </div>
        </div>

        <div class="header-actions">
          ${renderStageHeaderActions(state)}
        </div>
      </div>

      <!-- Right Content Body -->
      <div class="workspace-right-body">
        ${renderStageBody(state)}
      </div>

      <!-- Drawer for Item Switching -->
      <div class="workspace-drawer-backdrop" id="quiz-drawer-backdrop" style="display: none;">
        <div class="workspace-drawer-panel" role="dialog" aria-modal="true" aria-label="组卷列表">
          <div class="drawer-header">
            <h4 class="drawer-title">${icons.compass(16)} 试卷与草稿列表</h4>
            <button type="button" class="btn-icon-subtle" id="btn-close-quiz-drawer" title="关闭">${icons.x(14)}</button>
          </div>

          <div class="drawer-body">
            <!-- Blueprints List -->
            <div class="drawer-section">
              <div class="drawer-section-header">
                <span class="section-title">蓝图设置 (${blueprints.length})</span>
                <button type="button" class="btn-text-action" id="btn-drawer-create-blueprint">
                  ${icons.plus(12)} 新建
                </button>
              </div>
              <div class="drawer-items-list">
                ${
                  blueprints.length === 0
                    ? `<div class="drawer-empty-hint">暂无蓝图</div>`
                    : blueprints
                        .map(
                          (bp) => `
                      <div
                        class="drawer-item ${activeBlueprint?.id === bp.id ? 'is-selected' : ''}"
                        data-type="blueprint"
                        data-id="${bp.id}"
                        role="button"
                        tabindex="0"
                      >
                        <span class="item-icon">${icons.compass(14)}</span>
                        <div class="item-info">
                          <span class="item-name">${escapeHtml(bp.title || bp.prompt || '组卷计划')}</span>
                          <span class="item-meta">${formatBpStatus(bp.status)}</span>
                        </div>
                      </div>
                    `
                        )
                        .join('')
                }
              </div>
            </div>

            <!-- Drafts List -->
            <div class="drawer-section">
              <div class="drawer-section-header">
                <span class="section-title">生成草稿 (${drafts.length})</span>
              </div>
              <div class="drawer-items-list">
                ${
                  drafts.length === 0
                    ? `<div class="drawer-empty-hint">暂无草稿</div>`
                    : drafts
                        .map(
                          (d) => `
                      <div
                        class="drawer-item ${activeDraft?.id === d.id ? 'is-selected' : ''}"
                        data-type="draft"
                        data-id="${d.id}"
                        role="button"
                        tabindex="0"
                      >
                        <span class="item-icon">${icons.sparkles(14)}</span>
                        <div class="item-info">
                          <span class="item-name">${escapeHtml(d.title || '试题草稿')}</span>
                          <span class="item-meta">${(d.questions || []).length} 道题 · ${formatDraftStatus(d.status)}</span>
                        </div>
                      </div>
                    `
                        )
                        .join('')
                }
              </div>
            </div>

            <!-- Published Exams List -->
            <div class="drawer-section">
              <div class="drawer-section-header">
                <span class="section-title">已发布试卷 (${exams.length})</span>
              </div>
              <div class="drawer-items-list">
                ${
                  exams.length === 0
                    ? `<div class="drawer-empty-hint">暂无已发试卷</div>`
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
                          <span class="item-name">${escapeHtml(e.document?.title || e.title || '试卷')}</span>
                          <span class="item-meta">${(e.document?.questions || []).length} 道题</span>
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
  attachQuizGenEvents(container, state, handlers);
}

function renderStageHeaderActions(state) {
  const { examStudioSubTab, activeBlueprint, activeDraft, activeExam } = state;

  if (examStudioSubTab === 'blueprint') {
    if (!activeBlueprint) {
      return `
        <button type="button" class="btn-primary-action" id="btn-trigger-create-blueprint" title="新建组卷蓝图">
          ${icons.plus(14)} 新建蓝图
        </button>
      `;
    }

    const isConfirmed = activeBlueprint.status === 'confirmed';
    return `
      ${
        !isConfirmed
          ? `
        <button type="button" class="btn-primary-action" id="btn-confirm-blueprint" title="确认试卷设置">
          ${icons.check(14)} 确认设置
        </button>
      `
          : `
        <button type="button" class="btn-primary-action" id="btn-generate-draft-from-bp" title="根据当前蓝图开始生成题目">
          ${icons.sparkles(14)} 开始组题
        </button>
      `
      }

      <button type="button" class="btn-icon-action" id="btn-open-quiz-drawer" title="切换列表">
        ${icons.list(14)}
      </button>
    `;
  }

  if (examStudioSubTab === 'draft') {
    if (!activeDraft) {
      return `
        <button type="button" class="btn-primary-action" id="btn-switch-to-blueprint-stage">
          ${icons.compass(14)} 前往设置
        </button>
      `;
    }

    const isComplete = activeDraft.status === 'completed' || activeDraft.status === 'ready';
    return `
      <button
        type="button"
        class="btn-primary-action"
        id="btn-publish-draft-exam"
        title="将当前草稿正式发布为试卷"
      >
        ${icons.checkCircle(14)} 发布试卷
      </button>

      <button type="button" class="btn-icon-action" id="btn-open-quiz-drawer" title="切换列表">
        ${icons.list(14)}
      </button>
    `;
  }

  if (examStudioSubTab === 'exams') {
    if (!activeExam) return '';
    return `
      <button type="button" class="btn-primary-action" id="btn-goto-attempt-exam" title="进入作答工作区">
        ${icons.play(14)} 去作答
      </button>

      <button type="button" class="btn-icon-action" id="btn-export-exam-doc" title="导出试卷排版">
        ${icons.download(14)}
      </button>

      <button type="button" class="btn-icon-action" id="btn-open-quiz-drawer" title="切换列表">
        ${icons.list(14)}
      </button>
    `;
  }

  return '';
}

function renderStageBody(state) {
  const { examStudioSubTab, activeBlueprint, activeDraft, activeExam } = state;

  if (examStudioSubTab === 'blueprint') {
    if (!activeBlueprint) {
      return `
        <div class="workspace-empty-state">
          <div class="empty-icon">${icons.compass(28)}</div>
          <h4 class="empty-title">想出一套什么卷？</h4>
          <p class="empty-subtitle">在左侧告诉 AI 您想出的试卷要求，或新建空白蓝图手动调整。</p>
          <div class="empty-actions-row">
            <button type="button" class="btn-primary-glow" id="btn-focus-chat-for-quiz">
              ${icons.messageSquare(14)} 告诉 AI 组卷
            </button>
            <button type="button" class="btn-outline-action" id="btn-empty-new-blueprint">
              ${icons.plus(14)} 新建蓝图
            </button>
          </div>
        </div>
      `;
    }

    const doc = activeBlueprint.document || activeBlueprint;
    const questionsDist = doc.question_distribution || activeBlueprint.question_distribution || [];
    const totalQuestions = questionsDist.reduce((acc, cur) => acc + (cur.count || 0), 0) || doc.total_questions || 10;
    const totalPoints = questionsDist.reduce((acc, cur) => acc + (cur.count || 0) * (cur.points_per_question || 0), 0) || doc.total_score || 100;

    return `
      <div class="blueprint-detail-container">
        <div class="blueprint-card">
          <div class="blueprint-header-row">
            <div class="bp-title-block">
              <span class="bp-icon">${icons.compass(18)}</span>
              <h3 class="bp-title">${escapeHtml(doc.title || activeBlueprint.title || '试卷设置')}</h3>
              <span class="status-pill status-pill-${activeBlueprint.status || 'draft'}">${formatBpStatus(activeBlueprint.status)}</span>
            </div>
            <div class="bp-meta-pills">
              <span class="meta-pill">时长: ${doc.duration_minutes || 60} 分钟</span>
              <span class="meta-pill">题量: ${totalQuestions} 题</span>
              <span class="meta-pill">满分: ${totalPoints} 分</span>
              <span class="meta-pill">难度: ${escapeHtml(doc.difficulty || 'medium')}</span>
            </div>
          </div>

          ${
            doc.prompt || activeBlueprint.prompt
              ? `
            <div class="blueprint-prompt-box">
              <span class="prompt-label">自然语言要求:</span>
              <p class="prompt-text">${escapeHtml(doc.prompt || activeBlueprint.prompt)}</p>
            </div>
          `
              : ''
          }
        </div>

        <!-- Question Types Distribution -->
        <div class="blueprint-section">
          <h4 class="section-heading">${icons.layers(14)} 题型与分值分布</h4>
          <div class="dist-grid">
            ${
              questionsDist.length === 0
                ? `<div class="dist-card"><span class="dist-name">综合题型</span><span class="dist-val">${totalQuestions} 题 · ${totalPoints} 分</span></div>`
                : questionsDist
                    .map(
                      (q) => `
                  <div class="dist-card">
                    <span class="dist-name">${formatQuestionType(q.type)}</span>
                    <div class="dist-detail">
                      <span class="dist-count">${q.count} 题</span>
                      <span class="dist-points">每题 ${q.points_per_question || 5} 分</span>
                    </div>
                  </div>
                `
                    )
                    .join('')
            }
          </div>
        </div>
      </div>
    `;
  }

  if (examStudioSubTab === 'draft') {
    if (!activeDraft) {
      return `
        <div class="workspace-empty-state">
          <div class="empty-icon">${icons.sparkles(28)}</div>
          <h4 class="empty-title">暂无生成中的题目草稿</h4>
          <p class="empty-subtitle">请先在「试卷设置」确认蓝图，并点击「开始组题」。</p>
          <div class="empty-actions-row">
            <button type="button" class="btn-primary-glow" id="btn-goto-blueprint-tab">
              ${icons.compass(14)} 查看试卷设置
            </button>
          </div>
        </div>
      `;
    }

    const questions = activeDraft.questions || [];

    return `
      <div class="draft-detail-container">
        <div class="draft-header-card">
          <div class="draft-title-row">
            <span class="draft-icon">${icons.sparkles(18)}</span>
            <h3 class="draft-title">${escapeHtml(activeDraft.title || '试题草稿')}</h3>
            <span class="status-pill status-pill-${activeDraft.status || 'draft'}">${formatDraftStatus(activeDraft.status)}</span>
          </div>
          <div class="draft-meta-row">
            <span>总题数: ${questions.length} 题</span>
            <span>·</span>
            <span>已生成: ${questions.filter((q) => q.status === 'completed' || q.status === 'ready' || q.stem).length} 题</span>
          </div>
        </div>

        <!-- Questions List -->
        <div class="draft-questions-list">
          ${
            questions.length === 0
              ? `<div class="empty-questions-hint">暂无题目内容</div>`
              : questions
                  .map((q, idx) => renderDraftQuestionCard(q, idx, activeDraft.id))
                  .join('')
          }
        </div>
      </div>
    `;
  }

  if (examStudioSubTab === 'exams') {
    if (!activeExam) {
      return `
        <div class="workspace-empty-state">
          <div class="empty-icon">${icons.target(28)}</div>
          <h4 class="empty-title">还没有已发布的试卷</h4>
          <p class="empty-subtitle">完成题目草稿后发布，即可在此查看排版并开始作答。</p>
          <div class="empty-actions-row">
            <button type="button" class="btn-primary-glow" id="btn-goto-drafts-tab">
              ${icons.sparkles(14)} 查看题目草稿
            </button>
          </div>
        </div>
      `;
    }

    const doc = activeExam.document || activeExam;
    const questions = doc.questions || [];

    return `
      <div class="exam-published-container">
        <div class="published-header-card">
          <div class="exam-title-row">
            <span class="exam-icon">${icons.target(18)}</span>
            <h3 class="exam-title">${escapeHtml(doc.title || activeExam.title || '期末自测卷')}</h3>
            <span class="status-pill status-pill-ready">已发布</span>
          </div>
          <div class="exam-meta-row">
            <span>总题量: ${questions.length} 题</span>
            <span>·</span>
            <span>满分: ${doc.total_score || 100} 分</span>
            <span>·</span>
            <span>时长: ${doc.duration_minutes || 60} 分钟</span>
            <span>·</span>
            <span>版本: v${activeExam.version_count || 1}</span>
          </div>
        </div>

        <!-- Questions Preview -->
        <div class="published-questions-preview">
          ${questions
            .map(
              (q, idx) => `
            <div class="published-question-card">
              <div class="q-header">
                <span class="q-num">第 ${idx + 1} 题</span>
                <span class="q-type-badge">${formatQuestionType(q.type)}</span>
                <span class="q-points">${q.points || 5} 分</span>
              </div>
              <div class="q-stem">${escapeHtml(q.stem || '')}</div>
              ${
                q.options && q.options.length > 0
                  ? `
                <div class="q-options-list">
                  ${q.options
                    .map(
                      (opt, oIdx) => `
                    <div class="q-opt-item">
                      <span class="opt-label">${String.fromCharCode(65 + oIdx)}.</span>
                      <span class="opt-text">${escapeHtml(opt.text || opt)}</span>
                    </div>
                  `
                    )
                    .join('')}
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

  return '';
}

function renderDraftQuestionCard(q, idx, draftId) {
  const isFailed = q.status === 'failed';
  const isGenerating = q.status === 'generating' || q.status === 'queued';

  return `
    <div class="draft-question-card ${isFailed ? 'is-failed' : ''}" data-question-id="${q.id}">
      <div class="q-card-header">
        <div class="q-header-left">
          <span class="q-index-badge">第 ${idx + 1} 题</span>
          <span class="q-type-tag">${formatQuestionType(q.type)}</span>
          <span class="q-points-tag">${q.points || 5} 分</span>
        </div>
        <div class="q-header-right">
          ${
            isFailed
              ? `
            <button
              type="button"
              class="btn-danger-sm btn-retry-draft-question"
              data-draft-id="${draftId}"
              data-question-id="${q.id}"
              title="重试生成此题"
            >
              ${icons.refreshCw(12)} 重试
            </button>
          `
              : ''
          }
        </div>
      </div>

      <div class="q-card-body">
        ${
          isGenerating
            ? `
          <div class="q-generating-placeholder">
            <span class="spinner-inline"></span>
            <span>正在根据知识点生成题干与选项...</span>
          </div>
        `
            : `
          <div class="q-stem-text">${escapeHtml(q.stem || '（题干生成中...）')}</div>
          ${
            q.options && q.options.length > 0
              ? `
            <div class="q-options-preview">
              ${q.options
                .map(
                  (opt, oIdx) => `
                <div class="q-opt-preview-item">
                  <span class="opt-key">${String.fromCharCode(65 + oIdx)}.</span>
                  <span class="opt-val">${escapeHtml(opt.text || opt)}</span>
                </div>
              `
                )
                .join('')}
            </div>
          `
              : ''
          }
          ${
            q.answer
              ? `
            <div class="q-answer-box">
              <span class="ans-label">参考答案:</span>
              <span class="ans-val">${escapeHtml(typeof q.answer === 'object' ? JSON.stringify(q.answer) : String(q.answer))}</span>
            </div>
          `
              : ''
          }
        `
        }
      </div>
    </div>
  `;
}

function attachQuizGenEvents(container, state, handlers) {
  // Stage tabs
  const tabBp = container.querySelector('#btn-tab-blueprints');
  const tabDraft = container.querySelector('#btn-tab-drafts');
  const tabExams = container.querySelector('#btn-tab-exams');

  if (tabBp) tabBp.onclick = () => handlers.onSelectExamStudioSubTab?.('blueprint');
  if (tabDraft) tabDraft.onclick = () => handlers.onSelectExamStudioSubTab?.('draft');
  if (tabExams) tabExams.onclick = () => handlers.onSelectExamStudioSubTab?.('exams');

  // Drawer
  const drawerBackdrop = container.querySelector('#quiz-drawer-backdrop');
  const openDrawerBtn = container.querySelector('#btn-open-quiz-drawer');
  const closeDrawerBtn = container.querySelector('#btn-close-quiz-drawer');

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

  // Focus Chat for Quiz prompt
  const focusChatBtn = container.querySelector('#btn-focus-chat-for-quiz');
  if (focusChatBtn) {
    focusChatBtn.onclick = () => {
      const textarea = document.querySelector('#chat-input-textarea');
      if (textarea) {
        textarea.value = '根据当前资料，出一套期末自测卷，包含10道选择题与2道大题';
        textarea.focus();
      }
    };
  }

  // Create Blueprint
  const createBpBtn = container.querySelector('#btn-trigger-create-blueprint');
  const emptyNewBpBtn = container.querySelector('#btn-empty-new-blueprint');
  const drawerNewBpBtn = container.querySelector('#btn-drawer-create-blueprint');

  const triggerCreateBp = () => {
    closeDrawer();
    handlers.onOpenBlueprintModal?.();
  };

  if (createBpBtn) createBpBtn.onclick = triggerCreateBp;
  if (emptyNewBpBtn) emptyNewBpBtn.onclick = triggerCreateBp;
  if (drawerNewBpBtn) drawerNewBpBtn.onclick = triggerCreateBp;

  // Confirm Blueprint
  const confirmBpBtn = container.querySelector('#btn-confirm-blueprint');
  if (confirmBpBtn) {
    confirmBpBtn.onclick = () => {
      const bpId = state.activeBlueprint?.id;
      if (bpId) handlers.onConfirmBlueprint?.(bpId);
    };
  }

  // Generate Draft from Blueprint
  const generateDraftBtn = container.querySelector('#btn-generate-draft-from-bp');
  if (generateDraftBtn) {
    generateDraftBtn.onclick = () => {
      const bpId = state.activeBlueprint?.id;
      if (bpId) handlers.onGenerateDraftFromBlueprint?.(bpId);
    };
  }

  // Publish Draft
  const publishDraftBtn = container.querySelector('#btn-publish-draft-exam');
  if (publishDraftBtn) {
    publishDraftBtn.onclick = () => {
      const draftId = state.activeDraft?.id;
      if (draftId) handlers.onPublishDraft?.(draftId);
    };
  }

  // Go to Attempt Exam
  const gotoAttemptBtn = container.querySelector('#btn-goto-attempt-exam');
  if (gotoAttemptBtn) {
    gotoAttemptBtn.onclick = () => {
      const examId = state.activeExam?.id;
      if (examId) handlers.onStartAttempt?.(examId, 'practice');
    };
  }

  // Export Exam
  const exportExamBtn = container.querySelector('#btn-export-exam-doc');
  if (exportExamBtn) {
    exportExamBtn.onclick = () => {
      const examId = state.activeExam?.id;
      if (examId) handlers.onExportExam?.(examId, 'pdf', 'questions');
    };
  }

  // Retry Draft Question
  container.querySelectorAll('.btn-retry-draft-question').forEach((btn) => {
    btn.onclick = () => {
      const draftId = btn.getAttribute('data-draft-id');
      const qid = btn.getAttribute('data-question-id');
      handlers.onRetryDraftQuestion?.(draftId, qid);
    };
  });

  // Stage Switch Shortcuts
  const gotoBpTab = container.querySelector('#btn-goto-blueprint-tab') || container.querySelector('#btn-switch-to-blueprint-stage');
  if (gotoBpTab) gotoBpTab.onclick = () => handlers.onSelectExamStudioSubTab?.('blueprint');

  const gotoDraftsTab = container.querySelector('#btn-goto-drafts-tab');
  if (gotoDraftsTab) gotoDraftsTab.onclick = () => handlers.onSelectExamStudioSubTab?.('draft');

  // Select item from drawer
  container.querySelectorAll('.drawer-item').forEach((el) => {
    el.onclick = () => {
      const type = el.getAttribute('data-type');
      const id = el.getAttribute('data-id');
      closeDrawer();
      if (type === 'blueprint') {
        handlers.onSelectBlueprint?.(id);
      } else if (type === 'draft') {
        handlers.onSelectDraft?.(id);
      } else if (type === 'exam') {
        handlers.onSelectExam?.(id);
      }
    };
  });
}

function formatBpStatus(st) {
  if (st === 'confirmed') return '已确认';
  if (st === 'generating') return '组题中';
  if (st === 'draft') return '草稿';
  return st || '草稿';
}

function formatDraftStatus(st) {
  if (st === 'completed' || st === 'ready') return '就绪';
  if (st === 'generating') return '生成中';
  if (st === 'failed') return '有失败题';
  return st || '生成中';
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
