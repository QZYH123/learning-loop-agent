/**
 * Central Reactive State Store for Learning Loop Agent
 */

export class Store {
  constructor() {
    const savedTheme = typeof localStorage !== 'undefined' ? localStorage.getItem('lla_theme') : null;
    
    // Load persisted sidebar collapse states
    const getSavedCollapse = (workspace, defaultVal = false) => {
      if (typeof localStorage === 'undefined') return defaultVal;
      const v = localStorage.getItem(`lla_sidebar_${workspace}_collapsed`);
      return v !== null ? v === 'true' : defaultVal;
    };

    this.state = {
      // Workspace & Navigation
      workspace: { subjects: [], active_subject_id: null },
      activeSubjectId: null,
      models: [],
      currentModelId: null,
      discoveredModels: [],
      
      // Primary Workspaces: 'learn' | 'sources' | 'exam_studio' | 'practice_exam' | 'settings_dev'
      activeNavTab: 'learn',

      // Collapsible sidebars per workspace
      sidebarCollapsed: {
        learn: getSavedCollapse('learn', false),
        sources: getSavedCollapse('sources', false),
        exam_studio: getSavedCollapse('exam_studio', false),
        practice_exam: getSavedCollapse('practice_exam', false)
      },
      
      // Sub-views for specific workspaces
      examStudioSubTab: 'blueprint', // 'blueprint' | 'draft' | 'preview_export'
      practiceExamViewMode: 'library', // 'library' | 'attempt' | 'review'
      sourcesTab: 'user_sources', // 'user_sources' | 'ai_documents'
      settingsDevSubTab: 'models', // 'models' | 'observability' | 'benchmarks'

      // Sessions State (Ticket 16, 17, 18)
      sessions: [],
      activeSessionId: null,
      activeSession: null,
      sessionSources: [],
      sessionSearchQuery: '',

      // Active Chat / Tutor State
      chat: {
        messages: [],
        active_model_id: null,
        grounding_mode: 'general-knowledge', // 'strict' | 'general-knowledge' | 'supplemental'
        learning_mode: 'chat', // 'chat' | 'socratic' | 'crash-course'
        socratic_state: null,
        source_version_ids: []
      },
      chatAttachments: [], // Temporary attachments for current message
      onlySpecifiedSources: false,
      selectionContext: null, // Pinned context { text, anchor_id, source_version_id, question_id, asset_id }
      learningArtifacts: [],

      // User Sources State (Ticket 03, 04, 05)
      sources: [],
      activeSourceId: null,
      activeSource: null,
      activeSourceVersions: [],
      activeSourceAnchors: [],
      activeAnchor: null,

      // AI-authored Documents State (Ticket 20)
      aiDocuments: [],
      activeAiDocumentId: null,
      activeAiDocument: null,
      aiDocumentVersions: [],
      aiDocumentProposals: [],
      activeAiDocProposalId: null,
      activeAiDocProposal: null,
      
      // Exam Studio State (Ticket 08, 09, 13)
      blueprints: [],
      activeBlueprintId: null,
      activeBlueprint: null,

      drafts: [],
      activeDraftId: null,
      activeDraft: null,

      // Practice & Exam State (Ticket 10, 11, 21)
      exams: [],
      activeExamId: null,
      activeExam: null,
      examVersions: [],

      attempts: [],
      activeAttemptId: null,
      activeAttempt: null,
      activeAttemptReview: null,

      revisionProposals: [],
      activeRevisionProposalId: null,
      activeRevisionProposal: null,

      // Document Rendering & Export (Ticket 14)
      renderDocument: null,
      renderEdition: 'questions', // 'questions' | 'solutions'

      // Observability & Evaluation (Ticket 15)
      orchestrationRuns: [],
      activeRunId: null,
      activeRun: null,

      evaluationSuites: [],
      activeEvalRunId: null,
      activeEvalRun: null,

      // Global HUD & Modals
      activeOperations: new Map(),
      toasts: [],
      commandPaletteOpen: false,
      modelModalOpen: false,
      subjectModalOpen: false,
      renameSubjectModalOpen: false,
      subjectToRename: null,
      createSessionModalOpen: false,
      createAiDocModalOpen: false,
      aiDocRevisionModalOpen: false,
      blueprintModalOpen: false,
      revisionModalOpen: false,
      citationModalOpen: false,
      activeCitation: null,
      theme: savedTheme || 'paper'
    };

    this.listeners = new Set();
  }

  getState() {
    return this.state;
  }

  setState(updater) {
    const nextState = typeof updater === 'function' ? updater(this.state) : updater;
    this.state = { ...this.state, ...nextState };
    this.notify();
  }

  subscribe(listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  notify() {
    for (const listener of this.listeners) {
      try {
        listener(this.state);
      } catch (err) {
        console.error('State subscriber error:', err);
      }
    }
  }

  // Toast Helper
  addToast(message, type = 'info', duration = 3500) {
    const id = 'toast_' + Math.random().toString(36).slice(2, 9);
    const toast = { id, message, type, timestamp: Date.now() };
    this.setState((s) => ({ toasts: [...s.toasts, toast] }));
    if (duration > 0) {
      setTimeout(() => {
        this.removeToast(id);
      }, duration);
    }
    return id;
  }

  removeToast(id) {
    this.setState((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
  }

  // Operation Tracker Helper
  trackOperation(op) {
    if (!op || !op.id) return;
    this.setState((s) => {
      const nextMap = new Map(s.activeOperations);
      if (['succeeded', 'failed', 'canceled'].includes(op.status)) {
        nextMap.delete(op.id);
      } else {
        nextMap.set(op.id, op);
      }
      return { activeOperations: nextMap };
    });
  }

  // Sidebar Collapse Helper
  toggleSidebar(workspace) {
    const current = !!this.state.sidebarCollapsed[workspace];
    const next = !current;
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(`lla_sidebar_${workspace}_collapsed`, String(next));
    }
    this.setState((s) => ({
      sidebarCollapsed: {
        ...s.sidebarCollapsed,
        [workspace]: next
      }
    }));
  }

  // Theme Toggle Helper
  toggleTheme() {
    const nextTheme = this.state.theme === 'paper' ? 'chalkboard' : 'paper';
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('lla_theme', nextTheme);
    }
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', nextTheme);
    }
    this.setState({ theme: nextTheme });
  }

  // Helper selectors
  getActiveSubject() {
    const { workspace, activeSubjectId } = this.state;
    return workspace.subjects?.find((s) => s.id === activeSubjectId) || null;
  }

  getActiveModel() {
    const { models, currentModelId, chat } = this.state;
    const targetId = currentModelId || chat?.active_model_id;
    return models?.find((m) => m.id === targetId) || models?.[0] || null;
  }

  getAttemptAnswer(attempt, questionId) {
    if (!attempt || !Array.isArray(attempt.answers)) return null;
    const item = attempt.answers.find((a) => a.question_id === questionId);
    return item?.answer || null;
  }

  getAttemptFeedback(attempt, questionId) {
    if (!attempt || !Array.isArray(attempt.feedback)) return null;
    return attempt.feedback.find((f) => f.question_id === questionId) || null;
  }
}

export const store = new Store();
