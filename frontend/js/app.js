/**
 * Main Application Orchestrator for Learning Loop Agent
 * Strictly aligned with Tickets 03–22:
 * 4+1 Information Architecture, real contract alignment, complete error/loading states,
 * and reliable asynchronous flows. Strictly ZERO emojis throughout.
 */

import { api } from './api.js';
import { store } from './state.js';
import { renderNavbar } from './components/navbar.js';
import { renderChatView } from './components/chat_view.js';
import { renderSourcesView } from './components/sources_view.js';
import { renderExamStudioView } from './components/exam_studio_view.js';
import { renderPracticeExamView } from './components/practice_exam_view.js';
import { renderSettingsDevView } from './components/settings_dev_view.js';
import { renderModals } from './components/modals.js';
import { renderCommandPalette } from './components/command_palette.js';
import { renderToasts } from './components/toast.js';

class App {
  constructor() {
    this.root = document.getElementById('app');
    this.timerInterval = null;
  }

  async init() {
    this.renderAppShell();
    this.setupGlobalShortcuts();

    // Subscribe store to trigger re-renders
    store.subscribe((state) => this.render(state));

    // Load initial workspace, models, eval suites
    await this.loadInitialData();
    this.startAttemptTimer();
  }

  renderAppShell() {
    this.root.innerHTML = `
      <div class="app-shell" data-testid="app-shell">
        <div id="navbar-root"></div>
        <main class="main-workspace-container" id="main-workspace-root" role="main"></main>
        <div id="modal-root"></div>
        <div id="cmd-root"></div>
        <div id="toast-root"></div>
      </div>
    `;

    // Apply active theme
    const theme = store.getState().theme || 'paper';
    document.documentElement.setAttribute('data-theme', theme);
  }

  async loadInitialData() {
    try {
      const [workspace, modelsList, currentModelRes, evalSuites] = await Promise.all([
        api.getWorkspace().catch(() => ({ subjects: [], active_subject_id: null })),
        api.listModels().catch(() => ({ items: [] })),
        api.getCurrentModel().catch(() => null),
        api.listEvaluationSuites().catch(() => ({ items: [] }))
      ]);

      const subjects = workspace.subjects || [];
      const activeId = workspace.active_subject_id || (subjects[0] ? subjects[0].id : null);
      const models = modelsList.items || [];
      const currentModelId = currentModelRes?.model_id || (models[0] ? models[0].id : null);

      store.setState({
        workspace,
        activeSubjectId: activeId,
        models,
        currentModelId,
        evaluationSuites: evalSuites.items || []
      });

      if (activeId) {
        await this.loadSubjectData(activeId);
      }
    } catch (err) {
      console.error('Failed to load initial data:', err);
      store.addToast('加载初始数据失败: ' + err.message, 'error');
    }
  }

  async loadSubjectData(subjectId) {
    if (!subjectId) return;

    try {
      const [
        sessionsData,
        chatData,
        sourcesData,
        aiDocsData,
        blueprintsData,
        draftsData,
        examsData,
        runsData
      ] = await Promise.all([
        api.listSessions(subjectId).catch(() => ({ items: [] })),
        api.getChat(subjectId).catch(() => ({ messages: [], grounding_mode: 'general-knowledge', learning_mode: 'chat', active_model_id: null })),
        api.listSources(subjectId).catch(() => ({ items: [] })),
        api.listAiDocuments(subjectId).catch(() => ({ items: [] })),
        api.listBlueprints(subjectId).catch(() => ({ items: [] })),
        api.listDrafts(subjectId).catch(() => ({ items: [] })),
        api.listExams(subjectId).catch(() => ({ items: [] })),
        api.listOrchestrationRuns().catch(() => ({ items: [] }))
      ]);

      const sessions = sessionsData.items || [];
      const sources = sourcesData.items || [];
      const aiDocs = aiDocsData.items || [];
      const blueprints = blueprintsData.items || [];
      const drafts = draftsData.items || [];
      const exams = examsData.items || [];
      const runs = runsData.items || [];

      // Find active session
      const activeSession = sessions[0] || null;
      const activeSessionId = activeSession?.id || null;

      store.setState({
        sessions,
        activeSessionId,
        activeSession,
        chat: chatData,
        sources,
        activeSourceId: sources[0]?.id || null,
        activeSource: sources[0] || null,
        aiDocuments: aiDocs,
        activeAiDocumentId: aiDocs[0]?.id || null,
        activeAiDocument: aiDocs[0] || null,
        blueprints,
        activeBlueprintId: blueprints[0]?.id || null,
        activeBlueprint: blueprints[0] || null,
        drafts,
        activeDraftId: drafts[0]?.id || null,
        activeDraft: drafts[0] || null,
        exams,
        activeExamId: exams[0]?.id || null,
        activeExam: exams[0] || null,
        orchestrationRuns: runs
      });

      // Load deep resources
      if (sources[0]?.id) {
        this.loadSourceVersions(sources[0].id);
      }
      if (aiDocs[0]?.id) {
        this.loadAiDocDetails(aiDocs[0].id);
      }
      if (exams[0]?.id) {
        this.loadExamRevisions(exams[0].id);
      }
    } catch (err) {
      console.error('Failed to load subject data:', err);
      store.addToast('获取科目详情失败', 'error');
    }
  }

  async loadSourceVersions(sourceId) {
    try {
      const [versionsData, sourceDetail] = await Promise.all([
        api.listSourceVersions(sourceId).catch(() => ({ items: [] })),
        api.getSource(sourceId).catch(() => null)
      ]);

      const versions = versionsData.items || [];
      const latestVersionId = versions[0]?.id;

      let anchors = [];
      if (latestVersionId) {
        const anchorsData = await api.listSourceVersionAnchors(latestVersionId).catch(() => ({ items: [] }));
        anchors = anchorsData.items || [];
      }

      store.setState({
        activeSource: sourceDetail,
        activeSourceVersions: versions,
        activeSourceAnchors: anchors
      });
    } catch (err) {
      console.error(err);
    }
  }

  async loadAiDocDetails(docId) {
    try {
      const [doc, versionsData, proposalsData] = await Promise.all([
        api.getAiDocument(docId).catch(() => null),
        api.listAiDocumentVersions(docId).catch(() => ({ items: [] })),
        api.listAiDocumentRevisionProposals(docId).catch(() => ({ items: [] }))
      ]);

      const proposals = proposalsData.items || [];

      store.setState({
        activeAiDocument: doc,
        aiDocumentVersions: versionsData.items || [],
        aiDocumentProposals: proposals,
        activeAiDocProposalId: proposals[0]?.id || null,
        activeAiDocProposal: proposals[0] || null
      });
    } catch (err) {
      console.error(err);
    }
  }

  async loadExamRevisions(examId) {
    try {
      const [examDetail, proposalsData, versionsData] = await Promise.all([
        api.getExam(examId).catch(() => null),
        api.listRevisionProposals(examId).catch(() => ({ items: [] })),
        api.listExamVersions(examId).catch(() => ({ items: [] }))
      ]);

      const proposals = proposalsData.items || [];

      store.setState({
        activeExam: examDetail,
        revisionProposals: proposals,
        activeRevisionProposalId: proposals[0]?.id || null,
        activeRevisionProposal: proposals[0] || null,
        examVersions: versionsData.items || []
      });
    } catch (err) {
      console.error(err);
    }
  }

  startAttemptTimer() {
    if (this.timerInterval) clearInterval(this.timerInterval);
    this.timerInterval = setInterval(() => {
      const { activeAttempt } = store.getState();
      if (activeAttempt && activeAttempt.status === 'in-progress' && !activeAttempt.is_completed) {
        store.setState((s) => ({
          activeAttempt: {
            ...s.activeAttempt,
            elapsed_seconds: (s.activeAttempt.elapsed_seconds || 0) + 1
          }
        }));
      }
    }, 1000);
  }

  setupGlobalShortcuts() {
    window.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        store.setState((s) => ({ commandPaletteOpen: !s.commandPaletteOpen }));
      }
    });
  }

  // Master render method
  render(state) {
    const handlers = this.getHandlers();

    // 1. Render Navbar
    const navbarRoot = document.getElementById('navbar-root');
    if (navbarRoot) renderNavbar(state, navbarRoot, handlers);

    // 2. Render Main Workspace Container
    const mainWorkspaceRoot = document.getElementById('main-workspace-root');
    if (mainWorkspaceRoot) {
      this.renderWorkspace(state, mainWorkspaceRoot, handlers);
    }

    // 3. Render Modals & Overlays
    const modalRoot = document.getElementById('modal-root');
    if (modalRoot) renderModals(state, modalRoot, handlers);

    const cmdRoot = document.getElementById('cmd-root');
    if (cmdRoot) renderCommandPalette(state, cmdRoot, handlers);

    const toastRoot = document.getElementById('toast-root');
    if (toastRoot) renderToasts(state, toastRoot, handlers);
  }

  renderWorkspace(state, container, handlers) {
    const { activeNavTab } = state;

    if (activeNavTab === 'learn') {
      renderChatView(state, container, handlers);
    } else if (activeNavTab === 'sources') {
      renderSourcesView(state, container, handlers);
    } else if (activeNavTab === 'exam_studio') {
      renderExamStudioView(state, container, handlers);
    } else if (activeNavTab === 'practice_exam') {
      renderPracticeExamView(state, container, handlers);
    } else if (activeNavTab === 'settings_dev') {
      renderSettingsDevView(state, container, handlers);
    }
  }

  getHandlers() {
    return {
      // Primary Navigation
      onSelectNavTab: (tabId) => {
        store.setState({ activeNavTab: tabId });
      },
      onSelectExamStudioSubTab: (subtab) => {
        store.setState({ activeNavTab: 'exam_studio', examStudioSubTab: subtab });
      },
      onSelectPracticeViewMode: (viewMode) => {
        store.setState({ activeNavTab: 'practice_exam', practiceExamViewMode: viewMode });
      },
      onSwitchSourcesTab: (tab) => {
        store.setState({ sourcesTab: tab });
      },
      onSelectSettingsSubTab: (subtab) => {
        store.setState({ activeNavTab: 'settings_dev', settingsDevSubTab: subtab });
      },
      onToggleSidebar: (workspace) => {
        store.toggleSidebar(workspace);
      },
      onToggleTheme: () => {
        store.toggleTheme();
      },
      onToggleCommandPalette: () => {
        store.setState((s) => ({ commandPaletteOpen: !s.commandPaletteOpen }));
      },
      onCloseCommandPalette: () => {
        store.setState({ commandPaletteOpen: false });
      },

      // Modal Triggers
      onOpenSubjectModal: (mode) => {
        store.setState({ subjectModalOpen: true });
      },
      onOpenRenameSubjectModal: (subject) => {
        store.setState({ renameSubjectModalOpen: true, subjectToRename: subject });
      },
      onOpenModelModal: () => {
        store.setState({ modelModalOpen: true });
      },
      onOpenCreateSessionModal: () => {
        store.setState({ createSessionModalOpen: true });
      },
      onOpenCreateAiDocModal: () => {
        store.setState({ createAiDocModalOpen: true });
      },
      onOpenAiDocRevisionModal: (docId) => {
        store.setState({ aiDocRevisionModalOpen: true, activeAiDocumentId: docId });
      },
      onOpenBlueprintModal: () => {
        store.setState({ blueprintModalOpen: true });
      },
      onOpenRevisionModal: () => {
        store.setState({ revisionModalOpen: true });
      },
      onCloseModals: () => {
        store.setState({
          modelModalOpen: false,
          subjectModalOpen: false,
          renameSubjectModalOpen: false,
          createSessionModalOpen: false,
          createAiDocModalOpen: false,
          aiDocRevisionModalOpen: false,
          blueprintModalOpen: false,
          revisionModalOpen: false,
          citationModalOpen: false,
          activeCitation: null
        });
      },

      // Subject Actions
      onCreateSubject: async (name) => {
        try {
          const res = await api.createSubject(name);
          store.addToast(`科目空间「${name}」已创建`, 'success');
          store.setState({ subjectModalOpen: false });
          await this.loadInitialData();
          if (res.id) await this.loadSubjectData(res.id);
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onRenameSubject: async (subjectId, newName) => {
        try {
          await api.renameSubject(subjectId, newName);
          store.addToast(`科目已重命名为「${newName}」`, 'success');
          store.setState({ renameSubjectModalOpen: false, subjectToRename: null });
          await this.loadInitialData();
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onSwitchSubject: async (subjectId) => {
        store.setState({ activeSubjectId: subjectId });
        await api.activateSubject(subjectId).catch(() => {});
        await this.loadSubjectData(subjectId);
      },
      onDeleteSubject: async (subjectId) => {
        if (!confirm('确定要删除此科目空间及其所有资料和试卷吗？')) return;
        try {
          await api.deleteSubject(subjectId);
          store.addToast('科目空间已删除', 'success');
          await this.loadInitialData();
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },

      // Session Actions (Ticket 16, 17, 18)
      onSearchSessions: (query) => {
        store.setState({ sessionSearchQuery: query });
      },
      onCreateSession: async ({ title, learning_mode, grounding_mode, source_version_ids }) => {
        const { activeSubjectId, currentModelId } = store.getState();
        if (!activeSubjectId) return;

        try {
          const newSession = await api.createSession(activeSubjectId, {
            title,
            learning_mode,
            grounding_mode,
            source_version_ids,
            model_id: currentModelId || undefined
          });

          store.addToast('新学习会话已建立', 'success');
          store.setState({ createSessionModalOpen: false });

          const sessionsData = await api.listSessions(activeSubjectId);
          store.setState({
            sessions: sessionsData.items || [],
            activeSessionId: newSession.id,
            activeSession: newSession
          });
        } catch (err) {
          store.addToast(`创建会话失败: ${err.message}`, 'error');
        }
      },
      onSelectSession: async (sessionId) => {
        store.setState({ activeSessionId: sessionId });
        try {
          await api.activateSession(sessionId).catch(() => {});
          const sess = await api.getSession(sessionId);
          store.setState({ activeSession: sess });
        } catch (err) {
          console.error(err);
        }
      },
      onRenameSession: async (sessionId, newTitle) => {
        try {
          const updated = await api.updateSession(sessionId, { title: newTitle });
          store.addToast('会话名称已更新', 'success');
          const { activeSubjectId } = store.getState();
          const sessionsData = await api.listSessions(activeSubjectId);
          store.setState({
            sessions: sessionsData.items || [],
            activeSession: updated
          });
        } catch (err) {
          store.addToast(`重命名失败: ${err.message}`, 'error');
        }
      },
      onDeleteSession: async (sessionId) => {
        try {
          await api.deleteSession(sessionId);
          store.addToast('会话已删除', 'info');
          const { activeSubjectId } = store.getState();
          const sessionsData = await api.listSessions(activeSubjectId);
          const nextSessions = sessionsData.items || [];
          store.setState({
            sessions: nextSessions,
            activeSessionId: nextSessions[0]?.id || null,
            activeSession: nextSessions[0] || null
          });
        } catch (err) {
          store.addToast(`删除失败: ${err.message}`, 'error');
        }
      },
      onAddSessionSource: async (sessionId, sourceVersionId) => {
        try {
          if (sessionId) {
            await api.addSessionSource(sessionId, { source_version_id: sourceVersionId });
            const sess = await api.getSession(sessionId);
            store.setState({ activeSession: sess });
          } else {
            const { activeSubjectId, chat } = store.getState();
            const nextSources = [...(chat.source_version_ids || []), sourceVersionId];
            await api.updateChatConfig(activeSubjectId, { source_version_ids: nextSources });
            const nextChat = await api.getChat(activeSubjectId);
            store.setState({ chat: nextChat });
          }
          store.addToast('资料已固定至当前会话', 'success');
        } catch (err) {
          store.addToast(`添加资料失败: ${err.message}`, 'error');
        }
      },
      onRemoveSessionSource: async (sessionId, sourceVersionId) => {
        try {
          if (sessionId) {
            await api.removeSessionSource(sessionId, sourceVersionId);
            const sess = await api.getSession(sessionId);
            store.setState({ activeSession: sess });
          } else {
            const { activeSubjectId, chat } = store.getState();
            const nextSources = (chat.source_version_ids || []).filter((id) => id !== sourceVersionId);
            await api.updateChatConfig(activeSubjectId, { source_version_ids: nextSources });
            const nextChat = await api.getChat(activeSubjectId);
            store.setState({ chat: nextChat });
          }
          store.addToast('已从会话中移除资料', 'info');
        } catch (err) {
          store.addToast(`移除失败: ${err.message}`, 'error');
        }
      },

      // Chat & Tutor Actions
      onSwitchLearningMode: async (learningMode) => {
        const { activeSessionId, activeSubjectId } = store.getState();
        try {
          if (activeSessionId) {
            const updated = await api.updateSession(activeSessionId, { learning_mode: learningMode });
            store.setState({ activeSession: updated });
          } else if (activeSubjectId) {
            const nextChat = await api.updateChatConfig(activeSubjectId, { learning_mode: learningMode });
            store.setState({ chat: nextChat });
          }
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onUpdateGroundingMode: async (groundingMode) => {
        const { activeSessionId, activeSubjectId } = store.getState();
        try {
          if (activeSessionId) {
            const updated = await api.updateSession(activeSessionId, { grounding_mode: groundingMode });
            store.setState({ activeSession: updated });
          } else if (activeSubjectId) {
            const nextChat = await api.updateChatConfig(activeSubjectId, { grounding_mode: groundingMode });
            store.setState({ chat: nextChat });
          }
          store.addToast(`知识依据已切换: ${groundingMode}`, 'info');
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onSendMessage: async ({ content, intent = 'ask', attachments = [] }) => {
        const { activeSubjectId, activeSessionId, activeSession, chat, selectionContext, currentModelId } = store.getState();
        if (!activeSubjectId) {
          store.addToast('请先选择或创建一个科目空间', 'error');
          return;
        }

        try {
          // Optimistically append user message
          const userMsg = { role: 'user', content, intent, timestamp: Date.now() };
          if (activeSession) {
            store.setState((s) => ({
              activeSession: { ...s.activeSession, messages: [...(s.activeSession.messages || []), userMsg] }
            }));
          } else {
            store.setState((s) => ({
              chat: { ...s.chat, messages: [...(s.chat?.messages || []), userMsg] }
            }));
          }

          const payload = {
            content,
            intent,
            grounding_mode: activeSession?.grounding_mode || chat.grounding_mode || 'general-knowledge',
            model_id: activeSession?.model_id || currentModelId || undefined
          };

          if (selectionContext) {
            payload.selection = {
              document_kind: selectionContext.source_id ? 'source' : 'exam',
              document_id: selectionContext.source_id || selectionContext.exam_id,
              version_id: selectionContext.source_version_id,
              selected_text: selectionContext.text
            };
          }

          // Clear temporary attachments after payload prepared
          store.setState({ chatAttachments: [] });

          let accepted = null;
          if (activeSessionId) {
            accepted = await api.createSessionMessage(activeSessionId, payload);
          } else {
            accepted = await api.sendMessage(activeSubjectId, payload);
          }

          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          if (activeSessionId) {
            const updatedSess = await api.getSession(activeSessionId);
            store.setState({ activeSession: updatedSess });
          } else {
            const updatedChat = await api.getChat(activeSubjectId);
            store.setState({ chat: updatedChat });
          }
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onSendIntentMessage: async (intent) => {
        const { activeSubjectId, activeSessionId } = store.getState();
        if (!activeSubjectId) return;

        try {
          let accepted = null;
          if (activeSessionId) {
            accepted = await api.createSessionMessage(activeSessionId, { intent });
          } else {
            accepted = await api.sendMessage(activeSubjectId, { intent });
          }

          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          if (activeSessionId) {
            const updatedSess = await api.getSession(activeSessionId);
            store.setState({ activeSession: updatedSess });
          } else {
            const updatedChat = await api.getChat(activeSubjectId);
            store.setState({ chat: updatedChat });
          }
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onClearChat: async () => {
        const { activeSubjectId, activeSessionId } = store.getState();
        if (!activeSubjectId) return;
        try {
          if (activeSessionId) {
            // Delete and re-create clean session or clear
            store.setState((s) => ({ activeSession: { ...s.activeSession, messages: [] } }));
          } else {
            await api.clearChat(activeSubjectId);
            store.setState((s) => ({ chat: { ...s.chat, messages: [] } }));
          }
          store.addToast('对话已清空', 'info');
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onAddChatAttachments: (files) => {
        const newAtts = files.map((file) => {
          const isImage = file.type.startsWith('image/');
          return {
            file,
            name: file.name,
            size_bytes: file.size,
            is_image: isImage,
            preview_url: isImage ? URL.createObjectURL(file) : null,
            status: 'ready'
          };
        });
        store.setState((s) => ({ chatAttachments: [...s.chatAttachments, ...newAtts] }));
      },
      onRemoveChatAttachment: (index) => {
        store.setState((s) => ({
          chatAttachments: s.chatAttachments.filter((_, idx) => idx !== index)
        }));
      },
      onPinSelection: (sel) => {
        store.setState({ selectionContext: sel });
        store.addToast('已将段落选区固定至导师提问', 'info');
      },
      onClearSelection: () => {
        store.setState({ selectionContext: null });
      },
      onInspectCitation: async ({ citationId }) => {
        try {
          const cit = await api.getCitation(citationId);
          store.setState({ citationModalOpen: true, activeCitation: cit });
        } catch (err) {
          store.addToast('无法获取引用详情', 'error');
        }
      },

      // Model Management & Discovery (Ticket 16, 19)
      onSaveModel: async (modelConfig) => {
        try {
          const res = await api.addModel(modelConfig);
          store.addToast(`模型「${res.model}」注册成功`, 'success');
          store.setState({ modelModalOpen: false });
          const modelsList = await api.listModels();
          store.setState({ models: modelsList.items || [] });
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onDiscoverModels: async ({ provider, base_url, api_key }) => {
        try {
          store.addToast('正在向服务端探测可用模型列表...', 'info');
          const res = await api.discoverModels({ provider, base_url, api_key });
          const items = res.items || res.models || [];
          if (items.length > 0) {
            store.setState({ discoveredModels: items });
            store.addToast(`成功发现 ${items.length} 个可用模型`, 'success');
          } else {
            store.addToast('未获取到模型列表，请手动输入模型名称', 'info');
          }
        } catch (err) {
          store.addToast(`模型发现失败: ${err.message}，已保留手动输入`, 'error');
        }
      },
      onSelectGlobalCurrentModel: async (modelId) => {
        try {
          await api.selectCurrentModel({ model_id: modelId });
          store.setState({ currentModelId: modelId });
          store.addToast('已切换系统当前模型', 'success');
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onVerifyModel: async (modelId) => {
        try {
          store.addToast('正在进行模型连通性测试...', 'info');
          const res = await api.verifyModel(modelId);
          store.addToast(res.status === 'ok' ? '模型连接通畅，就绪可用' : '连接异常', res.status === 'ok' ? 'success' : 'error');
        } catch (err) {
          store.addToast(`连通性测试失败: ${err.message}`, 'error');
        }
      },
      onDeleteModel: async (modelId) => {
        try {
          await api.deleteModel(modelId);
          store.addToast('模型已移除', 'success');
          const modelsList = await api.listModels();
          store.setState({ models: modelsList.items || [] });
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },

      // Sources Actions
      onUploadFiles: async (files) => {
        const { activeSubjectId } = store.getState();
        if (!activeSubjectId) {
          store.addToast('请先选择或创建一个科目空间', 'error');
          return;
        }

        for (const file of files) {
          try {
            store.addToast(`正在解析资料《${file.name}》...`, 'info');
            const res = await api.uploadSource(activeSubjectId, file);
            if (res.operation?.id) {
              store.trackOperation(res.operation);
              await api.pollOperation(res.operation.id, {
                onProgress: (op) => store.trackOperation(op)
              });
            }
            store.addToast(`《${file.name}》已收录就绪`, 'success');
          } catch (err) {
            store.addToast(`上传 ${file.name} 失败: ${err.message}`, 'error');
          }
        }

        const sourcesData = await api.listSources(activeSubjectId);
        store.setState({ sources: sourcesData.items || [] });
      },
      onIterateSourceVersion: async (sourceId, file) => {
        try {
          store.addToast(`正在上传新版本并重新解析《${file.name}》...`, 'info');
          const res = await api.uploadSourceVersion(sourceId, file);
          if (res.operation?.id) {
            store.trackOperation(res.operation);
            await api.pollOperation(res.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }
          store.addToast('资料新版本已迭代解析完毕', 'success');
          await this.loadSourceVersions(sourceId);
        } catch (err) {
          store.addToast(`迭代版本失败: ${err.message}`, 'error');
        }
      },
      onSelectSource: async (sourceId) => {
        store.setState({ activeSourceId: sourceId });
        await this.loadSourceVersions(sourceId);
      },
      onDeleteSource: async (sourceId) => {
        if (!confirm('确定删除此学习资料吗？引用此资料的会话和试卷将保留历史记录，但无法继续检索新内容。')) return;
        try {
          await api.deleteSource(sourceId);
          store.addToast('资料已删除', 'success');
          const { activeSubjectId } = store.getState();
          const sourcesData = await api.listSources(activeSubjectId);
          const nextSources = sourcesData.items || [];
          store.setState({
            sources: nextSources,
            activeSourceId: nextSources[0]?.id || null,
            activeSource: nextSources[0] || null
          });
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },

      // AI-Authored Documents Actions (Ticket 20)
      onCreateAiDocument: async ({ title, instruction, source_version_ids }) => {
        const { activeSubjectId } = store.getState();
        if (!activeSubjectId) return;

        try {
          store.addToast(`正在指令 AI 生成《${title}》...`, 'info');
          store.setState({ createAiDocModalOpen: false });

          const accepted = await api.createAiDocument(activeSubjectId, { title, instruction, source_version_ids });
          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          store.addToast(`《${title}》已生成完毕`, 'success');
          const docsData = await api.listAiDocuments(activeSubjectId);
          const nextDocs = docsData.items || [];
          const newDocId = accepted.resource?.id || nextDocs[0]?.id;

          store.setState({
            aiDocuments: nextDocs,
            activeAiDocumentId: newDocId,
            sourcesTab: 'ai_documents'
          });

          if (newDocId) await this.loadAiDocDetails(newDocId);
        } catch (err) {
          store.addToast(`生成 AI 文档失败: ${err.message}`, 'error');
        }
      },
      onSelectAiDoc: async (docId) => {
        store.setState({ activeAiDocumentId: docId });
        await this.loadAiDocDetails(docId);
      },
      onCreateAiDocRevisionProposal: async (docId, instruction) => {
        try {
          store.addToast('正在生成 AI 资料修改提案...', 'info');
          store.setState({ aiDocRevisionModalOpen: false });

          const { activeAiDocument } = store.getState();
          const baseVersionId = activeAiDocument?.versions?.[0]?.id || activeAiDocument?.id;

          const accepted = await api.createAiDocumentRevisionProposal(docId, {
            instruction,
            base_version_id: baseVersionId
          });

          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          store.addToast('AI 修改建议提案已生成', 'success');
          await this.loadAiDocDetails(docId);
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onApplyAiDocProposal: async (proposalId) => {
        const { activeAiDocumentId } = store.getState();
        try {
          await api.applyAiDocumentRevisionProposal(proposalId);
          store.addToast('已将 AI 建议应用为新版本', 'success');
          await this.loadAiDocDetails(activeAiDocumentId);
        } catch (err) {
          store.addToast(`应用修改失败: ${err.message}`, 'error');
        }
      },
      onDiscardAiDocProposal: async (proposalId) => {
        const { activeAiDocumentId } = store.getState();
        try {
          await api.discardAiDocumentRevisionProposal(proposalId);
          store.addToast('提案已放弃', 'info');
          await this.loadAiDocDetails(activeAiDocumentId);
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onRestoreAiDocVersion: async (docId, versionId) => {
        try {
          await api.restoreAiDocumentVersion(docId, versionId);
          store.addToast('文档历史版本已恢复', 'success');
          await this.loadAiDocDetails(docId);
        } catch (err) {
          store.addToast(`恢复版本失败: ${err.message}`, 'error');
        }
      },

      // Exam Blueprints Actions (Ticket 08)
      onCreateBlueprint: async ({ prompt, total_score, grounding_mode }) => {
        const { activeSubjectId, activeSourceVersions } = store.getState();
        if (!activeSubjectId) return;

        try {
          store.addToast('正在构思并解析试卷蓝图...', 'info');
          store.setState({ blueprintModalOpen: false });

          const srcIds = activeSourceVersions[0]?.id ? [activeSourceVersions[0].id] : [];
          const accepted = await api.parseBlueprint(activeSubjectId, {
            prompt,
            total_score,
            grounding_mode,
            source_version_ids: srcIds
          });

          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          const bpsData = await api.listBlueprints(activeSubjectId);
          const nextBps = bpsData.items || [];
          store.setState({
            blueprints: nextBps,
            activeBlueprintId: nextBps[0]?.id || null,
            activeBlueprint: nextBps[0] || null,
            activeNavTab: 'exam_studio',
            examStudioSubTab: 'blueprint'
          });
          store.addToast('组卷蓝图构思完成', 'success');
        } catch (err) {
          store.addToast(`蓝图解析失败: ${err.message}`, 'error');
        }
      },
      onSelectBlueprint: async (bpId) => {
        store.setState({ activeBlueprintId: bpId });
        try {
          const bp = await api.getBlueprint(bpId);
          store.setState({ activeBlueprint: bp });
        } catch (err) {
          console.error(err);
        }
      },
      onConfirmBlueprint: async (bpId) => {
        try {
          const confirmed = await api.confirmBlueprint(bpId);
          store.setState({ activeBlueprint: confirmed });
          store.addToast('蓝图已确认，可开始增量组题', 'success');
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onGenerateDraftFromBlueprint: async (bpId) => {
        const { activeSubjectId } = store.getState();
        try {
          store.addToast('正在增量创建试卷题目槽位...', 'info');
          const accepted = await api.generateDraftFromBlueprint(bpId);

          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          const draftsData = await api.listDrafts(activeSubjectId);
          const nextDrafts = draftsData.items || [];
          store.setState({
            drafts: nextDrafts,
            activeDraftId: nextDrafts[0]?.id || null,
            activeDraft: nextDrafts[0] || null,
            examStudioSubTab: 'draft'
          });
          store.addToast('试卷草稿创建就绪，题目正在增量推演', 'success');
        } catch (err) {
          store.addToast(`生成试题失败: ${err.message}`, 'error');
        }
      },

      // Exam Drafts Actions (Ticket 09)
      onSelectDraft: async (draftId) => {
        store.setState({ activeDraftId: draftId });
        try {
          const d = await api.getDraft(draftId);
          store.setState({ activeDraft: d });
        } catch (err) {
          console.error(err);
        }
      },
      onRetryDraftQuestion: async (draftId, questionId) => {
        try {
          store.addToast('正在单独重试生成该题...', 'info');
          const accepted = await api.retryDraftQuestion(draftId, questionId);

          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          const updatedDraft = await api.getDraft(draftId);
          store.setState({ activeDraft: updatedDraft });
          store.addToast('该题已重新生成完毕', 'success');
        } catch (err) {
          store.addToast(`重试生成失败: ${err.message}`, 'error');
        }
      },
      onPublishDraft: async (draftId) => {
        const { activeSubjectId } = store.getState();
        try {
          store.addToast('正在正式发布试卷...', 'info');
          const accepted = await api.publishDraft(draftId);

          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          const examsData = await api.listExams(activeSubjectId);
          const nextExams = examsData.items || [];
          store.setState({
            exams: nextExams,
            activeExamId: nextExams[0]?.id || null,
            activeExam: nextExams[0] || null,
            examStudioSubTab: 'exam'
          });
          store.addToast('正式试卷发布成功！已归档至作答中心', 'success');
        } catch (err) {
          store.addToast(`发布失败: ${err.message}`, 'error');
        }
      },

      // Exams & AI Revision Proposals Actions (Ticket 13)
      onSelectExam: async (examId) => {
        store.setState({ activeExamId: examId });
        await this.loadExamRevisions(examId);
      },
      onCreateExamRevisionProposal: async (examId, instruction) => {
        try {
          store.addToast('正在分析并生成试卷 AI 修改差异提案...', 'info');
          store.setState({ revisionModalOpen: false });

          const { activeExam } = store.getState();
          const baseVersionId = activeExam?.versions?.[0]?.id || activeExam?.id;

          const accepted = await api.proposeRevision(examId, {
            instruction,
            base_version_id: baseVersionId
          });

          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          await this.loadExamRevisions(examId);
          store.addToast('修改比对提案已就绪', 'success');
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onApplyProposal: async (proposalId) => {
        const { activeExamId } = store.getState();
        try {
          const updatedExam = await api.applyRevisionProposal(proposalId);
          store.setState({ activeExam: updatedExam });
          store.addToast('修改提案已成功合并至正式试卷', 'success');
          await this.loadExamRevisions(activeExamId);
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onDiscardProposal: async (proposalId) => {
        const { activeExamId } = store.getState();
        try {
          await api.discardRevisionProposal(proposalId);
          store.addToast('提案已放弃', 'info');
          await this.loadExamRevisions(activeExamId);
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onUndoExamChange: async (examId) => {
        try {
          await api.undoExamChange(examId);
          store.addToast('已撤销上一步试卷修改', 'success');
          await this.loadExamRevisions(examId);
        } catch (err) {
          store.addToast(`撤销失败: ${err.message}`, 'error');
        }
      },
      onRedoExamChange: async (examId) => {
        try {
          await api.redoExamChange(examId);
          store.addToast('已重做试卷修改', 'success');
          await this.loadExamRevisions(examId);
        } catch (err) {
          store.addToast(`重做失败: ${err.message}`, 'error');
        }
      },

      // Practice & Exam Attempt Actions (Ticket 10, 11, 21)
      onSelectExamForPractice: (examId) => {
        store.setState({
          activeExamId: examId,
          activeAttempt: null,
          activeAttemptReview: null
        });
      },
      onSelectAttemptHistory: async (attemptId) => {
        try {
          const att = await api.getAttempt(attemptId);
          if (att.status === 'completed' || att.is_completed) {
            const review = await api.getAttemptReview(attemptId).catch(() => null);
            if (review) {
              store.setState({ activeAttemptReview: review, activeAttempt: att });
              return;
            }
          }
          store.setState({ activeAttempt: att, activeAttemptReview: null });
        } catch (err) {
          store.addToast('加载作答记录失败', 'error');
        }
      },
      onStartAttempt: async (examId, mode = 'practice', showSuggestedScore = false) => {
        try {
          store.addToast(`正在初始化${mode === 'practice' ? '练习' : '正式考试'}答题纸...`, 'info');
          const attempt = await api.createAttempt(examId, {
            mode,
            show_suggested_score: showSuggestedScore
          });

          store.setState((s) => ({
            activeAttemptId: attempt.id,
            activeAttempt: attempt,
            activeAttemptReview: null,
            attempts: [attempt, ...s.attempts]
          }));
        } catch (err) {
          store.addToast(`开启作答失败: ${err.message}`, 'error');
        }
      },
      onSaveAttemptAnswer: async (attemptId, questionId, answer) => {
        try {
          await api.saveAttemptAnswer(attemptId, questionId, answer);
          store.setState((s) => {
            if (!s.activeAttempt || s.activeAttempt.id !== attemptId) return {};
            const answers = s.activeAttempt.answers || [];
            const existingIdx = answers.findIndex((a) => a.question_id === questionId);
            let nextAnswers = [];
            if (existingIdx >= 0) {
              nextAnswers = [...answers];
              nextAnswers[existingIdx] = { ...nextAnswers[existingIdx], answer };
            } else {
              nextAnswers = [...answers, { question_id: questionId, answer }];
            }
            return {
              activeAttempt: {
                ...s.activeAttempt,
                answers: nextAnswers
              }
            };
          });
        } catch (err) {
          console.error('Failed to auto-save answer:', err);
        }
      },
      onRequestQuestionFeedback: async (attemptId, questionId) => {
        const { currentModelId } = store.getState();
        try {
          store.addToast('正在获取本题 AI 得分要点与反馈...', 'info');
          const accepted = await api.requestQuestionFeedback(attemptId, questionId, {
            model_id: currentModelId,
            show_suggested_score: true
          });

          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          const updatedAtt = await api.getAttempt(attemptId);
          store.setState({ activeAttempt: updatedAtt });
          store.addToast('本题反馈已生成', 'success');
        } catch (err) {
          store.addToast(`获取反馈失败: ${err.message}`, 'error');
        }
      },
      onCompleteAttempt: async (attemptId) => {
        try {
          const completed = await api.completeAttempt(attemptId);
          store.setState({ activeAttempt: completed });
          store.addToast('作答已标记完成（答案已锁定为只读）', 'success');
        } catch (err) {
          store.addToast(`标记完成失败: ${err.message}`, 'error');
        }
      },
      onContinueAttempt: async (attemptId) => {
        try {
          const resumed = await api.continueAttempt(attemptId);
          store.setState({ activeAttempt: resumed });
          store.addToast('已解锁，可继续修改作答', 'info');
        } catch (err) {
          store.addToast(`继续作答失败: ${err.message}`, 'error');
        }
      },
      onSubmitAttemptGrading: async (attemptId) => {
        const { currentModelId } = store.getState();
        try {
          store.addToast('正在提交全卷智能批改与薄弱点分析...', 'info');
          const accepted = await api.submitAttemptGrading(attemptId, {
            model_id: currentModelId,
            show_suggested_score: true
          });

          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          const review = await api.getAttemptReview(attemptId);
          const updatedAtt = await api.getAttempt(attemptId);
          store.setState({
            activeAttempt: updatedAtt,
            activeAttemptReview: review
          });
          store.addToast('全卷批改完毕！已生成成绩报告', 'success');
        } catch (err) {
          store.addToast(`批改失败: ${err.message}`, 'error');
        }
      },
      onPauseAttempt: async (attemptId) => {
        try {
          const paused = await api.pauseAttempt(attemptId);
          store.setState({ activeAttempt: paused });
          store.addToast('作答已暂停', 'info');
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onResumeAttempt: async (attemptId) => {
        try {
          const resumed = await api.resumeAttempt(attemptId);
          store.setState({ activeAttempt: resumed });
          store.addToast('作答已恢复计时', 'info');
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onExitAttempt: () => {
        store.setState({ activeAttempt: null, activeAttemptReview: null });
      },

      // Renderer Actions (Ticket 14)
      onSwitchRenderEdition: async (edition) => {
        const { activeExamId } = store.getState();
        if (!activeExamId) return;
        await this.loadRenderDocument(activeExamId, edition);
      },
      onExportExam: async (examId, format, edition) => {
        try {
          store.addToast(`正在生成 ${format.toUpperCase()} 导出排版...`, 'info');
          const accepted = await api.createExamExport(examId, { format, edition });
          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }
          const exp = await api.getExamExport(accepted.resource?.id || accepted.operation?.resource?.id);
          if (exp.download_url) {
            window.open(exp.download_url, '_blank');
          }
          store.addToast('文件已导出就绪', 'success');
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },

      // Observability & Evaluation Actions (Ticket 15)
      onSelectRun: async (runId) => {
        try {
          const run = await api.getOrchestrationRun(runId);
          store.setState({ activeRunId: runId, activeRun: run });
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onRunEvaluationSuite: async (suiteId) => {
        try {
          store.addToast('正在运行自动化基准测试套件...', 'info');
          const accepted = await api.runEvaluationSuite(suiteId);
          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }
          const evalRun = await api.getEvaluationRun(accepted.resource?.id || accepted.operation?.resource?.id);
          store.setState({ activeEvalRun: evalRun });
          store.addToast('基准评估完毕', 'success');
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },

      // Toast Actions
      onDismissToast: (toastId) => {
        store.removeToast(toastId);
      }
    };
  }
}

// Bootstrap
window.addEventListener('DOMContentLoaded', () => {
  const app = new App();
  app.init();
});
