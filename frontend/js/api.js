const jsonHeaders = { 'Content-Type': 'application/json' };

export async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { ...jsonHeaders, ...(options.headers || {}) }
  });

  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`服务返回了无法解析的响应（HTTP ${response.status}）`);
  }

  if (!response.ok || payload.ok === false) {
    const message = payload?.error?.message || `请求失败（HTTP ${response.status}）`;
    throw new Error(message);
  }
  return payload;
}

export const api = {
  getWorkspace() {
    return apiRequest('/api/workspace');
  },

  createSubject(name) {
    return apiRequest('/api/subjects', { method: 'POST', body: JSON.stringify({ name }) });
  },

  renameSubject(subjectId, name) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ name })
    });
  },

  activateSubject(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/activate`, { method: 'POST' });
  },

  deleteSubject(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}`, { method: 'DELETE' });
  },

  addModel({ provider, model, baseUrl, apiKey }) {
    return apiRequest('/api/models', {
      method: 'POST',
      body: JSON.stringify({ provider, model, base_url: baseUrl, api_key: apiKey })
    });
  },

  deleteModel(modelId) {
    return apiRequest(`/api/models/${encodeURIComponent(modelId)}`, { method: 'DELETE' });
  },

  verifyModel(modelId) {
    return apiRequest(`/api/models/${encodeURIComponent(modelId)}/verify`, { method: 'POST' });
  },

  selectChatModel(subjectId, modelId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/chat/model`, {
      method: 'POST',
      body: JSON.stringify({ model_id: modelId })
    });
  },

  sendMessage(subjectId, content, modelId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/chat/messages`, {
      method: 'POST',
      body: JSON.stringify({ content, model_id: modelId || null })
    });
  },

  stopGeneration(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/chat/stop`, { method: 'POST' });
  },

  clearChat(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/chat`, { method: 'DELETE' });
  }
};
