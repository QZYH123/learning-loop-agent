/**
 * Exam Studio Component (3-Step Integrated Workflow)
 * Aligned with Tickets 08, 09, 13, 18:
 * Step 1: 蓝图构思 (Blueprint) -> Step 2: 增量试题实验室 (Draft Lab) -> Step 3: 正式试卷与 AI 修订 (Exam & Revision)
 * Strict OpenAPI Contract Alignment throughout.
 */

import { icons } from '../icons.js';

export function renderExamStudioView(state, container, handlers) {
  const {
    examStudioSubTab = 'blueprint',
    blueprints = [],
    activeBlueprintId,
    drafts = [],
    activeDraftId,
    exams = [],
    activeExamId,
    revisionProposals = [],
    activeRevisionProposalId,
    examVersions = [],
    sidebarCollapsed = {}
  } = state;

  const isCollapsed = !!sidebarCollapsed.exam_studio;
  const activeBp = blueprints.find((b) => b.id === activeBlueprintId) || blueprints[0] || null;
  const activeDraft = drafts.find((d) => d.id === activeDraftId) || drafts[0] || null;
  const activeExam = exams.find((e) => e.id === activeExamId) || exams[0] || null;
  const activeProposal = revisionProposals.find((p) => p.id === activeRevisionProposalId) || revisionProposals[0] || null;

  container.innerHTML = `
    <div class="learning-workspace-layout ${isCollapsed ? 'is-sidebar-collapsed' : ''}" data-testid="exam-studio-workspace">
      <!-- Left Sidebar: Steps & Resources Drawer -->
      <aside class="workspace-sidebar" id="exam-studio-sidebar">
        <!-- Sidebar Header -->
        <div class="sidebar-header-row">
          <div class="sidebar-title-block">
            ${icons.compass(15)}
            <span class="sidebar-title-text">组卷工坊</span>
          </div>
          <div class="sidebar-actions-block">
            <button
              type="button"
              class="btn-icon-sidebar"
              id="btn-toggle-studio-sidebar"
              title="${isCollapsed ? '展开侧栏' : '收起侧栏'}"
            >
              ${isCollapsed ? icons.panelLeftOpen(15) : icons.panelLeftClose(15)}
            </button>
          </div>
        </div>

        <!-- 3-Step Stepper Navigation -->
        <div class="studio-stepper-nav">
          <button
            type="button"
            class="studio-step-btn ${examStudioSubTab === 'blueprint' ? 'is-active' : ''}"
            data-studio-subtab="blueprint"
          >
            <span class="step-num-badge">1</span>
            <div class="step-btn-info">
              <span class="step-btn-title">蓝图构思</span>
              <span class="step-btn-count">${blueprints.length} 份蓝图</span>
            </div>
          </button>

          <button
            type="button"
            class="studio-step-btn ${examStudioSubTab === 'draft' ? 'is-active' : ''}"
            data-studio-subtab="draft"
          >
            <span class="step-num-badge">2</span>
            <div class="step-btn-info">
              <span class="step-btn-title">试题实验室</span>
              <span class="step-btn-count">${drafts.length} 份草稿</span>
            </div>
          </button>

          <button
            type="button"
            class="studio-step-btn ${examStudioSubTab === 'exam' ? 'is-active' : ''}"
            data-studio-subtab="exam"
          >
            <span class="step-num-badge">3</span>
            <div class="step-btn-info">
              <span class="step-btn-title">正式试卷与修订</span>
              <span class="step-btn-count">${exams.length} 套试卷</span>
            </div>
          </button>
        </div>

        <div class="dropdown-divider" style="margin: 8px 12px;"></div>

        <!-- Top Action Button per Step -->
        <div class="sidebar-top-action-bar">
          ${
            examStudioSubTab === 'blueprint'
              ? `
            <button type="button" class="btn-primary btn-sm btn-block" id="btn-open-create-blueprint">
              ${icons.plus(13)} 构思新蓝图...
            </button>
          `
              : examStudioSubTab === 'draft' && activeDraft
              ? `
            <button
              type="button"
              class="btn-primary btn-sm btn-block"
              id="btn-publish-draft"
              ${activeDraft.status === 'published' ? 'disabled' : ''}
            >
              ${icons.check(13)} ${activeDraft.status === 'published' ? '已发布为试卷' : '发布为正式试卷'}
            </button>
          `
              : examStudioSubTab === 'exam' && activeExam
              ? `
            <button type="button" class="btn-primary btn-sm btn-block" id="btn-open-exam-revision">
              ${icons.edit3(13)} AI 修改试卷提案...
            </button>
          `
              : ''
          }
        </div>

        <!-- Scrollable List for Current Step's Items -->
        <div class="sidebar-scrollable-list" id="studio-items-scroll">
          ${
            examStudioSubTab === 'blueprint'
              ? renderBlueprintsList(blueprints, activeBlueprintId)
              : examStudioSubTab === 'draft'
              ? renderDraftsList(drafts, activeDraftId)
              : renderExamsList(exams, activeExamId)
          }
        </div>
      </aside>

      <!-- Main Step Workspace Body -->
      <main class="workspace-main-content" id="exam-studio-main">
        ${
          isCollapsed
            ? `
          <button
            type="button"
            class="btn-sidebar-floating-expand"
            id="btn-floating-expand-studio"
            title="展开工坊侧栏"
          >
            ${icons.panelLeftOpen(15)}
            <span>${examStudioSubTab === 'blueprint' ? '蓝图列表' : examStudioSubTab === 'draft' ? '草稿列表' : '试卷列表'}</span>
          </button>
        `
            : ''
        }

        ${
          examStudioSubTab === 'blueprint'
            ? renderBlueprintDetail(activeBp, state)
            : examStudioSubTab === 'draft'
            ? renderDraftDetail(activeDraft, state)
            : renderExamDetail(activeExam, examVersions, revisionProposals, activeProposal, state)
        }
      </main>
    </div>
  `;

  // Attach Event Handlers
  attachStudioEvents(container, state, handlers);
}

function renderBlueprintsList(blueprints, activeBlueprintId) {
  if (!blueprints || blueprints.length === 0) {
    return `
      <div class="sidebar-empty-state">
        <div class="sidebar-empty-icon">${icons.compass(22)}</div>
        <div class="sidebar-empty-text">暂无组卷蓝图</div>
        <div class="sidebar-empty-subtext">点击上方按钮输入要求，由 AI 解析生成题型与考点结构。</div>
      </div>
    `;
  }

  return blueprints
    .map((bp) => {
      const isSelected = bp.id === activeBlueprintId;
      const isConfirmed = bp.status === 'confirmed';

      return `
      <div
        class="standard-card-item ${isSelected ? 'is-selected' : ''}"
        data-action="select-blueprint"
        data-blueprint-id="${bp.id}"
        role="button"
        tabindex="0"
      >
        <div class="source-card-header">
          <div class="source-title-row">
            ${icons.compass(14)}
            <span class="source-card-title" title="${escapeHtml(bp.title || bp.prompt || '组卷蓝图')}">
              ${escapeHtml(bp.title || bp.prompt || '组卷蓝图')}
            </span>
          </div>
          <span class="grounding-tag-chip ${isConfirmed ? 'grounding-covered' : ''}">
            ${isConfirmed ? '已确认' : '构思草稿'}
          </span>
        </div>
        <div class="source-card-meta">
          <span>总分 ${bp.total_score || 20} 分</span>
          <span>${bp.question_plan?.length || 0} 类题型</span>
          <span>${formatTimestamp(bp.created_at)}</span>
        </div>
      </div>
    `;
    })
    .join('');
}

function renderDraftsList(drafts, activeDraftId) {
  if (!drafts || drafts.length === 0) {
    return `
      <div class="sidebar-empty-state">
        <div class="sidebar-empty-icon">${icons.edit3(22)}</div>
        <div class="sidebar-empty-text">暂无试题草稿</div>
        <div class="sidebar-empty-subtext">确认蓝图后点击“开始增量组题”在此逐题生成与修改。</div>
      </div>
    `;
  }

  return drafts
    .map((dr) => {
      const isSelected = dr.id === activeDraftId;
      const questionsCount = dr.questions?.length || 0;
      const completedCount = (dr.questions || []).filter((q) => q.status === 'complete').length;

      return `
      <div
        class="standard-card-item ${isSelected ? 'is-selected' : ''}"
        data-action="select-draft"
        data-draft-id="${dr.id}"
        role="button"
        tabindex="0"
      >
        <div class="source-card-header">
          <div class="source-title-row">
            ${icons.edit3(14)}
            <span class="source-card-title" title="${escapeHtml(dr.title || '试题草稿')}">
              ${escapeHtml(dr.title || '试题草稿')}
            </span>
          </div>
          <span class="grounding-tag-chip ${dr.status === 'published' ? 'grounding-covered' : ''}">
            ${dr.status === 'published' ? '已发布' : `${completedCount}/${questionsCount} 题`}
          </span>
        </div>
        <div class="source-card-meta">
          <span>总分 ${dr.total_score || 20} 分</span>
          <span>${formatTimestamp(dr.created_at)}</span>
        </div>
      </div>
    `;
    })
    .join('');
}

function renderExamsList(exams, activeExamId) {
  if (!exams || exams.length === 0) {
    return `
      <div class="sidebar-empty-state">
        <div class="sidebar-empty-icon">${icons.target(22)}</div>
        <div class="sidebar-empty-text">暂无正式试卷</div>
        <div class="sidebar-empty-subtext">在试题实验室确认题目后点击“发布”即可生成正式试卷。</div>
      </div>
    `;
  }

  return exams
    .map((ex) => {
      const isSelected = ex.id === activeExamId;
      const qCount = ex.questions?.length || 0;

      return `
      <div
        class="standard-card-item ${isSelected ? 'is-selected' : ''}"
        data-action="select-exam-item"
        data-exam-id="${ex.id}"
        role="button"
        tabindex="0"
      >
        <div class="source-card-header">
          <div class="source-title-row">
            ${icons.target(14)}
            <span class="source-card-title" title="${escapeHtml(ex.title || '正式试卷')}">
              ${escapeHtml(ex.title || '正式试卷')}
            </span>
          </div>
          <span class="grounding-tag-chip grounding-covered">正式</span>
        </div>
        <div class="source-card-meta">
          <span>${qCount} 道题 · ${ex.total_score || 100} 分</span>
          <span>${formatTimestamp(ex.created_at)}</span>
        </div>
      </div>
    `;
    })
    .join('');
}

function renderBlueprintDetail(bp, state) {
  if (!bp) {
    return `
      <div class="detail-empty-container">
        <div class="empty-state-icon-circle">${icons.compass(24)}</div>
        <div class="empty-state-title">未选择组卷蓝图</div>
        <div class="empty-state-desc">点击左侧蓝图查看构思安排，或点击“构思新蓝图”输入提示词生成。</div>
      </div>
    `;
  }

  const isConfirmed = bp.status === 'confirmed';

  return `
    <div class="studio-detail-container" data-testid="blueprint-detail-view">
      <!-- Header -->
      <header class="detail-header-bar">
        <div class="detail-header-info">
          <div style="display: flex; align-items: center; gap: 8px;">
            ${icons.compass(18)}
            <h2 class="detail-title-text">${escapeHtml(bp.title || bp.prompt || '组卷蓝图')}</h2>
            <span class="grounding-tag-chip ${isConfirmed ? 'grounding-covered' : ''}">
              ${isConfirmed ? '已确认' : '构思草案'}
            </span>
          </div>
          <div class="detail-meta-row">
            <span>总分目标: ${bp.total_score || 20} 分</span>
            <span>难度系数: ${escapeHtml(bp.difficulty || 'medium')}</span>
            <span>知识依据: ${escapeHtml(bp.grounding_mode || 'general-knowledge')}</span>
          </div>
        </div>

        <div class="detail-header-actions">
          ${
            !isConfirmed
              ? `
            <button type="button" class="btn-primary btn-sm" id="btn-confirm-blueprint" data-blueprint-id="${bp.id}">
              ${icons.check(13)} 确认蓝图
            </button>
          `
              : `
            <button type="button" class="btn-primary btn-sm" id="btn-generate-draft-from-bp" data-blueprint-id="${bp.id}">
              ${icons.play(13)} 基于蓝图增量组题...
            </button>
          `
          }
          <button type="button" class="btn-icon-subtle btn-delete-subtle" id="btn-delete-blueprint" data-blueprint-id="${bp.id}" title="删除蓝图">
            ${icons.trash2(14)}
          </button>
        </div>
      </header>

      <!-- Main Body: Question Plan Table & Topics -->
      <div class="studio-detail-body">
        <div class="blueprint-prompt-card">
          <div class="blueprint-card-label">原始组卷诉求:</div>
          <div class="blueprint-prompt-text">"${escapeHtml(bp.prompt || '根据讲义提炼核心试题')}"</div>
        </div>

        <div class="blueprint-plan-card">
          <div class="blueprint-card-label">题型与题量规划 (Question Plan):</div>
          <table class="standard-table">
            <thead>
              <tr>
                <th>题型</th>
                <th>题量</th>
                <th>单题分值</th>
                <th>小计</th>
                <th>考察考点与目标</th>
              </tr>
            </thead>
            <tbody>
              ${
                (bp.question_plan || [])
                  .map(
                    (p) => `
                <tr>
                  <td><strong>${formatQuestionType(p.type)}</strong></td>
                  <td>${p.count} 道</td>
                  <td>${p.points_per_question} 分</td>
                  <td><strong>${p.count * p.points_per_question} 分</strong></td>
                  <td>${escapeHtml(p.topics?.join('、 ') || p.topic || '基础概念与推演')}</td>
                </tr>
              `
                  )
                  .join('')
              }
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

function renderDraftDetail(draft, state) {
  if (!draft) {
    return `
      <div class="detail-empty-container">
        <div class="empty-state-icon-circle">${icons.edit3(24)}</div>
        <div class="empty-state-title">未选择试题草稿</div>
        <div class="empty-state-desc">在左侧选择草稿进行题目重试、修改，或在步骤 1 中基于蓝图生成。</div>
      </div>
    `;
  }

  const questions = draft.questions || [];
  const completed = questions.filter((q) => q.status === 'complete').length;

  return `
    <div class="studio-detail-container" data-testid="draft-detail-view">
      <!-- Header -->
      <header class="detail-header-bar">
        <div class="detail-header-info">
          <div style="display: flex; align-items: center; gap: 8px;">
            ${icons.edit3(18)}
            <h2 class="detail-title-text">${escapeHtml(draft.title || '试题草稿实验室')}</h2>
            <span class="grounding-tag-chip ${draft.status === 'published' ? 'grounding-covered' : ''}">
              ${draft.status === 'published' ? '已发布' : `生成进度: ${completed}/${questions.length}`}
            </span>
          </div>
          <div class="detail-meta-row">
            <span>题目总数: ${questions.length} 题</span>
            <span>总分: ${draft.total_score || 20} 分</span>
          </div>
        </div>

        <div class="detail-header-actions">
          <button
            type="button"
            class="btn-primary btn-sm"
            id="btn-publish-draft-main"
            data-draft-id="${draft.id}"
            ${draft.status === 'published' ? 'disabled' : ''}
          >
            ${icons.check(13)} ${draft.status === 'published' ? '已发布为试卷' : '确认并发布正式试卷'}
          </button>
        </div>
      </header>

      <!-- Incremental Question Slots Grid -->
      <div class="draft-questions-scroll">
        ${
          questions.length === 0
            ? `<div class="empty-anchors-note">草稿中暂无题目槽位。</div>`
            : questions
                .map((q, idx) => {
                  const isDone = q.status === 'complete';
                  const isFailed = q.status === 'failed';
                  const isGen = q.status === 'generating' || q.status === 'queued';

                  return `
            <div class="draft-question-slot-card ${isDone ? 'is-complete' : isFailed ? 'is-failed' : 'is-generating'}">
              <div class="slot-header-row">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span class="slot-num-badge">${idx + 1}</span>
                  <span class="slot-type-badge">${formatQuestionType(q.type || q.question?.type)}</span>
                  <span class="slot-points-badge">${q.points || q.question?.points || 2} 分</span>
                </div>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span class="grounding-tag-chip ${isDone ? 'grounding-covered' : isFailed ? 'grounding-not-covered' : ''}">
                    ${isDone ? '生成完毕' : isFailed ? '生成失败' : '正在增量出题...'}
                  </span>
                  <button
                    type="button"
                    class="btn-icon-subtle"
                    data-action="retry-draft-question"
                    data-draft-id="${draft.id}"
                    data-question-id="${q.id}"
                    title="单独重新生成此题"
                  >
                    ${icons.rotateCw(13)} 重试
                  </button>
                </div>
              </div>

              <!-- Question Content Area -->
              <div class="slot-body-content">
                ${
                  isGen
                    ? `<div class="slot-loading-state">${icons.rotateCw(14, 'spin')} 正在依据资料推演并生成题目与解析...</div>`
                    : isFailed
                    ? `<div class="slot-failed-state">${icons.alertTriangle(14)} 生成失败，请点击重试。</div>`
                    : `
                    <div class="slot-prompt-text">${escapeHtml(q.prompt || q.question?.prompt || '')}</div>
                    ${renderQuestionOptionsPreview(q)}
                    <div class="slot-solution-preview">
                      <span class="slot-solution-label">答案与解析:</span>
                      <span>${escapeHtml(q.explanation || q.question?.explanation || q.answer || q.question?.answer || '已包含')}</span>
                    </div>
                  `
                }
              </div>
            </div>
          `;
                })
                .join('')
        }
      </div>
    </div>
  `;
}

function renderExamDetail(exam, versions = [], proposals = [], activeProposal, state) {
  if (!exam) {
    return `
      <div class="detail-empty-container">
        <div class="empty-state-icon-circle">${icons.target(24)}</div>
        <div class="empty-state-title">未选择正式试卷</div>
        <div class="empty-state-desc">在左侧列表中选择试卷进行 AI 修改、版本管理或导出。</div>
      </div>
    `;
  }

  const questions = exam.questions || [];

  return `
    <div class="studio-detail-container" data-testid="exam-detail-view">
      <!-- Header -->
      <header class="detail-header-bar">
        <div class="detail-header-info">
          <div style="display: flex; align-items: center; gap: 8px;">
            ${icons.target(18)}
            <h2 class="detail-title-text">${escapeHtml(exam.title || '正式试卷')}</h2>
            <span class="grounding-tag-chip grounding-covered">正式试卷</span>
          </div>
          <div class="detail-meta-row">
            <span>总题数: ${questions.length} 题</span>
            <span>总分值: ${exam.total_score || 100} 分</span>
          </div>
        </div>

        <div class="detail-header-actions">
          <button
            type="button"
            class="btn-primary btn-sm"
            id="btn-open-exam-revision-modal"
            data-exam-id="${exam.id}"
            title="向 AI 提出修改要求并生成结构化差异"
          >
            ${icons.edit3(13)} AI 修改提案...
          </button>

          <button
            type="button"
            class="btn-secondary btn-sm"
            id="btn-undo-exam-change"
            data-exam-id="${exam.id}"
            title="撤销上一次试卷修改"
          >
            ${icons.undo(13)} 撤销
          </button>

          <button
            type="button"
            class="btn-secondary btn-sm"
            id="btn-redo-exam-change"
            data-exam-id="${exam.id}"
            title="重做试卷修改"
          >
            ${icons.redo(13)} 重做
          </button>
        </div>
      </header>

      <!-- Active Revision Proposal Banner (Ticket 13) -->
      ${
        activeProposal && activeProposal.status === 'pending'
          ? `
        <div class="revision-proposal-diff-banner">
          <div class="diff-banner-header">
            <div style="display: flex; align-items: center; gap: 6px; font-weight: 700; color: #1e40af;">
              ${icons.edit3(14)}
              <span>AI 试卷修改提案 (待确认)</span>
            </div>
            <div style="display: flex; gap: 8px;">
              <button type="button" class="btn-primary btn-sm" id="btn-apply-exam-proposal" data-proposal-id="${activeProposal.id}">
                ${icons.check(13)} 应用提案
              </button>
              <button type="button" class="btn-secondary btn-sm" id="btn-discard-exam-proposal" data-proposal-id="${activeProposal.id}">
                ${icons.x(13)} 放弃提案
              </button>
            </div>
          </div>
          <div class="diff-instruction-quote">
            <strong>修改指令:</strong> "${escapeHtml(activeProposal.instruction || '')}"
          </div>
        </div>
      `
          : ''
      }

      <!-- Questions List View -->
      <div class="draft-questions-scroll">
        ${questions
          .map(
            (q, idx) => `
          <div class="exam-question-item-card">
            <div class="slot-header-row">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span class="slot-num-badge">${idx + 1}</span>
                <span class="slot-type-badge">${formatQuestionType(q.type)}</span>
                <span class="slot-points-badge">${q.points || 2} 分</span>
              </div>
            </div>
            <div class="slot-prompt-text">${escapeHtml(q.prompt || '')}</div>
            ${renderQuestionOptionsPreview(q)}
            <div class="slot-solution-preview">
              <span class="slot-solution-label">答案与评分标准:</span>
              <span>${escapeHtml(q.answer || q.explanation || '标准答案')}</span>
            </div>
          </div>
        `
          )
          .join('')}
      </div>
    </div>
  `;
}

function renderQuestionOptionsPreview(q) {
  const options = q.options || q.question?.options;
  if (!Array.isArray(options) || options.length === 0) return '';
  return `
    <div class="slot-options-list">
      ${options
        .map(
          (opt, idx) => `
        <div class="slot-option-row">
          <span class="option-letter">${String.fromCharCode(65 + idx)}.</span>
          <span>${escapeHtml(typeof opt === 'string' ? opt : opt.text || opt.content || '')}</span>
        </div>
      `
        )
        .join('')}
    </div>
  `;
}

function attachStudioEvents(container, state, handlers) {
  // Sidebar Toggle
  const toggleBtn = container.querySelector('#btn-toggle-studio-sidebar');
  if (toggleBtn) toggleBtn.onclick = () => handlers.onToggleSidebar?.('exam_studio');

  const floatingBtn = container.querySelector('#btn-floating-expand-studio');
  if (floatingBtn) floatingBtn.onclick = () => handlers.onToggleSidebar?.('exam_studio');

  // Subtab Navigation
  container.querySelectorAll('[data-studio-subtab]').forEach((btn) => {
    btn.onclick = () => {
      const subtab = btn.getAttribute('data-studio-subtab');
      handlers.onSelectExamStudioSubTab?.(subtab);
    };
  });

  // Create Blueprint Modal
  const createBpBtn = container.querySelector('#btn-open-create-blueprint');
  if (createBpBtn) createBpBtn.onclick = () => handlers.onOpenBlueprintModal?.();

  // Select Blueprint
  container.querySelectorAll('[data-action="select-blueprint"]').forEach((card) => {
    card.onclick = () => {
      const id = card.getAttribute('data-blueprint-id');
      handlers.onSelectBlueprint?.(id);
    };
  });

  // Confirm Blueprint
  const confirmBpBtn = container.querySelector('#btn-confirm-blueprint');
  if (confirmBpBtn) {
    confirmBpBtn.onclick = () => {
      const id = confirmBpBtn.getAttribute('data-blueprint-id');
      handlers.onConfirmBlueprint?.(id);
    };
  }

  // Generate Draft from Blueprint
  const genDraftBtn = container.querySelector('#btn-generate-draft-from-bp');
  if (genDraftBtn) {
    genDraftBtn.onclick = () => {
      const id = genDraftBtn.getAttribute('data-blueprint-id');
      handlers.onGenerateDraftFromBlueprint?.(id);
    };
  }

  // Select Draft
  container.querySelectorAll('[data-action="select-draft"]').forEach((card) => {
    card.onclick = () => {
      const id = card.getAttribute('data-draft-id');
      handlers.onSelectDraft?.(id);
    };
  });

  // Retry Draft Question
  container.querySelectorAll('[data-action="retry-draft-question"]').forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const dId = btn.getAttribute('data-draft-id');
      const qId = btn.getAttribute('data-question-id');
      handlers.onRetryDraftQuestion?.(dId, qId);
    };
  });

  // Publish Draft
  const publishDraftBtn = container.querySelector('#btn-publish-draft');
  if (publishDraftBtn) {
    publishDraftBtn.onclick = () => {
      if (state.activeDraftId) handlers.onPublishDraft?.(state.activeDraftId);
    };
  }
  const publishDraftMainBtn = container.querySelector('#btn-publish-draft-main');
  if (publishDraftMainBtn) {
    publishDraftMainBtn.onclick = () => {
      const dId = publishDraftMainBtn.getAttribute('data-draft-id');
      handlers.onPublishDraft?.(dId);
    };
  }

  // Select Exam Item
  container.querySelectorAll('[data-action="select-exam-item"]').forEach((card) => {
    card.onclick = () => {
      const id = card.getAttribute('data-exam-id');
      handlers.onSelectExam?.(id);
    };
  });

  // Exam Revision Modal
  const openExamRevBtn = container.querySelector('#btn-open-exam-revision-modal');
  if (openExamRevBtn) openExamRevBtn.onclick = () => handlers.onOpenRevisionModal?.();

  // Undo / Redo
  const undoBtn = container.querySelector('#btn-undo-exam-change');
  if (undoBtn) undoBtn.onclick = () => handlers.onUndoExamChange?.(state.activeExamId);

  const redoBtn = container.querySelector('#btn-redo-exam-change');
  if (redoBtn) redoBtn.onclick = () => handlers.onRedoExamChange?.(state.activeExamId);

  // Apply / Discard Exam Revision Proposal
  const applyExamPropBtn = container.querySelector('#btn-apply-exam-proposal');
  if (applyExamPropBtn) {
    applyExamPropBtn.onclick = () => {
      const pId = applyExamPropBtn.getAttribute('data-proposal-id');
      handlers.onApplyProposal?.(pId);
    };
  }

  const discardExamPropBtn = container.querySelector('#btn-discard-exam-proposal');
  if (discardExamPropBtn) {
    discardExamPropBtn.onclick = () => {
      const pId = discardExamPropBtn.getAttribute('data-proposal-id');
      handlers.onDiscardProposal?.(pId);
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
