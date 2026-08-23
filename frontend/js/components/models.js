import { icons } from '../icons.js';
import { API_FORMATS, escapeHtml, normalizeBaseUrl, statusLabel } from '../util.js';

let lastModelsKey = null;

export function renderModels(state, root, handlers) {
  const key = modelsDialogKey(state);
  if (key === lastModelsKey) return;
  lastModelsKey = key;
  const html = modelsDialogHtml(state);
  if (!html) {
    root.innerHTML = '';
    return;
  }
  root.innerHTML = html;
  bindModelDialog(root, state, handlers);
}

function modelsDialogKey(state) {
  if (state.modal !== 'models') return '';
  return JSON.stringify({
    models: (state.models || []).map((item) => [
      item.id,
      item.model,
      item.provider,
      item.api_format,
      item.has_api_key,
      item.validation?.status,
      item.validation?.message,
      item.id === state.currentModelId,
    ]),
    editingId: state.editingModelId || null,
    busy: state.modelBusy,
    discovered: (state.discoveredModels || []).map((item) => item.name),
    discoverError: state.discoverError || '',
  });
}

function modelsDialogHtml(state) {
  if (state.modal !== 'models') return '';

  const form = state.modelForm || defaultForm();
  const discovered = state.discoveredModels || [];
  const editingId = state.editingModelId || null;
  const busy = state.modelBusy;
  const formatMeta = API_FORMATS.find((item) => item.id === form.api_format) || API_FORMATS[0];

  return `
    <div class="overlay">
      <div class="dialog dialog-models" role="dialog" aria-modal="true">
        <h2>模型服务</h2>
        <div class="model-list">
          ${(state.models || []).length
            ? state.models
                .map(
                  (item) => `
            <div class="model-row ${item.id === editingId ? 'is-editing' : ''}">
              <div>
                <div class="item-title">${escapeHtml(item.model)}</div>
                <div class="item-sub">
                  <span>${escapeHtml(item.provider)}</span>
                  <span>${formatLabel(item.api_format)}</span>
                  <span>${item.has_api_key ? '已填 Key' : '无 Key'}</span>
                  <span class="${item.validation?.status === 'ok' ? 'status-ok' : item.validation?.status === 'error' ? 'status-bad' : ''}">${statusLabel('validation', item.validation?.status)}</span>
                </div>
                ${item.validation?.message && item.validation.status === 'error' ? `<div class="model-error">${escapeHtml(item.validation.message)}</div>` : ''}
              </div>
              <div class="pane-actions">
                <button type="button" class="btn btn-ghost btn-sm" data-action="select-model" data-id="${item.id}" ${item.id === state.currentModelId ? 'disabled' : ''}>${item.id === state.currentModelId ? '当前' : '使用'}</button>
                <button type="button" class="icon-btn" data-action="edit-model" data-id="${item.id}" title="编辑">${icons.edit3(14)}</button>
                <button type="button" class="icon-btn" data-action="verify-model" data-id="${item.id}" title="测试连接" ${busy === 'verify' ? 'disabled' : ''}>${icons.zap(14)}</button>
                <button type="button" class="icon-btn" data-action="delete-model" data-id="${item.id}" title="删除">${icons.trash2(14)}</button>
              </div>
            </div>
          `,
                )
                .join('')
            : '<p class="item-sub">还没有模型服务</p>'}
        </div>
        <form id="model-form" class="form-grid">
          <label class="field"><span class="field-label">服务商</span><input class="input" name="provider" value="${escapeHtml(form.provider)}" placeholder="OpenAI / 自定义" /></label>
          <label class="field"><span class="field-label">API 格式</span>
            <input type="hidden" name="api_format" value="${escapeHtml(form.api_format)}" />
            <div class="dropdown field-dropdown">
              <button type="button" class="select select-trigger" data-action="toggle-format" title="${escapeHtml(formatMeta.hint)}" aria-expanded="false">
                <span class="select-value">${escapeHtml(formatMeta.label)}</span>
                ${icons.chevronDown(14)}
              </button>
              <div class="menu format-menu" role="menu" hidden>
                ${API_FORMATS.map((item) => `<button type="button" class="menu-item ${item.id === form.api_format ? 'is-active' : ''}" role="menuitem" data-action="pick-format" data-format="${escapeHtml(item.id)}"><span>${escapeHtml(item.label)}</span></button>`).join('')}
              </div>
            </div>
            <span class="field-hint" data-format-hint>${escapeHtml(formatMeta.hint)}，示例 ${escapeHtml(formatMeta.baseUrl)}</span>
          </label>
          <label class="field"><span class="field-label">Base URL</span><input class="input" name="base_url" value="${escapeHtml(form.base_url)}" placeholder="${escapeHtml(formatMeta.baseUrl)}" /></label>
          <label class="field"><span class="field-label">API Key</span><input class="input" name="api_key" type="password" value="${escapeHtml(form.api_key)}" placeholder="${editingId ? '留空则保持原 Key' : '可选'}" autocomplete="off" /></label>
          <label class="field"><span class="field-label">模型</span>
            <input class="input" name="model" list="discovered-models" value="${escapeHtml(form.model)}" placeholder="填写或从下方选择" />
            <datalist id="discovered-models">${discovered.map((item) => `<option value="${escapeHtml(item.name)}"></option>`).join('')}</datalist>
          </label>
          <label class="field field-inline">
            <input type="checkbox" name="vision" ${form.vision ? 'checked' : ''} />
            <span class="field-label">视觉</span>
          </label>
        </form>
        ${
          discovered.length
            ? `<div class="discover-list">${discovered
                .map(
                  (item) =>
                    `<button type="button" class="mini ${item.name === form.model ? 'is-active' : ''}" data-action="pick-discovered" data-name="${escapeHtml(item.name)}">${escapeHtml(item.name)}</button>`,
                )
                .join('')}</div>`
            : ''
        }
        ${state.discoverError ? `<p class="model-error">${escapeHtml(state.discoverError)}</p>` : ''}
        <div class="dialog-actions">
          <button type="button" class="btn btn-ghost" data-action="open-runs">运行记录</button>
          <button type="button" class="btn btn-ghost" data-action="discover-models" ${busy ? 'disabled' : ''}>${busy === 'discover' ? '发现中' : '发现模型'}</button>
          <button type="button" class="btn btn-ghost" data-action="close">关闭</button>
          <button type="button" class="btn btn-primary" data-action="save-model" ${busy ? 'disabled' : ''}>${editingId ? '保存' : '添加'}</button>
        </div>
      </div>
    </div>
  `;
}

function bindModelDialog(root, state, handlers) {
  let currentFormat = (state.modelForm || defaultForm()).api_format;
  const formEl = root.querySelector('#model-form');
  const overlay = root.querySelector('.overlay');
  const formatMenu = root.querySelector('.format-menu');
  const formatValue = root.querySelector('.select-value');
  const formatHint = root.querySelector('[data-format-hint]');
  const formatTrigger = root.querySelector('[data-action="toggle-format"]');

  const applyFormat = (id) => {
    const spec = API_FORMATS.find((item) => item.id === id);
    if (!spec || !formEl.elements.api_format) return;
    const prev = currentFormat;
    formEl.elements.api_format.value = id;
    if (formatValue) formatValue.textContent = spec.label;
    if (formatHint) formatHint.textContent = `${spec.hint}，示例 ${spec.baseUrl}`;
    if (formatTrigger) formatTrigger.title = spec.hint;
    formatMenu?.querySelectorAll('[data-format]').forEach((btn) => {
      btn.classList.toggle('is-active', btn.dataset.format === id);
    });
    const old = API_FORMATS.find((item) => item.id === prev);
    if (!formEl.elements.base_url.value || formEl.elements.base_url.value === old?.baseUrl) {
      formEl.elements.base_url.value = spec.baseUrl;
    }
    if (id === 'ollama' && (formEl.elements.provider.value === 'OpenAI' || prev === 'openai-chat-completions' || prev === 'openai-responses')) {
      formEl.elements.provider.value = 'Ollama';
    }
    currentFormat = id;
  };

  const syncForm = () => handlers.onModelFormChange(readForm(formEl));
  formEl.addEventListener('change', syncForm);
  formEl.addEventListener('input', syncForm);
  overlay.addEventListener('keydown', (event) => {
    if (formatMenu?.hidden !== false) return;
    const items = [...formatMenu.querySelectorAll('.menu-item')];
    const focused = items.findIndex((item) => item.classList.contains('is-focused'));
    if (event.key === 'Escape') {
      event.preventDefault();
      formatMenu.hidden = true;
      formatTrigger?.setAttribute('aria-expanded', 'false');
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      items.forEach((item) => item.classList.remove('is-focused'));
      const next = event.key === 'ArrowDown'
        ? (focused + 1) % items.length
        : (focused <= 0 ? items.length - 1 : focused - 1);
      items[next]?.classList.add('is-focused');
      items[next]?.focus();
      return;
    }
    if (event.key === 'Enter' && focused >= 0) {
      event.preventDefault();
      items[focused]?.click();
    }
  });

  let closeArmed = false;
  overlay.addEventListener('pointerdown', (event) => {
    closeArmed = event.target === overlay;
  });
  overlay.addEventListener('click', (event) => {
    event.stopPropagation();
    const action = event.target.closest('[data-action]')?.dataset.action;
    const id = event.target.closest('[data-id]')?.dataset.id;
    if (action === 'toggle-format') {
      if (formatMenu) {
        formatMenu.hidden = !formatMenu.hidden;
        formatTrigger?.setAttribute('aria-expanded', formatMenu.hidden ? 'false' : 'true');
      }
      return;
    }
    if (action === 'open-runs') {
      handlers.onOpenRuns();
      return;
    }
    if (action === 'pick-format') {
      const formatId = event.target.closest('[data-format]')?.dataset.format;
      if (formatId) applyFormat(formatId);
      if (formatMenu) formatMenu.hidden = true;
      syncForm();
      return;
    }
    if (formatMenu) formatMenu.hidden = true;
    if (action === 'close' || (event.target === overlay && closeArmed)) {
      handlers.onCloseModal();
      return;
    }
    if (action === 'save-model') handlers.onSaveModel(readForm(formEl));
    if (action === 'discover-models') handlers.onDiscoverModels(readForm(formEl));
    if (action === 'select-model') handlers.onSelectModel(id);
    if (action === 'edit-model') handlers.onEditModel(id);
    if (action === 'verify-model') handlers.onVerifyModel(id);
    if (action === 'delete-model') handlers.onDeleteModel(id);
    if (action === 'pick-discovered') handlers.onPickDiscovered(event.target.closest('[data-name]').dataset.name);
    closeArmed = false;
  });
}

export function defaultForm() {
  return {
    provider: 'OpenAI',
    api_format: 'openai-chat-completions',
    base_url: 'https://api.openai.com/v1',
    api_key: '',
    model: '',
    vision: false,
  };
}

export function formFromModel(model) {
  return {
    provider: model.provider || 'OpenAI',
    api_format: model.api_format || 'openai-chat-completions',
    base_url: model.base_url || '',
    api_key: '',
    model: model.model || '',
    vision: !!model.capabilities?.vision,
  };
}

function readForm(form) {
  const data = new FormData(form);
  return {
    provider: String(data.get('provider') || '').trim(),
    api_format: String(data.get('api_format') || 'openai-chat-completions'),
    base_url: normalizeBaseUrl(String(data.get('base_url') || '')),
    api_key: String(data.get('api_key') || ''),
    model: String(data.get('model') || '').trim(),
    vision: form.vision?.checked === true,
  };
}

function formatLabel(id) {
  return API_FORMATS.find((item) => item.id === id)?.label || id;
}
