/**
 * Central Reactive State Store for Learning Loop Agent
 * Strictly aligned with Issue 16, 17, 18, 19, 20, 21, 22
 */

export class Store {
  constructor() {
    const savedTheme = typeof localStorage !== 'undefined' ? localStorage.getItem('lla_theme') : null;
    const savedLeftCollapse = typeof localStorage !== 'undefined' ? localStorage.getItem('lla_sidebar_left_collapsed') === 'true' : false;
    const savedRightCollapse = typeof localStorage !== 'undefined' ? localStorage.getItem('lla_sidebar_right_collapsed') === 'true' : false;

    this.state = {
      // Workspace & Subject Navigation
      workspace: { subjects: [], active_subject_id: null },
      activeSubjectId: null,
      models: [],
      currentModelId: null,
      discoveredModels: [],

      // 4 Primary Workspaces: 'learn' | 'sources' | 'quiz_gen' | 'attempts'
      activeNavTab: 'learn',

      // Collapsible sidebar states (Left chat, Right content)
      sidebarCollapsed: {
        left: savedLeftCollapse,
        right: savedRightCollapse
      },

      // Sub-tabs for specific workspaces
      sourcesTab: 'user_sources', // 'user_sources' | 'ai_documents'
      examStudioSubTab: 'blueprint', // 'blueprint' | 'draft' | 'exams'

      // Sessions State (Ticket 16, 17, 18)
      sessions: [],
      activeSessionId: null,
      activeSession: null,

      // Active Chat / Tutor State
      chat: {
        messages: [],
        active_model_id: null,
        chat_style: 'default', // 'default' | 'socratic' | 'crash-course'
        grounding_mode: 'general-knowledge',
        source_version_ids: []
      },
      chatAttachments: [], // Temporary attachments for current message
      selectionContext: null, // Pinned context { text, anchor_id, source_version_id, question_id }

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

      // Global Operations, Modals & Theme
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

  // Toast Notification Helper
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
  toggleSidebar(side = 'left') {
    const current = !!this.state.sidebarCollapsed[side];
    const next = !current;
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(`lla_sidebar_${side}_collapsed`, String(next));
    }
    this.setState((s) => ({
      sidebarCollapsed: {
        ...s.sidebarCollapsed,
        [side]: next
      }
    }));
  }

  // Theme Toggle Helper
  toggleTheme() {
    const nextTheme = this.state.theme === 'paper' ? 'dark' : 'paper';
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem('lla_theme', nextTheme);
    }
    if (typeof document !== 'undefined') {
      document.documentElement.setAttribute('data-theme', nextTheme);
    }
    this.setState({ theme: nextTheme });
  }
}

export const store = new Store();
