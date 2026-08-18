export class ApiError extends Error {
  constructor(message, code = 'INTERNAL_ERROR', status = 500, details = null) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

function formatErrorMessage(error, payload, status) {
  const base = error?.message || (typeof payload === 'string' && payload) || `请求失败 ${status}`;
  const fields = error?.details?.fields;
  if (!Array.isArray(fields) || !fields.length) return base;
  const detail = fields
    .map((item) => {
      const path = String(item?.path || '').replace(/^body\.?/, '');
      const message = item?.message || '';
      if (path && message) return `${path}: ${message}`;
      return path || message;
    })
    .filter(Boolean)
    .slice(0, 3)
    .join('；');
  return detail ? `${base}（${detail}）` : base;
}

async function request(endpoint, options = {}) {
  const headers = { Accept: 'application/json', ...(options.headers || {}) };
  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  let response;
  try {
    response = await fetch(endpoint, { ...options, headers });
  } catch (err) {
    throw new ApiError(
      '无法连接本地服务，请确认已启动 uvicorn（http://127.0.0.1:4173）',
      'NETWORK_ERROR',
      0,
      { cause: String(err?.message || err) },
    );
  }
  if (response.status === 204) return null;

  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json')
    ? await response.json().catch(() => null)
    : await response.text().catch(() => null);

  if (!response.ok) {
    const error = payload && typeof payload === 'object' ? payload.error : null;
    throw new ApiError(
      formatErrorMessage(error, payload, response.status),
      error?.code || 'API_ERROR',
      response.status,
      error?.details || payload,
    );
  }
  return payload;
}

function json(method, endpoint, body) {
  return request(endpoint, { method, body: body === undefined ? undefined : JSON.stringify(body) });
}

export const api = {
  getHealth() {
    return request('/api/health');
  },
  getWorkspace() {
    return request('/api/workspace');
  },

  listSubjects() {
    return request('/api/subjects');
  },
  createSubject(name) {
    return json('POST', '/api/subjects', { name });
  },
  getSubject(subjectId) {
    return request(`/api/subjects/${encodeURIComponent(subjectId)}`);
  },
  renameSubject(subjectId, name) {
    return json('PATCH', `/api/subjects/${encodeURIComponent(subjectId)}`, { name });
  },
  deleteSubject(subjectId) {
    return request(`/api/subjects/${encodeURIComponent(subjectId)}`, { method: 'DELETE' });
  },
  activateSubject(subjectId) {
    return json('POST', `/api/subjects/${encodeURIComponent(subjectId)}/activate`);
  },

  listModels() {
    return request('/api/models');
  },
  createModel(config) {
    return json('POST', '/api/models', config);
  },
  getModel(modelId) {
    return request(`/api/models/${encodeURIComponent(modelId)}`);
  },
  updateModel(modelId, patch) {
    return json('PATCH', `/api/models/${encodeURIComponent(modelId)}`, patch);
  },
  deleteModel(modelId) {
    return request(`/api/models/${encodeURIComponent(modelId)}`, { method: 'DELETE' });
  },
  verifyModel(modelId) {
    return json('POST', `/api/models/${encodeURIComponent(modelId)}/verify`);
  },
  getCurrentModel() {
    return request('/api/models/current');
  },
  selectCurrentModel(modelId) {
    return json('PUT', '/api/models/current', { model_id: modelId });
  },
  discoverModels(payload) {
    return json('POST', '/api/models/discover', payload);
  },

  getOperation(operationId) {
    return request(`/api/operations/${encodeURIComponent(operationId)}`);
  },
  cancelOperation(operationId) {
    return json('POST', `/api/operations/${encodeURIComponent(operationId)}/cancel`);
  },
  async pollOperation(operationId, { intervalMs = 400, maxAttempts = 180, onProgress } = {}) {
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      const op = await this.getOperation(operationId);
      onProgress?.(op);
      if (op.status === 'succeeded') return op;
      if (op.status === 'failed' || op.status === 'canceled') {
        throw new ApiError(op.error?.message || `任务${op.status === 'canceled' ? '已取消' : '失败'}`, op.error?.code || 'OPERATION_FAILED', 400, op.error);
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    throw new ApiError('任务超时', 'OPERATION_TIMEOUT', 408);
  },

  listSessions(subjectId) {
    return request(`/api/subjects/${encodeURIComponent(subjectId)}/sessions`);
  },
  createSession(subjectId, payload = {}) {
    return json('POST', `/api/subjects/${encodeURIComponent(subjectId)}/sessions`, payload);
  },
  getSession(sessionId) {
    return request(`/api/sessions/${encodeURIComponent(sessionId)}`);
  },
  updateSession(sessionId, patch) {
    return json('PATCH', `/api/sessions/${encodeURIComponent(sessionId)}`, patch);
  },
  deleteSession(sessionId) {
    return request(`/api/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
  },
  activateSession(sessionId) {
    return json('POST', `/api/sessions/${encodeURIComponent(sessionId)}/activate`);
  },
  createSessionMessage(sessionId, payload) {
    return json('POST', `/api/sessions/${encodeURIComponent(sessionId)}/messages`, payload);
  },
  listSessionSources(sessionId) {
    return request(`/api/sessions/${encodeURIComponent(sessionId)}/sources`);
  },
  addSessionSource(sessionId, sourceVersionId) {
    return json('POST', `/api/sessions/${encodeURIComponent(sessionId)}/sources`, { source_version_id: sourceVersionId });
  },
  removeSessionSource(sessionId, versionId) {
    return request(`/api/sessions/${encodeURIComponent(sessionId)}/sources/${encodeURIComponent(versionId)}`, { method: 'DELETE' });
  },

  uploadAttachment(subjectId, file) {
    const body = new FormData();
    body.append('file', file);
    return request(`/api/subjects/${encodeURIComponent(subjectId)}/attachments`, { method: 'POST', body });
  },

  listSources(subjectId) {
    return request(`/api/subjects/${encodeURIComponent(subjectId)}/sources`);
  },
  uploadSource(subjectId, file, displayName) {
    const body = new FormData();
    body.append('file', file);
    if (displayName) body.append('display_name', displayName);
    return request(`/api/subjects/${encodeURIComponent(subjectId)}/sources`, { method: 'POST', body });
  },
  getSource(sourceId) {
    return request(`/api/sources/${encodeURIComponent(sourceId)}`);
  },
  deleteSource(sourceId) {
    return request(`/api/sources/${encodeURIComponent(sourceId)}`, { method: 'DELETE' });
  },
  listSourceVersions(sourceId) {
    return request(`/api/sources/${encodeURIComponent(sourceId)}/versions`);
  },
  uploadSourceVersion(sourceId, file) {
    const body = new FormData();
    body.append('file', file);
    return request(`/api/sources/${encodeURIComponent(sourceId)}/versions`, { method: 'POST', body });
  },
  listSourceVersionAnchors(versionId) {
    return request(`/api/source-versions/${encodeURIComponent(versionId)}/anchors`);
  },

  listAiDocuments(subjectId) {
    return request(`/api/subjects/${encodeURIComponent(subjectId)}/documents`);
  },
  createAiDocument(subjectId, payload) {
    return json('POST', `/api/subjects/${encodeURIComponent(subjectId)}/documents`, payload);
  },
  getAiDocument(documentId) {
    return request(`/api/documents/${encodeURIComponent(documentId)}`);
  },
  listAiDocumentVersions(documentId) {
    return request(`/api/documents/${encodeURIComponent(documentId)}/versions`);
  },
  listAiDocumentRevisionProposals(documentId) {
    return request(`/api/documents/${encodeURIComponent(documentId)}/revision-proposals`);
  },
  createAiDocumentRevisionProposal(documentId, payload) {
    return json('POST', `/api/documents/${encodeURIComponent(documentId)}/revision-proposals`, payload);
  },
  applyAiDocumentRevisionProposal(proposalId) {
    return json('POST', `/api/document-revision-proposals/${encodeURIComponent(proposalId)}/apply`);
  },
  discardAiDocumentRevisionProposal(proposalId) {
    return json('POST', `/api/document-revision-proposals/${encodeURIComponent(proposalId)}/discard`);
  },
  restoreAiDocumentVersion(documentId, versionId) {
    return json('POST', `/api/documents/${encodeURIComponent(documentId)}/versions/${encodeURIComponent(versionId)}/restore`);
  },

  listBlueprints(subjectId) {
    return request(`/api/subjects/${encodeURIComponent(subjectId)}/exam-blueprints`);
  },
  parseBlueprint(subjectId, payload) {
    return json('POST', `/api/subjects/${encodeURIComponent(subjectId)}/exam-blueprints`, payload);
  },
  getBlueprint(blueprintId) {
    return request(`/api/exam-blueprints/${encodeURIComponent(blueprintId)}`);
  },
  updateBlueprint(blueprintId, patch) {
    return json('PATCH', `/api/exam-blueprints/${encodeURIComponent(blueprintId)}`, patch);
  },
  deleteBlueprint(blueprintId) {
    return request(`/api/exam-blueprints/${encodeURIComponent(blueprintId)}`, { method: 'DELETE' });
  },
  confirmBlueprint(blueprintId) {
    return json('POST', `/api/exam-blueprints/${encodeURIComponent(blueprintId)}/confirm`);
  },
  generateDraftFromBlueprint(blueprintId) {
    return json('POST', `/api/exam-blueprints/${encodeURIComponent(blueprintId)}/generate`);
  },

  listDrafts(subjectId) {
    return request(`/api/subjects/${encodeURIComponent(subjectId)}/exam-drafts`);
  },
  getDraft(draftId) {
    return request(`/api/exam-drafts/${encodeURIComponent(draftId)}`);
  },
  retryDraftQuestion(draftId, questionId) {
    return json('POST', `/api/exam-drafts/${encodeURIComponent(draftId)}/questions/${encodeURIComponent(questionId)}/retry`);
  },
  publishDraft(draftId, payload = {}) {
    return json('POST', `/api/exam-drafts/${encodeURIComponent(draftId)}/publish`, payload);
  },

  listExams(subjectId) {
    return request(`/api/subjects/${encodeURIComponent(subjectId)}/exams`);
  },
  getExam(examId) {
    return request(`/api/exams/${encodeURIComponent(examId)}`);
  },
  listExamVersions(examId) {
    return request(`/api/exams/${encodeURIComponent(examId)}/versions`);
  },
  undoExamChange(examId) {
    return json('POST', `/api/exams/${encodeURIComponent(examId)}/undo`);
  },
  redoExamChange(examId) {
    return json('POST', `/api/exams/${encodeURIComponent(examId)}/redo`);
  },
  listRevisionProposals(examId) {
    return request(`/api/exams/${encodeURIComponent(examId)}/revision-proposals`);
  },
  createRevisionProposal(examId, payload) {
    return json('POST', `/api/exams/${encodeURIComponent(examId)}/revision-proposals`, payload);
  },
  applyRevisionProposal(proposalId) {
    return json('POST', `/api/revision-proposals/${encodeURIComponent(proposalId)}/apply`);
  },
  discardRevisionProposal(proposalId) {
    return json('POST', `/api/revision-proposals/${encodeURIComponent(proposalId)}/discard`);
  },

  createAttempt(examId, payload) {
    return json('POST', `/api/exams/${encodeURIComponent(examId)}/attempts`, payload);
  },
  getAttempt(attemptId) {
    return request(`/api/attempts/${encodeURIComponent(attemptId)}`);
  },
  saveAttemptAnswer(attemptId, questionId, answer) {
    return json('PUT', `/api/attempts/${encodeURIComponent(attemptId)}/answers/${encodeURIComponent(questionId)}`, { answer });
  },
  requestQuestionFeedback(attemptId, questionId, payload = {}) {
    return json('POST', `/api/attempts/${encodeURIComponent(attemptId)}/answers/${encodeURIComponent(questionId)}/feedback`, payload);
  },
  completeAttempt(attemptId) {
    return json('POST', `/api/attempts/${encodeURIComponent(attemptId)}/complete`);
  },
  continueAttempt(attemptId) {
    return json('POST', `/api/attempts/${encodeURIComponent(attemptId)}/continue`);
  },
  submitAttemptGrading(attemptId, payload = {}) {
    return json('POST', `/api/attempts/${encodeURIComponent(attemptId)}/grade`, payload);
  },
  getAttemptReview(attemptId) {
    return request(`/api/attempts/${encodeURIComponent(attemptId)}/review`);
  },
  pauseAttempt(attemptId) {
    return json('POST', `/api/attempts/${encodeURIComponent(attemptId)}/pause`);
  },
  resumeAttempt(attemptId) {
    return json('POST', `/api/attempts/${encodeURIComponent(attemptId)}/resume`);
  },
};
