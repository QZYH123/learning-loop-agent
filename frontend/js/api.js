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
      '无法连接本地服务，请确认应用已打开',
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

function filenameFromDisposition(header) {
  const starred = /filename\*=UTF-8''([^;]+)/i.exec(header || '');
  if (starred?.[1]) return decodeURIComponent(starred[1]);
  const quoted = /filename="([^"]+)"/i.exec(header || '');
  if (quoted?.[1]) return quoted[1];
  const plain = /filename=([^;]+)/i.exec(header || '');
  return plain?.[1]?.trim() || '';
}

function triggerDownload(blob, fileName) {
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = fileName;
  link.rel = 'noopener';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

async function downloadFile(endpoint, { accept, fallbackName }) {
  let response;
  try {
    response = await fetch(endpoint, { headers: { Accept: accept } });
  } catch (err) {
    throw new ApiError(
      '无法连接本地服务，请确认应用已打开',
      'NETWORK_ERROR',
      0,
      { cause: String(err?.message || err) },
    );
  }
  if (!response.ok) {
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json')
      ? await response.json().catch(() => null)
      : await response.text().catch(() => null);
    const error = payload && typeof payload === 'object' ? payload.error : null;
    throw new ApiError(
      formatErrorMessage(error, payload, response.status),
      error?.code || 'API_ERROR',
      response.status,
      error?.details || payload,
    );
  }
  const blob = await response.blob();
  const fileName = filenameFromDisposition(response.headers.get('content-disposition')) || fallbackName;
  triggerDownload(blob, fileName);
  return { fileName };
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
  exportSubject(subjectId) {
    return downloadFile(`/api/subjects/${encodeURIComponent(subjectId)}/export`, {
      accept: 'application/zip, application/json',
      fallbackName: 'subject.zip',
    });
  },
  importSubject(file) {
    const body = new FormData();
    body.append('file', file);
    return request('/api/subjects/import', { method: 'POST', body });
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
  async pollOperation(operationId, { deadlineMs = 15 * 60 * 1000, onProgress, intervalMs = 400, maxIntervalMs = 2500 } = {}) {
    const deadline = Date.now() + deadlineMs;
    let current = intervalMs;
    while (Date.now() < deadline) {
      const op = await this.getOperation(operationId);
      onProgress?.(op);
      if (op.status === 'succeeded') return op;
      if (op.status === 'failed' || op.status === 'canceled') {
        throw new ApiError(op.error?.message || `任务${op.status === 'canceled' ? '已取消' : '失败'}`, op.error?.code || 'OPERATION_FAILED', 400, op.error);
      }
      await new Promise((resolve) => setTimeout(resolve, current));
      current = Math.min(Math.round(current * 1.5), maxIntervalMs);
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
  }, // payload 可含 workspace_context，原样上送
  appendSessionNote(sessionId, payload) {
    return json('POST', `/api/sessions/${encodeURIComponent(sessionId)}/notes`, payload);
  },
  retrySessionMessage(sessionId, messageId, payload = {}) {
    return json('POST', `/api/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(messageId)}/retry`, payload);
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
  getCitation(citationId) {
    return request(`/api/citations/${encodeURIComponent(citationId)}`);
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
  deleteAiDocument(documentId) {
    return request(`/api/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' });
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
  deleteDraft(draftId) {
    return request(`/api/exam-drafts/${encodeURIComponent(draftId)}`, { method: 'DELETE' });
  },
  updateDraft(draftId, patch) {
    return json('PATCH', `/api/exam-drafts/${encodeURIComponent(draftId)}`, patch);
  },
  replaceDraftQuestion(draftId, questionId, payload) {
    return json('PUT', `/api/exam-drafts/${encodeURIComponent(draftId)}/questions/${encodeURIComponent(questionId)}`, payload);
  },
  deleteDraftQuestion(draftId, questionId) {
    return request(`/api/exam-drafts/${encodeURIComponent(draftId)}/questions/${encodeURIComponent(questionId)}`, { method: 'DELETE' });
  },
  retryDraftQuestion(draftId, questionId) {
    return json('POST', `/api/exam-drafts/${encodeURIComponent(draftId)}/questions/${encodeURIComponent(questionId)}/retry`);
  },
  publishDraft(draftId, payload = {}) {
    return json('POST', `/api/exam-drafts/${encodeURIComponent(draftId)}/publish`, payload);
  },
  listDraftRevisionProposals(draftId) {
    return request(`/api/exam-drafts/${encodeURIComponent(draftId)}/revision-proposals`);
  },
  createDraftRevisionProposal(draftId, payload) {
    return json('POST', `/api/exam-drafts/${encodeURIComponent(draftId)}/revision-proposals`, payload);
  },
  applyDraftRevisionProposal(proposalId) {
    return json('POST', `/api/draft-revision-proposals/${encodeURIComponent(proposalId)}/apply`);
  },
  discardDraftRevisionProposal(proposalId) {
    return json('POST', `/api/draft-revision-proposals/${encodeURIComponent(proposalId)}/discard`);
  },

  listExams(subjectId) {
    return request(`/api/subjects/${encodeURIComponent(subjectId)}/exams`);
  },
  listMissedQuestions(subjectId) {
    return request(`/api/subjects/${encodeURIComponent(subjectId)}/missed-questions`);
  },
  getExam(examId) {
    return request(`/api/exams/${encodeURIComponent(examId)}`);
  },
  deleteExam(examId) {
    return request(`/api/exams/${encodeURIComponent(examId)}`, { method: 'DELETE' });
  },
  updateExam(examId, patch) {
    return json('PATCH', `/api/exams/${encodeURIComponent(examId)}`, patch);
  },
  listExamVersions(examId) {
    return request(`/api/exams/${encodeURIComponent(examId)}/versions`);
  },
  restoreExamVersion(examId, versionId) {
    return json('POST', `/api/exams/${encodeURIComponent(examId)}/versions/${encodeURIComponent(versionId)}/restore`);
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
  getExamRenderDocument(examId, edition) {
    const params = new URLSearchParams({ edition });
    return request(`/api/exams/${encodeURIComponent(examId)}/render-document?${params}`);
  },
  createExamExport(examId, payload) {
    return json('POST', `/api/exams/${encodeURIComponent(examId)}/exports`, payload);
  },
  getExamExport(exportId) {
    return request(`/api/exports/${encodeURIComponent(exportId)}`);
  },
  async downloadExamExport(exportId) {
    return downloadFile(`/api/exports/${encodeURIComponent(exportId)}/file`, {
      accept: 'application/pdf, text/markdown, application/json',
      fallbackName: `export-${exportId}`,
    });
  },

  listExamAttempts(examId) {
    return request(`/api/exams/${encodeURIComponent(examId)}/attempts`);
  },
  createAttempt(examId, payload) {
    return json('POST', `/api/exams/${encodeURIComponent(examId)}/attempts`, payload);
  },
  getAttempt(attemptId) {
    return request(`/api/attempts/${encodeURIComponent(attemptId)}`);
  },
  updateAttempt(attemptId, patch) {
    return json('PATCH', `/api/attempts/${encodeURIComponent(attemptId)}`, patch);
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

  listOrchestrationRuns(params = {}) {
    const query = new URLSearchParams();
    if (params.subject_id) query.set('subject_id', params.subject_id);
    if (params.category) query.set('category', params.category);
    const suffix = query.toString();
    return request(`/api/orchestration-runs${suffix ? `?${suffix}` : ''}`);
  },
  getOrchestrationRun(runId) {
    return request(`/api/orchestration-runs/${encodeURIComponent(runId)}`);
  },
  listEvaluationSuites() {
    return request('/api/evaluation-suites');
  },
  runEvaluationSuite(suiteId, payload) {
    return json('POST', `/api/evaluation-suites/${encodeURIComponent(suiteId)}/runs`, payload);
  },
  getEvaluationRun(runId) {
    return request(`/api/evaluation-runs/${encodeURIComponent(runId)}`);
  },

  getPet() {
    return request('/api/pet');
  },
  updatePet(patch) {
    return json('PATCH', '/api/pet', patch);
  },
  patPet() {
    return json('POST', '/api/pet/pat');
  },
};
