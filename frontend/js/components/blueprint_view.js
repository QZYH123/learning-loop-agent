import { icons } from '../icons.js';

export function renderBlueprintView(state, container, handlers) {
  const blueprints = state.blueprints || [];
  const activeBlueprintId = state.activeBlueprintId;
  const activeBlueprint = blueprints.find((b) => b.id === activeBlueprintId) || blueprints[0] || null;

  container.innerHTML = `
    <div class="studio-pane-layout">
      <!-- Left Sidebar: Blueprints List -->
      <aside class="studio-pane-sidebar">
        <div class="pane-sidebar-header" style="display: flex; align-items: center; justify-content: space-between;">
          <h3 class="pane-title">
            <span>${icons.compass(18)}</span>
            <span>组卷蓝图</span>
          </h3>
          <button class="btn-primary-glow" id="btn-create-blueprint-prompt" style="padding: 4px 10px; font-size: 12px;">
            <span>${icons.plus(13)}</span>
            <span>设计蓝图</span>
          </button>
        </div>

        <div class="history-blueprints-list">
          ${
            blueprints.length === 0
              ? `<div style="text-align: center; padding: 24px 8px; color: var(--ink-muted); font-size: 12px;">暂无组卷蓝图，请点击上方按钮设计</div>`
              : blueprints
                  .map(
                    (bp) => `
                <div class="blueprint-list-item ${activeBlueprint?.id === bp.id ? 'is-selected' : ''}" data-blueprint-id="${bp.id}">
                  <div style="display: flex; align-items: center; justify-content: space-between;">
                    <span style="font-weight: 700; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 140px;">
                      ${escapeHtml(bp.title || bp.prompt || '组卷计划')}
                    </span>
                    <span class="status-pill status-pill-${bp.status || 'draft'}">${formatBpStatus(bp.status)}</span>
                  </div>
                  <div style="display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: var(--ink-muted); margin-top: 4px;">
                    <span>总分: ${bp.total_score || 20} 分</span>
                    <span>计划题数: ${bp.plans?.length || bp.question_count || 4} 题</span>
                  </div>
                </div>
              `
                  )
                  .join('')
          }
        </div>
      </aside>

      <!-- Right Main Content: Blueprint Workspace -->
      <main class="studio-pane-content">
        ${
          activeBlueprint
            ? `
          <div class="blueprint-detail-container">
            <div class="blueprint-detail-header">
              <div class="title-row">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="padding: 6px; background: var(--marker-yellow); border: var(--sketch-border-thin); border-radius: var(--sketch-radius-sm);">
                    ${icons.compass(18)}
                  </span>
                  <div>
                    <h2>${escapeHtml(activeBlueprint.title || '组卷蓝图架构')}</h2>
                    <span style="font-size: 12px; color: var(--ink-muted);">状态: ${formatBpStatus(activeBlueprint.status)} · 目标总分: ${activeBlueprint.total_score || 20} 分</span>
                  </div>
                </div>
              </div>

              <div class="action-buttons-row" style="display: flex; align-items: center; gap: 8px;">
                ${
                  activeBlueprint.status === 'draft'
                    ? `
                  <button class="btn-primary-glow" id="btn-confirm-blueprint">
                    <span>${icons.check(14)}</span>
                    <span>确认蓝图架构</span>
                  </button>
                `
                    : activeBlueprint.status === 'confirmed'
                      ? `
                  <button class="btn-primary-glow" id="btn-generate-draft-questions">
                    <span>${icons.sparkles(14)}</span>
                    <span>生成全套题目草稿</span>
                  </button>
                `
                      : ''
                }
              </div>
            </div>

            <!-- Prompt & Specifications -->
            <div class="section-card" style="padding: 16px; background: var(--bg-paper-alt); border: var(--sketch-border-thin); border-radius: var(--sketch-radius);">
              <div style="font-weight: 700; font-size: 13px; margin-bottom: 6px;">出题意图与要求 (Prompt)：</div>
              <div style="padding: 10px 14px; background: var(--bg-paper); border: 1px dashed var(--ink-light); border-radius: var(--sketch-radius-sm); font-size: 13px; color: var(--ink-secondary);">
                ${escapeHtml(activeBlueprint.prompt || '按课程核心考点组卷')}
              </div>
            </div>

            <!-- Question Plans List -->
            <div class="plans-section" style="display: flex; flex-direction: column; gap: 12px;">
              <div style="display: flex; align-items: center; justify-content: space-between;">
                <h4 style="font-family: var(--font-hand); font-size: 18px; font-weight: 700; display: flex; align-items: center; gap: 6px;">
                  <span>${icons.list(16)}</span>
                  <span>题目分布与考点规划 (${activeBlueprint.plans?.length || 0} 题)</span>
                </h4>
              </div>

              <div class="plans-grid">
                ${(activeBlueprint.plans || [])
                  .map(
                    (plan, idx) => `
                  <div class="plan-card">
                    <div style="display: flex; align-items: center; justify-content: space-between;">
                      <div style="display: flex; align-items: center; gap: 6px;">
                        <span class="score-pill">第 ${idx + 1} 题</span>
                        <span class="type-pill">${formatQuestionType(plan.type)}</span>
                        <span class="difficulty-pill">${formatDifficulty(plan.difficulty)}</span>
                      </div>
                      <span class="score-pill" style="background: var(--marker-yellow);">${plan.score || 5} 分</span>
                    </div>

                    <div style="font-weight: 700; font-size: 14px; margin-top: 4px;">
                      ${escapeHtml(plan.target_knowledge_point || plan.topic || '核心考点考查')}
                    </div>

                    ${
                      plan.requirements
                        ? `<div style="font-size: 12px; color: var(--ink-muted);">考查要求: ${escapeHtml(plan.requirements)}</div>`
                        : ''
                    }
                  </div>
                `
                  )
                  .join('')}
              </div>
            </div>
          </div>
        `
            : `
          <div class="copilot-empty-state">
            <div class="empty-glow-icon">${icons.compass(28)}</div>
            <h3 style="font-family: var(--font-hand); font-size: 22px;">尚未设计组卷蓝图</h3>
            <p style="font-size: 13px; color: var(--ink-muted); max-width: 320px;">
              输入出题诉求（例如"考查虚拟内存与分页机制，包含2道单选和1道简答"），系统将为您架构科学的题型与分值蓝图。
            </p>
            <button class="btn-primary-glow" id="btn-empty-create-blueprint" style="margin-top: 10px;">
              <span>${icons.plus(15)}</span>
              <span>立即设计组卷蓝图</span>
            </button>
          </div>
        `
        }
      </main>
    </div>
  `;

  // Attach handlers
  const btnCreate = container.querySelector('#btn-create-blueprint-prompt');
  const btnEmptyCreate = container.querySelector('#btn-empty-create-blueprint');
  const openCreateDialog = () => handlers.onOpenBlueprintModal?.();

  if (btnCreate) btnCreate.onclick = openCreateDialog;
  if (btnEmptyCreate) btnEmptyCreate.onclick = openCreateDialog;

  container.querySelectorAll('.blueprint-list-item').forEach((item) => {
    item.onclick = () => {
      const bpId = item.getAttribute('data-blueprint-id');
      handlers.onSelectBlueprint?.(bpId);
    };
  });

  const btnConfirm = container.querySelector('#btn-confirm-blueprint');
  if (btnConfirm && activeBlueprint) {
    btnConfirm.onclick = () => handlers.onConfirmBlueprint?.(activeBlueprint.id);
  }

  const btnGenerate = container.querySelector('#btn-generate-draft-questions');
  if (btnGenerate && activeBlueprint) {
    btnGenerate.onclick = () => handlers.onGenerateDraft?.(activeBlueprint.id);
  }
}

function formatBpStatus(st) {
  switch (st) {
    case 'draft':
      return '草案待确认';
    case 'confirmed':
      return '已确认';
    case 'generated':
      return '已生成试题';
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

function formatDifficulty(d) {
  switch (d) {
    case 'easy':
      return '基础';
    case 'hard':
      return '进阶';
    default:
      return '中等';
  }
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
