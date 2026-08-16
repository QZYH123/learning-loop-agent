/**
 * Unified API Client for Learning Loop Agent
 * Strictly adhering to OpenAPI 3.1 schema and backend endpoints.
 */

const BASE_URL = '';

class ApiClient {
  async request(path, options = {}) {
    const url = `${BASE_URL}${path}`;
    const headers = {
      ...options.headers
    };

    if (!(options.body instanceof FormData)) {
      headers['Content-Type'] = 'application/json';
    }

    const config = {
      ...options,
      headers
    };

    const res = await fetch(url, config);

    if (res.status === 204) {
      return null;
    }

    const data = await res.json().catch(() => null);

    if (!res.ok) {
      const errorMsg = data?.detail || data?.message || `HTTP error ${res.status}`;
      throw new Error(errorMsg);
    }

    return data;
  }

  // --- Workspace & Subjects ---
  async getWorkspace() {
    return this.request('/api/workspace');
  }

  async createSubject(name) {
    return this.request('/api/workspace/subjects', {
      method: 'POST',
      body: JSON.stringify({ name })
    });
  }

  async deleteSubject(subjectId) {
    return this.request(`/api/workspace/subjects/${encodeURIComponent(subjectId)}`, {
      method: 'DELETE'
    });
  }

  async renameSubject(subjectId, newName) {
    return this.request(`/api/workspace/subjects/${encodeURIComponent(subjectId)}/rename`, {
      method: 'POST',
      body: JSON.stringify({ name: newName })
    });
  }

  async activateSubject(subjectId) {
    return this.request('/api/workspace/active-subject', {
      method: 'POST',
      body: JSON.stringify({ subject_id: subjectId })
    });
  }

  // --- Models (Issue 19 & ADR 0005) ---
  async listModels() {
    return this.request('/api/models');
  }

  async createModel(payload) {
    return this.request('/api/models', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async getCurrentModel() {
    return this.request('/api/models/current');
  }

  async selectCurrentModel(modelId) {
    return this.request('/api/models/current', {
      method: 'POST',
      body: JSON.stringify({ model_id: modelId })
    });
  }

  async deleteModel(modelId) {
    return this.request(`/api/models/${encodeURIComponent(modelId)}`, {
      method: 'DELETE'
    });
  }

  async discoverModels(payload) {
    return this.request('/api/models/discover', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  // --- Operations (Async Task Polling) ---
  async getOperation(operationId) {
    return this.request(`/api/operations/${encodeURIComponent(operationId)}`);
  }

  async cancelOperation(operationId) {
    return this.request(`/api/operations/${encodeURIComponent(operationId)}/cancel`, {
      method: 'POST'
    });
  }

  async pollOperation(operationId, { intervalMs = 300, maxAttempts = 120, onProgress = null } = {}) {
    let attempts = 0;
    while (attempts < maxAttempts) {
      const op = await this.getOperation(operationId);
      if (onProgress) onProgress(op);

      if (op.status === 'succeeded') {
        return op;
      }
      if (op.status === 'failed' || op.status === 'canceled') {
        throw new Error(op.error?.message || `Operation ${op.status}`);
      }

      await new Promise((resolve) => setTimeout(resolve, intervalMs));
      attempts++;
    }
    throw new Error('Operation timed out');
  }

  // --- Sessions (Ticket 16, 17, 18) ---
  async listSessions(subjectId) {
    return this.request(`/api/subjects/${encodeURIComponent(subjectId)}/sessions`);
  }

  async createSession(subjectId, { title, source_version_ids = [] }) {
    return this.request(`/api/subjects/${encodeURIComponent(subjectId)}/sessions`, {
      method: 'POST',
      body: JSON.stringify({ title, source_version_ids })
    });
  }

  async getSession(sessionId) {
    return this.request(`/api/sessions/${encodeURIComponent(sessionId)}`);
  }

  async deleteSession(sessionId) {
    return this.request(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'DELETE'
    });
  }

  async createSessionMessage(sessionId, payload) {
    return this.request(`/api/sessions/${encodeURIComponent(sessionId)}/messages`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  // --- General Subject Chat & Attachments ---
  async getChat(subjectId) {
    return this.request(`/api/subjects/${encodeURIComponent(subjectId)}/chat`);
  }

  async sendMessage(subjectId, payload) {
    return this.request(`/api/subjects/${encodeURIComponent(subjectId)}/chat/messages`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async stopChat(subjectId) {
    return this.request(`/api/subjects/${encodeURIComponent(subjectId)}/chat/stop`, {
      method: 'POST'
    });
  }

  async clearChat(subjectId) {
    return this.request(`/api/subjects/${encodeURIComponent(subjectId)}/chat/clear`, {
      method: 'POST'
    });
  }

  async uploadChatAttachment(subjectId, file) {
    const formData = new FormData();
    formData.append('file', file);
    return this.request(`/api/subjects/${encodeURIComponent(subjectId)}/chat/attachments`, {
      method: 'POST',
      body: formData
    });
  }

  // --- User Sources ---
  async listSources(subjectId) {
    return this.request(`/api/subjects/${encodeURIComponent(subjectId)}/sources`);
  }

  async uploadSource(subjectId, file) {
    const formData = new FormData();
    formData.append('file', file);
    return this.request(`/api/subjects/${encodeURIComponent(subjectId)}/sources/upload`, {
      method: 'POST',
      body: formData
    });
  }

  async getSource(sourceId) {
    return this.request(`/api/sources/${encodeURIComponent(sourceId)}`);
  }

  async deleteSource(sourceId) {
    return this.request(`/api/sources/${encodeURIComponent(sourceId)}`, {
      method: 'DELETE'
    });
  }

  async listSourceVersions(sourceId) {
    return this.request(`/api/sources/${encodeURIComponent(sourceId)}/versions`);
  }

  async listSourceVersionAnchors(versionId) {
    return this.request(`/api/source-versions/${encodeURIComponent(versionId)}/anchors`);
  }

  // --- AI-Authored Documents (Ticket 20) ---
  async listAiDocuments(subjectId) {
    return this.request(`/api/subjects/${encodeURIComponent(subjectId)}/ai-documents`);
  }

  async createAiDocument(subjectId, payload) {
    return this.request(`/api/subjects/${encodeURIComponent(subjectId)}/ai-documents`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async getAiDocument(documentId) {
    return this.request(`/api/ai-documents/${encodeURIComponent(documentId)}`);
  }

  async listAiDocumentVersions(documentId) {
    return this.request(`/api/ai-documents/${encodeURIComponent(documentId)}/versions`);
  }

  async listAiDocumentRevisionProposals(documentId) {
    return this.request(`/api/ai-documents/${encodeURIComponent(documentId)}/revision-proposals`);
  }

  async createAiDocumentRevisionProposal(documentId, payload) {
    return this.request(`/api/ai-documents/${encodeURIComponent(documentId)}/revision-proposals`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async applyAiDocumentRevisionProposal(proposalId) {
    return this.request(`/api/ai-document-proposals/${encodeURIComponent(proposalId)}/apply`, {
      method: 'POST'
    });
  }

  async discardAiDocumentRevisionProposal(proposalId) {
    return this.request(`/api/ai-document-proposals/${encodeURIComponent(proposalId)}/discard`, {
      method: 'POST'
    });
  }

  async restoreAiDocumentVersion(documentId, versionId) {
    return this.request(`/api/ai-documents/${encodeURIComponent(documentId)}/versions/${encodeURIComponent(versionId)}/restore`, {
      method: 'POST'
    });
  }

  // --- Exam Studio: Blueprints, Drafts, Exams (Ticket 08, 09, 13) ---
  async listBlueprints(subjectId) {
    return this.request(`/api/subjects/${encodeURIComponent(subjectId)}/exam-blueprints`);
  }

  async parseBlueprint(subjectId, prompt) {
    return this.request(`/api/subjects/${encodeURIComponent(subjectId)}/exam-blueprints/parse`, {
      method: 'POST',
      body: JSON.stringify({ prompt })
    });
  }

  async getBlueprint(blueprintId) {
    return this.request(`/api/exam-blueprints/${encodeURIComponent(blueprintId)}`);
  }

  async confirmBlueprint(blueprintId) {
    return this.request(`/api/exam-blueprints/${encodeURIComponent(blueprintId)}/confirm`, {
      method: 'POST'
    });
  }

  async generateDraftFromBlueprint(blueprintId) {
    return this.request(`/api/exam-blueprints/${encodeURIComponent(blueprintId)}/generate-draft`, {
      method: 'POST'
    });
  }

  async listDrafts(subjectId) {
    return this.request(`/api/subjects/${encodeURIComponent(subjectId)}/exam-drafts`);
  }

  async getDraft(draftId) {
    return this.request(`/api/exam-drafts/${encodeURIComponent(draftId)}`);
  }

  async retryDraftQuestion(draftId, questionId) {
    return this.request(`/api/exam-drafts/${encodeURIComponent(draftId)}/questions/${encodeURIComponent(questionId)}/retry`, {
      method: 'POST'
    });
  }

  async publishDraft(draftId) {
    return this.request(`/api/exam-drafts/${encodeURIComponent(draftId)}/publish`, {
      method: 'POST'
    });
  }

  async listExams(subjectId) {
    return this.request(`/api/subjects/${encodeURIComponent(subjectId)}/exams`);
  }

  async getExam(examId) {
    return this.request(`/api/exams/${encodeURIComponent(examId)}`);
  }

  async listExamVersions(examId) {
    return this.request(`/api/exams/${encodeURIComponent(examId)}/versions`);
  }

  async createExamExport(examId, { format = 'pdf', edition = 'questions' }) {
    return this.request(`/api/exams/${encodeURIComponent(examId)}/exports`, {
      method: 'POST',
      body: JSON.stringify({ format, edition })
    });
  }

  async getExamExport(exportId) {
    return this.request(`/api/exam-exports/${encodeURIComponent(exportId)}`);
  }

  // --- Attempts, Practice & Grading (Ticket 10, 11, 21) ---
  async createAttempt(examId, payload = {}) {
    return this.request(`/api/exams/${encodeURIComponent(examId)}/attempts`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async getAttempt(attemptId) {
    return this.request(`/api/attempts/${encodeURIComponent(attemptId)}`);
  }

  async saveAttemptAnswer(attemptId, questionId, answer) {
    return this.request(`/api/attempts/${encodeURIComponent(attemptId)}/answers`, {
      method: 'PUT',
      body: JSON.stringify({ question_id: questionId, answer })
    });
  }

  async requestQuestionFeedback(attemptId, questionId, payload = {}) {
    return this.request(`/api/attempts/${encodeURIComponent(attemptId)}/questions/${encodeURIComponent(questionId)}/feedback`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async completeAttempt(attemptId) {
    return this.request(`/api/attempts/${encodeURIComponent(attemptId)}/complete`, {
      method: 'POST'
    });
  }

  async continueAttempt(attemptId) {
    return this.request(`/api/attempts/${encodeURIComponent(attemptId)}/continue`, {
      method: 'POST'
    });
  }

  async submitAttemptGrading(attemptId, payload = {}) {
    return this.request(`/api/attempts/${encodeURIComponent(attemptId)}/grade`, {
      method: 'POST',
      body: JSON.stringify(payload)
    });
  }

  async getAttemptReview(attemptId) {
    return this.request(`/api/attempts/${encodeURIComponent(attemptId)}/review`);
  }
}

export const api = new ApiClient();
