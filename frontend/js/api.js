/**
 * Unified API Client for Learning Loop Agent
 * Strictly aligned with FastAPI routes and OpenAPI 3.1 contract.
 */

export class ApiError extends Error {
  constructor(message, code = 'INTERNAL_ERROR', status = 500, details = null) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

async function apiRequest(endpoint, options = {}) {
  const url = endpoint.startsWith('http') ? endpoint : endpoint;
  const headers = {
    Accept: 'application/json',
    ...(options.headers || {})
  };

  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(url, { ...options, headers });

  if (response.status === 204) {
    return null;
  }

  const contentType = response.headers.get('content-type') || '';
  let payload = null;

  if (contentType.includes('application/json')) {
    payload = await response.json().catch(() => null);
  } else {
    payload = await response.text().catch(() => null);
  }

  if (!response.ok) {
    const msg =
      (payload && typeof payload === 'object' && (payload.detail || payload.message || payload.error?.message)) ||
      `HTTP error ${response.status}`;
    const code = (payload && typeof payload === 'object' && payload.error?.code) || 'API_ERROR';
    throw new ApiError(msg, code, response.status, payload);
  }

  return payload;
}

export const api = {
  // --- Workspace & Subjects ---
  getWorkspace() {
    return apiRequest('/api/workspace');
  },

  listSubjects() {
    return apiRequest('/api/subjects').catch(() => ({ items: [] }));
  },

  createSubject(name) {
    return apiRequest('/api/subjects', {
      method: 'POST',
      body: JSON.stringify({ name })
    });
  },

  getSubject(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}`);
  },

  renameSubject(subjectId, name) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ name })
    });
  },

  deleteSubject(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}`, {
      method: 'DELETE'
    });
  },

  activateSubject(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/activate`, {
      method: 'POST'
    });
  },

  listArtifacts(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/artifacts`).catch(() => ({ items: [] }));
  },

  // --- Model Management & Discovery (Issue 19, ADR 0005) ---
  listModels() {
    return apiRequest('/api/models').catch(() => ({ items: [] }));
  },

  createModel(config) {
    return apiRequest('/api/models', {
      method: 'POST',
      body: JSON.stringify({
        provider: config.provider || 'openai',
        api_format: config.api_format || 'openai-chat-completions',
        model: config.model,
        base_url: config.base_url || 'https://api.openai.com/v1',
        api_key: config.api_key || undefined,
        name: config.name || config.model
      })
    });
  },

  addModel(config) {
    return this.createModel(config);
  },

  getModel(modelId) {
    return apiRequest(`/api/models/${encodeURIComponent(modelId)}`);
  },

  deleteModel(modelId) {
    return apiRequest(`/api/models/${encodeURIComponent(modelId)}`, {
      method: 'DELETE'
    });
  },

  getCurrentModel() {
    return apiRequest('/api/models/current');
  },

  selectCurrentModel(modelId) {
    return apiRequest('/api/models/current', {
      method: 'PUT',
      body: JSON.stringify({ model_id: modelId })
    });
  },

  verifyModel(modelId) {
    return apiRequest(`/api/models/${encodeURIComponent(modelId)}/verify`, {
      method: 'POST'
    });
  },

  discoverModels({ provider, api_format, base_url, api_key }) {
    return apiRequest('/api/models/discover', {
      method: 'POST',
      body: JSON.stringify({
        provider: provider || 'openai',
        api_format: api_format || 'openai-chat-completions',
        base_url: base_url || 'https://api.openai.com/v1',
        api_key: api_key || undefined
      })
    });
  },

  // --- Async Operations & Polling ---
  getOperation(operationId) {
    return apiRequest(`/api/operations/${encodeURIComponent(operationId)}`);
  },

  cancelOperation(operationId) {
    return apiRequest(`/api/operations/${encodeURIComponent(operationId)}/cancel`, {
      method: 'POST'
    });
  },

  async pollOperation(operationId, { intervalMs = 250, maxAttempts = 120, onProgress = null } = {}) {
    let attempts = 0;
    while (attempts < maxAttempts) {
      const op = await this.getOperation(operationId);
      if (onProgress) onProgress(op);

      if (op.status === 'succeeded') {
        return op;
      }
      if (op.status === 'failed' || op.status === 'canceled') {
        const errorMsg = op.error?.message || `Operation ${op.status}`;
        throw new ApiError(errorMsg, op.error?.code || 'OPERATION_FAILED', 400, op.error);
      }

      await new Promise((resolve) => setTimeout(resolve, intervalMs));
      attempts++;
    }
    throw new ApiError('异步任务执行超时', 'OPERATION_TIMEOUT', 408);
  },

  // --- Multi-Session (Ticket 16, 17, 18) ---
  listSessions(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/sessions`).catch(() => ({ items: [] }));
  },

  createSession(subjectId, { title, learning_mode = 'chat', chat_style = 'default', grounding_mode = 'general-knowledge', source_version_ids = [] }) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/sessions`, {
      method: 'POST',
      body: JSON.stringify({
        title: title || '学习会话',
        learning_mode: learning_mode || chat_style || 'chat',
        chat_style: chat_style || learning_mode || 'default',
        grounding_mode,
        source_version_ids
      })
    });
  },

  getSession(sessionId) {
    return apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}`);
  },

  updateSession(sessionId, updates) {
    return apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'PATCH',
      body: JSON.stringify(updates)
    });
  },

  deleteSession(sessionId) {
    return apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE'
    });
  },

  activateSession(sessionId) {
    return apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}/activate`, {
      method: 'POST'
    });
  },

  createSessionMessage(sessionId, { content, chat_style = 'default', selection = null, source_version_ids = [], attachment_ids = [] }) {
    return apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}/messages`, {
      method: 'POST',
      body: JSON.stringify({
        content,
        chat_style,
        selection,
        source_version_ids,
        attachment_ids
      })
    });
  },

  // --- General Subject Chat & Attachments ---
  getChat(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/chat`);
  },

  sendMessage(subjectId, { content, chat_style = 'default', selection = null, source_version_ids = [], attachment_ids = [] }) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/chat/messages`, {
      method: 'POST',
      body: JSON.stringify({
        content,
        chat_style,
        selection,
        source_version_ids,
        attachment_ids
      })
    });
  },

  stopChat(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/chat/stop`, {
      method: 'POST'
    });
  },

  clearChat(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/chat`, {
      method: 'DELETE'
    });
  },

  uploadChatAttachment(subjectId, file) {
    const formData = new FormData();
    formData.append('file', file);
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/attachments`, {
      method: 'POST',
      body: formData
    });
  },

  // --- User Sources ---
  listSources(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/sources`).catch(() => ({ items: [] }));
  },

  uploadSource(subjectId, file) {
    const formData = new FormData();
    formData.append('file', file);
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/sources`, {
      method: 'POST',
      body: formData
    });
  },

  getSource(sourceId) {
    return apiRequest(`/api/sources/${encodeURIComponent(sourceId)}`);
  },

  deleteSource(sourceId) {
    return apiRequest(`/api/sources/${encodeURIComponent(sourceId)}`, {
      method: 'DELETE'
    });
  },

  listSourceVersions(sourceId) {
    return apiRequest(`/api/sources/${encodeURIComponent(sourceId)}/versions`).catch(() => ({ items: [] }));
  },

  listSourceVersionAnchors(versionId) {
    return apiRequest(`/api/source-versions/${encodeURIComponent(versionId)}/anchors`).catch(() => ({ items: [] }));
  },

  // --- AI-Authored Documents (Ticket 20) ---
  listAiDocuments(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/documents`).catch(() => ({ items: [] }));
  },

  createAiDocument(subjectId, payload) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/documents`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  getAiDocument(documentId) {
    return apiRequest(`/api/documents/${encodeURIComponent(documentId)}`);
  },

  listAiDocumentVersions(documentId) {
    return apiRequest(`/api/documents/${encodeURIComponent(documentId)}/versions`).catch(() => ({ items: [] }));
  },

  listAiDocumentRevisionProposals(documentId) {
    return apiRequest(`/api/documents/${encodeURIComponent(documentId)}/revision-proposals`).catch(() => ({ items: [] }));
  },

  createAiDocumentRevisionProposal(documentId, payload) {
    return apiRequest(`/api/documents/${encodeURIComponent(documentId)}/revision-proposals`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  applyAiDocumentRevisionProposal(proposalId) {
    return apiRequest(`/api/document-revision-proposals/${encodeURIComponent(proposalId)}/apply`, {
      method: 'POST'
    });
  },

  discardAiDocumentRevisionProposal(proposalId) {
    return apiRequest(`/api/document-revision-proposals/${encodeURIComponent(proposalId)}/discard`, {
      method: 'POST'
    });
  },

  restoreAiDocumentVersion(documentId, versionId) {
    return apiRequest(`/api/documents/${encodeURIComponent(documentId)}/versions/${encodeURIComponent(versionId)}/restore`, {
      method: 'POST'
    });
  },

  // --- Exam Studio: Blueprints, Drafts, Exams (Ticket 08, 09, 13) ---
  listBlueprints(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/exam-blueprints`).catch(() => ({ items: [] }));
  },

  createBlueprint(subjectId, payload) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/exam-blueprints`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  getBlueprint(blueprintId) {
    return apiRequest(`/api/exam-blueprints/${encodeURIComponent(blueprintId)}`);
  },

  confirmBlueprint(blueprintId) {
    return apiRequest(`/api/exam-blueprints/${encodeURIComponent(blueprintId)}/confirm`, {
      method: 'POST'
    });
  },

  generateDraftFromBlueprint(blueprintId) {
    return apiRequest(`/api/exam-blueprints/${encodeURIComponent(blueprintId)}/generate`, {
      method: 'POST'
    });
  },

  listDrafts(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/exam-drafts`).catch(() => ({ items: [] }));
  },

  getDraft(draftId) {
    return apiRequest(`/api/exam-drafts/${encodeURIComponent(draftId)}`);
  },

  retryDraftQuestion(draftId, questionId) {
    return apiRequest(`/api/exam-drafts/${encodeURIComponent(draftId)}/questions/${encodeURIComponent(questionId)}/retry`, {
      method: 'POST'
    });
  },

  publishDraft(draftId) {
    return apiRequest(`/api/exam-drafts/${encodeURIComponent(draftId)}/publish`, {
      method: 'POST'
    });
  },

  listExams(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/exams`).catch(() => ({ items: [] }));
  },

  getExam(examId) {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}`);
  },

  listExamVersions(examId) {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}/versions`).catch(() => ({ items: [] }));
  },

  createExamExport(examId, { format = 'pdf', edition = 'questions' }) {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}/exports`, {
      method: 'POST',
      body: JSON.stringify({ format, edition })
    });
  },

  getExamExport(exportId) {
    return apiRequest(`/api/exports/${encodeURIComponent(exportId)}`);
  },

  // --- Attempts, Practice & Grading (Ticket 10, 11, 21) ---
  createAttempt(examId, payload = {}) {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}/attempts`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  getAttempt(attemptId) {
    return apiRequest(`/api/attempts/${encodeURIComponent(attemptId)}`);
  },

  saveAttemptAnswer(attemptId, questionId, answer) {
    return apiRequest(`/api/attempts/${encodeURIComponent(attemptId)}/answers/${encodeURIComponent(questionId)}`, {
      method: 'PUT',
      body: JSON.stringify({ answer })
    });
  },

  requestQuestionFeedback(attemptId, questionId, payload = {}) {
    return apiRequest(`/api/attempts/${encodeURIComponent(attemptId)}/answers/${encodeURIComponent(questionId)}/feedback`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  completeAttempt(attemptId) {
    return apiRequest(`/api/attempts/${encodeURIComponent(attemptId)}/complete`, {
      method: 'POST'
    });
  },

  continueAttempt(attemptId) {
    return apiRequest(`/api/attempts/${encodeURIComponent(attemptId)}/continue`, {
      method: 'POST'
    });
  },

  submitAttemptGrading(attemptId, payload = {}) {
    return apiRequest(`/api/attempts/${encodeURIComponent(attemptId)}/grade`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  getAttemptReview(attemptId) {
    return apiRequest(`/api/attempts/${encodeURIComponent(attemptId)}/review`);
  },

  pauseAttempt(attemptId) {
    return apiRequest(`/api/attempts/${encodeURIComponent(attemptId)}/pause`, {
      method: 'POST'
    });
  },

  resumeAttempt(attemptId) {
    return apiRequest(`/api/attempts/${encodeURIComponent(attemptId)}/resume`, {
      method: 'POST'
    });
  }
};
