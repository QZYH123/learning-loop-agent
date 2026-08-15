import { api } from './api.js';

const root = document.getElementById('app');
if (!root) throw new Error('找不到应用挂载点 #app');

const SUBJECT_NAME_MAX_LENGTH = 80;
const CHAT_MESSAGE_MAX_LENGTH = 20_000;

let workspace = {
  schema_version: 1,
  active_subject_id: null,
  subjects: [],
  models: [],
  created_at: null,
  updated_at: null
};
let status = null;
let editingSubjectId = null;
let editingName = '';
let createDraft = '';
let showModelForm = false;
let verifyingModels = new Set();
let pollTimer = null;

function activeSubject() {
  return workspace.subjects.find((subject) => subject.id === workspace.active_subject_id) || null;
}

function subjectChat(subject) {
  const chat = subject?.data?.chat;
  if (chat && Array.isArray(chat.messages)) return chat;
  return { active_model_id: null, messages: [] };
}

function generatingMessage(chat) {
  return chat.messages.find((message) => message.status === 'generating') || null;
}

function hasGeneratingMessage() {
  return workspace.subjects.some((subject) => Boolean(generatingMessage(subjectChat(subject))));
}

function setStatus(payload) {
  if (payload.tone === 'error') status = { tone: 'error', text: payload.message };
  else if (payload.tone === 'warning') status = { tone: 'warning', text: payload.message };
  else status = { tone: 'success', text: payload.message };
}

function setError(error) {
  status = { tone: 'error', text: error.message || String(error) };
  render();
}

function startPolling() {
  stopPolling();
  if (!hasGeneratingMessage()) return;
  pollTimer = setTimeout(async () => {
    try {
      const payload = await api.getWorkspace();
      workspace = payload.workspace;
      render();
      startPolling();
    } catch (error) {
      setError(error);
    }
  }, 700);
}

function stopPolling() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

async function perform(promise) {
  const payload = await promise;
  if (payload.workspace) workspace = payload.workspace;
  setStatus(payload);
  render();
  startPolling();
  return payload;
}

async function init() {
  try {
    const payload = await api.getWorkspace();
    workspace = payload.workspace;
    if (payload.load_issue) status = { tone: 'warning', text: payload.load_issue };
    render();
    startPolling();
  } catch (error) {
    setError(error);
  }
}

function render() {
  const subject = activeSubject();
  root.innerHTML = `
    <div class="app-shell" data-testid="app-shell">
      <aside class="learning-panel" data-testid="learning-panel" aria-label="学习操作区">
        <header class="brand">
          <p class="brand-kicker">本地优先 · FastAPI</p>
          <h1>AI 学习工具</h1>
          <p class="brand-copy">围绕科目空间组织资料、会话和试卷。</p>
        </header>

        ${renderSubjectSection()}
        <p class="status ${status ? `status-${status.tone}` : ''}" role="status" aria-live="polite" data-testid="workspace-status">
          ${status ? escapeHtml(status.text) : ''}
        </p>
        ${renderModelSection()}
        ${renderChatSection(subject)}
      </aside>

      <main class="content-panel" data-testid="content-panel" aria-label="内容区">
        ${renderContentPanel(subject)}
      </main>
    </div>
  `;

  if (editingSubjectId) {
    const input = root.querySelector('[data-rename-input]');
    if (input) {
      input.focus();
      input.select();
    }
  }
}

function renderSubjectSection() {
  return `
    <section class="subject-spaces" aria-labelledby="subject-spaces-title">
      <div class="section-heading">
        <h2 id="subject-spaces-title">科目空间</h2>
        <span class="section-count" data-testid="subject-count">${workspace.subjects.length}</span>
      </div>

      <form class="create-subject-form" data-form="create-subject" data-testid="create-subject-form">
        <label class="visually-hidden" for="subject-name-input">新科目名称</label>
        <input
          id="subject-name-input" name="name" type="text" maxlength="${SUBJECT_NAME_MAX_LENGTH}"
          placeholder="例如：高等数学" autocomplete="off" value="${escapeHtml(createDraft)}"
          data-testid="subject-name-input"
        />
        <button type="submit" data-testid="create-subject-button">创建</button>
      </form>

      <ul class="subject-list" data-testid="subject-list">
        ${workspace.subjects.map(renderSubjectItem).join('')}
      </ul>
    </section>
  `;
}

function renderSubjectItem(subject) {
  const isActive = subject.id === workspace.active_subject_id;
  if (editingSubjectId === subject.id) {
    return `
      <li class="subject-item subject-item-editing" data-subject-id="${escapeHtml(subject.id)}">
        <form class="rename-subject-form" data-form="rename-subject" data-subject-id="${escapeHtml(subject.id)}">
          <label class="visually-hidden" for="rename-subject-input-${escapeHtml(subject.id)}">科目名称</label>
          <input id="rename-subject-input-${escapeHtml(subject.id)}" name="name" type="text"
            maxlength="${SUBJECT_NAME_MAX_LENGTH}" value="${escapeHtml(editingName)}" autocomplete="off" data-rename-input />
          <button type="submit" data-testid="save-rename-button">保存</button>
          <button type="button" data-action="rename-cancel" data-subject-id="${escapeHtml(subject.id)}">取消</button>
        </form>
      </li>
    `;
  }
  return `
    <li class="subject-item ${isActive ? 'subject-item-active' : ''}" data-subject-id="${escapeHtml(subject.id)}">
      <button class="subject-switch-button" type="button" data-action="activate-subject"
        data-subject-id="${escapeHtml(subject.id)}" aria-current="${isActive ? 'true' : 'false'}" data-testid="switch-subject-button">
        <span class="subject-name">${escapeHtml(subject.name)}</span>
        <span class="subject-updated">更新于 ${formatDate(subject.updated_at)}</span>
      </button>
      <div class="subject-actions">
        <button class="icon-button" type="button" data-action="start-rename"
          data-subject-id="${escapeHtml(subject.id)}" aria-label="重命名 ${escapeHtml(subject.name)}">✏️</button>
        <button class="icon-button icon-button-danger" type="button" data-action="delete-subject"
          data-subject-id="${escapeHtml(subject.id)}" aria-label="删除 ${escapeHtml(subject.name)}">🗑️</button>
      </div>
    </li>
  `;
}

function renderModelSection() {
  return `
    <section class="model-services" aria-labelledby="model-services-title" data-testid="model-services">
      <div class="section-heading">
        <h2 id="model-services-title">模型服务</h2>
        <span class="section-count" data-testid="model-count">${workspace.models.length}</span>
      </div>
      <button class="secondary-button" type="button" data-action="toggle-model-form" data-testid="toggle-model-form">
        ${showModelForm ? '收起配置' : '添加模型服务'}
      </button>
      ${showModelForm ? renderModelForm() : ''}
      <ul class="model-list" data-testid="model-list">${workspace.models.map(renderModelItem).join('')}</ul>
      ${workspace.models.length === 0 ? '<p class="section-hint">还没有模型服务。支持 OpenAI-compatible /chat/completions 文本接口。</p>' : ''}
    </section>
  `;
}

function renderModelForm() {
  return `
    <form class="model-form" data-form="model-add" data-testid="model-form">
      <label><span>服务商</span><input name="provider" type="text" maxlength="60" placeholder="例如：OpenAI" required /></label>
      <label><span>模型</span><input name="model" type="text" maxlength="120" placeholder="例如：gpt-4.1-mini" required /></label>
      <label><span>Base URL</span><input name="baseUrl" type="url" maxlength="500" placeholder="https://api.openai.com/v1" required /></label>
      <label><span>API Key（可选，仅保存在本地）</span><input name="apiKey" type="password" maxlength="2000" placeholder="sk-…" /></label>
      <button type="submit" data-testid="save-model-button">保存模型服务</button>
    </form>
  `;
}

function renderModelItem(profile) {
  const validating = verifyingModels.has(profile.id);
  return `
    <li class="model-item" data-model-id="${escapeHtml(profile.id)}" data-testid="model-item">
      <div class="model-main">
        <strong>${escapeHtml(profile.provider)} / ${escapeHtml(profile.model)}</strong>
        <code>${escapeHtml(profile.base_url)}</code>
        ${renderValidationBadge(profile.last_validation, validating)}
      </div>
      <div class="model-actions">
        <button class="small-button" type="button" data-action="verify-model"
          data-model-id="${escapeHtml(profile.id)}" ${validating ? 'disabled' : ''}>验证</button>
        <button class="small-button" type="button" data-action="use-model"
          data-model-id="${escapeHtml(profile.id)}">使用</button>
        <button class="small-button small-button-danger" type="button"
          data-action="delete-model" data-model-id="${escapeHtml(profile.id)}">删除</button>
      </div>
    </li>
  `;
}

function renderValidationBadge(validation, validating) {
  if (validating) return '<span class="validation-badge validation-checking">验证中…</span>';
  if (!validation) return '<span class="validation-badge validation-unknown">未验证</span>';
  const labels = { checking: '验证中…', ok: '可用', error: '验证失败', unknown: '未验证' };
  return `<span class="validation-badge validation-${escapeHtml(validation.status)}">${labels[validation.status] || '未验证'}</span>`;
}

function renderChatSection(subject) {
  if (!subject) {
    return `
      <section class="chat-panel" data-testid="chat-panel">
        <div class="section-heading"><h2>问答</h2></div>
        <p class="section-hint">创建科目空间后即可开始问答。</p>
      </section>
    `;
  }
  const chat = subjectChat(subject);
  const generating = generatingMessage(chat);
  return `
    <section class="chat-panel" aria-labelledby="chat-title" data-testid="chat-panel">
      <div class="section-heading chat-heading">
        <div>
          <h2 id="chat-title">问答</h2>
          <p class="chat-mode-note" data-testid="chat-mode-note">当前没有用户资料，回答使用通用知识模式</p>
        </div>
        <button class="small-button small-button-danger" type="button" data-action="clear-chat"
          data-subject-id="${escapeHtml(subject.id)}" data-testid="clear-chat-button"
          ${chat.messages.length === 0 || generating ? 'disabled' : ''}>清空记录</button>
      </div>
      <div class="chat-messages" data-testid="chat-messages">
        ${chat.messages.length === 0 ? renderChatEmpty() : chat.messages.map(renderChatMessage).join('')}
      </div>
      <form class="chat-composer" data-form="chat-send" data-subject-id="${escapeHtml(subject.id)}" data-testid="chat-composer">
        <div class="composer-row">
          <label class="composer-model-label" for="model-select">模型</label>
          <select id="model-select" name="model" data-model-select data-testid="model-select" ${generating ? 'disabled' : ''}>
            ${workspace.models.length === 0 ? '<option value="">请先添加模型服务</option>' : ''}
            ${workspace.models.map((profile) => `
              <option value="${escapeHtml(profile.id)}" ${profile.id === chat.active_model_id ? 'selected' : ''}>
                ${escapeHtml(profile.provider)} / ${escapeHtml(profile.model)}
              </option>`).join('')}
          </select>
        </div>
        <div class="composer-row">
          <label class="visually-hidden" for="chat-message-input">问题</label>
          <textarea id="chat-message-input" name="message" rows="3" maxlength="${CHAT_MESSAGE_MAX_LENGTH}"
            placeholder="${workspace.models.length === 0 ? '请先添加并验证模型服务' : '输入问题，例如：请解释泰勒展开'}"
            data-testid="chat-message-input" ${generating || workspace.models.length === 0 ? 'disabled' : ''}></textarea>
        </div>
        <div class="composer-actions">
          ${generating
            ? '<button class="stop-button" type="button" data-action="stop-generation" data-testid="stop-generation-button">停止生成</button>'
            : `<button class="primary-button" type="submit" data-testid="send-message-button" ${workspace.models.length === 0 ? 'disabled' : ''}>发送</button>`}
        </div>
      </form>
    </section>
  `;
}

function renderChatEmpty() {
  return `
    <div class="chat-empty" data-testid="chat-empty">
      <p>这个科目的会话记录会完整保存在本地。</p>
      <p>发送第一条问题开始学习。</p>
    </div>
  `;
}

function renderChatMessage(message) {
  if (message.role === 'user') {
    return `
      <article class="chat-message chat-message-user">
        <div class="chat-message-content">${formatContent(message.content)}</div>
      </article>
    `;
  }
  const model = message.model || {};
  const statusLabels = { generating: '正在生成…', complete: '已完成', stopped: '已停止', error: '生成失败' };
  const emptyCopy = {
    error: message.error?.message || '生成失败',
    stopped: '已停止生成。',
    complete: '模型未返回文本内容。',
    generating: '正在思考…'
  }[message.status] || '生成已结束。';
  const content = message.content
    ? formatContent(message.content)
    : `<span class="chat-status-copy">${escapeHtml(emptyCopy)}</span>`;
  return `
    <article class="chat-message chat-message-assistant chat-message-${escapeHtml(message.status)}" data-testid="chat-message-assistant">
      <div class="chat-message-meta">
        <span class="mode-badge mode-general" title="当前科目没有用户资料，回答未依据用户资料">通用知识模式</span>
        ${model.provider || model.model
          ? `<span class="model-badge" data-testid="message-model-info">${escapeHtml(model.provider)} / ${escapeHtml(model.model)}</span>`
          : ''}
        <span class="message-status">${statusLabels[message.status] || message.status}</span>
      </div>
      <div class="chat-message-content">${content}</div>
      ${message.status === 'error' && message.error ? `<p class="message-error">${escapeHtml(message.error.message)}</p>` : ''}
    </article>
  `;
}

function renderContentPanel(subject) {
  if (!subject) {
    return `
      <div class="content-empty">
        <div class="empty-card">
          <p class="empty-eyebrow">工作区</p>
          <h2>创建第一个科目空间</h2>
          <p>科目空间会把资料、会话记录、试卷和错题独立保存在一起。</p>
          <button type="button" class="primary-button" data-action="focus-create-subject">创建科目空间</button>
        </div>
      </div>
    `;
  }
  const chat = subjectChat(subject);
  return `
    <header class="content-header">
      <div>
        <p class="content-kicker">当前科目空间</p>
        <h2 data-testid="active-subject-name">${escapeHtml(subject.name)}</h2>
      </div>
      <p class="content-meta" data-testid="active-subject-meta">
        创建于 ${formatDate(subject.created_at)} · ${chat.messages.length} 条会话消息
      </p>
    </header>
    <section class="content-body">
      <div class="placeholder-card">
        <span class="placeholder-mark" aria-hidden="true">📚</span>
        <h3>工作区已就绪</h3>
        <p>左侧是 AI 问答和学习操作区，右侧将来放置试卷或学习文档。当前「${escapeHtml(subject.name)}」没有用户资料，问答会明确标注为通用知识模式。</p>
        <dl class="placeholder-facts">
          <div><dt>科目隔离</dt><dd>会话记录不会跨科目混合</dd></div>
          <div><dt>本地保存</dt><dd>完整会话记录在重新打开应用后恢复</dd></div>
        </dl>
      </div>
    </section>
  `;
}

root.addEventListener('submit', async (event) => {
  const form = event.target.closest('form[data-form]');
  if (!form) return;
  event.preventDefault();

  try {
    if (form.dataset.form === 'create-subject') {
      createDraft = form.elements.name?.value || '';
      await perform(api.createSubject(createDraft));
      if (workspace.subjects.length > 0) createDraft = '';
      render();
      root.querySelector('#subject-name-input')?.focus();
      return;
    }

    if (form.dataset.form === 'rename-subject') {
      editingName = form.elements.name?.value || '';
      const payload = await perform(api.renameSubject(form.dataset.subjectId, editingName));
      if (payload.ok) {
        editingSubjectId = null;
        editingName = '';
        render();
      }
      return;
    }

    if (form.dataset.form === 'model-add') {
      const elements = form.elements;
      const payload = await perform(api.addModel({
        provider: elements.provider?.value || '',
        model: elements.model?.value || '',
        baseUrl: elements.baseUrl?.value || '',
        apiKey: elements.apiKey?.value || ''
      }));
      if (payload.ok) {
        showModelForm = false;
        render();
      }
      return;
    }

    if (form.dataset.form === 'chat-send') {
      const subjectId = form.dataset.subjectId;
      const content = form.elements.message?.value || '';
      const modelId = form.elements.model?.value || '';
      const payload = await perform(api.sendMessage(subjectId, content, modelId));
      if (payload.ok) {
        const input = root.querySelector('#chat-message-input');
        if (input) input.value = '';
      }
    }
  } catch (error) {
    setError(error);
  }
});

root.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const { action, subjectId, modelId } = button.dataset;

  try {
    if (action === 'focus-create-subject') {
      root.querySelector('#subject-name-input')?.focus();
      return;
    }
    if (action === 'activate-subject') {
      await perform(api.activateSubject(subjectId));
      return;
    }
    if (action === 'start-rename') {
      const subject = workspace.subjects.find((candidate) => candidate.id === subjectId);
      if (!subject) return;
      editingSubjectId = subjectId;
      editingName = subject.name;
      status = null;
      render();
      return;
    }
    if (action === 'rename-cancel') {
      editingSubjectId = null;
      editingName = '';
      status = null;
      render();
      return;
    }
    if (action === 'delete-subject') {
      const subject = workspace.subjects.find((candidate) => candidate.id === subjectId);
      if (!subject || !confirmDelete(subject)) return;
      await perform(api.deleteSubject(subjectId));
      if (editingSubjectId === subjectId) {
        editingSubjectId = null;
        editingName = '';
      }
      return;
    }
    if (action === 'toggle-model-form') {
      showModelForm = !showModelForm;
      status = null;
      render();
      return;
    }
    if (action === 'verify-model') {
      verifyingModels.add(modelId);
      render();
      try {
        await perform(api.verifyModel(modelId));
      } finally {
        verifyingModels.delete(modelId);
        render();
      }
      return;
    }
    if (action === 'use-model') {
      const subject = activeSubject();
      if (!subject) return;
      await perform(api.selectChatModel(subject.id, modelId));
      return;
    }
    if (action === 'delete-model') {
      await perform(api.deleteModel(modelId));
      return;
    }
    if (action === 'clear-chat') {
      if (!confirmClear()) return;
      await perform(api.clearChat(subjectId));
      return;
    }
    if (action === 'stop-generation') {
      await perform(api.stopGeneration(subjectId || activeSubject()?.id));
    }
  } catch (error) {
    setError(error);
  }
});

root.addEventListener('change', async (event) => {
  const select = event.target.closest?.('[data-model-select]');
  if (!select) return;
  const subject = activeSubject();
  if (!subject || !select.value) return;
  try {
    await perform(api.selectChatModel(subject.id, select.value));
  } catch (error) {
    setError(error);
  }
});

function confirmDelete(subject) {
  return window.confirm?.(
    `确认删除科目空间「${subject.name}」？\n\n该科目空间下的资料、会话记录、试卷和作答都会随科目一起删除。`
  ) ?? false;
}

function confirmClear() {
  return window.confirm?.('确认清空当前科目的完整会话记录？此操作不可撤销。') ?? false;
}

function formatDate(timestamp) {
  if (!Number.isFinite(timestamp)) return '未知时间';
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
  }).format(new Date(timestamp));
}

function formatContent(content) {
  return escapeHtml(content).replaceAll('\n', '<br>');
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

init();
