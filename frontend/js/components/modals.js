/**
 * Global Modals & Dialogs Component
 * Strictly aligned with Issue 19 & ADR 0005:
 * - Model Configuration Modal: provider vs api_format dropdown (Chat Completions / Responses / Ollama),
 *   base_url with dynamic placeholders, api_key, model_name with discover models + manual fallback,
 *   save without test, test connection, discover models, model list & switch.
 * - Subject Space Modals (Create / Rename)
 * - Create Session Modal
 * - Create AI Document Modal & Revision Modal
 * - Create Blueprint Modal
 * - Citation Anchor Inspector Modal
 */

import { icons } from '../icons.js';

export function renderModals(state, container, handlers) {
  const {
    subjectModalOpen,
    renameSubjectModalOpen,
    subjectToRename,
    createSessionModalOpen,
    modelModalOpen,
    models = [],
    currentModelId,
    discoveredModels = [],
    createAiDocModalOpen,
    aiDocRevisionModalOpen,
    activeAiDocumentId,
    blueprintModalOpen,
    citationModalOpen,
    activeCitation,
    sources = []
  } = state;

  const isOpen =
    subjectModalOpen ||
    renameSubjectModalOpen ||
    createSessionModalOpen ||
    modelModalOpen ||
    createAiDocModalOpen ||
    aiDocRevisionModalOpen ||
    blueprintModalOpen ||
    citationModalOpen;

  if (!isOpen) {
    container.innerHTML = '';
    return;
  }

  let modalHtml = '';

  // 1. Model Configuration Modal
  if (modelModalOpen) {
    modalHtml = renderModelModal(state);
  }
  // 2. Create Subject Modal
  else if (subjectModalOpen) {
    modalHtml = renderCreateSubjectModal();
  }
  // 3. Rename Subject Modal
  else if (renameSubjectModalOpen) {
    modalHtml = renderRenameSubjectModal(subjectToRename);
  }
  // 4. Create Session Modal
  else if (createSessionModalOpen) {
    modalHtml = renderCreateSessionModal(sources);
  }
  // 5. Create AI Doc Modal
  else if (createAiDocModalOpen) {
    modalHtml = renderCreateAiDocModal();
  }
  // 6. AI Doc Revision Modal
  else if (aiDocRevisionModalOpen) {
    modalHtml = renderAiDocRevisionModal();
  }
  // 7. Create Blueprint Modal
  else if (blueprintModalOpen) {
    modalHtml = renderCreateBlueprintModal();
  }
  // 8. Citation Anchor Inspector Modal
  else if (citationModalOpen) {
    modalHtml = renderCitationModal(activeCitation);
  }

  container.innerHTML = `
    <div class="modal-backdrop" id="global-modal-backdrop">
      ${modalHtml}
    </div>
  `;

  attachModalEvents(container, state, handlers);
}

function renderModelModal(state) {
  const { models = [], currentModelId, discoveredModels = [] } = state;
  const activeModel = models.find((m) => m.id === currentModelId) || models[0] || null;

  return `
    <div class="modal-dialog modal-lg" role="dialog" aria-modal="true" aria-labelledby="modal-model-title">
      <div class="modal-header">
        <div class="modal-title-block">
          <span class="modal-title-icon">${icons.cpu(18)}</span>
          <h3 class="modal-title" id="modal-model-title">模型配置</h3>
        </div>
        <button type="button" class="btn-icon-subtle btn-close-modal" title="关闭">${icons.x(16)}</button>
      </div>

      <div class="modal-body">
        <!-- Add / Edit Model Form -->
        <form class="modal-form-grid" id="model-config-form">
          <div class="form-row form-row-2col">
            <div class="form-group">
              <label class="form-label" for="input-model-provider">服务商名称 <span class="required-star">*</span></label>
              <input
                type="text"
                class="form-input"
                id="input-model-provider"
                name="provider"
                placeholder="如: DeepSeek / OpenAI / Ollama"
                required
              />
            </div>

            <div class="form-group">
              <label class="form-label" for="select-model-api-format">API 格式 <span class="required-star">*</span></label>
              <select class="form-select" id="select-model-api-format" name="api_format" required>
                <option value="openai-chat-completions">Chat Completions</option>
                <option value="openai-responses">Responses</option>
                <option value="ollama">Ollama</option>
              </select>
            </div>
          </div>

          <div class="form-group">
            <label class="form-label" for="input-model-base-url">Base URL</label>
            <input
              type="text"
              class="form-input"
              id="input-model-base-url"
              name="base_url"
              placeholder="https://api.openai.com/v1"
            />
            <span class="form-hint" id="model-base-url-hint">示例: https://api.openai.com/v1</span>
          </div>

          <div class="form-group">
            <label class="form-label" for="input-model-api-key">API Key</label>
            <input
              type="password"
              class="form-input"
              id="input-model-api-key"
              name="api_key"
              placeholder="sk-... (Ollama 本地服务可留空)"
              autocomplete="off"
            />
          </div>

          <div class="form-group">
            <label class="form-label" for="input-model-name">模型名称 <span class="required-star">*</span></label>
            <div class="input-with-button-row">
              <input
                type="text"
                class="form-input"
                id="input-model-name"
                name="model"
                placeholder="如: deepseek-chat / gpt-4o / llama3.2"
                required
              />
              <button type="button" class="btn-outline-action" id="btn-discover-models" title="从服务端自动发现可用模型">
                ${icons.search(13)} 获取模型
              </button>
            </div>

            ${
              discoveredModels.length > 0
                ? `
              <div class="discovered-models-dropdown" id="discovered-models-list">
                <span class="disc-header">从服务发现的模型 (点击选择):</span>
                <div class="disc-chips-grid">
                  ${discoveredModels
                    .map(
                      (m) => `
                    <button type="button" class="disc-chip-btn" data-model-id="${m.id || m.name || m}">
                      ${escapeHtml(m.id || m.name || m)}
                    </button>
                  `
                    )
                    .join('')}
                </div>
              </div>
            `
                : ''
            }
          </div>

          <div class="form-actions-bar">
            <div class="form-actions-left">
              <button type="button" class="btn-outline-action" id="btn-test-model-connection" title="测试此配置的连通性与延迟">
                ${icons.activity(13)} 测试连接
              </button>
              <span class="test-result-indicator" id="test-connection-result"></span>
            </div>
            <div class="form-actions-right">
              <button type="submit" class="btn-primary-action" id="btn-save-model-config">
                ${icons.check(14)} 保存配置
              </button>
            </div>
          </div>
        </form>

        <!-- Saved Models List -->
        <div class="saved-models-section">
          <h4 class="section-title">${icons.sliders(14)} 已保存的模型服务 (${models.length})</h4>
          <div class="saved-models-list">
            ${
              models.length === 0
                ? `<div class="empty-models-hint">暂未添加模型服务，请填写上方表单添加</div>`
                : models
                    .map(
                      (m) => `
                  <div class="saved-model-item ${m.id === currentModelId ? 'is-active' : ''}">
                    <div class="model-item-left">
                      <span class="model-provider-badge">${escapeHtml(m.provider || 'AI')}</span>
                      <div class="model-item-info">
                        <span class="model-name-text">${escapeHtml(m.name || m.model || m.id)}</span>
                        <span class="model-meta-text">协议: ${formatApiFormat(m.api_format)} · ${escapeHtml(m.base_url || '默认地址')}</span>
                      </div>
                    </div>
                    <div class="model-item-actions">
                      ${
                        m.id === currentModelId
                          ? `<span class="active-tag">${icons.checkCircle(12)} 当前使用</span>`
                          : `
                        <button
                          type="button"
                          class="btn-outline-sm btn-select-active-model"
                          data-model-id="${m.id}"
                          title="切换为当前使用模型"
                        >
                          选用
                        </button>
                      `
                      }
                      <button
                        type="button"
                        class="btn-icon-subtle btn-delete-model-item"
                        data-model-id="${m.id}"
                        title="删除模型配置"
                      >
                        ${icons.trash(13)}
                      </button>
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
  `;
}

function renderCreateSubjectModal() {
  return `
    <div class="modal-dialog" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div class="modal-title-block">
          <span class="modal-title-icon">${icons.book(18)}</span>
          <h3 class="modal-title">新建科目空间</h3>
        </div>
        <button type="button" class="btn-icon-subtle btn-close-modal" title="关闭">${icons.x(16)}</button>
      </div>
      <form id="create-subject-form">
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label" for="input-subject-name">科目名称 <span class="required-star">*</span></label>
            <input type="text" class="form-input" id="input-subject-name" name="name" placeholder="如: 高等数学 / 计算机网络 / 考研英语" required autofocus />
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn-outline-action btn-close-modal">取消</button>
          <button type="submit" class="btn-primary-action">创建科目</button>
        </div>
      </form>
    </div>
  `;
}

function renderRenameSubjectModal(subj) {
  return `
    <div class="modal-dialog" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div class="modal-title-block">
          <span class="modal-title-icon">${icons.edit(18)}</span>
          <h3 class="modal-title">重命名科目</h3>
        </div>
        <button type="button" class="btn-icon-subtle btn-close-modal" title="关闭">${icons.x(16)}</button>
      </div>
      <form id="rename-subject-form" data-subject-id="${subj?.id}">
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label" for="input-rename-subject-name">科目新名称 <span class="required-star">*</span></label>
            <input type="text" class="form-input" id="input-rename-subject-name" name="name" value="${escapeHtml(subj?.name || '')}" required autofocus />
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn-outline-action btn-close-modal">取消</button>
          <button type="submit" class="btn-primary-action">确认重命名</button>
        </div>
      </form>
    </div>
  `;
}

function renderCreateSessionModal(sources = []) {
  return `
    <div class="modal-dialog" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div class="modal-title-block">
          <span class="modal-title-icon">${icons.messageSquare(18)}</span>
          <h3 class="modal-title">新建学习会话</h3>
        </div>
        <button type="button" class="btn-icon-subtle btn-close-modal" title="关闭">${icons.x(16)}</button>
      </div>
      <form id="create-session-form">
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label" for="input-session-title">会话主题</label>
            <input type="text" class="form-input" id="input-session-title" name="title" placeholder="如: 导数与微分基础巩固" autofocus />
          </div>

          <div class="form-group">
            <label class="form-label">固定参考资料范围 (可选)</label>
            <div class="sources-checkbox-list">
              ${
                sources.length === 0
                  ? `<div class="empty-sources-hint">暂无资料，会话将使用常识回答</div>`
                  : sources
                      .map(
                        (src) => `
                    <label class="source-checkbox-label">
                      <input type="checkbox" name="source_ids" value="${src.versions?.[0]?.id || src.id}" />
                      <span class="src-label-text">${escapeHtml(src.name)}</span>
                    </label>
                  `
                      )
                      .join('')
              }
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn-outline-action btn-close-modal">取消</button>
          <button type="submit" class="btn-primary-action">开始新会话</button>
        </div>
      </form>
    </div>
  `;
}

function renderCreateAiDocModal() {
  return `
    <div class="modal-dialog modal-lg" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div class="modal-title-block">
          <span class="modal-title-icon">${icons.fileText(18)}</span>
          <h3 class="modal-title">创建 AI 资料文档</h3>
        </div>
        <button type="button" class="btn-icon-subtle btn-close-modal" title="关闭">${icons.x(16)}</button>
      </div>
      <form id="create-aidoc-form">
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label" for="input-aidoc-title">文档标题 <span class="required-star">*</span></label>
            <input type="text" class="form-input" id="input-aidoc-title" name="title" placeholder="如: 高数第一章重点笔记" required autofocus />
          </div>
          <div class="form-group">
            <label class="form-label" for="textarea-aidoc-content">正文内容 / 大纲 <span class="required-star">*</span></label>
            <textarea class="form-textarea" id="textarea-aidoc-content" name="content" rows="6" placeholder="输入笔记正文或大纲要点..." required></textarea>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn-outline-action btn-close-modal">取消</button>
          <button type="submit" class="btn-primary-action">创建文档</button>
        </div>
      </form>
    </div>
  `;
}

function renderAiDocRevisionModal() {
  return `
    <div class="modal-dialog" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div class="modal-title-block">
          <span class="modal-title-icon">${icons.edit(18)}</span>
          <h3 class="modal-title">提出修改要求</h3>
        </div>
        <button type="button" class="btn-icon-subtle btn-close-modal" title="关闭">${icons.x(16)}</button>
      </div>
      <form id="propose-aidoc-revision-form">
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label" for="textarea-revision-instruction">修改说明 <span class="required-star">*</span></label>
            <textarea class="form-textarea" id="textarea-revision-instruction" name="instruction" rows="4" placeholder="如: 把第二部分讲得更生动通俗一些，并补一个典型例题" required autofocus></textarea>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn-outline-action btn-close-modal">取消</button>
          <button type="submit" class="btn-primary-action">生成修改提案</button>
        </div>
      </form>
    </div>
  `;
}

function renderCreateBlueprintModal() {
  return `
    <div class="modal-dialog" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div class="modal-title-block">
          <span class="modal-title-icon">${icons.compass(18)}</span>
          <h3 class="modal-title">新建组卷蓝图</h3>
        </div>
        <button type="button" class="btn-icon-subtle btn-close-modal" title="关闭">${icons.x(16)}</button>
      </div>
      <form id="create-blueprint-form">
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label" for="input-bp-title">试卷标题</label>
            <input type="text" class="form-input" id="input-bp-title" name="title" placeholder="如: 高等数学期末自测卷" />
          </div>
          <div class="form-group">
            <label class="form-label" for="textarea-bp-prompt">组卷要求与范围 <span class="required-star">*</span></label>
            <textarea class="form-textarea" id="textarea-bp-prompt" name="prompt" rows="3" placeholder="如: 根据资料出10道单选题和2道大题，偏重极限与微积分" required autofocus></textarea>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn-outline-action btn-close-modal">取消</button>
          <button type="submit" class="btn-primary-action">生成蓝图</button>
        </div>
      </form>
    </div>
  `;
}

function renderCitationModal(citation) {
  return `
    <div class="modal-dialog" role="dialog" aria-modal="true">
      <div class="modal-header">
        <div class="modal-title-block">
          <span class="modal-title-icon">${icons.link(18)}</span>
          <h3 class="modal-title">原文位置与依据</h3>
        </div>
        <button type="button" class="btn-icon-subtle btn-close-modal" title="关闭">${icons.x(16)}</button>
      </div>
      <div class="modal-body">
        <div class="citation-inspector-content">
          <div class="cit-meta">
            <span class="cit-source-title">${escapeHtml(citation?.source_title || '资料来源')}</span>
            ${citation?.anchor_title ? `<span class="cit-anchor-title">· ${escapeHtml(citation.anchor_title)}</span>` : ''}
          </div>
          <div class="cit-excerpt-box">
            <p>${escapeHtml(citation?.text_excerpt || citation?.content || '（暂无对应文本）')}</p>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn-primary-action btn-close-modal">关闭</button>
      </div>
    </div>
  `;
}

function attachModalEvents(container, state, handlers) {
  const backdrop = container.querySelector('#global-modal-backdrop');
  if (backdrop) {
    backdrop.onclick = (e) => {
      if (e.target === backdrop) handlers.onCloseModals?.();
    };
  }

  container.querySelectorAll('.btn-close-modal').forEach((btn) => {
    btn.onclick = () => handlers.onCloseModals?.();
  });

  // API Format Switcher in Model Modal: updates Base URL hint & placeholder
  const formatSelect = container.querySelector('#select-model-api-format');
  const baseUrlInput = container.querySelector('#input-model-base-url');
  const baseUrlHint = container.querySelector('#model-base-url-hint');

  if (formatSelect && baseUrlInput && baseUrlHint) {
    formatSelect.onchange = () => {
      const val = formatSelect.value;
      if (val === 'ollama') {
        baseUrlInput.placeholder = 'http://localhost:11434';
        baseUrlHint.textContent = '示例: http://localhost:11434';
      } else {
        baseUrlInput.placeholder = 'https://api.openai.com/v1';
        baseUrlHint.textContent = '示例: https://api.openai.com/v1';
      }
    };
  }

  // Model Form Submit
  const modelForm = container.querySelector('#model-config-form');
  if (modelForm) {
    modelForm.onsubmit = (e) => {
      e.preventDefault();
      const formData = new FormData(modelForm);
      const payload = {
        provider: formData.get('provider')?.trim(),
        api_format: formData.get('api_format'),
        base_url: formData.get('base_url')?.trim() || (formData.get('api_format') === 'ollama' ? 'http://localhost:11434' : 'https://api.openai.com/v1'),
        api_key: formData.get('api_key')?.trim() || null,
        model: formData.get('model')?.trim(),
        name: formData.get('provider')?.trim() + ' (' + formData.get('model')?.trim() + ')'
      };
      handlers.onSaveModelConfig?.(payload);
    };
  }

  // Discover Models Button
  const discoverBtn = container.querySelector('#btn-discover-models');
  if (discoverBtn) {
    discoverBtn.onclick = () => {
      const format = formatSelect ? formatSelect.value : 'openai-chat-completions';
      const baseUrl = baseUrlInput?.value.trim() || (format === 'ollama' ? 'http://localhost:11434' : 'https://api.openai.com/v1');
      const apiKeyInput = container.querySelector('#input-model-api-key');
      const apiKey = apiKeyInput?.value.trim() || null;

      handlers.onDiscoverModels?.({ api_format: format, base_url: baseUrl, api_key: apiKey });
    };
  }

  // Discovered Model Chip Click
  container.querySelectorAll('.disc-chip-btn').forEach((btn) => {
    btn.onclick = () => {
      const mid = btn.getAttribute('data-model-id');
      const modelInput = container.querySelector('#input-model-name');
      if (modelInput && mid) {
        modelInput.value = mid;
      }
    };
  });

  // Test Model Connection Button
  const testBtn = container.querySelector('#btn-test-model-connection');
  const testResult = container.querySelector('#test-connection-result');
  if (testBtn) {
    testBtn.onclick = async () => {
      if (testResult) testResult.innerHTML = '<span class="spinner-inline"></span> 测试中...';
      const format = formatSelect ? formatSelect.value : 'openai-chat-completions';
      const baseUrl = baseUrlInput?.value.trim() || (format === 'ollama' ? 'http://localhost:11434' : 'https://api.openai.com/v1');
      const apiKeyInput = container.querySelector('#input-model-api-key');
      const apiKey = apiKeyInput?.value.trim() || null;
      const modelInput = container.querySelector('#input-model-name');
      const model = modelInput?.value.trim() || 'default';

      handlers.onTestModelConnection?.(
        { api_format: format, base_url: baseUrl, api_key: apiKey, model },
        (res) => {
          if (testResult) {
            if (res.ok) {
              testResult.innerHTML = `<span class="test-ok">${icons.checkCircle(13)} 连通正常 (${res.latency_ms || 120}ms)</span>`;
            } else {
              testResult.innerHTML = `<span class="test-fail">${icons.alertTriangle(13)} 连接失败: ${escapeHtml(res.error || '')}</span>`;
            }
          }
        }
      );
    };
  }

  // Switch Active Model
  container.querySelectorAll('.btn-select-active-model').forEach((btn) => {
    btn.onclick = () => {
      const mid = btn.getAttribute('data-model-id');
      if (mid) handlers.onSelectCurrentModel?.(mid);
    };
  });

  // Delete Model
  container.querySelectorAll('.btn-delete-model-item').forEach((btn) => {
    btn.onclick = () => {
      const mid = btn.getAttribute('data-model-id');
      if (mid) handlers.onDeleteModel?.(mid);
    };
  });

  // Create Subject Form
  const createSubjForm = container.querySelector('#create-subject-form');
  if (createSubjForm) {
    createSubjForm.onsubmit = (e) => {
      e.preventDefault();
      const name = createSubjForm.querySelector('#input-subject-name')?.value.trim();
      if (name) handlers.onCreateSubject?.(name);
    };
  }

  // Rename Subject Form
  const renameSubjForm = container.querySelector('#rename-subject-form');
  if (renameSubjForm) {
    renameSubjForm.onsubmit = (e) => {
      e.preventDefault();
      const sid = renameSubjForm.getAttribute('data-subject-id');
      const name = renameSubjForm.querySelector('#input-rename-subject-name')?.value.trim();
      if (sid && name) handlers.onRenameSubject?.(sid, name);
    };
  }

  // Create Session Form
  const createSessForm = container.querySelector('#create-session-form');
  if (createSessForm) {
    createSessForm.onsubmit = (e) => {
      e.preventDefault();
      const title = createSessForm.querySelector('#input-session-title')?.value.trim() || '学习会话';
      const checkedBoxes = createSessForm.querySelectorAll('input[name="source_ids"]:checked');
      const sourceVersionIds = Array.from(checkedBoxes).map((cb) => cb.value);
      handlers.onCreateSession?.({ title, source_version_ids: sourceVersionIds });
    };
  }

  // Create AI Doc Form
  const createDocForm = container.querySelector('#create-aidoc-form');
  if (createDocForm) {
    createDocForm.onsubmit = (e) => {
      e.preventDefault();
      const title = createDocForm.querySelector('#input-aidoc-title')?.value.trim();
      const content = createDocForm.querySelector('#textarea-aidoc-content')?.value.trim();
      if (title && content) handlers.onCreateAiDocument?.({ title, content });
    };
  }

  // Propose AI Doc Revision Form
  const revForm = container.querySelector('#propose-aidoc-revision-form');
  if (revForm) {
    revForm.onsubmit = (e) => {
      e.preventDefault();
      const instruction = revForm.querySelector('#textarea-revision-instruction')?.value.trim();
      const docId = state.activeAiDocumentId;
      if (docId && instruction) handlers.onProposeAiDocRevision?.(docId, instruction);
    };
  }

  // Create Blueprint Form
  const createBpForm = container.querySelector('#create-blueprint-form');
  if (createBpForm) {
    createBpForm.onsubmit = (e) => {
      e.preventDefault();
      const title = createBpForm.querySelector('#input-bp-title')?.value.trim() || '期末自测卷';
      const prompt = createBpForm.querySelector('#textarea-bp-prompt')?.value.trim();
      if (prompt) handlers.onCreateBlueprint?.({ title, prompt });
    };
  }
}

function formatApiFormat(fmt) {
  if (fmt === 'openai-chat-completions') return 'Chat Completions';
  if (fmt === 'openai-responses') return 'Responses';
  if (fmt === 'ollama') return 'Ollama';
  return fmt || 'Chat Completions';
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
