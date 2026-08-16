import { icons } from '../icons.js';

export function renderRevisionView(state, container, handlers) {
  const proposals = state.revisionProposals || [];
  const activeProposalId = state.activeProposalId;
  const activeProposal = proposals.find((p) => p.id === activeProposalId) || proposals[0] || null;
  const activeExam = state.exams?.find((e) => e.id === state.activeExamId) || state.exams?.[0] || null;

  container.innerHTML = `
    <div class="studio-pane-layout">
      <!-- Left Sidebar: Revision Proposals List -->
      <aside class="studio-pane-sidebar">
        <div class="pane-sidebar-header" style="display: flex; align-items: center; justify-content: space-between;">
          <h3 class="pane-title">
            <span>${icons.gitCompare(18)}</span>
            <span>差异比对引擎</span>
          </h3>
          <button class="btn-primary-glow" id="btn-propose-revision-open" style="padding: 4px 10px; font-size: 12px;">
            <span>${icons.plus(13)}</span>
            <span>提案</span>
          </button>
        </div>

        <div class="proposals-items-list">
          ${
            proposals.length === 0
              ? `<div style="text-align: center; padding: 24px 8px; color: var(--ink-muted); font-size: 12px;">暂无修改提案，请点击上方发起提案</div>`
              : proposals
                  .map(
                    (p) => `
                <div class="proposal-item-card ${activeProposal?.id === p.id ? 'is-selected' : ''}" data-proposal-id="${p.id}">
                  <div style="display: flex; align-items: center; justify-content: space-between;">
                    <span style="font-weight: 700; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 140px;">
                      ${escapeHtml(p.instruction || '试卷修改提案')}
                    </span>
                    <span class="status-pill status-pill-${p.status || 'pending'}">${formatProposalStatus(p.status)}</span>
                  </div>
                  <div style="display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: var(--ink-muted); margin-top: 4px;">
                    <span>变更: ${p.changes?.length || 0} 处</span>
                    <span>${formatDate(p.created_at)}</span>
                  </div>
                </div>
              `
                  )
                  .join('')
          }
        </div>
      </aside>

      <!-- Right Main Content: Diff Inspector -->
      <main class="studio-pane-content">
        ${
          activeProposal
            ? `
          <div class="proposal-diff-container">
            <div class="diff-header">
              <div class="title-row">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="padding: 6px; background: var(--marker-yellow); border: var(--sketch-border-thin); border-radius: var(--sketch-radius-sm);">
                    ${icons.gitCompare(18)}
                  </span>
                  <div>
                    <h2>${escapeHtml(activeProposal.instruction || '结构化修改提案')}</h2>
                    <span style="font-size: 12px; color: var(--ink-muted);">状态: ${formatProposalStatus(activeProposal.status)} · 变更项数: ${activeProposal.changes?.length || 0}</span>
                  </div>
                </div>
              </div>

              <div class="action-buttons-row" style="display: flex; align-items: center; gap: 8px;">
                ${
                  activeProposal.status === 'pending'
                    ? `
                  <button class="btn-primary-glow" id="btn-apply-proposal">
                    <span>${icons.check(14)}</span>
                    <span>合并应用修改</span>
                  </button>
                  <button class="btn-secondary-glow btn-icon-danger" id="btn-discard-proposal">
                    <span>${icons.trash2(14)}</span>
                    <span>放弃此提案</span>
                  </button>
                `
                    : ''
                }
              </div>
            </div>

            <!-- Changes Diff Stream -->
            <div class="changes-stream" style="display: grid; gap: 14px;">
              ${(activeProposal.changes || [])
                .map(
                  (c, idx) => `
                <div class="outline-q-card">
                  <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                      <span class="score-pill">修改项 #${idx + 1}</span>
                      <span class="type-pill">${escapeHtml(c.path || '文档属性')}</span>
                      <span class="version-tag">${escapeHtml(c.operation || 'replace')}</span>
                    </div>
                  </div>

                  <div style="font-weight: 700; font-size: 13px; margin-top: 4px;">
                    ${escapeHtml(c.summary || '内容修正')}
                  </div>

                  <div class="diff-split-view" style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 6px;">
                    <div>
                      <div style="font-size: 11px; font-weight: 700; color: var(--accent-crimson); margin-bottom: 2px;">修改前 (Before):</div>
                      <div class="diff-text-red">
                        ${escapeHtml(typeof c.before === 'object' ? JSON.stringify(c.before, null, 2) : String(c.before || '（无）'))}
                      </div>
                    </div>

                    <div>
                      <div style="font-size: 11px; font-weight: 700; color: var(--accent-emerald); margin-bottom: 2px;">修改后 (After):</div>
                      <div class="diff-text-green">
                        ${escapeHtml(typeof c.after === 'object' ? JSON.stringify(c.after, null, 2) : String(c.after || '（无）'))}
                      </div>
                    </div>
                  </div>
                </div>
              `
                )
                .join('')}
            </div>
          </div>
        `
            : `
          <div class="copilot-empty-state">
            <div class="empty-glow-icon">${icons.gitCompare(28)}</div>
            <h3 style="font-family: var(--font-hand); font-size: 22px;">暂无差异比对提案</h3>
            <p style="font-size: 13px; color: var(--ink-muted); max-width: 320px;">
              针对已有试卷提出修改诉求（例如"将第2题改为考查多级页表"），AI 将生成红绿结构化差异，确认无误后可一键采纳合并。
            </p>
            ${
              activeExam
                ? `
              <button class="btn-primary-glow" id="btn-empty-propose-revision" style="margin-top: 10px;">
                <span>${icons.plus(15)}</span>
                <span>为当前试卷发起修改提案</span>
              </button>
            `
                : ''
            }
          </div>
        `
        }
      </main>
    </div>
  `;

  // Attach handlers
  const btnPropose = container.querySelector('#btn-propose-revision-open');
  const btnEmptyPropose = container.querySelector('#btn-empty-propose-revision');
  const openProposeDialog = () => handlers.onOpenRevisionModal?.();

  if (btnPropose) btnPropose.onclick = openProposeDialog;
  if (btnEmptyPropose) btnEmptyPropose.onclick = openProposeDialog;

  container.querySelectorAll('.proposal-item-card').forEach((card) => {
    card.onclick = () => {
      const pId = card.getAttribute('data-proposal-id');
      handlers.onSelectProposal?.(pId);
    };
  });

  const btnApply = container.querySelector('#btn-apply-proposal');
  if (btnApply && activeProposal) {
    btnApply.onclick = () => handlers.onApplyProposal?.(activeProposal.id);
  }

  const btnDiscard = container.querySelector('#btn-discard-proposal');
  if (btnDiscard && activeProposal) {
    btnDiscard.onclick = () => handlers.onDiscardProposal?.(activeProposal.id);
  }
}

function formatProposalStatus(s) {
  switch (s) {
    case 'pending':
      return '待采纳';
    case 'applied':
      return '已合并';
    case 'discarded':
      return '已放弃';
    default:
      return '就绪';
  }
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
