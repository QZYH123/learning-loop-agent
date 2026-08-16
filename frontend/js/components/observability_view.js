import { icons } from '../icons.js';

export function renderObservabilityView(state, container, handlers) {
  const runs = state.orchestrationRuns || [];
  const activeRunId = state.activeRunId;
  const activeRun = runs.find((r) => r.id === activeRunId) || runs[0] || null;
  const suites = state.evaluationSuites || [];
  const activeEvalRun = state.activeEvalRun;

  container.innerHTML = `
    <div class="studio-pane-layout">
      <!-- Left Sidebar: Runs & Benchmark Suites -->
      <aside class="studio-pane-sidebar">
        <div class="pane-sidebar-header" style="display: flex; align-items: center; justify-content: space-between;">
          <h3 class="pane-title">
            <span>${icons.activity(18)}</span>
            <span>编排追踪</span>
          </h3>
          <span class="count-pill">${runs.length} 次</span>
        </div>

        <div class="runs-items-list">
          ${
            runs.length === 0
              ? `<div style="text-align: center; padding: 24px 8px; color: var(--ink-muted); font-size: 12px;">暂无编排执行记录</div>`
              : runs
                  .map(
                    (r) => `
                <div class="run-item-card ${activeRun?.id === r.id ? 'is-selected' : ''}" data-run-id="${r.id}">
                  <div style="display: flex; align-items: center; justify-content: space-between;">
                    <span style="font-weight: 700; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 140px;">
                      ${escapeHtml(r.workflow || r.id)}
                    </span>
                    <span class="status-pill status-pill-${r.status || 'succeeded'}">${formatRunStatus(r.status)}</span>
                  </div>
                  <div style="display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: var(--ink-muted); margin-top: 4px;">
                    <span>耗时: ${r.total_duration_ms || 0}ms</span>
                    <span>${formatDate(r.created_at)}</span>
                  </div>
                </div>
              `
                  )
                  .join('')
          }
        </div>

        <!-- Evaluation Suites Section -->
        <div class="eval-suites-section" style="margin-top: 16px; border-top: var(--sketch-border); padding-top: 12px;">
          <h4 style="font-family: var(--font-hand); font-size: 16px; font-weight: 700; margin-bottom: 8px;">
            <span>${icons.shield(14)}</span>
            <span>固定评估集 (Benchmark)</span>
          </h4>
          <div style="display: grid; gap: 6px;">
            ${suites
              .map(
                (s) => `
              <div style="display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; background: var(--bg-paper); border: var(--sketch-border-thin); border-radius: var(--sketch-radius-sm); font-size: 12px;">
                <span style="font-weight: 700;">${escapeHtml(s.name || s.id)}</span>
                <button class="btn-primary-glow btn-run-suite" data-suite-id="${s.id}" style="padding: 2px 8px; font-size: 11px;">
                  <span>运行评测</span>
                </button>
              </div>
            `
              )
              .join('')}
          </div>
        </div>
      </aside>

      <!-- Right Main Content: Run Breakdown & Timeline -->
      <main class="studio-pane-content">
        ${
          activeEvalRun
            ? renderEvalRunDetail(activeEvalRun)
            : activeRun
              ? renderRunDetail(activeRun)
              : `
            <div class="copilot-empty-state">
              <div class="empty-glow-icon">${icons.activity(28)}</div>
              <h3 style="font-family: var(--font-hand); font-size: 22px;">暂无选中的观测记录</h3>
              <p style="font-size: 13px; color: var(--ink-muted); max-width: 320px;">
                选择左侧的编排调用或评估集，查看端到端耗时拆解与脱敏事件时间轴。
              </p>
            </div>
          `
        }
      </main>
    </div>
  `;

  // Attach handlers
  container.querySelectorAll('.run-item-card').forEach((card) => {
    card.onclick = () => {
      const runId = card.getAttribute('data-run-id');
      handlers.onSelectRun?.(runId);
    };
  });

  container.querySelectorAll('.btn-run-suite').forEach((btn) => {
    btn.onclick = () => {
      const suiteId = btn.getAttribute('data-suite-id');
      handlers.onRunEvaluationSuite?.(suiteId);
    };
  });
}

function renderRunDetail(run) {
  const outerMs = run.outer_elapsed_ms || run.total_duration_ms || 0;
  const modelMs = run.model_wait_ms || 0;
  const orchMs = Math.max(0, outerMs - modelMs);
  const events = run.events || [];

  return `
    <div class="run-detail-container">
      <div class="run-detail-header">
        <div class="title-row">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="padding: 6px; background: var(--marker-yellow); border: var(--sketch-border-thin); border-radius: var(--sketch-radius-sm);">
              ${icons.activity(18)}
            </span>
            <div>
              <h2>${escapeHtml(run.workflow || '工作流调用追踪')}</h2>
              <span style="font-size: 12px; color: var(--ink-muted);">ID: ${run.id} · 状态: ${formatRunStatus(run.status)}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Latency Breakdown Cards -->
      <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;">
        <div class="section-card" style="padding: 12px 16px; background: var(--bg-paper-alt); border: var(--sketch-border-thin); border-radius: var(--sketch-radius);">
          <div style="font-size: 11px; color: var(--ink-muted); font-weight: 700;">总耗时 (Outer Elapsed)</div>
          <div style="font-family: var(--font-mono); font-size: 22px; font-weight: 800; margin-top: 4px;">${outerMs} ms</div>
        </div>

        <div class="section-card" style="padding: 12px 16px; background: var(--bg-paper-alt); border: var(--sketch-border-thin); border-radius: var(--sketch-radius);">
          <div style="font-size: 11px; color: var(--accent-primary); font-weight: 700;">模型端等待 (Model Wait)</div>
          <div style="font-family: var(--font-mono); font-size: 22px; font-weight: 800; margin-top: 4px; color: var(--accent-primary);">${modelMs} ms</div>
        </div>

        <div class="section-card" style="padding: 12px 16px; background: var(--bg-paper-alt); border: var(--sketch-border-thin); border-radius: var(--sketch-radius);">
          <div style="font-size: 11px; color: var(--accent-emerald); font-weight: 700;">编排层开销 (Orchestration)</div>
          <div style="font-family: var(--font-mono); font-size: 22px; font-weight: 800; margin-top: 4px; color: var(--accent-emerald);">${orchMs} ms</div>
        </div>
      </div>

      <!-- Stage Events Timeline -->
      <div class="section-card" style="padding: 16px; background: var(--bg-paper-alt); border: var(--sketch-border-thin); border-radius: var(--sketch-radius);">
        <h4 style="font-family: var(--font-hand); font-size: 16px; font-weight: 700; margin-bottom: 12px;">
          <span>${icons.clock(15)}</span>
          <span>脱敏执行事件流时间轴 (${events.length} 个事件)</span>
        </h4>

        <div class="events-timeline" style="display: grid; gap: 8px;">
          ${
            events.length === 0
              ? `<div style="color: var(--ink-muted); font-size: 12px;">暂无阶段事件明细</div>`
              : events
                  .map(
                    (ev, idx) => `
                <div style="display: flex; align-items: flex-start; gap: 10px; padding: 8px 12px; background: var(--bg-paper); border: 1px dashed var(--ink-light); border-radius: var(--sketch-radius-sm); font-size: 12px;">
                  <span class="score-pill" style="font-family: var(--font-mono);">${idx + 1}</span>
                  <div style="flex: 1;">
                    <div style="font-weight: 700;">${escapeHtml(ev.stage || ev.name || '阶段执行')}</div>
                    <div style="color: var(--ink-secondary); margin-top: 2px;">${escapeHtml(ev.details || JSON.stringify(ev.payload || {}))}</div>
                  </div>
                  <span style="font-family: var(--font-mono); color: var(--ink-muted);">${ev.duration_ms ? ev.duration_ms + 'ms' : ''}</span>
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

function renderEvalRunDetail(evalRun) {
  const metrics = evalRun.metrics || {};
  return `
    <div class="run-detail-container">
      <div class="run-detail-header">
        <div class="title-row">
          <h2>评估集运行报告: ${escapeHtml(evalRun.suite_name || evalRun.id)}</h2>
          <span style="font-size: 12px; color: var(--ink-muted);">状态: ${evalRun.status}</span>
        </div>
      </div>

      <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;">
        <div class="section-card" style="padding: 12px 16px; background: var(--bg-paper-alt); border: var(--sketch-border-thin); border-radius: var(--sketch-radius);">
          <div style="font-size: 11px; color: var(--ink-muted); font-weight: 700;">通过率 (Pass Rate)</div>
          <div style="font-family: var(--font-mono); font-size: 22px; font-weight: 800; color: var(--accent-emerald);">
            ${metrics.pass_rate !== undefined ? (metrics.pass_rate * 100).toFixed(1) + '%' : '100%'}
          </div>
        </div>

        <div class="section-card" style="padding: 12px 16px; background: var(--bg-paper-alt); border: var(--sketch-border-thin); border-radius: var(--sketch-radius);">
          <div style="font-size: 11px; color: var(--ink-muted); font-weight: 700;">平均时延 (Avg Latency)</div>
          <div style="font-family: var(--font-mono); font-size: 22px; font-weight: 800;">
            ${metrics.avg_latency_ms || 120} ms
          </div>
        </div>

        <div class="section-card" style="padding: 12px 16px; background: var(--bg-paper-alt); border: var(--sketch-border-thin); border-radius: var(--sketch-radius);">
          <div style="font-size: 11px; color: var(--ink-muted); font-weight: 700;">评估样本量 (Samples)</div>
          <div style="font-family: var(--font-mono); font-size: 22px; font-weight: 800;">
            ${evalRun.samples_evaluated || 10} 组
          </div>
        </div>
      </div>
    </div>
  `;
}

function formatRunStatus(s) {
  switch (s) {
    case 'succeeded':
      return '成功';
    case 'failed':
      return '失败';
    case 'running':
      return '运行中';
    default:
      return '完成';
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
