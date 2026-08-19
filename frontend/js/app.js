import { api } from './api.js';
import { store } from './store.js';
import { navbarHtml, renderNavbar } from './components/navbar.js';
import {
  bindLearnLeft,
  bindLearnRight,
  learnLeftHtml,
  learnRightHtml,
  learnShellHtml,
} from './components/learn.js';
import {
  bindSourcesLeft,
  bindSourcesRight,
  sourcesLeftHtml,
  sourcesRightHtml,
  sourcesShellHtml,
} from './components/sources.js';
import {
  bindExamLeft,
  examLeftHtml,
  examRightHtml,
  examShellHtml,
} from './components/exam.js';
import {
  attemptLeftHtml,
  attemptRightHtml,
  attemptShellHtml,
  bindAttemptLeft,
  bindAttemptRight,
} from './components/attempt.js';
import { renderToasts } from './components/toast.js';
import { renderModals } from './components/modal.js';
import { defaultForm, formFromModel, renderModels } from './components/models.js';
import { matchCommand } from './commands.js';
import {
  blocksToText,
  currentAiVersion,
  officialSelection,
  readySourceVersionIds,
  sessionVisible,
  titleFromMessage,
  draftPublishState,
  sanitizeErrorMessage,
} from './util.js';

class App {
  constructor() {
    this.root = document.getElementById('app');
    this.ui = { composerFocus: false, range: [0, 0], chatScroll: 0, chatStick: true, contentScroll: 0, searchFocus: false, searchRange: [0, 0] };
    this.selectionPop = null;
    this.draftPoll = null;
    this.sourcePoll = null;
    this.generatingPoll = null;
    this.generatingWatchSessionId = null;
    this.sending = false;
    this.regions = { workspace: null, shell: '', left: '', right: '', nav: '' };
  }

  async init() {
    document.documentElement.setAttribute('data-theme', store.state.theme);
    this.root.innerHTML = `
      <div class="app" data-testid="app-shell">
        <div id="navbar-root"></div>
        <main class="main" id="workspace-root"></main>
        <div id="modal-root"></div>
        <div id="models-root"></div>
        <div id="toast-root"></div>
        <button type="button" class="btn btn-primary btn-sm ask-pop" id="ask-ai-pop">问 AI</button>
      </div>
    `;
    this.selectionPop = this.root.querySelector('#ask-ai-pop');
    store.subscribe(() => this.render());
    this.bindGlobals();
    await this.bootstrap();
    this.render();
  }

  bindGlobals() {
    document.addEventListener('click', (event) => this.onClick(event));
    document.addEventListener('change', (event) => this.onFieldChange(event));
    document.addEventListener('mouseup', (event) => this.onMouseUp(event));
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') store.setState({ openMenu: null, modal: null });
    });
    window.addEventListener('resize', () => {
      if (store.state.openMenu) store.setState({ openMenu: null });
    });
  }

  captureUi() {
    const composer = document.getElementById('composer-input');
    this.ui.composerFocus = composer && document.activeElement === composer;
    if (composer) this.ui.range = [composer.selectionStart, composer.selectionEnd];
    const search = document.getElementById('session-search');
    this.ui.searchFocus = search && document.activeElement === search;
    if (search) this.ui.searchRange = [search.selectionStart, search.selectionEnd];
    const chat = document.getElementById('chat-stream');
    if (chat) {
      this.ui.chatScroll = chat.scrollTop;
      this.ui.chatStick = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 48;
    }
    const content = document.getElementById('task-scroll');
    if (content) this.ui.contentScroll = content.scrollTop;
  }

  restoreUi() {
    const composer = document.getElementById('composer-input');
    if (composer) {
      composer.value = store.state.composerText;
      if (this.ui.composerFocus) {
        composer.focus();
        composer.setSelectionRange(this.ui.range[0], this.ui.range[1]);
      }
    }
    const search = document.getElementById('session-search');
    if (search && this.ui.searchFocus) {
      search.focus();
      search.setSelectionRange(this.ui.searchRange[0], this.ui.searchRange[1]);
    }
    const chat = document.getElementById('chat-stream');
    const content = document.getElementById('task-scroll');
    if (chat) chat.scrollTop = this.ui.chatStick ? chat.scrollHeight : this.ui.chatScroll;
    if (content) content.scrollTop = this.ui.contentScroll;
  }

  handlers() {
    return {
      onSelectWorkspace: (id) => store.setState({ workspace: id, openMenu: null }),
      onToggleMenu: (name) => store.setState({ openMenu: store.state.openMenu === name ? null : name }),
      onToggleTheme: () => store.setTheme(store.state.theme === 'paper' ? 'chalkboard' : 'paper'),
      onOpenModal: (modal) => store.setState({
        modal,
        openMenu: null,
        modelForm: store.state.modelForm || defaultForm(),
        discoveredModels: store.state.discoveredModels || [],
        discoverError: null,
        modelBusy: null,
        editingModelId: null,
      }),
      onEditModel: (id) => this.editModel(id),
      onPickDiscovered: (name) => {
        const form = { ...(store.state.modelForm || defaultForm()), model: name };
        store.setState({ modelForm: form });
      },
      onCloseModal: () => store.setState({ modal: null }),
      onCreateSubject: (name) => this.createSubject(name),
      onRenameSubject: (name) => this.renameSubject(name),
      onSwitchSubject: (id) => this.switchSubject(id),
      onDeleteSubject: () => this.deleteSubject(),
      onComposerInput: (value) => store.patch({ composerText: value }),
      onGetMentionSources: () => readyMentionSources(store.state.sources),
      onMentionSource: (source) => this.mentionSource(source),
      onSearchSessions: (value) => store.setState({ sessionSearch: value }),
      onSend: () => this.submitComposer(),
      onStopChat: () => this.stopChat(),
      onAddAttachments: (files) => store.setState({ attachments: [...store.state.attachments, ...files.map((file) => ({ file, name: file.name }))] }),
      onClearSelection: () => store.setState({ selection: null }),
      onUploadSources: (files) => this.onUploadSources(files),
      onDismissToast: (id) => store.removeToast(id),
      onModelFormChange: (form) => {
        store.patch({ modelForm: form });
      },
      onSaveModel: (form) => this.saveModel(form),
      onDiscoverModels: (form) => this.discoverModels(form),
      onSelectModel: (id) => this.selectModel(id),
      onVerifyModel: (id) => this.verifyModel(id),
      onDeleteModel: (id) => this.deleteModel(id),
      onSaveAnswer: (attemptId, questionId, answer) => this.saveAnswer(attemptId, questionId, answer),
      onCommandNeeds: () => ({
        exam: !!store.activeExam(),
        draft: !!store.activeDraft(),
        aiDocument: !!store.activeAiDocument(),
      }),
      onConfirmModal: () => this.confirmModal(),
    };
  }

  resetWorkspaceRegions() {
    this.regions.workspace = null;
    this.regions.shell = '';
    this.regions.left = '';
    this.regions.right = '';
  }

  workspaceView(workspace) {
    if (workspace === 'learn') {
      return {
        shellHtml: learnShellHtml,
        leftHtml: learnLeftHtml,
        rightHtml: learnRightHtml,
        bindLeft: bindLearnLeft,
        bindRight: bindLearnRight,
        leftSel: '.pane-sessions',
        rightSel: '.pane-chat',
      };
    }
    if (workspace === 'sources') {
      return {
        shellHtml: sourcesShellHtml,
        leftHtml: sourcesLeftHtml,
        rightHtml: sourcesRightHtml,
        bindLeft: bindSourcesLeft,
        bindRight: bindSourcesRight,
        leftSel: '.pane-ai',
        rightSel: '.pane-content',
      };
    }
    if (workspace === 'exam') {
      return {
        shellHtml: examShellHtml,
        leftHtml: examLeftHtml,
        rightHtml: examRightHtml,
        bindLeft: bindExamLeft,
        bindRight: null,
        leftSel: '.pane-ai',
        rightSel: '.pane-content',
      };
    }
    return {
      shellHtml: attemptShellHtml,
      leftHtml: attemptLeftHtml,
      rightHtml: attemptRightHtml,
      bindLeft: bindAttemptLeft,
      bindRight: (root, handlers, state) => bindAttemptRight(root, handlers, state.activeAttempt),
      leftSel: '.pane-ai',
      rightSel: '.pane-content',
    };
  }

  applyWorkspaceShell(ws, state) {
    if (!ws) return;
    const collapsed = !!state.sidebarCollapsed[state.workspace];
    const mobile = state.mobilePane[state.workspace];
    ws.classList.toggle('is-collapsed', collapsed);
    ws.setAttribute('data-mobile', mobile);
    ws.querySelectorAll('.mobile-switch [data-action="mobile-pane"]').forEach((btn) => {
      btn.classList.toggle('is-active', btn.dataset.pane === mobile);
    });
  }

  renderWorkspace(state, workspaceRoot, handlers) {
    const view = this.workspaceView(state.workspace);
    const collapsed = !!state.sidebarCollapsed[state.workspace];
    const mobile = state.mobilePane[state.workspace];
    const shellKey = `${collapsed ? '1' : '0'}|${mobile}`;
    const leftHtml = view.leftHtml(state, handlers);
    const rightHtml = view.rightHtml(state, handlers);
    const switched = this.regions.workspace !== state.workspace;

    if (switched) {
      this.regions.workspace = state.workspace;
      this.regions.shell = '';
      this.regions.left = '';
      this.regions.right = '';
      workspaceRoot.innerHTML = view.shellHtml(state);
    }

    const ws = workspaceRoot.querySelector('.ws');
    if (this.regions.shell !== shellKey) {
      if (!switched) this.applyWorkspaceShell(ws, state);
      this.regions.shell = shellKey;
    }

    const leftEl = workspaceRoot.querySelector(view.leftSel);
    const rightEl = workspaceRoot.querySelector(view.rightSel);
    if (leftEl && this.regions.left !== leftHtml) {
      leftEl.innerHTML = leftHtml;
      this.regions.left = leftHtml;
      view.bindLeft?.(leftEl, handlers, state);
    }
    if (rightEl && this.regions.right !== rightHtml) {
      rightEl.innerHTML = rightHtml;
      this.regions.right = rightHtml;
      view.bindRight?.(rightEl, handlers, state);
    }
  }

  render() {
    this.captureUi();
    const state = store.getState();
    const handlers = this.handlers();
    const navRoot = document.getElementById('navbar-root');
    const navHtml = navbarHtml(state);
    if (this.regions.nav !== navHtml) {
      renderNavbar(state, navRoot, handlers);
      this.regions.nav = navHtml;
    }
    const workspaceRoot = document.getElementById('workspace-root');
    if (!state.bootstrapped) {
      this.resetWorkspaceRegions();
      workspaceRoot.innerHTML = `<div class="boot">${spin()}<h3>加载中</h3></div>`;
    } else if (state.loadError) {
      this.resetWorkspaceRegions();
      workspaceRoot.innerHTML = `<div class="fail"><h3>加载失败</h3><p>${state.loadError}</p><button type="button" class="btn btn-primary" id="retry-boot">重试</button></div>`;
      workspaceRoot.querySelector('#retry-boot').onclick = () => this.bootstrap();
    } else if (!state.activeSubjectId) {
      this.resetWorkspaceRegions();
      workspaceRoot.innerHTML = `<div class="empty"><h3>开始新对话</h3><button type="button" class="btn btn-primary" data-action="open-subject">新建科目</button></div>`;
    } else {
      this.renderWorkspace(state, workspaceRoot, handlers);
    }
    renderModals(state, document.getElementById('modal-root'), handlers);
    renderModels(state, document.getElementById('models-root'), handlers);
    renderToasts(state, document.getElementById('toast-root'), handlers);
    this.restoreUi();
    this.bindRename();
    this.watchGeneratingMessages();
  }

  bindRename() {
    const input = document.querySelector('[data-rename-session]');
    if (!input) return;
    input.focus();
    input.onkeydown = async (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        await this.renameSession(store.state.renamingSessionId, input.value.trim());
      }
      if (event.key === 'Escape') store.setState({ renamingSessionId: null });
    };
    input.onblur = async () => {
      if (store.state.renamingSessionId) await this.renameSession(store.state.renamingSessionId, input.value.trim());
    };
  }

  async onClick(event) {
    const target = event.target.closest('[data-action]');
    if (!target) {
      if (!event.target.closest('.menu, .dropdown, [data-action="toggle-menu"]') && store.state.openMenu) {
        store.setState({ openMenu: null });
      }
      return;
    }
    const { action } = target.dataset;
    const id = target.dataset.id;
    try {
      if (action === 'select-workspace') store.setState({ workspace: target.dataset.workspace, openMenu: null });
      else if (action === 'toggle-menu') store.setState({ openMenu: store.state.openMenu === target.dataset.menu ? null : target.dataset.menu });
      else if (action === 'mobile-pane') this.setMobilePane(target.dataset.pane);
      else if (action === 'collapse-left') store.toggleSidebar(store.state.workspace);
      else if (action === 'create-session') await this.createSession();
      else if (action === 'select-session') await this.selectSession(id);
      else if (action === 'rename-session') {
        event.stopPropagation();
        store.setState({ renamingSessionId: id, openMenu: null });
      } else if (action === 'delete-session') {
        event.stopPropagation();
        await this.deleteSession(id);
      } else if (action === 'set-style') await this.setStyle(id);
      else if (action === 'set-grounding') store.setState({ groundingMode: id, openMenu: null });
      else if (action === 'select-model') await this.selectModel(id);
      else if (action === 'open-models') store.setState({ modal: 'models', openMenu: null, modelForm: store.state.modelForm || defaultForm() });
      else if (action === 'open-subject') store.setState({ modal: 'subject' });
      else if (action === 'pin-source') await this.pinSource(id);
      else if (action === 'unpin-source') await this.unpinSource(id);
      else if (action === 'send') await this.submitComposer();
      else if (action === 'stop-chat') await this.stopChat();
      else if (action === 'retry-message') await this.retryMessage(id);
      else if (action === 'clear-selection') store.setState({ selection: null });
      else if (action === 'remove-att') {
        const next = store.state.attachments.filter((_, index) => index !== Number(target.dataset.index));
        store.setState({ attachments: next });
      } else if (action === 'pick-attach') document.getElementById('chat-attach-input')?.click();
      else if (action === 'source-kind') store.setState({ sourceKind: target.dataset.kind });
      else if (action === 'upload-source') document.getElementById('source-file-input')?.click();
      else if (action === 'select-source') await this.selectSource(id);
      else if (action === 'delete-source') await this.deleteSource(id);
      else if (action === 'select-ai-doc') await this.selectAiDoc(id);
      else if (action === 'create-ai-doc') await this.createAiDocumentFromPrompt();
      else if (action === 'apply-doc-proposal') await this.applyDocProposal(id);
      else if (action === 'discard-doc-proposal') await this.discardDocProposal(id);
      else if (action === 'exam-tab') store.setState({ examTab: target.dataset.tab });
      else if (action === 'select-blueprint') await this.selectBlueprint(id);
      else if (action === 'remove-blueprint-point') await this.removeBlueprintPoint(id, target.dataset.index);
      else if (action === 'confirm-blueprint') await this.confirmBlueprint(id);
      else if (action === 'generate-draft') await this.generateDraft(id);
      else if (action === 'select-draft') await this.selectDraft(id);
      else if (action === 'retry-question') await this.retryQuestion(target.dataset.draftId, id);
      else if (action === 'publish-draft') await this.publishDraft(id);
      else if (action === 'apply-draft-proposal') await this.applyDraftProposal(id);
      else if (action === 'discard-draft-proposal') await this.discardDraftProposal(id);
      else if (action === 'select-exam') await this.selectExam(id);
      else if (action === 'apply-exam-proposal') await this.applyExamProposal(id);
      else if (action === 'discard-exam-proposal') await this.discardExamProposal(id);
      else if (action === 'undo-exam') await this.undoExam(id);
      else if (action === 'redo-exam') await this.redoExam(id);
      else if (action === 'go-attempt') store.setState({ workspace: 'attempt', activeExamId: id || store.state.activeExamId, mobilePane: { ...store.state.mobilePane, attempt: 'content' } });
      else if (action === 'go-exam') store.setState({ workspace: 'exam', examTab: 'blueprint', mobilePane: { ...store.state.mobilePane, exam: 'ai' } });
      else if (action === 'focus-composer') this.focusComposer();
      else if (action === 'start-attempt') await this.startAttempt(id, target.dataset.mode);
      else if (action === 'complete-attempt') await this.completeAttempt(id);
      else if (action === 'continue-attempt') await this.continueAttempt(id);
      else if (action === 'grade-attempt') await this.gradeAttempt(id);
      else if (action === 'pause-attempt') await this.run('暂停失败', () => api.pauseAttempt(id), () => this.refreshAttempt(id));
      else if (action === 'resume-attempt') await this.run('恢复失败', () => api.resumeAttempt(id), () => this.refreshAttempt(id));
      else if (action === 'ask-feedback') await this.askFeedback(target.dataset.attemptId, id);
    } catch (err) {
      store.addToast(sanitizeErrorMessage(err.message), 'error');
    }
  }

  async onFieldChange(event) {
    const target = event.target.closest('[data-action]');
    if (!target) return;
    const action = target.dataset.action;
    const id = target.dataset.id;
    const index = Number(target.dataset.index);
    try {
      if (action === 'plan-count' || action === 'plan-score') {
        await this.updateBlueprintPlan(id, index, action === 'plan-count' ? 'count' : 'score_each', target.value);
      }
    } catch (err) {
      store.addToast(sanitizeErrorMessage(err.message), 'error');
    }
  }

  askConfirm({ title, message, ok = '确认', action }) {
    store.setState({
      modal: 'confirm',
      confirmTitle: title,
      confirmMessage: message,
      confirmOk: ok,
      confirmAction: action,
      openMenu: null,
    });
  }

  async confirmModal() {
    const action = store.state.confirmAction;
    store.setState({ modal: null, confirmAction: null });
    if (action === 'delete-subject') await this.deleteSubjectConfirmed();
    else if (action === 'delete-session') await this.deleteSessionConfirmed(store.state.confirmSessionId);
    else if (action === 'delete-source') await this.deleteSourceConfirmed(store.state.confirmSourceId);
    else if (action === 'publish-draft') await this.publishDraftConfirmed(store.state.confirmDraftId, true);
  }

  setMobilePane(pane) {
    const key = store.state.workspace;
    store.setState({ mobilePane: { ...store.state.mobilePane, [key]: pane } });
  }

  focusComposer() {
    const key = store.state.workspace;
    store.setSidebarCollapsed(key, false);
    store.setState({
      mobilePane: { ...store.state.mobilePane, [key]: key === 'learn' ? 'chat' : 'ai' },
      openMenu: null,
    });
    queueMicrotask(() => document.getElementById('composer-input')?.focus());
  }

  onMouseUp(event) {
    const root = event.target.closest('[data-select-root]');
    const pop = this.selectionPop;
    if (!pop) return;
    if (event.target.closest('#ask-ai-pop')) return;
    const selection = window.getSelection();
    const text = selection?.toString().trim();
    if (!root || !text || text.length < 2) {
      pop.classList.remove('is-on');
      return;
    }
    const range = selection.getRangeAt(0).getBoundingClientRect();
    pop.style.left = `${Math.min(window.innerWidth - 80, range.left)}px`;
    pop.style.top = `${Math.max(56, range.top - 36)}px`;
    pop.classList.add('is-on');
    pop.onclick = () => {
      const question = event.target.closest('[data-question-id]');
      store.setState({
        selection: this.buildSelection(root.dataset.selectRoot, text, question?.dataset.questionId || null),
        mobilePane: { ...store.state.mobilePane, [store.state.workspace]: store.state.workspace === 'learn' ? 'chat' : 'ai' },
      });
      pop.classList.remove('is-on');
      selection.removeAllRanges();
      queueMicrotask(() => document.getElementById('composer-input')?.focus());
    };
  }

  buildSelection(rootKind, text, questionId) {
    if (rootKind === 'attempt' && store.activeAttempt()) {
      const attempt = store.activeAttempt();
      return {
        document_kind: 'exam',
        document_id: attempt.exam_id,
        version_id: attempt.exam_version_id,
        question_id: questionId,
        selected_text: text,
      };
    }
    if (rootKind === 'exam' && store.state.examTab === 'exam' && store.activeExam()) {
      const exam = store.activeExam();
      return { document_kind: 'exam', document_id: exam.id, version_id: exam.current_version_id, question_id: questionId, selected_text: text };
    }
    if (rootKind === 'exam' && store.state.examTab === 'draft' && store.activeDraft()) {
      const draft = store.activeDraft();
      return { document_kind: 'exam-draft', document_id: draft.id, version_id: draft.id, question_id: questionId, selected_text: text };
    }
    return { document_kind: 'source', document_id: store.state.activeSourceId || store.state.activeAiDocumentId, version_id: null, selected_text: text };
  }

  async bootstrap() {
    try {
      const workspace = await api.getWorkspace();
      const subjects = workspace.subjects || [];
      const models = workspace.models || [];
      const current = await api.getCurrentModel().catch(() => null);
      store.setState({
        bootstrapped: true,
        loadError: null,
        subjects,
        models,
        activeSubjectId: workspace.active_subject_id || subjects[0]?.id || null,
        currentModelId: current?.id || models[0]?.id || null,
      });
      if (store.state.activeSubjectId) await this.loadSubject(store.state.activeSubjectId);
    } catch (err) {
      store.setState({ bootstrapped: true, loadError: err.message });
    }
  }

  async loadSubject(subjectId) {
    const [sessionsData, sourcesData, docsData, blueprintsData, draftsData, examsData] = await Promise.all([
      api.listSessions(subjectId),
      api.listSources(subjectId),
      api.listAiDocuments(subjectId),
      api.listBlueprints(subjectId),
      api.listDrafts(subjectId),
      api.listExams(subjectId),
    ]);
    const sessions = sessionsData.items || [];
    const visible = sessions.filter(sessionVisible).sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
    const preferred = visible.find((item) => item.id === sessionsData.active_session_id);
    const activeSessionId = preferred?.id || visible[0]?.id || null;
    const sources = sourcesData.items || [];
    const docs = docsData.items || [];
    const blueprints = blueprintsData.items || [];
    const drafts = draftsData.items || [];
    const exams = examsData.items || [];
    store.setState({
      sessions,
      activeSessionId,
      sources,
      activeSourceId: store.state.activeSourceId && sources.some((item) => item.id === store.state.activeSourceId) ? store.state.activeSourceId : sources[0]?.id || null,
      aiDocuments: docs,
      activeAiDocumentId: store.state.activeAiDocumentId && docs.some((item) => item.id === store.state.activeAiDocumentId) ? store.state.activeAiDocumentId : docs[0]?.id || null,
      blueprints,
      activeBlueprintId: store.state.activeBlueprintId && blueprints.some((item) => item.id === store.state.activeBlueprintId) ? store.state.activeBlueprintId : blueprints[0]?.id || null,
      drafts,
      activeDraftId: store.state.activeDraftId && drafts.some((item) => item.id === store.state.activeDraftId) ? store.state.activeDraftId : drafts[0]?.id || null,
      exams,
      activeExamId: store.state.activeExamId && exams.some((item) => item.id === store.state.activeExamId) ? store.state.activeExamId : exams[0]?.id || null,
      examProposals: [],
      draftProposals: [],
    });
    if (store.state.activeSourceId) await this.loadSourceDetail(store.state.activeSourceId);
    if (store.state.activeAiDocumentId) await this.loadAiDocDetail(store.state.activeAiDocumentId);
    if (store.state.activeExamId) await this.loadExamDetail(store.state.activeExamId);
    await this.restoreAttempt(store.state.activeExamId);
    this.watchProcessingSources();
    this.watchDraft();
    this.watchGeneratingMessages();
  }

  async refreshSession() {
    if (!store.state.activeSessionId) return;
    const session = await api.getSession(store.state.activeSessionId);
    const current = store.state.sessions.find((item) => item.id === session.id);
    if (JSON.stringify(current) !== JSON.stringify(session)) {
      store.setState({
        sessions: store.state.sessions.map((item) => (item.id === session.id ? session : item)),
      });
    }
    this.watchGeneratingMessages();
  }

  async finalizeSessionAfterMessage() {
    if (!store.state.activeSubjectId) return;
    const listed = await api.listSessions(store.state.activeSubjectId);
    store.setState({ sessions: listed.items || [] });
    await this.refreshSession();
  }

  async pollSessionMessageOperation(operationId) {
    try {
      const done = await api.pollOperation(operationId, {
        onProgress: (op) => {
          store.trackOperation(op);
          store.patch({ chatOp: op });
        },
      });
      store.trackOperation(done);
      store.setState({ chatOp: null });
      return done;
    } catch (err) {
      store.setState({ chatOp: null });
      if (err.code !== 'OPERATION_TIMEOUT') store.addToast(err.message, 'error');
      throw err;
    }
  }

  async createSubject(name) {
    if (!name) return store.addToast('请填写科目名称', 'error');
    const subject = await api.createSubject(name);
    store.addToast('科目已创建', 'success');
    store.setState({ modal: null });
    await this.bootstrap();
    if (subject.id) await this.switchSubject(subject.id);
  }

  async renameSubject(name) {
    if (!name || !store.state.activeSubjectId) return store.addToast('请填写科目名称', 'error');
    await api.renameSubject(store.state.activeSubjectId, name);
    store.addToast('已重命名', 'success');
    store.setState({ modal: null });
    await this.bootstrap();
  }

  async switchSubject(subjectId) {
    const previous = store.state.activeSubjectId;
    const drafts = { ...store.state.composerBySubject };
    if (previous) drafts[previous] = store.state.composerText;
    store.setState({
      openMenu: null,
      activeSubjectId: subjectId,
      composerBySubject: drafts,
      composerText: drafts[subjectId] || '',
      attachments: [],
      selection: null,
    });
    await api.activateSubject(subjectId).catch(() => {});
    await this.loadSubject(subjectId);
  }

  async deleteSubject() {
    if (!store.state.activeSubjectId) return;
    this.askConfirm({
      title: '删除科目',
      message: '将删除该科目下的资料、会话、试卷和作答，无法恢复。',
      ok: '删除',
      action: 'delete-subject',
    });
  }

  async deleteSubjectConfirmed() {
    if (!store.state.activeSubjectId) return;
    await api.deleteSubject(store.state.activeSubjectId);
    store.addToast('科目已删除');
    store.setState({ openMenu: null });
    await this.bootstrap();
  }

  async createSession() {
    if (!store.state.activeSubjectId) return store.addToast('请先创建科目', 'error');
    store.setState({
      activeSessionId: null,
      mobilePane: { ...store.state.mobilePane, learn: 'chat', sources: 'ai', exam: 'ai', attempt: 'ai' },
      openMenu: null,
    });
    this.focusComposer();
  }

  async selectSession(sessionId) {
    this.ui.chatStick = true;
    await api.activateSession(sessionId).catch(() => {});
    const session = await api.getSession(sessionId);
    store.setState({
      activeSessionId: sessionId,
      sessions: store.state.sessions.map((item) => (item.id === sessionId ? session : item)),
      openMenu: null,
      mobilePane: { ...store.state.mobilePane, learn: 'chat' },
    });
    this.watchGeneratingMessages();
  }

  async renameSession(sessionId, title) {
    store.setState({ renamingSessionId: null });
    if (!sessionId || !title) return;
    const updated = await api.updateSession(sessionId, { title });
    store.setState({ sessions: store.state.sessions.map((item) => (item.id === sessionId ? updated : item)) });
  }

  async deleteSession(sessionId) {
    store.setState({ confirmSessionId: sessionId });
    this.askConfirm({
      title: '删除会话',
      message: '将删除该会话的全部消息，无法恢复。',
      ok: '删除',
      action: 'delete-session',
    });
  }

  async deleteSessionConfirmed(sessionId) {
    if (!sessionId) return;
    await api.deleteSession(sessionId);
    const data = await api.listSessions(store.state.activeSubjectId);
    const remaining = (data.items || []).filter(sessionVisible);
    store.setState({
      sessions: data.items || [],
      activeSessionId: remaining.some((item) => item.id === data.active_session_id)
        ? data.active_session_id
        : remaining[0]?.id || null,
    });
  }

  async setStyle(chatStyle) {
    store.setState({ openMenu: null, draftStyle: chatStyle });
    if (!store.state.activeSessionId) return;
    const updated = await api.updateSession(store.state.activeSessionId, { chat_style: chatStyle });
    store.setState({ sessions: store.state.sessions.map((item) => (item.id === updated.id ? updated : item)) });
  }

  async pinSource(versionId) {
    if (!store.state.activeSessionId) return store.addToast('先发送一条消息', 'error');
    await this.pinSessionSourceIdempotent(store.state.activeSessionId, versionId);
  }

  async pinSessionSourceIdempotent(sessionId, versionId) {
    const session = store.state.sessions.find((item) => item.id === sessionId);
    if ((session?.source_version_ids || []).includes(versionId)) return;
    try {
      await api.addSessionSource(sessionId, versionId);
    } catch (err) {
      if (err.code === 'SESSION_SOURCE_CONFLICT') return;
      throw err;
    }
    await this.refreshSession();
  }

  async mentionSource(source) {
    const versionId = source?.current_version?.id;
    if (!versionId) return;
    if (!store.state.activeSessionId) {
      const pending = store.state.pendingPins || [];
      if (!pending.includes(versionId)) {
        store.setState({ pendingPins: [...pending, versionId] });
      }
      return;
    }
    await this.pinSessionSourceIdempotent(store.state.activeSessionId, versionId);
  }

  async flushPendingPins(sessionId) {
    const pending = [...(store.state.pendingPins || [])];
    if (!pending.length) return;
    store.setState({ pendingPins: [] });
    for (const versionId of pending) {
      await this.pinSessionSourceIdempotent(sessionId, versionId);
    }
  }

  async unpinSource(versionId) {
    if (!store.state.activeSessionId) return;
    await api.removeSessionSource(store.state.activeSessionId, versionId);
    await this.refreshSession();
  }

  async abandonDraftSession(sessionId) {
    await api.deleteSession(sessionId).catch(() => {});
    store.setState({
      activeSessionId: null,
      sessions: store.state.sessions.filter((item) => item.id !== sessionId),
    });
  }

  async createNamedSession(content) {
    if (!store.state.activeSubjectId) throw new Error('请先创建科目');
    const base = titleFromMessage(content);
    const taken = new Set((store.state.sessions || []).map((item) => (item.title || '').toLowerCase()));
    let title = base;
    for (let index = 2; taken.has(title.toLowerCase()) && index < 20; index += 1) {
      title = `${base.slice(0, 20)} ${index}`;
    }
    try {
      return await api.createSession(store.state.activeSubjectId, {
        title,
        chat_style: store.state.draftStyle || 'default',
      });
    } catch (err) {
      if (err.code !== 'SESSION_NAME_DUPLICATE') throw err;
      return api.createSession(store.state.activeSubjectId, {
        title: `${base.slice(0, 16)} ${Date.now().toString(36).slice(-4)}`,
        chat_style: store.state.draftStyle || 'default',
      });
    }
  }

  async ensureSession(content) {
    const current = store.activeSession();
    let sessionId;
    if (current && sessionVisible(current)) {
      sessionId = current.id;
    } else if (store.state.activeSessionId && current) {
      sessionId = store.state.activeSessionId;
    } else {
      const session = await this.createNamedSession(content);
      store.setState({
        activeSessionId: session.id,
        sessions: [...store.state.sessions.filter((item) => item.id !== session.id), session],
      });
      sessionId = session.id;
    }
    await this.flushPendingPins(sessionId);
    return sessionId;
  }

  syncComposerFromDom() {
    const textarea = document.getElementById('composer-input');
    if (textarea) store.patch({ composerText: textarea.value });
  }

  async submitComposer() {
    if (this.sending) return;
    const busy = store.state.chatOp && ['queued', 'running', 'canceling'].includes(store.state.chatOp.status);
    if (busy) return;
    this.syncComposerFromDom();
    const content = store.state.composerText.trim();
    if (!content) return;

    const command = matchCommand(content);
    if (command) {
      this.sending = true;
      store.patch({ composerText: '' });
      store.setState({ attachments: [], selection: null, openMenu: null });
      try {
        await this.runCommand(command.def, command.args, content);
      } catch (err) {
        store.addToast(err.message, 'error');
      } finally {
        this.sending = false;
      }
      return;
    }

    this.sending = true;
    try {
      await this.send();
    } catch (err) {
      store.addToast(err.message, 'error');
    } finally {
      this.sending = false;
    }
  }

  async runCommand(def, args, rawCommand) {
    if (!store.activeModel()) return store.addToast('请先配置模型', 'error');
    if (def.run === 'proposeExamEdit' && !store.activeExam() && !store.activeDraft()) {
      return store.addToast('请先选择一份草稿或试卷', 'error');
    }
    if (def.run === 'proposeDocEdit' && !store.activeAiDocument()) {
      return store.addToast('请先选择一份 AI 文档', 'error');
    }
    const commandText = rawCommand || `${def.name} ${args}`.trim();
    const sid = await this.ensureSession(commandText);
    await api.appendSessionNote(sid, { role: 'user', content: commandText });
    await this.refreshSession();
    const labels = {
      parseBlueprint: '正在组卷',
      createAiDocument: '正在生成文档',
      proposeExamEdit: '正在生成修改预览',
      proposeDocEdit: '正在生成修改预览',
    };
    store.setState({ commandBusy: { sessionId: sid, label: labels[def.run] || '正在执行' } });
    try {
      let resultText = '';
      switch (def.run) {
        case 'parseBlueprint':
          store.setState({
            workspace: 'exam',
            examTab: 'blueprint',
            mobilePane: { ...store.state.mobilePane, exam: 'content' },
          });
          {
            const title = await this.parseBlueprint(args);
            resultText = `已生成蓝图「${title || '未命名'}」，请在组卷区确认题型与总分`;
          }
          break;
        case 'proposeExamEdit':
          if (store.activeExam()) await this.proposeExamEdit(args);
          else await this.proposeDraftEdit(args);
          resultText = '修改预览已就绪，请应用或放弃';
          break;
        case 'createAiDocument':
          store.setState({
            workspace: 'sources',
            sourceKind: 'docs',
            mobilePane: { ...store.state.mobilePane, sources: 'content' },
          });
          {
            const title = await this.createAiDocument(this.documentInstructionWithContext(args));
            resultText = `已生成文档「${title || '学习笔记'}」，可在资料区查看`;
          }
          break;
        case 'proposeDocEdit':
          if (!store.activeAiDocument()) throw new Error('请先选择一份 AI 文档');
          await this.proposeDocEdit(args);
          resultText = '修改预览已就绪，请应用或放弃';
          break;
        default:
          break;
      }
      if (resultText) {
        await api.appendSessionNote(sid, { role: 'system', content: resultText });
        await this.refreshSession();
      }
    } catch (err) {
      const failed = `${def.name}失败：${err.message || '未知错误'}`;
      try {
        await api.appendSessionNote(sid, { role: 'system', content: failed });
        await this.refreshSession();
      } catch {
        /* keep the original command error */
      }
      throw err;
    } finally {
      store.setState({ commandBusy: null });
    }
  }

  documentInstructionWithContext(args) {
    const session = store.activeSession();
    const messages = session?.messages || [];
    if (!messages.length) return args;
    const lines = messages.slice(-6).map((msg) => {
      const role = msg.role === 'user' ? '用户' : 'AI';
      return `${role}：${blocksToText(msg.content)}`;
    });
    let context = lines.join('\n');
    if (context.length > 2000) context = context.slice(0, 2000);
    return `${args}\n\n（当前对话上下文，供整理参考）\n${context}`;
  }

  async send() {
    const content = store.state.composerText.trim();
    if (!content) return;
    if (!store.activeModel()) return store.addToast('请先配置模型', 'error');
    const wasDraft = !sessionVisible(store.activeSession());
    const sessionId = await this.ensureSession(content);
    const workspace = store.state.workspace;
    const attachmentIds = [];
    for (const item of store.state.attachments) {
      const uploaded = await api.uploadAttachment(store.state.activeSubjectId, item.file);
      attachmentIds.push(uploaded.id);
    }
    const selection = officialSelection(store.state.selection);
    const payload = {
      content: selection || !store.state.selection?.selected_text
        ? content
        : `${content}\n\n> ${store.state.selection.selected_text}`,
      chat_style: store.activeSession()?.chat_style || 'default',
      grounding_mode: store.state.groundingMode,
    };
    if (store.state.currentModelId) payload.model_id = store.state.currentModelId;
    if (selection) payload.selection = selection;
    if (attachmentIds.length) payload.attachment_ids = attachmentIds;

    store.patch({ composerText: '' });
    store.setState({ attachments: [], selection: null, openMenu: null });

    let accepted;
    try {
      accepted = await api.createSessionMessage(sessionId, payload);
    } catch (err) {
      if (wasDraft) await this.abandonDraftSession(sessionId);
      throw err;
    }
    store.setState({ chatOp: accepted.operation });
    store.trackOperation(accepted.operation);
    this.ui.chatStick = true;
    await this.finalizeSessionAfterMessage();
    try {
      await this.pollSessionMessageOperation(accepted.operation.id);
    } catch {
      /* timeout handled by generating watch */
    }
    await this.finalizeSessionAfterMessage();

    if (workspace === 'exam' && !store.state.blueprints.length && content.length > 4) {
      await this.parseBlueprint(content);
    }
  }

  async stopChat() {
    let operationId = store.state.chatOp?.id;
    if (!operationId) {
      const session = store.activeSession();
      const messageList = session?.messages || [];
      const last = messageList[messageList.length - 1];
      if (last?.role === 'assistant' && ['queued', 'generating'].includes(last.status)) {
        const active = store.state.operations.find(
          (item) => item.resource?.type === 'chat-message'
            && item.resource?.id === last.id
            && !['succeeded', 'failed', 'canceled'].includes(item.status),
        );
        operationId = active?.id;
      }
    }
    if (!operationId) return;
    await api.cancelOperation(operationId);
    store.setState({ chatOp: null });
    await this.refreshSession();
  }

  async retryMessage(messageId) {
    if (!store.state.activeSessionId || !messageId) return;
    const accepted = await api.retrySessionMessage(store.state.activeSessionId, messageId, {
      model_id: store.state.currentModelId,
    });
    store.setState({ chatOp: accepted.operation });
    store.trackOperation(accepted.operation);
    await this.finalizeSessionAfterMessage();
    try {
      await this.pollSessionMessageOperation(accepted.operation.id);
    } catch {
      /* timeout handled by generating watch */
    }
    await this.finalizeSessionAfterMessage();
  }

  async parseBlueprint(prompt) {
    const accepted = await api.parseBlueprint(store.state.activeSubjectId, {
      prompt,
      grounding_mode: store.state.groundingMode,
      source_version_ids: readySourceVersionIds(store.state.sources),
      model_id: store.state.currentModelId,
    });
    store.trackOperation(accepted.operation);
    store.setState({ examTab: 'blueprint', workspace: 'exam', mobilePane: { ...store.state.mobilePane, exam: 'content' } });
    const done = await api.pollOperation(accepted.operation.id, { onProgress: (op) => store.trackOperation(op) });
    store.trackOperation(done);
    const data = await api.listBlueprints(store.state.activeSubjectId);
    const id = accepted.resource?.id || data.items?.[0]?.id;
    store.setState({ blueprints: data.items || [], activeBlueprintId: id || null });
    if (id) store.setState({ activeBlueprintId: id, blueprints: data.items || [] });
    store.addToast('蓝图已生成', 'success');
    const blueprint = (data.items || []).find((item) => item.id === id);
    return blueprint?.title || '';
  }

  async proposeDraftEdit(instruction) {
    const draft = store.activeDraft();
    if (!draft) throw new Error('请先选择一份草稿或试卷');
    const accepted = await api.createDraftRevisionProposal(draft.id, {
      instruction,
      model_id: store.state.currentModelId,
    });
    store.trackOperation(accepted.operation);
    await api.pollOperation(accepted.operation.id, { onProgress: (op) => store.trackOperation(op) });
    await this.loadDraftProposals(draft.id);
    store.setState({ examTab: 'draft', workspace: 'exam', mobilePane: { ...store.state.mobilePane, exam: 'content' } });
    store.addToast('修改预览已就绪', 'success');
  }

  async loadDraftProposals(draftId) {
    const proposals = await api.listDraftRevisionProposals(draftId);
    store.setState({ draftProposals: proposals.items || [] });
  }

  async applyDraftProposal(proposalId) {
    await api.applyDraftRevisionProposal(proposalId);
    const draftId = store.state.activeDraftId;
    if (draftId) {
      await this.selectDraft(draftId);
      await this.loadDraftProposals(draftId);
    }
    store.addToast('已应用修改', 'success');
  }

  async discardDraftProposal(proposalId) {
    await api.discardDraftRevisionProposal(proposalId);
    if (store.state.activeDraftId) await this.loadDraftProposals(store.state.activeDraftId);
  }

  async proposeExamEdit(instruction) {
    const exam = store.activeExam();
    const accepted = await api.createRevisionProposal(exam.id, {
      base_version_id: exam.current_version_id,
      instruction,
      scope: { kind: 'whole-exam', question_ids: [], block_ids: [] },
      model_id: store.state.currentModelId,
    });
    store.trackOperation(accepted.operation);
    await api.pollOperation(accepted.operation.id, { onProgress: (op) => store.trackOperation(op) });
    await this.loadExamDetail(exam.id);
    store.setState({ examTab: 'exam', mobilePane: { ...store.state.mobilePane, exam: 'content' } });
    store.addToast('修改预览已就绪', 'success');
  }

  async proposeDocEdit(instruction) {
    const doc = store.activeAiDocument();
    const version = currentAiVersion(doc);
    if (!version) return;
    const accepted = await api.createAiDocumentRevisionProposal(doc.id, {
      base_version_id: version.id,
      instruction,
      model_id: store.state.currentModelId,
    });
    store.trackOperation(accepted.operation);
    await api.pollOperation(accepted.operation.id, { onProgress: (op) => store.trackOperation(op) });
    await this.loadAiDocDetail(doc.id);
    store.setState({ sourceKind: 'docs', mobilePane: { ...store.state.mobilePane, sources: 'content' } });
    store.addToast('修改预览已就绪', 'success');
  }

  async createAiDocumentFromPrompt() {
    const instruction = store.state.composerText.trim() || '整理当前资料的要点';
    await this.createAiDocument(instruction);
  }

  async createAiDocument(instruction) {
    if (!store.activeModel()) return store.addToast('请先配置模型', 'error');
    const accepted = await api.createAiDocument(store.state.activeSubjectId, {
      instruction,
      source_version_ids: readySourceVersionIds(store.state.sources),
      grounding_mode: store.state.groundingMode,
      model_id: store.state.currentModelId,
    });
    store.trackOperation(accepted.operation);
    const done = await api.pollOperation(accepted.operation.id, { onProgress: (op) => store.trackOperation(op) });
    store.trackOperation(done);
    const data = await api.listAiDocuments(store.state.activeSubjectId);
    const id = accepted.resource?.id || done.result?.id || data.items?.[0]?.id;
    store.setState({ aiDocuments: data.items || [], activeAiDocumentId: id, sourceKind: 'docs', workspace: 'sources' });
    if (id) await this.loadAiDocDetail(id);
    store.addToast('文档已生成', 'success');
    const doc = (store.state.aiDocuments || []).find((item) => item.id === id);
    return doc?.title || '';
  }

  async saveModel(form) {
    if (!form.provider || !form.model || !form.base_url) return store.addToast('请填写服务商、模型和地址', 'error');
    const editingId = store.state.editingModelId;
    store.setState({ modelBusy: 'save', discoverError: null, modelForm: form });
    try {
      const payload = {
        provider: form.provider,
        api_format: form.api_format,
        model: form.model,
        base_url: form.base_url,
        capabilities: { text: true, vision: !!form.vision },
      };
      if (form.api_key) payload.api_key = form.api_key;
      if (editingId) {
        await api.updateModel(editingId, payload);
        store.addToast('已保存', 'success');
      } else {
        await api.createModel({ ...payload, api_key: form.api_key || undefined });
        store.addToast('模型已添加', 'success');
      }
      const models = (await api.listModels()).items || [];
      const savedModelId = editingId || models.find((item) => item.provider === form.provider && item.model === form.model)?.id;
      store.setState({ models, modelForm: defaultForm(), editingModelId: null, modelBusy: null });
      if (!store.state.currentModelId && models[0]) await this.selectModel(models[0].id);
      if (savedModelId) void this.verifyModel(savedModelId);
    } catch (err) {
      store.setState({ modelBusy: null });
      store.addToast(err.message, 'error');
    }
  }

  async discoverModels(form) {
    if (!form.base_url) return store.addToast('请填写 Base URL', 'error');
    store.setState({ modelBusy: 'discover', discoverError: null, modelForm: form, discoveredModels: [] });
    try {
      const result = await api.discoverModels({
        api_format: form.api_format,
        base_url: form.base_url,
        api_key: form.api_key || undefined,
        manual_model_name: form.model || null,
      });
      const models = result.models || [];
      const nextForm = models.length === 1 && !form.model ? { ...form, model: models[0].name } : form;
      store.setState({
        discoveredModels: models,
        modelForm: nextForm,
        modelBusy: null,
        discoverError: result.error?.message || (models.length ? null : '没有返回模型，可手动填写'),
      });
      if (models.length) store.addToast(`发现 ${models.length} 个模型`, 'success');
      else store.addToast(result.error?.message || '没有返回模型，可手动填写', 'error');
    } catch (err) {
      store.setState({ modelBusy: null, discoverError: err.message });
      store.addToast(err.message, 'error');
    }
  }

  editModel(modelId) {
    const model = store.state.models.find((item) => item.id === modelId);
    if (!model) return;
    store.setState({
      editingModelId: modelId,
      modelForm: formFromModel(model),
      discoverError: null,
    });
  }

  async selectModel(modelId) {
    if (!modelId) return store.addToast('未选择模型', 'error');
    try {
      const model = await api.selectCurrentModel(modelId);
      if (!model?.id) throw new Error('切换模型失败');
      store.setState({ currentModelId: model.id, openMenu: null });
    } catch (err) {
      store.addToast(err.message, 'error');
    }
  }

  async verifyModel(modelId) {
    if (!modelId) return store.addToast('未选择模型', 'error');
    store.setState({ modelBusy: 'verify' });
    try {
      const accepted = await api.verifyModel(modelId);
      const operationId = accepted?.operation?.id;
      if (!operationId) throw new Error('验证任务未创建');
      store.trackOperation(accepted.operation);
      await api.pollOperation(operationId, { onProgress: (op) => store.trackOperation(op) });
      const models = (await api.listModels()).items || [];
      const updated = models.find((item) => item.id === modelId);
      store.setState({ models, modelBusy: null });
      store.addToast(updated?.validation?.message || '连接可用', 'success');
    } catch (err) {
      const models = await api.listModels().then((res) => res.items || []).catch(() => store.state.models);
      store.setState({ models, modelBusy: null });
      store.addToast(err.message, 'error');
    }
  }

  async deleteModel(modelId) {
    try {
      await api.deleteModel(modelId);
      const models = (await api.listModels()).items || [];
      store.setState({
        models,
        currentModelId: store.state.currentModelId === modelId ? models[0]?.id || null : store.state.currentModelId,
        editingModelId: store.state.editingModelId === modelId ? null : store.state.editingModelId,
      });
    } catch (err) {
      store.addToast(err.message, 'error');
    }
  }

  async selectSource(sourceId) {
    store.setState({ activeSourceId: sourceId, sourceKind: 'files' });
    await this.loadSourceDetail(sourceId);
  }

  async loadSourceDetail(sourceId) {
    const source = await api.getSource(sourceId);
    const versionId = source.current_version?.id;
    const [anchorsRes, versionsRes] = await Promise.all([
      versionId && source.status === 'ready'
        ? api.listSourceVersionAnchors(versionId).catch(() => ({ items: [] }))
        : Promise.resolve({ items: [] }),
      api.listSourceVersions(sourceId).catch(() => ({ items: [] })),
    ]);
    store.setState({
      sources: store.state.sources.map((item) => (item.id === sourceId ? source : item)),
      sourceAnchors: anchorsRes.items || [],
      sourceVersions: versionsRes.items || [],
    });
  }

  async onUploadSources(files) {
    if (!store.state.activeSubjectId) return store.addToast('请先创建科目', 'error');
    for (const file of files) {
      const accepted = await api.uploadSource(store.state.activeSubjectId, file);
      store.trackOperation(accepted.operation);
      try {
        await api.pollOperation(accepted.operation.id, { onProgress: (op) => store.trackOperation(op) });
        store.addToast(`${file.name} 已上传`, 'success');
      } catch (err) {
        store.addToast(err.message, 'error');
      }
    }
    const data = await api.listSources(store.state.activeSubjectId);
    store.setState({ sources: data.items || [], activeSourceId: data.items?.[0]?.id || null, sourceKind: 'files' });
    if (store.state.activeSourceId) await this.loadSourceDetail(store.state.activeSourceId);
  }

  async deleteSource(sourceId) {
    store.setState({ confirmSourceId: sourceId });
    this.askConfirm({
      title: '删除资料',
      message: '将删除这份资料。已引用它的会话和试卷仍会保留历史来源。',
      ok: '删除',
      action: 'delete-source',
    });
  }

  async deleteSourceConfirmed(sourceId) {
    if (!sourceId) return;
    await api.deleteSource(sourceId);
    const data = await api.listSources(store.state.activeSubjectId);
    store.setState({ sources: data.items || [], activeSourceId: data.items?.[0]?.id || null, sourceAnchors: [], sourceVersions: [] });
  }

  async selectAiDoc(docId) {
    store.setState({ activeAiDocumentId: docId, sourceKind: 'docs' });
    await this.loadAiDocDetail(docId);
  }

  async loadAiDocDetail(docId) {
    const [doc, proposals] = await Promise.all([
      api.getAiDocument(docId),
      api.listAiDocumentRevisionProposals(docId),
    ]);
    store.setState({
      aiDocuments: store.state.aiDocuments.map((item) => (item.id === docId ? doc : item)),
      activeAiDocumentId: docId,
      aiDocumentProposals: proposals.items || [],
    });
  }

  async applyDocProposal(proposalId) {
    await api.applyAiDocumentRevisionProposal(proposalId);
    await this.loadAiDocDetail(store.state.activeAiDocumentId);
    store.addToast('已应用', 'success');
  }

  async discardDocProposal(proposalId) {
    await api.discardAiDocumentRevisionProposal(proposalId);
    await this.loadAiDocDetail(store.state.activeAiDocumentId);
  }

  async selectBlueprint(id) {
    const blueprint = await api.getBlueprint(id);
    store.setState({
      activeBlueprintId: id,
      blueprints: store.state.blueprints.map((item) => (item.id === id ? blueprint : item)),
    });
  }

  async removeBlueprintPoint(id, index) {
    const current = store.state.blueprints.find((item) => item.id === id);
    if (!current || current.status !== 'draft') return;
    const syllabus = (current.syllabus || []).filter((_, itemIndex) => itemIndex !== Number(index));
    await api.updateBlueprint(id, { syllabus });
    const [list, detail] = await Promise.all([
      api.listBlueprints(store.state.activeSubjectId),
      api.getBlueprint(id),
    ]);
    store.setState({
      activeBlueprintId: id,
      blueprints: (list.items || []).map((item) => (item.id === id ? detail : item)),
    });
  }

  async confirmBlueprint(id) {
    const blueprint = await api.confirmBlueprint(id);
    store.setState({ blueprints: store.state.blueprints.map((item) => (item.id === id ? blueprint : item)) });
    store.addToast('蓝图已确认', 'success');
  }

  async generateDraft(id) {
    const accepted = await api.generateDraftFromBlueprint(id);
    store.trackOperation(accepted.operation);
    const data = await api.listDrafts(store.state.activeSubjectId);
    const draftId = accepted.resource?.id || data.items?.[0]?.id;
    store.setState({ examTab: 'draft', drafts: data.items || [], activeDraftId: draftId || null });
    if (draftId) await this.selectDraft(draftId);
    this.watchDraft();
    store.addToast('已开始组题', 'success');
    api.pollOperation(accepted.operation.id, { onProgress: (op) => store.trackOperation(op) })
      .then(async () => {
        if (store.state.activeDraftId) await this.selectDraft(store.state.activeDraftId);
      })
      .catch((err) => store.addToast(sanitizeErrorMessage(err.message), 'error'));
  }

  async selectDraft(id) {
    const draft = await api.getDraft(id);
    store.setState({
      activeDraftId: id,
      drafts: store.state.drafts.map((item) => (item.id === id ? draft : item)),
      examTab: 'draft',
    });
    await this.loadDraftProposals(id).catch(() => store.setState({ draftProposals: [] }));
    this.watchDraft();
  }

  async updateBlueprintPlan(blueprintId, index, field, rawValue) {
    const current = store.state.blueprints.find((item) => item.id === blueprintId);
    if (!current || current.status !== 'draft') return;
    const plan = (current.question_plan || []).map((row, rowIndex) => ({ ...row }));
    if (!plan[index]) return;
    const value = Number(rawValue);
    if (!Number.isFinite(value) || value <= 0) return;
    plan[index][field] = field === 'count' ? Math.max(1, Math.round(value)) : value;
    const total = plan.reduce((sum, row) => sum + row.count * row.score_each, 0);
    await api.updateBlueprint(blueprintId, { question_plan: plan, total_score: total });
    const detail = await api.getBlueprint(blueprintId);
    store.setState({
      blueprints: store.state.blueprints.map((item) => (item.id === blueprintId ? detail : item)),
    });
  }

  watchDraft() {
    if (this.draftPoll) window.clearInterval(this.draftPoll);
    const draft = store.activeDraft();
    if (!draft || draft.status !== 'generating') return;
    this.draftPoll = window.setInterval(async () => {
      try {
        const latest = await api.getDraft(draft.id);
        const current = store.state.drafts.find((item) => item.id === latest.id);
        if (JSON.stringify(current) === JSON.stringify(latest)) {
          if (latest.status !== 'generating') {
            window.clearInterval(this.draftPoll);
            this.draftPoll = null;
          }
          return;
        }
        store.setState({ drafts: store.state.drafts.map((item) => (item.id === latest.id ? latest : item)) });
        if (latest.status !== 'generating') {
          window.clearInterval(this.draftPoll);
          this.draftPoll = null;
        }
      } catch {
        window.clearInterval(this.draftPoll);
        this.draftPoll = null;
      }
    }, 1500);
  }

  watchGeneratingMessages() {
    const session = store.activeSession();
    const messageList = session?.messages || [];
    const last = messageList[messageList.length - 1];
    const shouldWatch = !!session
      && store.state.workspace === 'learn'
      && last?.role === 'assistant'
      && ['queued', 'generating'].includes(last.status);

    if (!shouldWatch) {
      if (this.generatingPoll) {
        window.clearInterval(this.generatingPoll);
        this.generatingPoll = null;
        this.generatingWatchSessionId = null;
      }
      return;
    }

    if (this.generatingPoll && this.generatingWatchSessionId === session.id) return;

    if (this.generatingPoll) {
      window.clearInterval(this.generatingPoll);
      this.generatingPoll = null;
    }
    this.generatingWatchSessionId = session.id;
    this.generatingPoll = window.setInterval(async () => {
      try {
        const latest = await api.getSession(session.id);
        const current = store.state.sessions.find((item) => item.id === latest.id);
        const latestLast = (latest.messages || [])[latest.messages.length - 1];
        const stillGenerating = latestLast?.role === 'assistant'
          && ['queued', 'generating'].includes(latestLast.status);
        if (JSON.stringify(current) !== JSON.stringify(latest)) {
          store.setState({
            sessions: store.state.sessions.map((item) => (item.id === latest.id ? latest : item)),
          });
        }
        if (!stillGenerating) {
          window.clearInterval(this.generatingPoll);
          this.generatingPoll = null;
          this.generatingWatchSessionId = null;
          if (store.state.activeSubjectId) {
            const listed = await api.listSessions(store.state.activeSubjectId);
            store.setState({ sessions: listed.items || [] });
          }
        }
      } catch {
        window.clearInterval(this.generatingPoll);
        this.generatingPoll = null;
        this.generatingWatchSessionId = null;
      }
    }, 3000);
  }

  watchProcessingSources() {
    if (this.sourcePoll) window.clearInterval(this.sourcePoll);
    if (!(store.state.sources || []).some((item) => item.status === 'processing')) return;
    this.sourcePoll = window.setInterval(async () => {
      try {
        const data = await api.listSources(store.state.activeSubjectId);
        if (JSON.stringify(store.state.sources) === JSON.stringify(data.items || [])) {
          if (!(data.items || []).some((item) => item.status === 'processing')) {
            window.clearInterval(this.sourcePoll);
            this.sourcePoll = null;
          }
          return;
        }
        store.setState({ sources: data.items || [] });
        if (store.state.activeSourceId) await this.loadSourceDetail(store.state.activeSourceId);
        if (!(data.items || []).some((item) => item.status === 'processing')) {
          window.clearInterval(this.sourcePoll);
          this.sourcePoll = null;
        }
      } catch {
        window.clearInterval(this.sourcePoll);
        this.sourcePoll = null;
      }
    }, 1500);
  }

  async retryQuestion(draftId, questionId) {
    const accepted = await api.retryDraftQuestion(draftId, questionId);
    store.trackOperation(accepted.operation);
    await api.pollOperation(accepted.operation.id, { onProgress: (op) => store.trackOperation(op) });
    await this.selectDraft(draftId);
  }

  async publishDraft(id) {
    const draft = store.state.drafts.find((item) => item.id === id) || store.activeDraft();
    const state = draftPublishState(draft);
    if (!state.canPublish) return store.addToast('先重试失败或未完成的题目', 'error');
    if (state.needsConfirm) {
      store.setState({ confirmDraftId: id });
      this.askConfirm({
        title: '发布试卷',
        message: '草稿仍有待复查题目。确认后将按当前内容发布。',
        ok: '仍要发布',
        action: 'publish-draft',
      });
      return;
    }
    await this.publishDraftConfirmed(id, false);
  }

  async publishDraftConfirmed(id, acceptNeedsReview) {
    if (!id) return;
    const exam = await api.publishDraft(id, { accept_needs_review: !!acceptNeedsReview });
    const data = await api.listExams(store.state.activeSubjectId);
    const examId = exam?.id || data.items?.[0]?.id;
    store.setState({ exams: data.items || [], activeExamId: examId, examTab: 'exam' });
    if (examId) await this.loadExamDetail(examId);
    store.addToast('试卷已发布', 'success');
  }

  async selectExam(id) {
    store.setState({ activeExamId: id });
    await this.loadExamDetail(id);
    if (store.state.workspace === 'attempt') await this.restoreAttempt(id);
  }

  async loadExamDetail(examId) {
    const [exam, proposals] = await Promise.all([api.getExam(examId), api.listRevisionProposals(examId)]);
    store.setState({
      exams: store.state.exams.map((item) => (item.id === examId ? exam : item)),
      examProposals: proposals.items || [],
    });
  }

  async applyExamProposal(id) {
    await api.applyRevisionProposal(id);
    await this.loadExamDetail(store.state.activeExamId);
    store.addToast('已应用', 'success');
  }

  async discardExamProposal(id) {
    await api.discardRevisionProposal(id);
    await this.loadExamDetail(store.state.activeExamId);
  }

  async undoExam(id) {
    const exam = await api.undoExamChange(id);
    store.setState({ exams: store.state.exams.map((item) => (item.id === id ? exam : item)) });
  }

  async redoExam(id) {
    const exam = await api.redoExamChange(id);
    store.setState({ exams: store.state.exams.map((item) => (item.id === id ? exam : item)) });
  }

  canViewReview(attempt) {
    return attempt?.mode === 'practice' || attempt?.completion_status === 'completed';
  }

  async refreshAttempt(id) {
    const attempt = await api.getAttempt(id);
    const review = this.canViewReview(attempt)
      ? await api.getAttemptReview(id).catch(() => null)
      : null;
    store.setState({ activeAttempt: attempt, activeAttemptId: attempt.id, review });
    return attempt;
  }

  async startAttempt(examId, mode) {
    const attempt = await api.createAttempt(examId, { mode, show_suggested_score: mode === 'practice' });
    store.rememberAttempt(examId, attempt.id);
    store.setState({ activeExamId: examId, mobilePane: { ...store.state.mobilePane, attempt: 'content' } });
    await this.refreshAttempt(attempt.id);
  }

  async restoreAttempt(examId) {
    if (!examId) return store.setState({ activeAttempt: null, activeAttemptId: null, review: null });
    const ids = store.state.attemptsByExam[examId] || [];
    for (const id of ids) {
      try {
        await this.refreshAttempt(id);
        return;
      } catch {
        /* stale */
      }
    }
    store.setState({ activeAttempt: null, activeAttemptId: null, review: null });
  }

  async saveAnswer(attemptId, questionId, answer) {
    try {
      await api.saveAttemptAnswer(attemptId, questionId, answer);
      await this.refreshAttempt(attemptId);
    } catch (err) {
      store.addToast(err.message, 'error');
    }
  }

  async completeAttempt(id) {
    await api.completeAttempt(id);
    await this.refreshAttempt(id);
    store.addToast('已完成作答', 'success');
  }

  async continueAttempt(id) {
    await api.continueAttempt(id);
    await this.refreshAttempt(id);
  }

  async gradeAttempt(id) {
    const accepted = await api.submitAttemptGrading(id, { model_id: store.state.currentModelId });
    store.trackOperation(accepted.operation);
    await api.pollOperation(accepted.operation.id, { onProgress: (op) => store.trackOperation(op) });
    await this.refreshAttempt(id);
    store.addToast('批改完成', 'success');
  }

  async askFeedback(attemptId, questionId) {
    const accepted = await api.requestQuestionFeedback(attemptId, questionId, { model_id: store.state.currentModelId });
    store.trackOperation(accepted.operation);
    await api.pollOperation(accepted.operation.id, { onProgress: (op) => store.trackOperation(op) });
    await this.refreshAttempt(attemptId);
  }

  async run(fail, task, after) {
    try {
      const result = await task();
      if (after) await after(result);
    } catch (err) {
      store.addToast(err.message || fail, 'error');
    }
  }
}

function readyMentionSources(sources) {
  return (sources || []).filter((src) => src.current_version?.id && (src.status === 'ready' || src.current_version.status === 'ready'));
}

function spin() {
  return `<svg class="spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-9-9"/></svg>`;
}

window.addEventListener('DOMContentLoaded', () => {
  new App().init();
});
