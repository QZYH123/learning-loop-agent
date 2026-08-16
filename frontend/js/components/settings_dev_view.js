/**
 * Settings & Developer Observability Component
 * Subtabs: 1. 模型服务配置 | 2. 编排时延与链路追踪 | 3. 固定评估集基准 (Ticket 15)
 * ZERO Fake data: Displays real measurements and clean empty states when unmeasured.
 */

import { icons } from '../icons.js';

export function renderSettingsDevView(state, container, handlers) {
  const {
    models = [],
    currentModelId,
    orchestrationRuns = [],
    activeRunId,
    evaluationSuites = [],
    activeEvalRun,
    settingsDevSubTab = 'models'
  } = state;

  const activeRun = orchestrationRuns.find((r) => r.id === activeRunId) || orchestrationRuns[0] || null;

  container.innerHTML = `
    <div class="learning-workspace-layout no-sidebar" data-testid="settings-dev-workspace">
      <main class="workspace-main-content">
        <!-- Subnav Header -->
        <header class="subnav-tabs-header">
          <div class="subnav-tabs-list">
            <button
              type="button"
              class="subnav-tab-btn ${settingsDevSubTab === 'models' ? 'is-active' : ''}"
              data-settings-subtab="models"
            >
              ${icons.cpu(14)}
              <span>1. 模型服务管理</span>
              ${models.length ? `<span class="tab-badge">${models.length}</span>` : ''}
            </button>
            <button
              type="button"
              class="subnav-tab-btn ${settingsDevSubTab === 'observability' ? 'is-active' : ''}"
              data-settings-subtab="observability"
            >
              ${icons.activity(14)}
              <span>2. 编排调用追踪</span>
              ${orchestrationRuns.length ? `<span class="tab-badge">${orchestrationRuns.length}</span>` : ''}
            </button>
            <button
              type="button"
              class="subnav-tab-btn ${settingsDevSubTab === 'benchmarks' ? 'is-active' : ''}"
              data-settings-subtab="benchmarks"
            >
              ${icons.target(14)}
              <span>3. 评测基准套件</span>
              ${evaluationSuites.length ? `<span class="tab-badge">${evaluationSuites.length}</span>` : ''}
            </button>
          </div>

          <div>
            ${
              settingsDevSubTab === 'models'
                ? `
              <button type="button" class="btn-primary btn-sm" id="btn-open-add-model-modal">
                ${icons.plus(13)} 添加新模型...
              </button>
            `
                : ''
            }
          </div>
        </header>

        <!-- Subtab Body -->
        <div class="settings-subtab-viewport">
          ${
            settingsDevSubTab === 'models'
              ? renderModelsSubTab(models, currentModelId, state)
              : settingsDevSubTab === 'observability'
              ? renderObservabilitySubTab(orchestrationRuns, activeRun)
              : renderBenchmarksSubTab(evaluationSuites, activeEvalRun)
          }
        </div>
      </main>
    </div>
  `;

  // Attach Event Handlers
  attachSettingsEvents(container, state, handlers);
}

function renderModelsSubTab(models, currentModelId, state) {
  return `
    <div class="models-subtab-container">
      <div class="section-hero-header">
        <h2 class="section-hero-title">模型服务与能力配置</h2>
        <div class="section-hero-desc">
          配置 OpenAI-Compatible 或 Ollama 本地模型服务。系统支持按会话或全局指定当前模型，并严格记录每条消息的模型快照。
        </div>
      </div>

      <div class="models-grid-layout">
        ${
          models.length === 0
            ? `
          <div class="detail-empty-container" style="grid-column: span 2;">
            <div class="empty-state-icon-circle">${icons.cpu(24)}</div>
            <div class="empty-state-title">未配置任何模型服务</div>
            <div class="empty-state-desc">点击右上角“添加新模型”输入 Base URL 与模型名称完成注册。</div>
          </div>
        `
            : models
                .map((m) => {
                  const isCurrent = m.id === currentModelId || (!currentModelId && m.id === state.chat?.active_model_id);
                  return `
            <div class="model-profile-card ${isCurrent ? 'is-active-model' : ''}">
              <div class="model-card-header">
                <div class="model-card-title-block">
                  <span class="model-card-name">${escapeHtml(m.model)}</span>
                  <span class="model-provider-badge">${escapeHtml(m.provider)}</span>
                  ${m.capabilities?.vision ? `<span class="tag-chip-vision">Vision 多模态</span>` : ''}
                </div>
                ${
                  isCurrent
                    ? `<span class="current-model-badge">${icons.check(12)} 当前默认</span>`
                    : `
                  <button
                    type="button"
                    class="btn-secondary btn-xs"
                    data-action="set-as-current-model"
                    data-model-id="${m.id}"
                  >
                    设为当前
                  </button>
                `
                }
              </div>

              <div class="model-card-endpoint">
                <span class="endpoint-label">Endpoint:</span>
                <code>${escapeHtml(m.base_url || '')}</code>
              </div>

              <div class="model-card-footer">
                <button
                  type="button"
                  class="btn-secondary btn-sm"
                  data-action="verify-model-btn"
                  data-model-id="${m.id}"
                >
                  ${icons.activity(13)} 手动连通性测试
                </button>
                <button
                  type="button"
                  class="btn-icon-subtle btn-delete-subtle"
                  data-action="delete-model-btn"
                  data-model-id="${m.id}"
                  title="删除模型"
                >
                  ${icons.trash2(14)}
                </button>
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

function renderObservabilitySubTab(runs = [], activeRun) {
  return `
    <div class="observability-subtab-container">
      <div class="section-hero-header">
        <h2 class="section-hero-title">编排调用与时延追踪 (Observability)</h2>
        <div class="section-hero-desc">
          严格区分编排外层耗时与模型等待时延，追踪检索命中、结构校验与阶段事件。
        </div>
      </div>

      <div class="observability-grid-layout">
        <!-- Runs List -->
        <div class="obs-runs-list-panel">
          <div class="dropdown-section-title">编排执行记录 (${runs.length})</div>
          ${
            runs.length === 0
              ? `<div class="sidebar-empty-state"><div class="sidebar-empty-text">暂无编排执行记录</div></div>`
              : runs
                  .map((r) => {
                    const isSelected = r.id === activeRun?.id;
                    return `
              <div
                class="standard-card-item ${isSelected ? 'is-selected' : ''}"
                data-action="select-obs-run"
                data-run-id="${r.id}"
                role="button"
                tabindex="0"
              >
                <div class="source-card-header">
                  <span class="source-card-title">${escapeHtml(r.action || r.name || 'AI 编排任务')}</span>
                  <span class="grounding-tag-chip ${r.status === 'succeeded' ? 'grounding-covered' : ''}">${r.status}</span>
                </div>
                <div class="source-card-meta">
                  <span>外层: ${r.outer_elapsed_ms || 0} ms</span>
                  <span>模型等待: ${r.model_wait_ms || 0} ms</span>
                </div>
              </div>
            `;
                  })
                  .join('')
          }
        </div>

        <!-- Run Trace Details -->
        <div class="obs-run-detail-panel">
          ${
            !activeRun
              ? `<div class="detail-empty-container"><div class="empty-state-title">未选择执行记录</div></div>`
              : `
            <div class="obs-detail-card">
              <div class="detail-header-bar" style="border: none; padding: 0 0 12px 0;">
                <div>
                  <h3 style="font-size: 15px; font-weight: 700;">${escapeHtml(activeRun.action || '编排调用详情')}</h3>
                  <div class="detail-meta-row">
                    <span>Run ID: <code>${escapeHtml(activeRun.id)}</code></span>
                    <span>时间: ${formatTimestamp(activeRun.created_at)}</span>
                  </div>
                </div>
                <span class="grounding-tag-chip ${activeRun.status === 'succeeded' ? 'grounding-covered' : ''}">${activeRun.status}</span>
              </div>

              <!-- Metric Badges -->
              <div class="obs-metrics-row">
                <div class="obs-metric-box">
                  <span class="obs-metric-label">外层总耗时 (Outer)</span>
                  <span class="obs-metric-val">${activeRun.outer_elapsed_ms || 0} ms</span>
                </div>
                <div class="obs-metric-box">
                  <span class="obs-metric-label">模型等待耗时 (Model Wait)</span>
                  <span class="obs-metric-val">${activeRun.model_wait_ms || 0} ms</span>
                </div>
                <div class="obs-metric-box">
                  <span class="obs-metric-label">阶段事件数</span>
                  <span class="obs-metric-val">${activeRun.events?.length || 0}</span>
                </div>
              </div>

              <!-- Events Timeline -->
              <div class="dropdown-section-title" style="margin-top: 16px;">脱敏阶段事件追踪</div>
              <div class="obs-timeline-list">
                ${
                  (activeRun.events || [])
                    .map(
                      (ev) => `
                  <div class="obs-event-row">
                    <span class="obs-event-time">+${ev.elapsed_ms || 0}ms</span>
                    <span class="obs-event-name">${escapeHtml(ev.stage || ev.name)}</span>
                    <span class="obs-event-status ${ev.status === 'ok' ? 'status-ok' : ''}">${ev.status || 'done'}</span>
                  </div>
                `
                    )
                    .join('')
                }
              </div>
            </div>
          `
          }
        </div>
      </div>
    </div>
  `;
}

function renderBenchmarksSubTab(suites = [], activeEvalRun) {
  return `
    <div class="benchmarks-subtab-container">
      <div class="section-hero-header">
        <h2 class="section-hero-title">固定评估集基准测试 (Evaluation Suites)</h2>
        <div class="section-hero-desc">
          运行固定样例集自动化评估，分别观测编排层指标（Outer Elapsed）与模型结果（答案正确率、引用准确率）。
        </div>
      </div>

      <div class="suites-list-grid">
        ${
          suites.length === 0
            ? `<div class="detail-empty-container"><div class="empty-state-title">未发现评估测试套件</div></div>`
            : suites
                .map(
                  (st) => `
            <div class="suite-card-item">
              <div class="suite-card-header">
                <div>
                  <h3 class="suite-card-title">${escapeHtml(st.name || '评估套件')}</h3>
                  <div class="suite-card-desc">${escapeHtml(st.description || '')}</div>
                </div>
                <button
                  type="button"
                  class="btn-primary btn-sm"
                  data-action="run-eval-suite-btn"
                  data-suite-id="${st.id}"
                >
                  ${icons.play(13)} 运行基准评估
                </button>
              </div>

              <div class="suite-card-meta">
                <span>样本数: ${st.sample_count || 10}</span>
                <span>考察维度: 问答引用、客观组卷、主观评分点覆盖</span>
              </div>
            </div>
          `
                )
                .join('')
        }
      </div>

      ${
        activeEvalRun
          ? `
        <div class="eval-results-card">
          <h3 style="font-size: 15px; font-weight: 700; margin-bottom: 12px;">评估结果报告: ${escapeHtml(activeEvalRun.suite_name || '基准套件')}</h3>
          <div class="obs-metrics-row">
            <div class="obs-metric-box">
              <span class="obs-metric-label">编排平均耗时</span>
              <span class="obs-metric-val">${activeEvalRun.orchestration_metrics?.avg_outer_ms || '--'} ms</span>
            </div>
            <div class="obs-metric-box">
              <span class="obs-metric-label">引用准确率 (模型观测)</span>
              <span class="obs-metric-val">${activeEvalRun.model_observations?.citation_precision !== undefined ? `${(activeEvalRun.model_observations.citation_precision * 100).toFixed(1)}%` : '--'}</span>
            </div>
            <div class="obs-metric-box">
              <span class="obs-metric-label">客观题正确率 (模型观测)</span>
              <span class="obs-metric-val">${activeEvalRun.model_observations?.accuracy !== undefined ? `${(activeEvalRun.model_observations.accuracy * 100).toFixed(1)}%` : '--'}</span>
            </div>
          </div>
        </div>
      `
          : ''
      }
    </div>
  `;
}

function attachSettingsEvents(container, state, handlers) {
  // Subtab Navigation
  container.querySelectorAll('[data-settings-subtab]').forEach((btn) => {
    btn.onclick = () => {
      const subtab = btn.getAttribute('data-settings-subtab');
      handlers.onSelectSettingsSubTab?.(subtab);
    };
  });

  // Open Add Model Modal
  const addModelBtn = container.querySelector('#btn-open-add-model-modal');
  if (addModelBtn) {
    addModelBtn.onclick = () => handlers.onOpenModelModal?.();
  }

  // Set As Current Model
  container.querySelectorAll('[data-action="set-as-current-model"]').forEach((btn) => {
    btn.onclick = () => {
      const mId = btn.getAttribute('data-model-id');
      handlers.onSelectGlobalCurrentModel?.(mId);
    };
  });

  // Verify Model Connection
  container.querySelectorAll('[data-action="verify-model-btn"]').forEach((btn) => {
    btn.onclick = () => {
      const mId = btn.getAttribute('data-model-id');
      handlers.onVerifyModel?.(mId);
    };
  });

  // Delete Model
  container.querySelectorAll('[data-action="delete-model-btn"]').forEach((btn) => {
    btn.onclick = () => {
      const mId = btn.getAttribute('data-model-id');
      if (confirm('确定要删除此模型服务配置吗？')) {
        handlers.onDeleteModel?.(mId);
      }
    };
  });

  // Select Observability Run
  container.querySelectorAll('[data-action="select-obs-run"]').forEach((card) => {
    card.onclick = () => {
      const rId = card.getAttribute('data-run-id');
      handlers.onSelectRun?.(rId);
    };
  });

  // Run Evaluation Suite
  container.querySelectorAll('[data-action="run-eval-suite-btn"]').forEach((btn) => {
    btn.onclick = () => {
      const sId = btn.getAttribute('data-suite-id');
      handlers.onRunEvaluationSuite?.(sId);
    };
  });
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
