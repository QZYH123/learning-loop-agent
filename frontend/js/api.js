/**
 * Unified API Client for Learning Loop Agent
 * Strictly aligned with OpenAPI 3.1 main contract (docs/api/openapi.yaml & docs/api/schemas.yaml).
 * Zero fabricated fields or fake endpoints.
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
    if (payload && typeof payload === 'object' && payload.error) {
      throw new ApiError(
        payload.error.message || '请求处理失败',
        payload.error.code || 'API_ERROR',
        response.status,
        payload.error.details
      );
    }
    throw new ApiError(`HTTP 错误 [${response.status}] ${response.statusText}`, 'HTTP_ERROR', response.status, payload);
  }

  return payload;
}

export const api = {
  // Core & Workspace (Ticket 01)
  getWorkspace() {
    return apiRequest('/api/workspace');
  },

  listSubjects() {
    return apiRequest('/api/subjects');
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

  // Model Management & Discovery (Ticket 02, 16, 19)
  listModels() {
    return apiRequest('/api/models').catch(() => ({ items: [] }));
  },

  addModel({ provider, model, base_url = 'https://api.openai.com/v1', api_key = null }) {
    return apiRequest('/api/models', {
      method: 'POST',
      body: JSON.stringify({ provider, model, base_url, api_key: api_key || undefined })
    });
  },

  createModel(config) {
    return this.addModel(config);
  },

  getModel(modelId) {
    return apiRequest(`/api/models/${encodeURIComponent(modelId)}`);
  },

  updateModel(modelId, patch) {
    return apiRequest(`/api/models/${encodeURIComponent(modelId)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch)
    });
  },

  deleteModel(modelId) {
    return apiRequest(`/api/models/${encodeURIComponent(modelId)}`, {
      method: 'DELETE'
    });
  },

  getCurrentModel() {
    return apiRequest('/api/models/current');
  },

  selectCurrentModel({ model_id }) {
    return apiRequest('/api/models/current', {
      method: 'PUT',
      body: JSON.stringify({ model_id })
    });
  },

  verifyModel(modelId) {
    return apiRequest(`/api/models/${encodeURIComponent(modelId)}/verify`, {
      method: 'POST'
    });
  },

  discoverModels({ provider, base_url, api_key = null }) {
    return apiRequest('/api/models/discover', {
      method: 'POST',
      body: JSON.stringify({
        provider,
        base_url,
        api_key: api_key || undefined
      })
    });
  },

  // Multi-Sessions (Ticket 16, 17, 18)
  listSessions(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/sessions`).catch(() => ({ items: [] }));
  },

  createSession(subjectId, { title, source_version_ids = [], learning_mode = 'chat', grounding_mode = 'general-knowledge', model_id = null }) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/sessions`, {
      method: 'POST',
      body: JSON.stringify({
        title,
        source_version_ids,
        learning_mode,
        grounding_mode,
        model_id: model_id || undefined
      })
    });
  },

  getSession(sessionId) {
    return apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}`);
  },

  updateSession(sessionId, patch) {
    return apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch)
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

  createSessionMessage(sessionId, payload) {
    return apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}/messages`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  listSessionSources(sessionId) {
    return apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}/sources`).catch(() => ({ items: [] }));
  },

  addSessionSource(sessionId, { source_version_id }) {
    return apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}/sources`, {
      method: 'POST',
      body: JSON.stringify({ source_version_id })
    });
  },

  updateSessionSource(sessionId, versionId, { target_version_id }) {
    return apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}/sources/${encodeURIComponent(versionId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ target_version_id })
    });
  },

  removeSessionSource(sessionId, versionId) {
    return apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}/sources/${encodeURIComponent(versionId)}`, {
      method: 'DELETE'
    });
  },

  // Legacy Subject Chat (Ticket 02, 04, 06, 07)
  getChat(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/chat`);
  },

  updateChatConfig(subjectId, patch) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/chat`, {
      method: 'PATCH',
      body: JSON.stringify(patch)
    });
  },

  sendMessage(subjectId, payload) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/chat/messages`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  selectChatModel(subjectId, modelId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/chat/model`, {
      method: 'POST',
      body: JSON.stringify({ model_id: modelId })
    });
  },

  clearChat(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/chat`, {
      method: 'DELETE'
    });
  },

  generateCrashCourse(subjectId, { prompt, source_version_ids = [], grounding_mode = 'general-knowledge' }) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/chat/crash-course`, {
      method: 'POST',
      body: JSON.stringify({ prompt, source_version_ids, grounding_mode })
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

  // Sources & Anchors (Ticket 03, 04, 05)
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
    return apiRequest(`/api/sources/${encodeURIComponent(sourceId)}/versions`);
  },

  uploadSourceVersion(sourceId, file) {
    const formData = new FormData();
    formData.append('file', file);
    return apiRequest(`/api/sources/${encodeURIComponent(sourceId)}/versions`, {
      method: 'POST',
      body: formData
    });
  },

  getSourceVersion(versionId) {
    return apiRequest(`/api/source-versions/${encodeURIComponent(versionId)}`);
  },

  listSourceVersionAnchors(versionId) {
    return apiRequest(`/api/source-versions/${encodeURIComponent(versionId)}/anchors`).catch(() => ({ items: [] }));
  },

  getSourceAnchor(versionId, anchorId) {
    return apiRequest(`/api/source-versions/${encodeURIComponent(versionId)}/anchors/${encodeURIComponent(anchorId)}`);
  },

  getSourceAssetUrl(versionId, assetId) {
    return `/api/source-versions/${encodeURIComponent(versionId)}/assets/${encodeURIComponent(assetId)}`;
  },

  // AI-Authored Source Documents (Ticket 16, 20)
  listAiDocuments(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/documents`).catch(() => ({ items: [] }));
  },

  createAiDocument(subjectId, { title, instruction, source_version_ids = [], grounding_mode = 'general-knowledge' }) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/documents`, {
      method: 'POST',
      body: JSON.stringify({
        title,
        instruction,
        source_version_ids,
        grounding_mode
      })
    });
  },

  getAiDocument(documentId) {
    return apiRequest(`/api/documents/${encodeURIComponent(documentId)}`);
  },

  listAiDocumentVersions(documentId) {
    return apiRequest(`/api/documents/${encodeURIComponent(documentId)}/versions`).catch(() => ({ items: [] }));
  },

  restoreAiDocumentVersion(documentId, versionId) {
    return apiRequest(`/api/documents/${encodeURIComponent(documentId)}/versions/${encodeURIComponent(versionId)}/restore`, {
      method: 'POST'
    });
  },

  listAiDocumentRevisionProposals(documentId) {
    return apiRequest(`/api/documents/${encodeURIComponent(documentId)}/revision-proposals`).catch(() => ({ items: [] }));
  },

  createAiDocumentRevisionProposal(documentId, { instruction, base_version_id, scope = { kind: 'whole-document', section_ids: [] } }) {
    return apiRequest(`/api/documents/${encodeURIComponent(documentId)}/revision-proposals`, {
      method: 'POST',
      body: JSON.stringify({
        instruction,
        base_version_id,
        scope
      })
    });
  },

  getAiDocumentRevisionProposal(proposalId) {
    return apiRequest(`/api/document-revision-proposals/${encodeURIComponent(proposalId)}`);
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

  // Exam Blueprints (Ticket 08)
  listBlueprints(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/exam-blueprints`).catch(() => ({ items: [] }));
  },

  parseBlueprint(subjectId, { prompt, source_version_ids = [], grounding_mode = 'general-knowledge', total_score = 20 }) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/exam-blueprints`, {
      method: 'POST',
      body: JSON.stringify({
        prompt,
        source_version_ids,
        grounding_mode,
        total_score
      })
    });
  },

  getBlueprint(blueprintId) {
    return apiRequest(`/api/exam-blueprints/${encodeURIComponent(blueprintId)}`);
  },

  updateBlueprint(blueprintId, patch) {
    return apiRequest(`/api/exam-blueprints/${encodeURIComponent(blueprintId)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch)
    });
  },

  deleteBlueprint(blueprintId) {
    return apiRequest(`/api/exam-blueprints/${encodeURIComponent(blueprintId)}`, {
      method: 'DELETE'
    });
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

  // Exam Drafts & Incremental Generation (Ticket 09)
  listDrafts(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/exam-drafts`).catch(() => ({ items: [] }));
  },

  getDraft(draftId) {
    return apiRequest(`/api/exam-drafts/${encodeURIComponent(draftId)}`);
  },

  updateDraft(draftId, patch) {
    return apiRequest(`/api/exam-drafts/${encodeURIComponent(draftId)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch)
    });
  },

  deleteDraft(draftId) {
    return apiRequest(`/api/exam-drafts/${encodeURIComponent(draftId)}`, {
      method: 'DELETE'
    });
  },

  retryDraftQuestion(draftId, questionId) {
    return apiRequest(`/api/exam-drafts/${encodeURIComponent(draftId)}/questions/${encodeURIComponent(questionId)}/retry`, {
      method: 'POST'
    });
  },

  replaceDraftQuestion(draftId, questionId, question) {
    return apiRequest(`/api/exam-drafts/${encodeURIComponent(draftId)}/questions/${encodeURIComponent(questionId)}`, {
      method: 'PUT',
      body: JSON.stringify({ question })
    });
  },

  deleteDraftQuestion(draftId, questionId) {
    return apiRequest(`/api/exam-drafts/${encodeURIComponent(draftId)}/questions/${encodeURIComponent(questionId)}`, {
      method: 'DELETE'
    });
  },

  publishDraft(draftId, payload = {}) {
    return apiRequest(`/api/exam-drafts/${encodeURIComponent(draftId)}/publish`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  },

  // Exams, Versions, Undo/Redo & Revision Proposals (Ticket 09, 13)
  listExams(subjectId) {
    return apiRequest(`/api/subjects/${encodeURIComponent(subjectId)}/exams`).catch(() => ({ items: [] }));
  },

  getExam(examId) {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}`);
  },

  deleteExam(examId) {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}`, {
      method: 'DELETE'
    });
  },

  replaceExamDocument(examId, document) {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}`, {
      method: 'PUT',
      body: JSON.stringify({ document })
    });
  },

  listExamVersions(examId) {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}/versions`);
  },

  getExamVersion(examId, versionId) {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}/versions/${encodeURIComponent(versionId)}`);
  },

  restoreExamVersion(examId, versionId) {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}/versions/${encodeURIComponent(versionId)}/restore`, {
      method: 'POST'
    });
  },

  undoExamChange(examId) {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}/undo`, {
      method: 'POST'
    });
  },

  redoExamChange(examId) {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}/redo`, {
      method: 'POST'
    });
  },

  proposeRevision(examId, { instruction, base_version_id, scope = { kind: 'whole-exam', question_ids: [], block_ids: [] } }) {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}/revision-proposals`, {
      method: 'POST',
      body: JSON.stringify({
        instruction,
        base_version_id,
        scope
      })
    });
  },

  listRevisionProposals(examId) {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}/revision-proposals`).catch(() => ({ items: [] }));
  },

  getRevisionProposal(proposalId) {
    return apiRequest(`/api/revision-proposals/${encodeURIComponent(proposalId)}`);
  },

  applyRevisionProposal(proposalId) {
    return apiRequest(`/api/revision-proposals/${encodeURIComponent(proposalId)}/apply`, {
      method: 'POST'
    });
  },

  discardRevisionProposal(proposalId) {
    return apiRequest(`/api/revision-proposals/${encodeURIComponent(proposalId)}/discard`, {
      method: 'POST'
    });
  },

  // Exam Attempts & Grading (Ticket 10, 11, 21)
  createAttempt(examId, { mode = 'practice', show_suggested_score = false } = {}) {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}/attempts`, {
      method: 'POST',
      body: JSON.stringify({ mode, show_suggested_score })
    });
  },

  getAttempt(attemptId) {
    return apiRequest(`/api/attempts/${encodeURIComponent(attemptId)}`);
  },

  updateAttempt(attemptId, patch) {
    return apiRequest(`/api/attempts/${encodeURIComponent(attemptId)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch)
    });
  },

  saveAttemptAnswer(attemptId, questionId, answer) {
    return apiRequest(`/api/attempts/${encodeURIComponent(attemptId)}/answers/${encodeURIComponent(questionId)}`, {
      method: 'PUT',
      body: JSON.stringify({ answer })
    });
  },

  requestQuestionFeedback(attemptId, questionId, { model_id = null, show_suggested_score = false } = {}) {
    return apiRequest(`/api/attempts/${encodeURIComponent(attemptId)}/answers/${encodeURIComponent(questionId)}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ model_id: model_id || undefined, show_suggested_score })
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

  submitAttemptGrading(attemptId, { model_id = null, show_suggested_score = false } = {}) {
    return apiRequest(`/api/attempts/${encodeURIComponent(attemptId)}/grade`, {
      method: 'POST',
      body: JSON.stringify({ model_id: model_id || undefined, show_suggested_score })
    });
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
  },

  submitAttempt(attemptId) {
    return apiRequest(`/api/attempts/${encodeURIComponent(attemptId)}/submit`, {
      method: 'POST'
    });
  },

  getAttemptReview(attemptId) {
    return apiRequest(`/api/attempts/${encodeURIComponent(attemptId)}/review`);
  },

  // Citations (Ticket 04)
  getCitation(citationId) {
    return apiRequest(`/api/citations/${encodeURIComponent(citationId)}`);
  },

  // Unified Rendering & Export (Ticket 14)
  getExamRenderDocument(examId, edition = 'questions') {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}/render-document?edition=${encodeURIComponent(edition)}`);
  },

  createExamExport(examId, { format = 'pdf', edition = 'questions' } = {}) {
    return apiRequest(`/api/exams/${encodeURIComponent(examId)}/exports`, {
      method: 'POST',
      body: JSON.stringify({ format, edition })
    });
  },

  getExamExport(exportId) {
    return apiRequest(`/api/exports/${encodeURIComponent(exportId)}`);
  },

  getExportDownloadUrl(exportId) {
    return `/api/exports/${encodeURIComponent(exportId)}/file`;
  },

  // Async Operations (All Tickets)
  getOperation(operationId) {
    return apiRequest(`/api/operations/${encodeURIComponent(operationId)}`);
  },

  cancelOperation(operationId) {
    return apiRequest(`/api/operations/${encodeURIComponent(operationId)}/cancel`, {
      method: 'POST'
    });
  },

  async pollOperation(operationId, { onProgress = null, intervalMs = 600, maxAttempts = 100 } = {}) {
    let attempts = 0;
    while (attempts < maxAttempts) {
      const op = await this.getOperation(operationId);
      if (onProgress) onProgress(op);

      if (op.status === 'succeeded') {
        return op;
      }
      if (op.status === 'failed') {
        throw new ApiError(op.error?.message || '异步任务执行失败', op.error?.code || 'OPERATION_FAILED', 400, op.error?.details);
      }
      if (op.status === 'canceled') {
        throw new ApiError('异步任务已被取消', 'OPERATION_CANCELED', 400);
      }

      await new Promise((resolve) => setTimeout(resolve, intervalMs));
      attempts++;
    }
    throw new ApiError('异步任务等待超时', 'OPERATION_TIMEOUT', 408);
  },

  // Observability & Evaluation (Ticket 15)
  listOrchestrationRuns(params = {}) {
    const query = new URLSearchParams(params).toString();
    return apiRequest(`/api/orchestration-runs${query ? `?${query}` : ''}`).catch(() => ({ items: [] }));
  },

  getOrchestrationRun(runId) {
    return apiRequest(`/api/orchestration-runs/${encodeURIComponent(runId)}`);
  },

  listEvaluationSuites() {
    return apiRequest('/api/evaluation-suites').catch(() => ({ items: [] }));
  },

  runEvaluationSuite(suiteId, { model_id = null, sample_limit = null } = {}) {
    return apiRequest(`/api/evaluation-suites/${encodeURIComponent(suiteId)}/runs`, {
      method: 'POST',
      body: JSON.stringify({ model_id, sample_limit })
    });
  },

  getEvaluationRun(evaluationRunId) {
    return apiRequest(`/api/evaluation-runs/${encodeURIComponent(evaluationRunId)}`);
  }
};
