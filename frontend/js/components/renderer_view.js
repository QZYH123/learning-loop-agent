import { icons } from '../icons.js';

export function renderRendererView(state, container, handlers) {
  const activeExam = state.exams?.find((e) => e.id === state.activeExamId) || state.exams?.[0] || null;
  const renderDoc = state.renderDocument;
  const edition = state.renderEdition || 'questions';

  container.innerHTML = `
    <div class="studio-pane-content" style="padding: 20px;">
      ${
        activeExam
          ? `
        <div class="renderer-control-bar" style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; padding: 10px 16px; background: var(--bg-paper); border: var(--sketch-border); border-radius: var(--sketch-radius); box-shadow: var(--sketch-shadow);">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-weight: 700; font-family: var(--font-hand); font-size: 16px;">排版版本：</span>
            <button class="mode-pill-btn ${edition === 'questions' ? 'is-active' : ''}" data-edition="questions" style="padding: 4px 10px; font-size: 13px;">
              <span>纯试题卷</span>
            </button>
            <button class="mode-pill-btn ${edition === 'solutions' ? 'is-active' : ''}" data-edition="solutions" style="padding: 4px 10px; font-size: 13px;">
              <span>答案解析卷</span>
            </button>
            <button class="mode-pill-btn ${edition === 'complete' ? 'is-active' : ''}" data-edition="complete" style="padding: 4px 10px; font-size: 13px;">
              <span>母卷全貌</span>
            </button>
          </div>

          <div style="display: flex; align-items: center; gap: 8px;">
            <button class="btn-primary-glow" id="btn-trigger-print" title="调用系统高精打印">
              <span>${icons.printer(14)}</span>
              <span>立即打印 / 存为 PDF</span>
            </button>
            <button class="btn-secondary-glow" id="btn-export-md" title="导出 Markdown 格式">
              <span>${icons.download(14)}</span>
              <span>导出 Markdown</span>
            </button>
            <button class="btn-secondary-glow" id="btn-export-json" title="导出标准 JSON">
              <span>${icons.download(14)}</span>
              <span>导出 JSON</span>
            </button>
          </div>
        </div>

        <!-- Rendered Sheet Canvas -->
        <div class="unified-render-document" id="printable-exam-paper">
          <div class="doc-header-block">
            <h1 class="doc-main-title">${escapeHtml(renderDoc?.title || activeExam.document?.title || '标准化考试试卷')}</h1>
            <div style="font-size: 13px; color: var(--ink-secondary); margin-top: 6px;">
              <span>满分: ${renderDoc?.total_score || activeExam.document?.total_score || 100} 分</span> · 
              <span>考试时间: 120 分钟</span> · 
              <span>版本: v${activeExam.version_count || 1}</span>
            </div>
            <div style="margin-top: 10px; font-size: 12px; border-top: 1px dashed var(--ink-light); padding-top: 6px; display: flex; justify-content: space-around;">
              <span>姓名：________________</span>
              <span>准考证号：________________</span>
              <span>成绩：________</span>
            </div>
          </div>

          <!-- Question Sections -->
          <div class="doc-questions-flow" style="display: flex; flex-direction: column; gap: 20px;">
            ${(renderDoc?.sections || activeExam.document?.questions || [])
              .map((q, idx) => {
                const isSol = edition === 'solutions' || edition === 'complete';
                return `
                <div class="render-q-item">
                  <div style="font-weight: 700; font-size: 14px; line-height: 1.6;">
                    ${idx + 1}. (${q.score || 5}分) ${escapeHtml(renderStem(q.stem))}
                  </div>

                  ${
                    q.options && q.options.length > 0
                      ? `
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 8px; margin-top: 8px; padding-left: 14px;">
                      ${q.options
                        .map(
                          (opt) => `
                        <div><b>${opt.id}.</b> ${escapeHtml(opt.text)}</div>
                      `
                        )
                        .join('')}
                    </div>
                  `
                      : ''
                  }

                  ${
                    isSol
                      ? `
                    <div class="q-explanation-box" style="margin-top: 10px; background: var(--bg-sticky);">
                      <div style="font-weight: 700; color: var(--accent-emerald);">【答案】${escapeHtml(formatAnswer(q.answer))}</div>
                      ${q.explanation ? `<div style="color: var(--ink-secondary); margin-top: 2px;">【解析】${escapeHtml(q.explanation)}</div>` : ''}
                      ${
                        q.scoring_points && q.scoring_points.length > 0
                          ? `
                        <div style="color: var(--accent-primary); font-size: 11px; margin-top: 4px;">
                          【采分点】${q.scoring_points.map((p) => `[+${p.points}分] ${p.description}`).join('；')}
                        </div>
                      `
                          : ''
                      }
                    </div>
                  `
                      : '<div style="height: 36px;"></div>'
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
          <div class="empty-glow-icon">${icons.printer(28)}</div>
          <h3 style="font-family: var(--font-hand); font-size: 22px;">暂无排版试卷</h3>
          <p style="font-size: 13px; color: var(--ink-muted); max-width: 320px;">
            请先在「题目工坊」发布试卷，即可在此进行试题卷、答案卷与母卷的统一排版与打印。
          </p>
        </div>
      `
      }
    </div>
  `;

  // Attach handlers
  container.querySelectorAll('.mode-pill-btn[data-edition]').forEach((btn) => {
    btn.onclick = () => {
      const ed = btn.getAttribute('data-edition');
      handlers.onSwitchRenderEdition?.(ed);
    };
  });

  const btnPrint = container.querySelector('#btn-trigger-print');
  if (btnPrint) {
    btnPrint.onclick = () => window.print();
  }

  const btnExportMd = container.querySelector('#btn-export-md');
  if (btnExportMd && activeExam) {
    btnExportMd.onclick = () => handlers.onExportExam?.(activeExam.id, 'markdown', edition);
  }

  const btnExportJson = container.querySelector('#btn-export-json');
  if (btnExportJson && activeExam) {
    btnExportJson.onclick = () => handlers.onExportExam?.(activeExam.id, 'json', edition);
  }
}

function renderStem(stem) {
  if (Array.isArray(stem)) {
    return stem.map((s) => s.text || '').join('\n');
  }
  return typeof stem === 'string' ? stem : '';
}

function formatAnswer(ans) {
  if (!ans) return '未设置';
  if (ans.kind === 'choice') return ans.option_ids?.join(', ') || '未设置';
  if (ans.kind === 'fill-blank') return ans.blanks?.map((b) => b.value).join(', ') || '未设置';
  if (ans.kind === 'text') return ans.text || '未设置';
  return JSON.stringify(ans);
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
