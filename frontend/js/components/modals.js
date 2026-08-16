/**
 * Global Modals & Dialogs Component
 * Strictly aligned with Tickets 01, 04, 08, 13, 16, 17, 19, 20 & ADR 0005:
 * - Create / Rename Subject Space
 * - Create Learning Session (with sources picker and modes)
 * - Model Configuration & Model Discovery (Provider + API Format: Chat Completions / Responses / Ollama)
 * - Create AI Document & AI Document Revision Proposal
 * - Create Blueprint & Exam Revision Proposal
 * - Citation Anchor Inspector
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
    revisionModalOpen,
    activeExamId,
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
    revisionModalOpen ||
    citationModalOpen;

  if (!isOpen) {
    container.innerHTML = '';
    return;
  }

  container.innerHTML = `
    <!-- 1. Create Subject Modal -->
    ${
      subjectModalOpen
        ? `
      <div class="modal-overlay" id="modal-overlay-create-subject">
        <div class="modal-box modal-box-sm">
          <div class="modal-header-bar">
            <div class="modal-title-row">
              ${icons.plus(16)}
              <span>新建科目空间</span>
            </div>
            <button type="button" class="btn-icon-subtle" data-action="close-modal">${icons.x(14)}</button>
          </div>
          <form id="form-create-subject" class="modal-body-content">
            <div class="form-group-block">
              <label class="form-label-text">科目名称</label>
              <input type="text" class="form-input-control" id="input-subject-name" placeholder="例如：高等数学、微观经济学、法理学..." required autofocus />
            </div>
            <div class="modal-footer-row">
              <button type="button" class="btn-secondary" data-action="close-modal">取消</button>
              <button type="submit" class="btn-primary">${icons.check(14)} 创建空间</button>
            </div>
          </form>
        </div>
      </div>
    `
        : ''
    }

    <!-- 2. Rename Subject Modal -->
    ${
      renameSubjectModalOpen
        ? `
      <div class="modal-overlay" id="modal-overlay-rename-subject">
        <div class="modal-box modal-box-sm">
          <div class="modal-header-bar">
            <div class="modal-title-row">
              ${icons.edit3(16)}
              <span>重命名科目空间</span>
            </div>
            <button type="button" class="btn-icon-subtle" data-action="close-modal">${icons.x(14)}</button>
          </div>
          <form id="form-rename-subject" class="modal-body-content">
            <div class="form-group-block">
              <label class="form-label-text">科目新名称</label>
              <input type="text" class="form-input-control" id="input-rename-subject-name" value="${escapeHtml(subjectToRename?.name || '')}" required autofocus />
            </div>
            <div class="modal-footer-row">
              <button type="button" class="btn-secondary" data-action="close-modal">取消</button>
              <button type="submit" class="btn-primary">${icons.check(14)} 保存名称</button>
            </div>
          </form>
        </div>
      </div>
    `
        : ''
    }

    <!-- 3. Create Learning Session Modal -->
    ${
      createSessionModalOpen
        ? `
      <div class="modal-overlay" id="modal-overlay-create-session">
        <div class="modal-box modal-box-md">
          <div class="modal-header-bar">
            <div class="modal-title-row">
              ${icons.messageSquare(16)}
              <span>新建学习会话</span>
            </div>
            <button type="button" class="btn-icon-subtle" data-action="close-modal">${icons.x(14)}</button>
          </div>
          <form id="form-create-session" class="modal-body-content">
            <div class="form-group-block">
              <label class="form-label-text">会话标题 (可选)</label>
              <input type="text" class="form-input-control" id="input-session-title" placeholder="例如：矩阵对角化专题探讨、第一章速成提纲..." autofocus />
            </div>

            <div class="form-group-grid-2">
              <div class="form-group-block">
                <label class="form-label-text">伴学风格</label>
                <select class="form-select-control" id="select-session-learning-mode">
                  <option value="chat">普通问答 (Default)</option>
                  <option value="socratic">苏格拉底启发 (Socratic)</option>
                  <option value="crash-course">章节速成提纲 (Crash Course)</option>
                </select>
              </div>

              <div class="form-group-block">
                <label class="form-label-text">知识依据模式</label>
                <select class="form-select-control" id="select-session-grounding-mode">
                  <option value="general-knowledge">通用常识模式</option>
                  <option value="strict">严格资料模式</option>
                  <option value="supplemental">补充扩展模式</option>
                </select>
              </div>
            </div>

            <!-- Reference Sources Selector -->
            <div class="form-group-block">
              <label class="form-label-text">绑定资料范围 (可选)</label>
              ${
                sources.length === 0
                  ? `<div class="dropdown-empty-note">科目库暂无资料，新会话将使用通用常识回答。</div>`
                  : `
                <div class="modal-checkbox-list">
                  ${sources
                    .map(
                      (src) => `
                    <label class="modal-checkbox-item">
                      <input type="checkbox" name="session_source_version" value="${src.versions?.[0]?.id || src.id}" />
                      <span>${escapeHtml(src.display_name || src.name)}</span>
                    </label>
                  `
                    )
                    .join('')}
                </div>
              `
              }
            </div>

            <div class="modal-footer-row">
              <button type="button" class="btn-secondary" data-action="close-modal">取消</button>
              <button type="submit" class="btn-primary">${icons.check(14)} 建立会话</button>
            </div>
          </form>
        </div>
      </div>
    `
        : ''
    }

    <!-- 4. Model Configuration & Discovery Modal (Issue 19 & ADR 0005) -->
    ${
      modelModalOpen
        ? `
      <div class="modal-overlay" id="modal-overlay-model-config">
        <div class="modal-box modal-box-lg">
          <div class="modal-header-bar">
            <div class="modal-title-row">
              ${icons.cpu(16)}
              <span>模型服务配置与模型发现</span>
            </div>
            <button type="button" class="btn-icon-subtle" data-action="close-modal">${icons.x(14)}</button>
          </div>

          <div class="modal-body-content model-config-modal-body">
            <!-- Left: Configured Models List -->
            <div class="model-config-left-pane">
              <div class="dropdown-section-title">已配置模型服务 (${models.length})</div>
              ${
                models.length === 0
                  ? `<div class="sidebar-empty-state"><div class="sidebar-empty-text">暂未添加任何模型服务</div></div>`
                  : `
                <div class="configured-models-list">
                  ${models
                    .map((m) => {
                      const isCurrent = m.id === currentModelId || (!currentModelId && m.id === state.chat?.active_model_id);
                      return `
                    <div class="configured-model-item ${isCurrent ? 'is-current-active' : ''}">
                      <div class="model-item-top">
                        <div class="model-item-title-block">
                          <span class="model-item-name" title="${escapeHtml(m.model || m.name)}">${escapeHtml(m.model || m.name)}</span>
                          <span class="model-provider-badge">${escapeHtml(m.provider || 'AI')}</span>
                          ${m.capabilities?.vision ? `<span class="tag-chip-vision">Vision</span>` : ''}
                        </div>
                        ${
                          isCurrent
                            ? `<span class="current-model-badge">${icons.check(12)} 当前使用</span>`
                            : `
                          <button
                            type="button"
                            class="btn-secondary btn-xs"
                            data-action="select-current-model"
                            data-model-id="${m.id}"
                            title="设为系统当前默认模型"
                          >
                            设为当前
                          </button>
                        `
                        }
                      </div>

                      <div class="model-item-endpoint">格式: ${formatApiFormat(m.api_format)} · ${escapeHtml(m.base_url || '默认地址')}</div>

                      <div class="model-item-actions">
                        <button
                          type="button"
                          class="btn-secondary btn-xs"
                          data-action="verify-model-connection"
                          data-model-id="${m.id}"
                          title="手动测试连通性"
                        >
                          ${icons.activity(12)} 测试连接
                        </button>
                        <button
                          type="button"
                          class="btn-icon-subtle btn-delete-subtle"
                          data-action="delete-model"
                          data-model-id="${m.id}"
                          title="移除此模型配置"
                        >
                          ${icons.trash2(12)}
                        </button>
                      </div>
                    </div>
                  `;
                    })
                    .join('')}
                </div>
              `
              }
            </div>

            <!-- Right: Add / Register Model Form with Model Discovery -->
            <div class="model-config-right-pane">
              <div class="dropdown-section-title">添加 / 注册新模型服务</div>
              <form id="form-register-model">
                <div class="form-group-grid-2">
                  <div class="form-group-block">
                    <label class="form-label-text">服务商名称 <span class="required-star">*</span></label>
                    <input
                      type="text"
                      class="form-input-control"
                      id="input-model-provider-name"
                      placeholder="如: DeepSeek / OpenAI / Ollama"
                      required
                    />
                  </div>

                  <div class="form-group-block">
                    <label class="form-label-text">API 格式 <span class="required-star">*</span></label>
                    <select class="form-select-control" id="select-model-api-format" required>
                      <option value="openai-chat-completions">Chat Completions</option>
                      <option value="openai-responses">Responses</option>
                      <option value="ollama">Ollama</option>
                    </select>
                  </div>
                </div>

                <div class="form-group-block">
                  <label class="form-label-text">Base URL</label>
                  <input
                    type="url"
                    class="form-input-control"
                    id="input-model-base-url"
                    placeholder="https://api.openai.com/v1"
                    value="https://api.openai.com/v1"
                  />
                  <span class="form-field-hint" id="model-base-url-hint">示例: https://api.openai.com/v1</span>
                </div>

                <div class="form-group-block">
                  <label class="form-label-text">API Key (可选，write-only)</label>
                  <input
                    type="password"
                    class="form-input-control"
                    id="input-model-api-key"
                    placeholder="sk-... (Ollama 本地服务通常留空)"
                    autocomplete="off"
                  />
                </div>

                <!-- Model Discovery Action Row (Issue 19) -->
                <div class="form-group-block">
                  <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
                    <label class="form-label-text" style="margin-bottom: 0;">模型标识 (Model ID) <span class="required-star">*</span></label>
                    <button
                      type="button"
                      class="btn-secondary btn-xs"
                      id="btn-discover-models"
                      title="向 Base URL 查询可用模型列表"
                    >
                      ${icons.search(12)} 获取可用模型
                    </button>
                  </div>

                  <!-- Discovered Models Dropdown (When available) -->
                  ${
                    discoveredModels.length > 0
                      ? `
                    <select class="form-select-control" id="select-discovered-model" style="margin-bottom: 6px;">
                      <option value="">-- 从获取到的模型列表中选择 --</option>
                      ${discoveredModels
                        .map(
                          (dm) => `
                        <option value="${escapeHtml(dm.id || dm.name)}">${escapeHtml(dm.id || dm.name)} ${dm.capabilities?.vision ? '[Vision]' : ''}</option>
                      `
                        )
                        .join('')}
                    </select>
                  `
                      : ''
                  }

                  <!-- Manual Text Input Fallback -->
                  <input
                    type="text"
                    class="form-input-control"
                    id="input-model-name"
                    placeholder="例如：deepseek-chat, gpt-4o, llama3.2..."
                    required
                  />
                  <span class="form-field-hint">若模型发现失败或提供商未提供列表接口，可直接手动输入模型标识。</span>
                </div>

                <div class="modal-footer-row" style="margin-top: 16px;">
                  <button type="submit" class="btn-primary btn-block">${icons.plus(14)} 保存并注册模型</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    `
        : ''
    }

    <!-- 5. Create AI Document Modal (Ticket 20) -->
    ${
      createAiDocModalOpen
        ? `
      <div class="modal-overlay" id="modal-overlay-create-ai-doc">
        <div class="modal-box modal-box-md">
          <div class="modal-header-bar">
            <div class="modal-title-row">
              ${icons.sparkles(16)}
              <span>创建 AI 资料文档</span>
            </div>
            <button type="button" class="btn-icon-subtle" data-action="close-modal">${icons.x(14)}</button>
          </div>
          <form id="form-create-ai-doc" class="modal-body-content">
            <div class="form-group-block">
              <label class="form-label-text">文档标题</label>
              <input type="text" class="form-input-control" id="input-ai-doc-title" placeholder="例如：线性代数特征值与特征向量精要..." required autofocus />
            </div>

            <div class="form-group-block">
              <label class="form-label-text">正文内容 / 大纲说明</label>
              <textarea
                class="form-textarea-control"
                id="input-ai-doc-instruction"
                rows="5"
                placeholder="输入笔记正文，或说明要生成的资料结构与知识要点..."
                required
              ></textarea>
            </div>

            <div class="modal-footer-row">
              <button type="button" class="btn-secondary" data-action="close-modal">取消</button>
              <button type="submit" class="btn-primary">${icons.check(14)} 创建文档</button>
            </div>
          </form>
        </div>
      </div>
    `
        : ''
    }

    <!-- 6. AI Document Revision Proposal Modal (Ticket 20) -->
    ${
      aiDocRevisionModalOpen
        ? `
      <div class="modal-overlay" id="modal-overlay-ai-doc-revision">
        <div class="modal-box modal-box-md">
          <div class="modal-header-bar">
            <div class="modal-title-row">
              ${icons.edit3(16)}
              <span>提出文档修改要求</span>
            </div>
            <button type="button" class="btn-icon-subtle" data-action="close-modal">${icons.x(14)}</button>
          </div>
          <form id="form-ai-doc-revision" class="modal-body-content">
            <div class="form-group-block">
              <label class="form-label-text">修改说明与具体诉求</label>
              <textarea
                class="form-textarea-control"
                id="input-ai-doc-rev-instruction"
                rows="4"
                placeholder="例如：补充特征方程推导过程、修正第二部分的定理表述、增加应用例题..."
                required
                autofocus
              ></textarea>
            </div>
            <div class="modal-footer-row">
              <button type="button" class="btn-secondary" data-action="close-modal">取消</button>
              <button type="submit" class="btn-primary">${icons.check(14)} 生成修改提案</button>
            </div>
          </form>
        </div>
      </div>
    `
        : ''
    }

    <!-- 7. Create Blueprint Modal (Ticket 08) -->
    ${
      blueprintModalOpen
        ? `
      <div class="modal-overlay" id="modal-overlay-create-blueprint">
        <div class="modal-box modal-box-md">
          <div class="modal-header-bar">
            <div class="modal-title-row">
              ${icons.compass(16)}
              <span>构思组卷蓝图</span>
            </div>
            <button type="button" class="btn-icon-subtle" data-action="close-modal">${icons.x(14)}</button>
          </div>
          <form id="form-create-blueprint" class="modal-body-content">
            <div class="form-group-block">
              <label class="form-label-text">组卷诉求提示词</label>
              <textarea
                class="form-textarea-control"
                id="input-blueprint-prompt"
                rows="3"
                placeholder="例如：围绕第三章生成一份期中测验试卷，包含单选 3 题、判断 2 题、简答 1 题，侧重考察定义与易错点推导..."
                required
                autofocus
              ></textarea>
            </div>

            <div class="form-group-grid-2">
              <div class="form-group-block">
                <label class="form-label-text">试卷总分设定</label>
                <input type="number" class="form-input-control" id="input-blueprint-total-score" value="100" min="5" max="150" required />
              </div>
              <div class="form-group-block">
                <label class="form-label-text">知识依据模式</label>
                <select class="form-select-control" id="select-blueprint-grounding">
                  <option value="general-knowledge">通用常识模式</option>
                  <option value="strict">严格资料模式</option>
                </select>
              </div>
            </div>

            <div class="modal-footer-row">
              <button type="button" class="btn-secondary" data-action="close-modal">取消</button>
              <button type="submit" class="btn-primary">${icons.play(14)} 解析并生成蓝图</button>
            </div>
          </form>
        </div>
      </div>
    `
        : ''
    }

    <!-- 8. Exam Revision Modal (Ticket 13) -->
    ${
      revisionModalOpen
        ? `
      <div class="modal-overlay" id="modal-overlay-exam-revision">
        <div class="modal-box modal-box-md">
          <div class="modal-header-bar">
            <div class="modal-title-row">
              ${icons.edit3(16)}
              <span>AI 试卷修改提案</span>
            </div>
            <button type="button" class="btn-icon-subtle" data-action="close-modal">${icons.x(14)}</button>
          </div>
          <form id="form-exam-revision" class="modal-body-content">
            <div class="form-group-block">
              <label class="form-label-text">试卷修改指令</label>
              <textarea
                class="form-textarea-control"
                id="input-exam-rev-instruction"
                rows="4"
                placeholder="例如：将第二题的难度提高、增加第三题的选项干扰项、为大题补充评分细则..."
                required
                autofocus
              ></textarea>
            </div>
            <div class="modal-footer-row">
              <button type="button" class="btn-secondary" data-action="close-modal">取消</button>
              <button type="submit" class="btn-primary">${icons.check(14)} 生成修改提案</button>
            </div>
          </form>
        </div>
      </div>
    `
        : ''
    }

    <!-- 9. Citation Anchor Inspector Modal (Ticket 04) -->
    ${
      citationModalOpen && activeCitation
        ? `
      <div class="modal-overlay" id="modal-overlay-citation">
        <div class="modal-box modal-box-md">
          <div class="modal-header-bar">
            <div class="modal-title-row">
              ${icons.bookmark(16)}
              <span>资料来源引用依据</span>
            </div>
            <button type="button" class="btn-icon-subtle" data-action="close-modal">${icons.x(14)}</button>
          </div>
          <div class="modal-body-content">
            <div class="citation-inspect-box">
              <div class="citation-meta-header">
                <span>资料版本 ID: <code>${escapeHtml(activeCitation.source_version_id?.slice(0, 8) || '未知')}</code></span>
                <span>锚点: <code>${escapeHtml(activeCitation.anchor_id || '段落')}</code></span>
              </div>
              <blockquote class="citation-quote-large">
                ${escapeHtml(activeCitation.quote || activeCitation.text_excerpt || activeCitation.content || '（无引用摘要）')}
              </blockquote>
            </div>
            <div class="modal-footer-row">
              <button
                type="button"
                class="btn-primary btn-sm"
                id="btn-pin-citation-to-selection"
              >
                ${icons.tag(13)} 固定此段落到对话提问
              </button>
              <button type="button" class="btn-secondary btn-sm" data-action="close-modal">关闭</button>
            </div>
          </div>
        </div>
      </div>
    `
        : ''
    }
  `;

  attachModalEvents(container, state, handlers);
}

function attachModalEvents(container, state, handlers) {
  // Close Modals on close button or overlay click
  container.querySelectorAll('[data-action="close-modal"]').forEach((btn) => {
    btn.onclick = () => handlers.onCloseModals?.();
  });

  container.querySelectorAll('.modal-overlay').forEach((overlay) => {
    overlay.onclick = (e) => {
      if (e.target === overlay) {
        handlers.onCloseModals?.();
      }
    };
  });

  // ESC key to close
  const onKeyDown = (e) => {
    if (e.key === 'Escape') handlers.onCloseModals?.();
  };
  document.removeEventListener('keydown', container._modalEscHandler);
  container._modalEscHandler = onKeyDown;
  document.addEventListener('keydown', onKeyDown);

  // 1. Create Subject Form
  const formCreateSubject = container.querySelector('#form-create-subject');
  if (formCreateSubject) {
    formCreateSubject.onsubmit = (e) => {
      e.preventDefault();
      const name = container.querySelector('#input-subject-name')?.value.trim();
      if (name) handlers.onCreateSubject?.(name);
    };
  }

  // 2. Rename Subject Form
  const formRenameSubject = container.querySelector('#form-rename-subject');
  if (formRenameSubject && state.subjectToRename) {
    formRenameSubject.onsubmit = (e) => {
      e.preventDefault();
      const newName = container.querySelector('#input-rename-subject-name')?.value.trim();
      if (newName) handlers.onRenameSubject?.(state.subjectToRename.id, newName);
    };
  }

  // 3. Create Session Form
  const formCreateSession = container.querySelector('#form-create-session');
  if (formCreateSession) {
    formCreateSession.onsubmit = (e) => {
      e.preventDefault();
      const title = container.querySelector('#input-session-title')?.value.trim() || undefined;
      const learning_mode = container.querySelector('#select-session-learning-mode')?.value || 'chat';
      const grounding_mode = container.querySelector('#select-session-grounding-mode')?.value || 'general-knowledge';

      const checkedSources = Array.from(
        container.querySelectorAll('input[name="session_source_version"]:checked')
      ).map((el) => el.value);

      handlers.onCreateSession?.({
        title,
        learning_mode,
        grounding_mode,
        source_version_ids: checkedSources
      });
    };
  }

  // 4. Model Config Form & API Format selector dynamic hints
  const formatSelect = container.querySelector('#select-model-api-format');
  const baseUrlInput = container.querySelector('#input-model-base-url');
  const baseUrlHint = container.querySelector('#model-base-url-hint');

  if (formatSelect && baseUrlInput && baseUrlHint) {
    formatSelect.onchange = () => {
      const val = formatSelect.value;
      if (val === 'ollama') {
        baseUrlInput.placeholder = 'http://localhost:11434';
        baseUrlInput.value = 'http://localhost:11434';
        baseUrlHint.textContent = '示例: http://localhost:11434';
      } else {
        baseUrlInput.placeholder = 'https://api.openai.com/v1';
        baseUrlInput.value = 'https://api.openai.com/v1';
        baseUrlHint.textContent = '示例: https://api.openai.com/v1';
      }
    };
  }

  const formRegisterModel = container.querySelector('#form-register-model');
  if (formRegisterModel) {
    formRegisterModel.onsubmit = (e) => {
      e.preventDefault();
      const provider = container.querySelector('#input-model-provider-name')?.value.trim() || 'AI';
      const api_format = container.querySelector('#select-model-api-format')?.value || 'openai-chat-completions';
      const base_url = container.querySelector('#input-model-base-url')?.value.trim() || (api_format === 'ollama' ? 'http://localhost:11434' : 'https://api.openai.com/v1');
      const api_key = container.querySelector('#input-model-api-key')?.value.trim() || null;
      const model = container.querySelector('#input-model-name')?.value.trim();

      if (model && base_url) {
        handlers.onSaveModel?.({
          provider,
          api_format,
          base_url,
          api_key,
          model,
          name: `${provider} (${model})`
        });
      }
    };
  }

  // Discover Models Button (Issue 19)
  const discoverBtn = container.querySelector('#btn-discover-models');
  if (discoverBtn) {
    discoverBtn.onclick = () => {
      const provider = container.querySelector('#input-model-provider-name')?.value.trim() || 'openai';
      const api_format = container.querySelector('#select-model-api-format')?.value || 'openai-chat-completions';
      const base_url = container.querySelector('#input-model-base-url')?.value.trim() || (api_format === 'ollama' ? 'http://localhost:11434' : 'https://api.openai.com/v1');
      const api_key = container.querySelector('#input-model-api-key')?.value.trim() || null;
      handlers.onDiscoverModels?.({ provider, api_format, base_url, api_key });
    };
  }

  // Select discovered model dropdown
  const discoveredSelect = container.querySelector('#select-discovered-model');
  if (discoveredSelect) {
    discoveredSelect.onchange = () => {
      if (discoveredSelect.value) {
        const inputName = container.querySelector('#input-model-name');
        if (inputName) inputName.value = discoveredSelect.value;
      }
    };
  }

  // Set Current Model
  container.querySelectorAll('[data-action="select-current-model"]').forEach((btn) => {
    btn.onclick = () => {
      const mId = btn.getAttribute('data-model-id');
      handlers.onSelectGlobalCurrentModel?.(mId);
    };
  });

  // Verify Model Connection
  container.querySelectorAll('[data-action="verify-model-connection"]').forEach((btn) => {
    btn.onclick = () => {
      const mId = btn.getAttribute('data-model-id');
      handlers.onVerifyModel?.(mId);
    };
  });

  // Delete Model
  container.querySelectorAll('[data-action="delete-model"]').forEach((btn) => {
    btn.onclick = () => {
      const mId = btn.getAttribute('data-model-id');
      handlers.onDeleteModel?.(mId);
    };
  });

  // 5. Create AI Document Form
  const formCreateAiDoc = container.querySelector('#form-create-ai-doc');
  if (formCreateAiDoc) {
    formCreateAiDoc.onsubmit = (e) => {
      e.preventDefault();
      const title = container.querySelector('#input-ai-doc-title')?.value.trim();
      const content = container.querySelector('#input-ai-doc-instruction')?.value.trim();
      if (title && content) handlers.onCreateAiDocument?.({ title, content });
    };
  }

  // 6. AI Document Revision Form
  const formAiDocRev = container.querySelector('#form-ai-doc-revision');
  if (formAiDocRev) {
    formAiDocRev.onsubmit = (e) => {
      e.preventDefault();
      const instruction = container.querySelector('#input-ai-doc-rev-instruction')?.value.trim();
      if (instruction && state.activeAiDocumentId) {
        handlers.onProposeAiDocRevision?.(state.activeAiDocumentId, instruction);
      }
    };
  }

  // 7. Create Blueprint Form
  const formCreateBlueprint = container.querySelector('#form-create-blueprint');
  if (formCreateBlueprint) {
    formCreateBlueprint.onsubmit = (e) => {
      e.preventDefault();
      const prompt = container.querySelector('#input-blueprint-prompt')?.value.trim();
      const total_score = parseInt(container.querySelector('#input-blueprint-total-score')?.value, 10) || 100;
      const grounding_mode = container.querySelector('#select-blueprint-grounding')?.value || 'general-knowledge';
      if (prompt) {
        handlers.onCreateBlueprint?.({ prompt, total_score, grounding_mode });
      }
    };
  }

  // 8. Exam Revision Form
  const formExamRevision = container.querySelector('#form-exam-revision');
  if (formExamRevision) {
    formExamRevision.onsubmit = (e) => {
      e.preventDefault();
      const instruction = container.querySelector('#input-exam-rev-instruction')?.value.trim();
      if (instruction && state.activeExamId) {
        handlers.onProposeExamRevision?.(state.activeExamId, instruction);
      }
    };
  }

  // 9. Pin Citation to Selection
  const btnPinCitation = container.querySelector('#btn-pin-citation-to-selection');
  if (btnPinCitation && state.activeCitation) {
    btnPinCitation.onclick = () => {
      handlers.onPinCitationToContext?.(state.activeCitation);
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
