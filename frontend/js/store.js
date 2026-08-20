const THEME_KEY = 'lla.theme';
const SIDEBAR_KEY = 'lla.sidebar';
const ATTEMPTS_KEY = 'lla.attempts';

function readJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* ignore quota */
  }
}

export class Store {
  constructor() {
    this.state = {
      bootstrapped: false,
      loadError: null,
      theme: localStorage.getItem(THEME_KEY) || 'paper',
      workspace: 'learn',
      subjects: [],
      activeSubjectId: null,
      models: [],
      currentModelId: null,
      sessions: [],
      activeSessionId: null,
      sessionSearch: '',
      draftStyle: 'default',
      sessionSources: [],
      sources: [],
      activeSourceId: null,
      sourceAnchors: [],
      sourceKind: 'files',
      aiDocuments: [],
      activeAiDocumentId: null,
      aiDocumentProposals: [],
      blueprints: [],
      activeBlueprintId: null,
      drafts: [],
      activeDraftId: null,
      exams: [],
      activeExamId: null,
      examProposals: [],
      draftProposals: [],
      draftQuestionEditId: null,
      draftQuestionPrompt: '',
      draftQuestionBusyId: null,
      draftProposalBusyId: null,
      retryingQuestionId: null,
      examTab: 'blueprint',
      sourceVersions: [],
      attemptsByExam: readJson(ATTEMPTS_KEY, {}),
      activeAttemptId: null,
      activeAttempt: null,
      review: null,
      composerText: '',
      composerBySubject: {},
      commandBusy: null,
      pendingPins: [],
      attachments: [],
      groundingMode: 'general-knowledge',
      selection: null,
      chatOp: null,
      operations: [],
      toasts: [],
      sidebarCollapsed: {
        learn: false,
        sources: false,
        exam: false,
        attempt: false,
        ...readJson(SIDEBAR_KEY, {}),
      },
      mobilePane: {
        learn: 'chat',
        sources: 'content',
        exam: 'content',
        attempt: 'content',
      },
      openMenu: null,
      modal: null,
      confirmTitle: '',
      confirmMessage: '',
      confirmOk: '确认',
      confirmAction: null,
      renamingSessionId: null,
      renamingBlueprintId: null,
      renamingExamId: null,
      modelForm: null,
      discoveredModels: [],
      discoverError: null,
      modelBusy: null,
      editingModelId: null,
    };
    this.listeners = new Set();
  }

  getState() {
    return this.state;
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  notify() {
    for (const listener of this.listeners) listener(this.state);
  }

  setState(patch) {
    const next = typeof patch === 'function' ? patch(this.state) : patch;
    this.state = { ...this.state, ...next };
    this.notify();
  }

  patch(partial) {
    Object.assign(this.state, partial);
  }

  activeSubject() {
    return this.state.subjects.find((item) => item.id === this.state.activeSubjectId) || null;
  }

  activeSession() {
    return this.state.sessions.find((item) => item.id === this.state.activeSessionId) || null;
  }

  activeModel() {
    return this.state.models.find((item) => item.id === this.state.currentModelId) || this.state.models[0] || null;
  }

  activeSource() {
    return this.state.sources.find((item) => item.id === this.state.activeSourceId) || null;
  }

  activeAiDocument() {
    return this.state.aiDocuments.find((item) => item.id === this.state.activeAiDocumentId) || null;
  }

  activeBlueprint() {
    return this.state.blueprints.find((item) => item.id === this.state.activeBlueprintId) || null;
  }

  activeDraft() {
    return this.state.drafts.find((item) => item.id === this.state.activeDraftId) || null;
  }

  activeExam() {
    return this.state.exams.find((item) => item.id === this.state.activeExamId) || null;
  }

  addToast(message, type = 'info') {
    const toast = { id: `toast-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`, message, type };
    this.setState({ toasts: [...this.state.toasts, toast] });
    window.setTimeout(() => this.removeToast(toast.id), type === 'error' ? 6000 : 3200);
  }

  removeToast(id) {
    this.setState({ toasts: this.state.toasts.filter((item) => item.id !== id) });
  }

  setTheme(theme) {
    localStorage.setItem(THEME_KEY, theme);
    document.documentElement.setAttribute('data-theme', theme);
    this.setState({ theme });
  }

  setSidebarCollapsed(workspace, collapsed) {
    const next = { ...this.state.sidebarCollapsed, [workspace]: !!collapsed };
    writeJson(SIDEBAR_KEY, next);
    this.setState({ sidebarCollapsed: next });
  }

  toggleSidebar(workspace) {
    this.setSidebarCollapsed(workspace, !this.state.sidebarCollapsed[workspace]);
  }

  rememberAttempt(examId, attemptId) {
    const current = this.state.attemptsByExam[examId] || [];
    const next = { ...this.state.attemptsByExam, [examId]: [attemptId, ...current.filter((id) => id !== attemptId)] };
    writeJson(ATTEMPTS_KEY, next);
    this.setState({ attemptsByExam: next, activeAttemptId: attemptId });
  }

  trackOperation(op) {
    if (!op?.id) return;
    const existing = this.state.operations.find((item) => item.id === op.id);
    const terminal = ['succeeded', 'failed', 'canceled'].includes(op.status);
    if (terminal) {
      if (!existing) return;
      this.setState({ operations: this.state.operations.filter((item) => item.id !== op.id) });
      return;
    }
    if (existing && existing.status === op.status) return;
    const rest = this.state.operations.filter((item) => item.id !== op.id);
    this.setState({ operations: [...rest, op] });
  }
}

export const store = new Store();
