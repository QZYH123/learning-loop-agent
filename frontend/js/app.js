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
  questionFromEditor,
  renderExamPrintDocument,
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
  defaultGroundingMode,
  nextOptionId,
  sessionVisible,
  titleFromMessage,
  draftPublishState,
  sanitizeErrorMessage,
  textToMarkdownBlocks,
} from './util.js';
import { attemptLimitMs, attemptRemainingMs, examDurationMinutes, formatElapsed } from './attempt-timer.js';
import { initPet, petNotify } from './pet.js';

class App {
  constructor() {
    this.root = document.getElementById('app');
    this.ui = { composerFocus: false, range: [0, 0], chatScroll: 0, chatStick: true, contentScroll: 0, searchFocus: false, searchRange: [0, 0], reviseFocus: false, reviseRange: [0, 0] };
    this.selectionPop = null;
    this.draftPoll = null;
    this.sourcePoll = null;
    this.generatingPoll = null;
    this.generatingWatchSessionId = null;
    this.sending = false;
    this.revising = false;
    this.applyingProposal = false;
    this.retryingQuestions = new Set();
    this.regions = { workspace: null, shell: '', left: '', right: '', nav: '' };
    this.attemptTimer = null;
    this.citeHighlightTimer = null;
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
    initPet();
  }

  bindGlobals() {
    document.addEventListener('click', (event) => this.onClick(event));
    document.addEventListener('change', (event) => this.onFieldChange(event));
    document.addEventListener('input', (event) => this.onFieldInput(event));
    document.addEventListener('mouseup', (event) => this.onMouseUp(event));
    document.addEventListener('keydown', (event) => this.onKeyDown(event));
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
    const rename = document.querySelector('[data-rename-session], [data-rename-resource]');
    this.ui.renameFocus = rename && document.activeElement === rename;
    if (rename) {
      this.ui.renameRange = [rename.selectionStart, rename.selectionEnd];
      this.ui.renameValue = rename.value;
    } else {
      this.ui.renameValue = null;
    }
    const revise = document.getElementById('question-revise-input');
    this.ui.reviseFocus = revise && document.activeElement === revise;
    if (revise) this.ui.reviseRange = [revise.selectionStart, revise.selectionEnd];
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
    const revise = document.getElementById('question-revise-input');
    if (revise) {
      revise.value = store.state.draftQuestionPrompt || '';
      if (this.ui.reviseFocus) {
        revise.focus();
        revise.setSelectionRange(this.ui.reviseRange[0], this.ui.reviseRange[1]);
      }
    }
    if (chat) chat.scrollTop = this.ui.chatStick ? chat.scrollHeight : this.ui.chatScroll;
    if (content) content.scrollTop = this.ui.contentScroll;
    const rename = document.querySelector('[data-rename-session], [data-rename-resource]');
    if (rename) {
      if (this.ui.renameValue != null) rename.value = this.ui.renameValue;
      if (this.ui.renameFocus) {
        rename.focus();
        rename.setSelectionRange(this.ui.renameRange[0], this.ui.renameRange[1]);
      }
    }
  }

  handlers() {
    return {
      onSelectWorkspace: (id) => {
        store.setState({ workspace: id, openMenu: null });
        if (id === 'attempt') this.loadMissedQuestions();
      },
      onToggleMenu: (name) => store.setState({
        openMenu: store.state.openMenu === name ? null : name,
        menuFocusIndex: -1,
      }),
      onOpenRuns: () => this.openRuns(),
      onRunEvaluation: (id) => this.runEvaluation(id),
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
      onExportSubject: () => this.exportSubject(),
      onImportSubject: (file) => this.importSubject(file),
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
      onConfirmExamEdition: (edition) => this.confirmExamEdition(edition),
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
    this.startAttemptTimer();
    this.highlightMenuFocus();
    this.watchGeneratingMessages();
  }

  bindRename() {
    const input = document.querySelector('[data-rename-session], [data-rename-resource]');
    if (!input) return;
    if (document.activeElement !== input) {
      input.focus();
      input.select();
    }
    const commit = async () => {
      if (input.dataset.renameResource) {
        await this.renameResource(input.dataset.renameResource, input.dataset.id, input.value.trim());
        return;
      }
      if (store.state.renamingSessionId) await this.renameSession(store.state.renamingSessionId, input.value.trim());
    };
    input.onkeydown = async (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        await commit();
      }
      if (event.key === 'Escape') {
        store.setState({ renamingSessionId: null, renamingBlueprintId: null, renamingExamId: null });
      }
    };
    input.onblur = async () => {
      if (store.state.renamingSessionId || store.state.renamingBlueprintId || store.state.renamingExamId) {
        await commit();
      }
    };
  }

  startAttemptTimer() {
    if (this.attemptTimer) {
      window.clearInterval(this.attemptTimer);
      this.attemptTimer = null;
    }
    const tick = () => {
      const el = document.querySelector('[data-attempt-timer]');
      if (!el) {
        if (this.attemptTimer) {
          window.clearInterval(this.attemptTimer);
          this.attemptTimer = null;
        }
        return;
      }
      const elapsed = Number(el.dataset.elapsedMs) || 0;
      const started = el.dataset.timingStartedAt ? Number(el.dataset.timingStartedAt) : 0;
      const running = el.dataset.running === '1';
      const limitMs = Number(el.dataset.limitMs) || 0;
      const ms = running && started ? elapsed + Math.max(0, Date.now() - started) : elapsed;
      const remaining = limitMs ? Math.max(0, limitMs - ms) : null;
      el.textContent = formatElapsed(remaining == null ? ms : remaining);
      if (limitMs && running && remaining === 0) this.expireExamAttempt();
    };
    tick();
    if (document.querySelector('[data-attempt-timer][data-running="1"]')) {
      this.attemptTimer = window.setInterval(tick, 1000);
    }
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
      if (action === 'select-workspace') {
        store.setState({ workspace: target.dataset.workspace, openMenu: null });
        if (target.dataset.workspace === 'attempt') await this.loadMissedQuestions();
      }
      else if (action === 'toggle-menu') {
        store.setState({
          openMenu: store.state.openMenu === target.dataset.menu ? null : target.dataset.menu,
          menuFocusIndex: -1,
        });
      } else if (action === 'open-runs') await this.openRuns();
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
      else if (action === 'set-grounding') {
        const subjectId = store.state.activeSubjectId;
        store.setState({
          groundingMode: id,
          groundingBySubject: subjectId
            ? { ...store.state.groundingBySubject, [subjectId]: id }
            : store.state.groundingBySubject,
          openMenu: null,
        });
      }
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
      else if (action === 'revise-ai-doc') this.reviseCurrentAiDocument();
      else if (action === 'view-source-version') await this.loadSourceDetail(id, target.dataset.versionId);
      else if (action === 'view-ai-doc-version') store.setState({ aiDocumentViewVersionId: target.dataset.versionId });
      else if (action === 'restore-ai-doc-version') await this.restoreAiDocumentVersion(id, target.dataset.versionId);
      else if (action === 'apply-doc-proposal') await this.applyDocProposal(id);
      else if (action === 'discard-doc-proposal') await this.discardDocProposal(id);
      else if (action === 'exam-tab') store.setState({ examTab: target.dataset.tab });
      else if (action === 'attempt-tab') {
        store.setState({ attemptTab: target.dataset.tab });
        if (target.dataset.tab === 'missed') await this.loadMissedQuestions();
      }
      else if (action === 'open-missed-question') await this.openMissedQuestion(target.dataset.attemptId, target.dataset.questionId);
      else if (action === 'practice-missed-set') await this.practiceMissedSet();
      else if (action === 'select-blueprint') await this.selectBlueprint(id);
      else if (action === 'rename-blueprint') {
        event.stopPropagation();
        store.setState({ renamingBlueprintId: id, renamingExamId: null, renamingSessionId: null, openMenu: null });
      }       else if (action === 'rename-exam') {
        event.stopPropagation();
        store.setState({ renamingExamId: id, renamingBlueprintId: null, renamingSessionId: null, openMenu: null });
      } else if (action === 'delete-blueprint') {
        event.stopPropagation();
        await this.deleteBlueprint(id);
      } else if (action === 'delete-draft') {
        event.stopPropagation();
        await this.deleteDraft(id);
      } else if (action === 'delete-exam') {
        event.stopPropagation();
        await this.deleteExam(id);
      }
      else if (action === 'create-blueprint') await this.createDefaultBlueprint();
      else if (action === 'remove-blueprint-point') await this.removeBlueprintPoint(id, target.dataset.index);
      else if (action === 'add-plan-row') await this.addBlueprintPlanRow(id);
      else if (action === 'remove-plan-row') await this.removeBlueprintPlanRow(id, target.dataset.index);
      else if (action === 'confirm-blueprint') await this.confirmBlueprint(id);
      else if (action === 'generate-draft') await this.generateDraft(id);
      else if (action === 'select-draft') await this.selectDraft(id);
      else if (action === 'retry-question') {
        if (this.retryingQuestions.has(id)) return;
        await this.retryQuestion(target.dataset.draftId, id);
      }
      else if (action === 'open-question-revise') {
        if (this.revising || store.state.draftQuestionBusyId) return;
        store.setState({ draftQuestionEditId: id, draftQuestionPrompt: '', draftHandEditId: null });
        queueMicrotask(() => document.getElementById('question-revise-input')?.focus());
      } else if (action === 'toggle-question-edit') {
        store.setState({
          draftHandEditId: store.state.draftHandEditId === id ? null : id,
          draftQuestionEditId: null,
        });
      } else if (action === 'save-question-edit') await this.saveDraftQuestionEdit(target.dataset.draftId, id);
      else if (action === 'add-option') this.addDraftOption(id);
      else if (action === 'move-question') await this.moveDraftQuestion(target.dataset.draftId, id, Number(target.dataset.delta));
      else if (action === 'delete-question') await this.deleteDraftQuestion(target.dataset.draftId, id);
      else if (action === 'cancel-question-revise') {
        if (this.revising) return;
        store.setState({ draftQuestionEditId: null, draftQuestionPrompt: '' });
      } else if (action === 'revise-question') {
        if (this.revising || store.state.draftQuestionBusyId) return;
        await this.reviseDraftQuestion(id);
      }
      else if (action === 'publish-draft') await this.publishDraft(id);
      else if (action === 'apply-draft-proposal') {
        if (this.applyingProposal || store.state.draftProposalBusyId) return;
        await this.applyDraftProposal(id);
      }
      else if (action === 'discard-draft-proposal') await this.discardDraftProposal(id);
      else if (action === 'select-exam') await this.selectExam(id);
      else if (action === 'apply-exam-proposal') {
        if (this.applyingProposal || store.state.draftProposalBusyId) return;
        await this.applyExamProposal(id);
      }
      else if (action === 'discard-exam-proposal') await this.discardExamProposal(id);
      else if (action === 'undo-exam') await this.undoExam(id);
      else if (action === 'redo-exam') await this.redoExam(id);
      else if (action === 'restore-exam-version') await this.restoreExamVersion(id, target.dataset.versionId);
      else if (action === 'toggle-suggested-score') await this.toggleSuggestedScore(id);
      else if (action === 'print-exam') this.askExamEdition(id, 'print');
      else if (action === 'export-exam-pdf') this.askExamEdition(id, 'pdf');
      else if (action === 'export-exam-markdown') this.askExamEdition(id, 'markdown');
      else if (action === 'go-attempt') {
        const examId = id || store.state.activeExamId;
        store.setState({
          workspace: 'attempt',
          activeExamId: examId,
          activeAttempt: null,
          activeAttemptId: null,
          review: null,
          startAnotherOpen: false,
          mobilePane: { ...store.state.mobilePane, attempt: 'content' },
        });
        await this.loadExamAttempts(examId);
        await this.loadMissedQuestions();
      }
      else if (action === 'go-exam') store.setState({ workspace: 'exam', examTab: 'blueprint', mobilePane: { ...store.state.mobilePane, exam: 'ai' } });
      else if (action === 'focus-composer') this.focusComposer();
      else if (action === 'start-attempt') await this.startAttempt(id, target.dataset.mode);
      else if (action === 'start-another') store.setState({ startAnotherOpen: !store.state.startAnotherOpen });
      else if (action === 'open-attempt') await this.openAttempt(id);
      else if (action === 'complete-attempt') await this.completeAttempt(id);
      else if (action === 'continue-attempt') await this.continueAttempt(id);
      else if (action === 'grade-attempt') await this.gradeAttempt(id);
      else if (action === 'pause-attempt') await this.run('暂停失败', () => api.pauseAttempt(id), () => this.refreshAttempt(id));
      else if (action === 'resume-attempt') await this.run('恢复失败', () => api.resumeAttempt(id), () => this.refreshAttempt(id));
      else if (action === 'ask-feedback') await this.askFeedback(target.dataset.attemptId, id);
      else if (action === 'open-tool-resource') await this.openToolResource(target.dataset.type, id);
      else if (action === 'open-citation') {
        await this.openCitation({
          sourceId: target.dataset.sourceId,
          versionId: target.dataset.versionId,
          anchorId: target.dataset.anchorId,
          citationId: target.dataset.citationId,
        });
      }
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
      if (action === 'plan-count' || action === 'plan-score' || action === 'plan-type' || action === 'plan-difficulty') {
        const field = action === 'plan-count' ? 'count' : action === 'plan-score' ? 'score_each' : action === 'plan-type' ? 'type' : 'difficulty';
        await this.updateBlueprintPlan(id, index, field, target.value);
      } else if (action === 'plan-duration') {
        await this.updateBlueprintDuration(id, target.value);
      } else if (action === 'toggle-missed-point') {
        const point = target.dataset.point;
        const selected = new Set(store.state.missedSelectedPoints || []);
        if (target.checked) selected.add(point);
        else selected.delete(point);
        store.setState({ missedSelectedPoints: [...selected], missedSelectionReady: true });
      }
    } catch (err) {
      store.addToast(sanitizeErrorMessage(err.message), 'error');
    }
  }

  onFieldInput(event) {
    if (event.target.id === 'question-revise-input') {
      store.patch({ draftQuestionPrompt: event.target.value });
    }
  }

  onKeyDown(event) {
    if (this.handleMenuKeys(event)) return;
    if (event.key === 'Escape') {
      store.setState({
        openMenu: null,
        modal: null,
        draftQuestionEditId: null,
        draftHandEditId: null,
        draftQuestionPrompt: '',
        menuFocusIndex: -1,
      });
      return;
    }
    if (event.key === 'Enter' && event.target.id === 'question-revise-input') {
      event.preventDefault();
      if (this.revising || store.state.draftQuestionBusyId) return;
      this.reviseDraftQuestion(store.state.draftQuestionEditId).catch((err) => {
        store.addToast(sanitizeErrorMessage(err.message), 'error');
      });
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
    else if (action === 'delete-blueprint') await this.deleteBlueprintConfirmed(store.state.confirmBlueprintId);
    else if (action === 'delete-draft') await this.deleteDraftConfirmed(store.state.confirmDraftId);
    else if (action === 'delete-exam') await this.deleteExamConfirmed(store.state.confirmExamId);
    else if (action === 'publish-draft') await this.publishDraftConfirmed(store.state.confirmDraftId, true);
    else if (action === 'delete-question') await this.deleteDraftQuestionConfirmed(store.state.confirmDraftId, store.state.confirmQuestionId);
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
      missedQuestions: [],
      missedSelectedPoints: [],
      missedSelectionReady: false,
      groundingMode: defaultGroundingMode(sources, store.state.groundingBySubject[subjectId]),
    });
    if (store.state.activeSourceId) await this.loadSourceDetail(store.state.activeSourceId);
    if (store.state.activeAiDocumentId) await this.loadAiDocDetail(store.state.activeAiDocumentId);
    if (store.state.activeExamId) await this.loadExamDetail(store.state.activeExamId);
    await this.loadExamAttempts(store.state.activeExamId);
    await this.loadMissedQuestions();
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
        intervalMs: 500,
        maxIntervalMs: 500,
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

  async exportSubject() {
    if (!store.state.activeSubjectId) return;
    store.setState({ openMenu: null });
    try {
      await api.exportSubject(store.state.activeSubjectId);
    } catch (err) {
      store.addToast(err.message, 'error');
    }
  }

  async importSubject(file) {
    if (!file) return;
    store.setState({ openMenu: null });
    try {
      const subject = await api.importSubject(file);
      store.addToast('已导入', 'success');
      await this.bootstrap();
      if (subject?.id) await this.switchSubject(subject.id);
    } catch (err) {
      store.addToast(err.message, 'error');
    }
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

  async renameResource(kind, id, title) {
    if (kind === 'blueprint') {
      store.setState({ renamingBlueprintId: null });
      if (!id || !title) return;
      const updated = await api.updateBlueprint(id, { title });
      store.setState({
        blueprints: store.state.blueprints.map((item) => (item.id === id ? updated : item)),
      });
      return;
    }
    if (kind === 'exam') {
      store.setState({ renamingExamId: null });
      if (!id || !title) return;
      const updated = await api.updateExam(id, { title });
      store.setState({
        exams: store.state.exams.map((item) => (item.id === id ? { ...item, ...updated } : item)),
      });
    }
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
    if (command?.missingArgs) {
      store.addToast(command.def.argHint || `在 ${command.def.name} 后面写上具体要求`, 'error');
      return;
    }
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
    if (!store.activeModel() && !(def.run === 'parseBlueprint' && !args)) {
      return store.addToast('请先配置模型', 'error');
    }
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
            const blueprint = await this.parseBlueprint(args || this.defaultExamPrompt(), { useDefaults: !args });
            const title = blueprint?.title || '';
            const usedDefaults = (blueprint?.issues || []).some((issue) => issue.code === 'BLUEPRINT_USED_DEFAULTS');
            resultText = usedDefaults || !args
              ? `已生成蓝图「${title || '练习卷'}」。题型题量可在组卷区直接改，确认后再组题`
              : `已生成蓝图「${title || '未命名'}」，请在组卷区确认题型与总分`;
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
    payload.workspace_context = this.currentWorkspaceContext();

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
    const lastAssistant = [...(store.activeSession()?.messages || [])]
      .reverse()
      .find((item) => item.role === 'assistant');
    await this.refreshAfterToolEvents(lastAssistant?.tool_events);
    petNotify('chat');
  }

  currentWorkspaceContext() {
    const context = { workspace: store.state.workspace || 'learn' };
    if (store.state.activeBlueprintId) context.blueprint_id = store.state.activeBlueprintId;
    if (store.state.activeDraftId) context.draft_id = store.state.activeDraftId;
    if (store.state.activeExamId) context.exam_id = store.state.activeExamId;
    if (store.state.activeAiDocumentId) context.ai_document_id = store.state.activeAiDocumentId;
    if (store.state.activeAttemptId) context.attempt_id = store.state.activeAttemptId;
    return context;
  }

  async refreshAfterToolEvents(events) {
    const types = new Set((events || []).map((item) => item.resource?.type).filter(Boolean));
    if (!types.size || !store.state.activeSubjectId) return;
    if (types.has('exam-blueprint')) {
      const data = await api.listBlueprints(store.state.activeSubjectId);
      store.setState({ blueprints: data.items || [] });
    }
    if (types.has('draft-revision-proposal') || types.has('exam-draft')) {
      const data = await api.listDrafts(store.state.activeSubjectId);
      store.setState({ drafts: data.items || [] });
      if (store.state.activeDraftId) await this.loadDraftProposals(store.state.activeDraftId);
    }
    if (types.has('revision-proposal') || types.has('exam')) {
      const data = await api.listExams(store.state.activeSubjectId);
      store.setState({ exams: data.items || [] });
      if (store.state.activeExamId) await this.loadExamDetail(store.state.activeExamId);
    }
    if (types.has('ai-document') || types.has('ai-document-proposal')) {
      const data = await api.listAiDocuments(store.state.activeSubjectId);
      store.setState({ aiDocuments: data.items || [] });
      if (store.state.activeAiDocumentId) await this.loadAiDocDetail(store.state.activeAiDocumentId);
    }
  }

  async openToolResource(type, id) {
    if (!type || !id) return;
    const examContent = { ...store.state.mobilePane, exam: 'content' };
    const sourcesContent = { ...store.state.mobilePane, sources: 'content' };
    if (type === 'exam-blueprint') {
      store.setState({ workspace: 'exam', examTab: 'blueprint', mobilePane: examContent });
      await this.selectBlueprint(id);
      return;
    }
    if (type === 'draft-revision-proposal' || type === 'exam-draft') {
      store.setState({ workspace: 'exam', examTab: 'draft', mobilePane: examContent });
      if (type === 'exam-draft') {
        await this.selectDraft(id);
        return;
      }
      const data = await api.listDrafts(store.state.activeSubjectId);
      store.setState({ drafts: data.items || [] });
      const draftId = store.state.activeDraftId || data.items?.[0]?.id;
      if (draftId) await this.selectDraft(draftId);
      return;
    }
    if (type === 'revision-proposal' || type === 'exam') {
      store.setState({ workspace: 'exam', examTab: 'exam', mobilePane: examContent });
      if (type === 'exam') {
        await this.selectExam(id);
        return;
      }
      if (store.state.activeExamId) await this.loadExamDetail(store.state.activeExamId);
      return;
    }
    if (type === 'ai-document' || type === 'ai-document-proposal') {
      store.setState({ workspace: 'sources', sourceKind: 'docs', mobilePane: sourcesContent });
      if (type === 'ai-document') {
        await this.selectAiDoc(id);
        return;
      }
      if (store.state.activeAiDocumentId) await this.loadAiDocDetail(store.state.activeAiDocumentId);
      return;
    }
    if (type === 'attempt') {
      store.setState({
        workspace: 'attempt',
        activeAttemptId: id,
        mobilePane: { ...store.state.mobilePane, attempt: 'content' },
      });
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

  defaultExamPrompt() {
    const name = store.activeSubject()?.name;
    return name ? `出一套${name}练习卷` : '出一套练习卷';
  }

  async createDefaultBlueprint() {
    store.setState({ examTab: 'blueprint', workspace: 'exam', mobilePane: { ...store.state.mobilePane, exam: 'content' } });
    await this.parseBlueprint(this.defaultExamPrompt(), { useDefaults: true });
  }

  async parseBlueprint(prompt, options = {}) {
    const accepted = await api.parseBlueprint(store.state.activeSubjectId, {
      prompt: prompt || this.defaultExamPrompt(),
      grounding_mode: store.state.groundingMode,
      source_version_ids: readySourceVersionIds(store.state.sources),
      model_id: store.state.currentModelId,
      use_defaults: !!options.useDefaults,
    });
    store.trackOperation(accepted.operation);
    store.setState({ examTab: 'blueprint', workspace: 'exam', mobilePane: { ...store.state.mobilePane, exam: 'content' } });
    const done = await api.pollOperation(accepted.operation.id, { onProgress: (op) => store.trackOperation(op) });
    store.trackOperation(done);
    const data = await api.listBlueprints(store.state.activeSubjectId);
    const id = accepted.resource?.id || data.items?.[0]?.id;
    store.setState({ blueprints: data.items || [], activeBlueprintId: id || null });
    const blueprint = (data.items || []).find((item) => item.id === id) || null;
    const usedDefaults = (blueprint?.issues || []).some((issue) => issue.code === 'BLUEPRINT_USED_DEFAULTS');
    store.addToast(usedDefaults ? '已用默认题型生成蓝图，可改题量和分值' : '蓝图已生成', 'success');
    return blueprint;
  }

  async proposeDraftEdit(instruction, scope) {
    const draft = store.activeDraft();
    if (!draft) throw new Error('请先选择一份草稿或试卷');
    const accepted = await api.createDraftRevisionProposal(draft.id, {
      instruction,
      scope: scope || { kind: 'whole-exam', question_ids: [], block_ids: [] },
      model_id: store.state.currentModelId,
    });
    store.trackOperation(accepted.operation);
    await api.pollOperation(accepted.operation.id, { onProgress: (op) => store.trackOperation(op) });
    await this.loadDraftProposals(draft.id);
    store.setState({
      examTab: 'draft',
      workspace: 'exam',
      mobilePane: { ...store.state.mobilePane, exam: 'content' },
      draftQuestionEditId: null,
      draftQuestionPrompt: '',
    });
    store.addToast('修改预览已就绪', 'success');
  }

  async reviseDraftQuestion(questionId) {
    if (this.revising) return;
    const instruction = (document.getElementById('question-revise-input')?.value || store.state.draftQuestionPrompt || '').trim();
    if (!questionId) return;
    if (!instruction) return store.addToast('请填写修改要求', 'error');
    this.revising = true;
    store.setState({
      draftQuestionBusyId: questionId,
      draftQuestionEditId: null,
      draftQuestionPrompt: '',
    });
    try {
      await this.proposeDraftEdit(instruction, {
        kind: 'questions',
        question_ids: [questionId],
        block_ids: [],
      });
    } finally {
      this.revising = false;
      store.setState({ draftQuestionBusyId: null });
    }
  }

  async loadDraftProposals(draftId) {
    const proposals = await api.listDraftRevisionProposals(draftId);
    store.setState({ draftProposals: proposals.items || [] });
  }

  async applyDraftProposal(proposalId) {
    if (this.applyingProposal) return;
    this.applyingProposal = true;
    store.setState({ draftProposalBusyId: proposalId });
    try {
      await api.applyDraftRevisionProposal(proposalId);
      const draftId = store.state.activeDraftId;
      if (draftId) {
        await this.selectDraft(draftId);
        await this.loadDraftProposals(draftId);
      }
      store.addToast('已应用修改', 'success');
    } finally {
      this.applyingProposal = false;
      store.setState({ draftProposalBusyId: null });
    }
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
    store.setState({ activeSourceId: sourceId, sourceKind: 'files', sourceViewVersionId: null });
    await this.loadSourceDetail(sourceId);
  }

  async loadSourceDetail(sourceId, versionId = null, { required = false } = {}) {
    const source = await api.getSource(sourceId);
    const targetVersionId = versionId || source.current_version?.id;
    let anchorsRes = { items: [] };
    try {
      if (targetVersionId) {
        anchorsRes = await api.listSourceVersionAnchors(targetVersionId);
      }
    } catch (err) {
      if (required && (err.status === 410 || err.code === 'SOURCE_UNAVAILABLE')) throw err;
      anchorsRes = { items: [] };
    }
    const versionsRes = await api.listSourceVersions(sourceId).catch(() => ({ items: [] }));
    const sources = store.state.sources.some((item) => item.id === sourceId)
      ? store.state.sources.map((item) => (item.id === sourceId ? source : item))
      : [...store.state.sources, source];
    store.setState({
      sources,
      activeSourceId: sourceId,
      sourceAnchors: anchorsRes.items || [],
      sourceVersions: versionsRes.items || [],
      sourceViewVersionId: targetVersionId || null,
    });
  }

  async openCitation({ sourceId, versionId, anchorId, citationId } = {}) {
    try {
      if ((!sourceId || !versionId || !anchorId) && citationId) {
        const citation = await api.getCitation(citationId);
        if (citation.available === false) {
          store.addToast('资料已不可用', 'error');
          return;
        }
        sourceId = citation.source_id;
        versionId = citation.source_version_id;
        anchorId = citation.anchor_id;
      }
      if (!sourceId || !versionId || !anchorId) return;
      const isAiDoc = store.state.aiDocuments.some((item) => item.id === sourceId);
      if (isAiDoc) {
        store.setState({
          workspace: 'sources',
          sourceKind: 'docs',
          mobilePane: { ...store.state.mobilePane, sources: 'content' },
          openMenu: null,
        });
        await this.selectAiDoc(sourceId);
        return;
      }
      await this.loadSourceDetail(sourceId, versionId, { required: true });
      store.setState({
        workspace: 'sources',
        sourceKind: 'files',
        mobilePane: { ...store.state.mobilePane, sources: 'content' },
        openMenu: null,
      });
      this.highlightCitedAnchor(anchorId);
    } catch (err) {
      if (err.status === 410 || err.code === 'SOURCE_UNAVAILABLE') {
        store.addToast('资料已不可用', 'error');
        return;
      }
      throw err;
    }
  }

  highlightCitedAnchor(anchorId) {
    if (this.citeHighlightTimer) window.clearTimeout(this.citeHighlightTimer);
    const apply = () => {
      const node = document.getElementById(`anchor-${anchorId}`);
      if (!node) return;
      node.scrollIntoView({ block: 'center' });
      node.classList.add('is-cited');
      this.citeHighlightTimer = window.setTimeout(() => node.classList.remove('is-cited'), 2000);
    };
    queueMicrotask(apply);
    window.setTimeout(apply, 50);
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
    const sources = data.items || [];
    store.setState({
      sources,
      activeSourceId: sources[0]?.id || null,
      sourceKind: 'files',
      groundingMode: defaultGroundingMode(sources, store.state.groundingBySubject[store.state.activeSubjectId]),
    });
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
    const sources = data.items || [];
    store.setState({
      sources,
      activeSourceId: sources[0]?.id || null,
      sourceAnchors: [],
      sourceVersions: [],
      groundingMode: defaultGroundingMode(sources, store.state.groundingBySubject[store.state.activeSubjectId]),
    });
  }

  async selectAiDoc(docId) {
    store.setState({ activeAiDocumentId: docId, sourceKind: 'docs', aiDocumentViewVersionId: null });
    await this.loadAiDocDetail(docId);
  }

  reviseCurrentAiDocument() {
    this.focusComposer();
    const text = store.state.composerText.trim();
    if (!text.startsWith('/改文档')) store.setState({ composerText: text ? `/改文档 ${text}` : '/改文档 ' });
  }

  async restoreAiDocumentVersion(documentId, versionId) {
    await api.restoreAiDocumentVersion(documentId, versionId);
    store.setState({ aiDocumentViewVersionId: null });
    await this.loadAiDocDetail(documentId);
    store.addToast('已恢复版本', 'success');
  }

  async openRuns() {
    store.setState({ modal: 'runs', openMenu: null });
    try {
      const [runs, suites] = await Promise.all([
        api.listOrchestrationRuns({ subject_id: store.state.activeSubjectId || undefined }),
        api.listEvaluationSuites().catch(() => ({ items: [] })),
      ]);
      store.setState({
        orchestrationRuns: runs.items || [],
        evaluationSuites: suites.items || [],
      });
    } catch (err) {
      store.addToast(sanitizeErrorMessage(err.message), 'error');
    }
  }

  async runEvaluation(suiteId) {
    const modelId = store.state.currentModelId;
    if (!modelId) return store.addToast('请先配置模型', 'error');
    store.setState({ runsBusy: suiteId });
    try {
      const accepted = await api.runEvaluationSuite(suiteId, { model_id: modelId });
      store.trackOperation(accepted.operation);
      await api.pollOperation(accepted.operation.id, { onProgress: (op) => store.trackOperation(op) });
      const runId = accepted.resource?.id || accepted.operation?.resource?.id;
      const evaluation = runId ? await api.getEvaluationRun(runId) : null;
      const runs = await api.listOrchestrationRuns({ subject_id: store.state.activeSubjectId || undefined });
      store.setState({
        evaluationRun: evaluation,
        orchestrationRuns: runs.items || [],
        runsBusy: null,
      });
      store.addToast('评估完成', 'success');
    } catch (err) {
      store.setState({ runsBusy: null });
      store.addToast(sanitizeErrorMessage(err.message), 'error');
    }
  }

  handleMenuKeys(event) {
    if (!store.state.openMenu) return false;
    if (!['ArrowDown', 'ArrowUp', 'Enter', 'Home', 'End'].includes(event.key)) return false;
    const menu = document.querySelector('.menu[role="menu"]');
    if (!menu) return false;
    const items = [...menu.querySelectorAll('.menu-item:not([disabled])')];
    if (!items.length) return false;
    event.preventDefault();
    let index = store.state.menuFocusIndex;
    if (event.key === 'ArrowDown') index = index < 0 ? 0 : (index + 1) % items.length;
    else if (event.key === 'ArrowUp') index = index <= 0 ? items.length - 1 : index - 1;
    else if (event.key === 'Home') index = 0;
    else if (event.key === 'End') index = items.length - 1;
    else if (event.key === 'Enter' && index >= 0) {
      items[index]?.click();
      return true;
    }
    store.setState({ menuFocusIndex: index });
    return true;
  }

  highlightMenuFocus() {
    if (!store.state.openMenu) return;
    const menu = document.querySelector('.menu[role="menu"]');
    if (!menu) return;
    const items = [...menu.querySelectorAll('.menu-item:not([disabled])')];
    items.forEach((item, index) => item.classList.toggle('is-focused', index === store.state.menuFocusIndex));
    items[store.state.menuFocusIndex]?.scrollIntoView({ block: 'nearest' });
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
      renamingBlueprintId: null,
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

  async deleteBlueprint(id) {
    store.setState({ confirmBlueprintId: id });
    this.askConfirm({
      title: '删除蓝图',
      message: '将删除这份蓝图。没有需要一并删除的关联对象。',
      ok: '删除',
      action: 'delete-blueprint',
    });
  }

  async deleteBlueprintConfirmed(id) {
    if (!id) return;
    try {
      await api.deleteBlueprint(id);
      const data = await api.listBlueprints(store.state.activeSubjectId);
      const items = data.items || [];
      const nextId = items.find((item) => item.id === store.state.activeBlueprintId && item.id !== id)?.id || items[0]?.id || null;
      store.setState({ blueprints: items, activeBlueprintId: nextId });
      if (nextId) await this.selectBlueprint(nextId);
      store.addToast('蓝图已删除');
    } catch (err) {
      store.addToast(sanitizeErrorMessage(err.message), 'error');
    }
  }

  async deleteDraft(id) {
    const draft = store.state.drafts.find((item) => item.id === id) || await api.getDraft(id);
    const proposals = await api.listDraftRevisionProposals(id).catch(() => ({ items: [] }));
    store.setState({ confirmDraftId: id });
    this.askConfirm({
      title: '删除草稿',
      message: `将删除这份草稿。题目 ${(draft.questions || []).length} 道，修改提案 ${(proposals.items || []).length} 份。`,
      ok: '删除',
      action: 'delete-draft',
    });
  }

  async deleteDraftConfirmed(id) {
    if (!id) return;
    try {
      await api.deleteDraft(id);
      const data = await api.listDrafts(store.state.activeSubjectId);
      const items = data.items || [];
      const nextId = items.find((item) => item.id === store.state.activeDraftId && item.id !== id)?.id || items[0]?.id || null;
      store.setState({ drafts: items, activeDraftId: nextId, draftProposals: [] });
      if (nextId) await this.selectDraft(nextId);
      store.addToast('草稿已删除');
    } catch (err) {
      store.addToast(sanitizeErrorMessage(err.message), 'error');
    }
  }

  async deleteExam(id) {
    const [versions, proposals, attempts] = await Promise.all([
      api.listExamVersions(id),
      api.listRevisionProposals(id),
      api.listExamAttempts(id),
    ]);
    store.setState({ confirmExamId: id });
    this.askConfirm({
      title: '删除试卷',
      message: `将删除这份试卷。版本 ${(versions.items || []).length} 个，修改提案 ${(proposals.items || []).length} 份，作答 ${(attempts.items || []).length} 份。`,
      ok: '删除',
      action: 'delete-exam',
    });
  }

  async deleteExamConfirmed(id) {
    if (!id) return;
    try {
      await api.deleteExam(id);
      const data = await api.listExams(store.state.activeSubjectId);
      const items = data.items || [];
      const nextId = items.find((item) => item.id !== id)?.id || null;
      store.setState({
        exams: items,
        activeExamId: nextId,
        examProposals: [],
        examAttempts: [],
        activeAttempt: null,
        activeAttemptId: null,
        review: null,
      });
      if (nextId) await this.loadExamDetail(nextId);
      if (store.state.workspace === 'attempt') await this.loadExamAttempts(nextId);
      store.addToast('试卷已删除');
    } catch (err) {
      store.addToast(sanitizeErrorMessage(err.message), 'error');
    }
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
      draftQuestionEditId: id === store.state.activeDraftId ? store.state.draftQuestionEditId : null,
      draftHandEditId: id === store.state.activeDraftId ? store.state.draftHandEditId : null,
      draftQuestionPrompt: id === store.state.activeDraftId ? store.state.draftQuestionPrompt : '',
    });
    await this.loadDraftProposals(id).catch(() => store.setState({ draftProposals: [] }));
    this.watchDraft();
  }

  async updateBlueprintPlan(blueprintId, index, field, rawValue) {
    const current = store.state.blueprints.find((item) => item.id === blueprintId);
    if (!current || current.status !== 'draft') return;
    const plan = (current.question_plan || []).map((row) => ({ ...row }));
    if (!plan[index]) return;
    if (field === 'type' || field === 'difficulty') {
      plan[index][field] = rawValue;
    } else {
      const value = Number(rawValue);
      if (!Number.isFinite(value) || value <= 0) return;
      plan[index][field] = field === 'count' ? Math.max(1, Math.round(value)) : value;
    }
    const total = plan.reduce((sum, row) => sum + row.count * row.score_each, 0);
    await this.commitBlueprint(blueprintId, { question_plan: plan, total_score: total });
  }

  async updateBlueprintDuration(blueprintId, rawValue) {
    const current = store.state.blueprints.find((item) => item.id === blueprintId);
    if (!current || current.status !== 'draft') return;
    const trimmed = String(rawValue || '').trim();
    const duration = trimmed === '' ? null : Number(trimmed);
    if (duration != null && (!Number.isFinite(duration) || duration < 1)) return;
    await this.commitBlueprint(blueprintId, { duration_minutes: duration });
  }

  async addBlueprintPlanRow(blueprintId) {
    const current = store.state.blueprints.find((item) => item.id === blueprintId);
    if (!current || current.status !== 'draft') return;
    const plan = [...(current.question_plan || []), { type: 'single-choice', count: 2, difficulty: 'medium', score_each: 2 }];
    const total = plan.reduce((sum, row) => sum + row.count * row.score_each, 0);
    await this.commitBlueprint(blueprintId, { question_plan: plan, total_score: total });
  }

  async removeBlueprintPlanRow(blueprintId, index) {
    const current = store.state.blueprints.find((item) => item.id === blueprintId);
    if (!current || current.status !== 'draft') return;
    const plan = (current.question_plan || []).filter((_, rowIndex) => rowIndex !== Number(index));
    if (!plan.length) return;
    const total = plan.reduce((sum, row) => sum + row.count * row.score_each, 0);
    await this.commitBlueprint(blueprintId, { question_plan: plan, total_score: total });
  }

  async commitBlueprint(blueprintId, patch) {
    await api.updateBlueprint(blueprintId, patch);
    const detail = await api.getBlueprint(blueprintId);
    store.setState({
      blueprints: store.state.blueprints.map((item) => (item.id === blueprintId ? detail : item)),
    });
  }

  async saveDraftQuestionEdit(draftId, questionId) {
    const form = document.querySelector(`[data-question-edit="${questionId}"]`);
    const draft = store.state.drafts.find((item) => item.id === draftId);
    const slot = draft?.questions?.find((item) => item.id === questionId);
    if (!form || !slot?.question) return;
    const payload = questionFromEditor(slot.question, form);
    await api.replaceDraftQuestion(draftId, questionId, payload);
    store.setState({ draftHandEditId: null });
    await this.selectDraft(draftId);
    store.addToast('已保存', 'success');
  }

  addDraftOption(slotId) {
    const form = document.querySelector(`[data-question-edit="${slotId}"]`);
    const drafts = store.state.drafts.map((draft) => {
      if (draft.id !== store.state.activeDraftId) return draft;
      return {
        ...draft,
        questions: (draft.questions || []).map((slot) => {
          if (slot.id !== slotId || !slot.question) return slot;
          const question = form ? questionFromEditor(slot.question, form) : slot.question;
          const options = [...(question.options || [])];
          const id = nextOptionId(options);
          options.push({ id, content: textToMarkdownBlocks('') });
          return { ...slot, question: { ...question, options } };
        }),
      };
    });
    store.setState({ drafts });
  }

  async moveDraftQuestion(draftId, questionId, delta) {
    const draft = store.state.drafts.find((item) => item.id === draftId);
    const ids = (draft?.questions || []).map((item) => item.id);
    const index = ids.indexOf(questionId);
    const next = index + delta;
    if (index < 0 || next < 0 || next >= ids.length) return;
    [ids[index], ids[next]] = [ids[next], ids[index]];
    await api.updateDraft(draftId, { question_order: ids });
    await this.selectDraft(draftId);
  }

  async deleteDraftQuestion(draftId, questionId) {
    store.setState({ confirmDraftId: draftId, confirmQuestionId: questionId });
    this.askConfirm({
      title: '删题',
      message: '将从这份草稿删除这道题。',
      ok: '删除',
      action: 'delete-question',
    });
  }

  async deleteDraftQuestionConfirmed(draftId, questionId) {
    if (!draftId || !questionId) return;
    await api.deleteDraftQuestion(draftId, questionId);
    store.setState({ draftHandEditId: null, confirmDraftId: null, confirmQuestionId: null });
    await this.selectDraft(draftId);
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
    }, 500);
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
        const sources = data.items || [];
        store.setState({
          sources,
          groundingMode: defaultGroundingMode(sources, store.state.groundingBySubject[store.state.activeSubjectId]),
        });
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
    if (this.retryingQuestions.has(questionId)) return;
    this.retryingQuestions.add(questionId);
    store.setState({ retryingQuestionId: questionId });
    try {
      const accepted = await api.retryDraftQuestion(draftId, questionId);
      store.trackOperation(accepted.operation);
      await api.pollOperation(accepted.operation.id, { onProgress: (op) => store.trackOperation(op) });
      await this.selectDraft(draftId);
    } finally {
      this.retryingQuestions.delete(questionId);
      if (store.state.retryingQuestionId === questionId) store.setState({ retryingQuestionId: null });
    }
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
    petNotify('exam-published');
  }

  async selectExam(id) {
    store.setState({
      activeExamId: id,
      renamingExamId: null,
      startAnotherOpen: false,
      activeAttempt: store.state.workspace === 'attempt' ? null : store.state.activeAttempt,
      activeAttemptId: store.state.workspace === 'attempt' ? null : store.state.activeAttemptId,
      review: store.state.workspace === 'attempt' ? null : store.state.review,
    });
    await this.loadExamDetail(id);
    if (store.state.workspace === 'attempt') await this.loadExamAttempts(id);
  }

  async loadExamDetail(examId) {
    const [exam, proposals, versions] = await Promise.all([
      api.getExam(examId),
      api.listRevisionProposals(examId),
      api.listExamVersions(examId).catch(() => ({ items: [] })),
    ]);
    store.setState({
      exams: store.state.exams.map((item) => (item.id === examId ? exam : item)),
      examProposals: proposals.items || [],
      examVersions: versions.items || [],
    });
  }

  async applyExamProposal(id) {
    if (this.applyingProposal) return;
    this.applyingProposal = true;
    store.setState({ draftProposalBusyId: id });
    try {
      await api.applyRevisionProposal(id);
      await this.loadExamDetail(store.state.activeExamId);
      store.addToast('已应用', 'success');
    } finally {
      this.applyingProposal = false;
      store.setState({ draftProposalBusyId: null });
    }
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

  async restoreExamVersion(examId, versionId) {
    const exam = store.state.exams.find((item) => item.id === examId);
    if (!versionId || versionId === exam?.current_version_id) return;
    await api.restoreExamVersion(examId, versionId);
    await this.loadExamDetail(examId);
    store.addToast('已恢复版本', 'success');
  }

  async toggleSuggestedScore(attemptId) {
    const attempt = store.state.activeAttempt;
    if (!attempt || attempt.id !== attemptId) return;
    const updated = await api.updateAttempt(attemptId, { show_suggested_score: !attempt.show_suggested_score });
    store.setState({ activeAttempt: updated });
  }

  async expireExamAttempt() {
    const attempt = store.state.activeAttempt;
    if (!attempt || this.expiringAttempt || attempt.completion_status === 'completed') return;
    const exam = store.state.exams.find((item) => item.id === attempt.exam_id);
    const minutes = examDurationMinutes(exam, store.state.blueprints);
    const remaining = attemptRemainingMs(attempt, attemptLimitMs(minutes));
    if (remaining !== 0) return;
    this.expiringAttempt = true;
    try {
      await this.completeAttempt(attempt.id, { timedOut: true });
    } catch (err) {
      store.addToast(sanitizeErrorMessage(err.message), 'error');
    } finally {
      this.expiringAttempt = false;
    }
  }

  askExamEdition(examId, action) {
    const titles = { print: '打印', pdf: '导出 PDF', markdown: '导出 Markdown' };
    store.setState({
      modal: 'exam-edition',
      examEdition: 'questions',
      examEditionAction: action,
      examEditionExamId: examId,
      examEditionTitle: titles[action] || '选择版别',
      openMenu: null,
    });
  }

  async confirmExamEdition(edition) {
    const action = store.state.examEditionAction;
    const examId = store.state.examEditionExamId;
    const resolved = edition === 'solutions' ? 'solutions' : 'questions';
    store.setState({
      modal: null,
      examEditionAction: null,
      examEditionExamId: null,
      examEditionTitle: '',
      examEdition: 'questions',
    });
    if (!examId) return;
    try {
      if (action === 'print') await this.printExam(examId, resolved);
      else if (action === 'pdf') await this.exportExam(examId, 'pdf', resolved);
      else if (action === 'markdown') await this.exportExam(examId, 'markdown', resolved);
    } catch (err) {
      store.addToast(sanitizeErrorMessage(err.message), 'error');
    }
  }

  async printExam(examId, edition) {
    const doc = await api.getExamRenderDocument(examId, edition);
    const iframe = document.createElement('iframe');
    iframe.setAttribute('title', '打印');
    iframe.setAttribute('aria-hidden', 'true');
    iframe.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;';
    document.body.appendChild(iframe);
    const popup = iframe.contentWindow;
    if (!popup) {
      iframe.remove();
      store.addToast('无法打开打印预览', 'error');
      return;
    }
    popup.document.write(`<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>${escapeHtml(doc.title || '试卷')}</title>
    <link rel="stylesheet" href="/vendor/fonts/fonts.css" />
    <link rel="stylesheet" href="/styles.css" />
    <link rel="stylesheet" href="/vendor/katex/katex.min.css" />
  </head>
  <body data-theme="${escapeHtml(store.state.theme || 'paper')}">${renderExamPrintDocument(doc)}</body>
</html>`);
    popup.document.close();
    let printed = false;
    const triggerPrint = () => {
      if (printed) return;
      printed = true;
      popup.focus();
      popup.print();
      setTimeout(() => iframe.remove(), 1000);
    };
    const links = [...popup.document.querySelectorAll('link[rel="stylesheet"]')];
    if (!links.length) {
      triggerPrint();
      return;
    }
    let remaining = links.length;
    const done = () => {
      remaining -= 1;
      if (remaining <= 0) triggerPrint();
    };
    links.forEach((link) => {
      link.addEventListener('load', done, { once: true });
      link.addEventListener('error', done, { once: true });
    });
    setTimeout(triggerPrint, 1500);
  }

  async exportExam(examId, format, edition) {
    store.addToast('正在导出');
    const accepted = await api.createExamExport(examId, { format, edition });
    store.trackOperation(accepted.operation);
    await api.pollOperation(accepted.operation.id, { onProgress: (op) => store.trackOperation(op) });
    const exportId = accepted.resource?.id || accepted.operation?.resource?.id;
    if (!exportId) throw new Error('导出已完成，但没有文件');
    await api.getExamExport(exportId);
    await api.downloadExamExport(exportId);
    store.addToast('已导出', 'success');
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
    const attempt = await api.createAttempt(examId, { mode, show_suggested_score: false });
    store.setState({
      activeExamId: examId,
      startAnotherOpen: false,
      mobilePane: { ...store.state.mobilePane, attempt: 'content' },
    });
    await this.refreshAttempt(attempt.id);
    await this.loadExamAttempts(examId);
  }

  async openAttempt(attemptId) {
    store.setState({ startAnotherOpen: false, mobilePane: { ...store.state.mobilePane, attempt: 'content' } });
    await this.refreshAttempt(attemptId);
  }

  async loadMissedQuestions() {
    if (!store.state.activeSubjectId) {
      store.setState({ missedQuestions: [] });
      return;
    }
    try {
      const data = await api.listMissedQuestions(store.state.activeSubjectId);
      const items = data.items || [];
      const available = new Set(items.map((item) => item.knowledge_point));
      let selected = store.state.missedSelectedPoints || [];
      if (!store.state.missedSelectionReady) {
        selected = items.slice(0, 5).map((item) => item.knowledge_point);
      } else {
        selected = selected.filter((point) => available.has(point));
      }
      store.setState({ missedQuestions: items, missedSelectedPoints: selected });
    } catch {
      store.setState({ missedQuestions: [] });
    }
  }

  async openMissedQuestion(attemptId, questionId) {
    store.setState({ attemptTab: 'exams' });
    await this.openAttempt(attemptId);
    const apply = () => {
      const escaped = typeof CSS !== 'undefined' && CSS.escape ? CSS.escape(questionId || '') : questionId;
      const node = document.querySelector(`[data-question-id="${escaped}"]`);
      node?.scrollIntoView({ block: 'center' });
    };
    queueMicrotask(apply);
    window.setTimeout(apply, 50);
  }

  async practiceMissedSet() {
    const selected = store.state.missedSelectedPoints || [];
    if (!selected.length) {
      store.addToast('请先选择考点', 'error');
      return;
    }
    const prompt = `针对以下薄弱考点出一套复习卷：${selected.join('、')}`;
    store.setState({ workspace: 'exam', examTab: 'blueprint', mobilePane: { ...store.state.mobilePane, exam: 'content' } });
    await this.parseBlueprint(prompt);
  }

  async loadExamAttempts(examId) {
    if (!examId) {
      store.setState({ examAttempts: [], activeAttempt: null, activeAttemptId: null, review: null });
      return;
    }
    try {
      const data = await api.listExamAttempts(examId);
      store.setState({ examAttempts: data.items || [] });
    } catch {
      store.setState({ examAttempts: [] });
    }
  }

  async saveAnswer(attemptId, questionId, answer) {
    try {
      await api.saveAttemptAnswer(attemptId, questionId, answer);
      await this.refreshAttempt(attemptId);
    } catch (err) {
      store.addToast(err.message, 'error');
    }
  }

  async completeAttempt(id, { timedOut = false } = {}) {
    await api.completeAttempt(id);
    await this.refreshAttempt(id);
    store.addToast(timedOut ? '时间到，已完成作答' : '已完成作答', 'success');
    petNotify('attempt-completed');
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
    petNotify('attempt-completed');
  }

  async askFeedback(attemptId, questionId) {
    const accepted = await api.requestQuestionFeedback(attemptId, questionId, { model_id: store.state.currentModelId });
    store.trackOperation(accepted.operation);
    await api.pollOperation(accepted.operation.id, { onProgress: (op) => store.trackOperation(op) });
    await this.refreshAttempt(attemptId);
    const feedback = (store.state.activeAttempt?.feedback || []).find((item) => item.question_id === questionId);
    petNotify(feedback?.correct === true ? 'correct' : 'feedback');
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

function boot() {
  new App().init();
}

if (document.readyState === 'loading') {
  window.addEventListener('DOMContentLoaded', boot, { once: true });
} else {
  boot();
}
