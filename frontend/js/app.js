/**
 * Main Application Orchestrator for Learning Loop Agent
 * Strictly aligned with Issue 16–22, ADR 0003, ADR 0004, ADR 0005:
 * - 4 Primary Workspaces: 学习 (learn), 资料 (sources), 组卷 (quiz_gen), 作答 (attempts)
 * - Identical two-column skeleton: Left AI Chat + Right Workspace Content
 * - Simple but useful interaction experience
 */

import { api } from './api.js';
import { store } from './state.js';
import { renderNavbar } from './components/navbar.js';
import { renderChatPanel } from './components/chat_panel.js';
import { renderLearnView } from './components/learn_view.js';
import { renderSourcesView } from './components/sources_view.js';
import { renderQuizGenView } from './components/quiz_gen_view.js';
import { renderAttemptsView } from './components/attempts_view.js';
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

    // Load initial workspace and models
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

    // Apply saved theme
    const theme = store.getState().theme || 'paper';
    document.documentElement.setAttribute('data-theme', theme);
  }

  async loadInitialData() {
    try {
      const [workspace, modelsList, currentModelRes] = await Promise.all([
        api.getWorkspace().catch(() => ({ subjects: [], active_subject_id: null })),
        api.listModels().catch(() => ({ items: [] })),
        api.getCurrentModel().catch(() => null)
      ]);

      const subjects = workspace.subjects || [];
      const activeId = workspace.active_subject_id || (subjects[0] ? subjects[0].id : null);
      const models = modelsList.items || [];
      const currentModelId = currentModelRes?.model_id || (models[0] ? models[0].id : null);

      store.setState({
        workspace,
        activeSubjectId: activeId,
        models,
        currentModelId
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
        examsData
      ] = await Promise.all([
        api.listSessions(subjectId).catch(() => ({ items: [] })),
        api.getChat(subjectId).catch(() => ({ messages: [], grounding_mode: 'general-knowledge', chat_style: 'default', active_model_id: null })),
        api.listSources(subjectId).catch(() => ({ items: [] })),
        api.listAiDocuments(subjectId).catch(() => ({ items: [] })),
        api.listBlueprints(subjectId).catch(() => ({ items: [] })),
        api.listDrafts(subjectId).catch(() => ({ items: [] })),
        api.listExams(subjectId).catch(() => ({ items: [] }))
      ]);

      const sessions = sessionsData.items || [];
      const sources = sourcesData.items || [];
      const aiDocs = aiDocsData.items || [];
      const blueprints = blueprintsData.items || [];
      const drafts = draftsData.items || [];
      const exams = examsData.items || [];

      // Find active session
      let activeSession = sessions[0] || null;
      let activeSessionId = activeSession?.id || null;

      // If no session exists, create a default one
      if (!activeSession && subjectId) {
        try {
          activeSession = await api.createSession(subjectId, { title: '学习会话' });
          activeSessionId = activeSession.id;
          sessions.unshift(activeSession);
        } catch (e) {
          // ignore
        }
      }

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
        activeExam: exams[0] || null
      });

      // Load deep resources
      if (sources[0]?.id) {
        this.loadSourceVersions(sources[0].id);
      }
      if (aiDocs[0]?.id) {
        this.loadAiDocDetails(aiDocs[0].id);
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

  // Master Render Method
  render(state) {
    const handlers = this.getHandlers();

    // 1. Render Top Navbar
    const navbarRoot = document.getElementById('navbar-root');
    if (navbarRoot) renderNavbar(state, navbarRoot, handlers);

    // 2. Render 2-Column Workspace Container
    const mainWorkspaceRoot = document.getElementById('main-workspace-root');
    if (mainWorkspaceRoot) {
      this.renderMasterWorkspace(state, mainWorkspaceRoot, handlers);
    }

    // 3. Render Modals & Overlays
    const modalRoot = document.getElementById('modal-root');
    if (modalRoot) renderModals(state, modalRoot, handlers);

    const cmdRoot = document.getElementById('cmd-root');
    if (cmdRoot) renderCommandPalette(state, cmdRoot, handlers);

    const toastRoot = document.getElementById('toast-root');
    if (toastRoot) renderToasts(state, toastRoot, handlers);
  }

  renderMasterWorkspace(state, container, handlers) {
    const { activeNavTab, sidebarCollapsed = {} } = state;
    const isLeftCollapsed = !!sidebarCollapsed.left;

    container.innerHTML = `
      <div class="workspace-twocol-skeleton ${isLeftCollapsed ? 'is-left-collapsed' : ''}">
        <!-- Left: AI Chat Panel (Same across all 4 workspaces) -->
        <aside class="workspace-left-chat ${isLeftCollapsed ? 'is-collapsed' : ''}" id="workspace-left-chat-root"></aside>

        <!-- Right: Current Workspace Content -->
        <section class="workspace-right-content" id="workspace-right-content-root"></section>
      </div>
    `;

    // Render Left AI Chat
    const leftChatRoot = container.querySelector('#workspace-left-chat-root');
    if (leftChatRoot) {
      renderChatPanel(state, leftChatRoot, handlers);
    }

    // Render Right Content according to active workspace
    const rightContentRoot = container.querySelector('#workspace-right-content-root');
    if (rightContentRoot) {
      if (activeNavTab === 'learn') {
        renderLearnView(state, rightContentRoot, handlers);
      } else if (activeNavTab === 'sources') {
        renderSourcesView(state, rightContentRoot, handlers);
      } else if (activeNavTab === 'quiz_gen') {
        renderQuizGenView(state, rightContentRoot, handlers);
      } else if (activeNavTab === 'attempts') {
        renderAttemptsView(state, rightContentRoot, handlers);
      }
    }
  }

  getHandlers() {
    return {
      // Primary Navigation
      onSelectNavTab: (tabId) => {
        store.setState({ activeNavTab: tabId });
      },
      onSelectExamStudioSubTab: (subtab) => {
        store.setState({ activeNavTab: 'quiz_gen', examStudioSubTab: subtab });
      },
      onSwitchSourcesTab: (tab) => {
        store.setState({ sourcesTab: tab });
      },
      onToggleSidebar: (side) => {
        store.toggleSidebar(side);
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
      onOpenSubjectModal: () => {
        store.setState({ subjectModalOpen: true });
      },
      onOpenRenameSubjectModal: (subject) => {
        store.setState({ renameSubjectModalOpen: true, subjectToRename: subject });
      },
      onOpenModelModal: () => {
        store.setState({ modelModalOpen: true, discoveredModels: [] });
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
      onCloseModals: () => {
        store.setState({
          modelModalOpen: false,
          subjectModalOpen: false,
          renameSubjectModalOpen: false,
          createSessionModalOpen: false,
          createAiDocModalOpen: false,
          aiDocRevisionModalOpen: false,
          blueprintModalOpen: false,
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

      // Model Management Actions (Ticket 19 & ADR 0005)
      onSaveModelConfig: async (payload) => {
        try {
          const res = await api.createModel(payload);
          store.addToast(`模型「${payload.name || payload.model}」已保存`, 'success');

          // If no active model, select it
          const { currentModelId } = store.getState();
          if (!currentModelId && res.id) {
            await api.selectCurrentModel(res.id).catch(() => {});
            store.setState({ currentModelId: res.id });
          }

          const modelsList = await api.listModels().catch(() => ({ items: [] }));
          store.setState({
            models: modelsList.items || [],
            modelModalOpen: false
          });
        } catch (err) {
          store.addToast(`保存模型失败: ${err.message}`, 'error');
        }
      },
      onSelectCurrentModel: async (modelId) => {
        try {
          await api.selectCurrentModel(modelId);
          store.setState({ currentModelId: modelId });
          store.addToast('已切换当前使用模型', 'success');
        } catch (err) {
          store.addToast(`切换模型失败: ${err.message}`, 'error');
        }
      },
      onDeleteModel: async (modelId) => {
        if (!confirm('确定要删除此模型配置吗？')) return;
        try {
          await api.deleteModel(modelId);
          store.addToast('模型配置已删除', 'info');
          const modelsList = await api.listModels().catch(() => ({ items: [] }));
          const models = modelsList.items || [];
          const { currentModelId } = store.getState();
          const nextModelId = currentModelId === modelId ? (models[0]?.id || null) : currentModelId;
          store.setState({ models, currentModelId: nextModelId });
        } catch (err) {
          store.addToast(`删除模型失败: ${err.message}`, 'error');
        }
      },
      onTestModelConnection: async (payload, callback) => {
        try {
          const t0 = Date.now();
          const res = await api.discoverModels(payload);
          const latency_ms = Date.now() - t0;
          callback({ ok: true, latency_ms });
        } catch (err) {
          callback({ ok: false, error: err.message });
        }
      },
      onDiscoverModels: async (payload) => {
        try {
          store.addToast('正在获取可用模型列表...', 'info');
          const res = await api.discoverModels(payload);
          const list = res.models || res.items || [];
          store.setState({ discoveredModels: list });
          if (list.length > 0) {
            store.addToast(`已发现 ${list.length} 个模型`, 'success');
          } else {
            store.addToast('未发现模型，请手动输入模型名称', 'info');
          }
        } catch (err) {
          store.addToast(`获取模型失败: ${err.message}，仍可手动输入`, 'warning');
        }
      },

      // Chat & Tutor Actions
      onSendMessage: async (content) => {
        const {
          activeSubjectId,
          activeSessionId,
          activeSession,
          chat,
          chatAttachments,
          selectionContext,
          activeNavTab
        } = store.getState();

        if (!activeSubjectId) {
          store.addToast('请先选择或创建科目空间', 'warning');
          return;
        }

        const chatStyle = activeSession?.chat_style || chat?.chat_style || 'default';
        const sourceVersionIds = activeSession?.source_version_ids || chat?.source_version_ids || [];
        const attachmentIds = chatAttachments.map((a) => a.id);

        // Optimistically add user message
        const userMsg = {
          role: 'user',
          content,
          created_at: Date.now()
        };

        store.setState((s) => {
          const currentMsgs = s.activeSession?.messages || s.chat?.messages || [];
          const updatedMsgs = [...currentMsgs, userMsg];

          return {
            chatAttachments: [],
            selectionContext: null,
            activeSession: s.activeSession ? { ...s.activeSession, messages: updatedMsgs } : null,
            chat: { ...s.chat, messages: updatedMsgs }
          };
        });

        // If in Quiz Gen workspace, also auto-handle natural language quiz requests
        if (activeNavTab === 'quiz_gen' && content.length >= 3) {
          api.parseBlueprint(activeSubjectId, content)
            .then(async (accepted) => {
              if (accepted.operation?.id) {
                store.trackOperation(accepted.operation);
                await api.pollOperation(accepted.operation.id, {
                  onProgress: (op) => store.trackOperation(op)
                });
              }
              const bp = await api.getBlueprint(accepted.resource?.id || accepted.operation?.resource?.id).catch(() => null);
              if (bp) {
                const blueprintsList = await api.listBlueprints(activeSubjectId).catch(() => ({ items: [] }));
                store.setState({
                  blueprints: blueprintsList.items || [],
                  activeBlueprintId: bp.id,
                  activeBlueprint: bp,
                  examStudioSubTab: 'blueprint'
                });
                store.addToast('已根据您的要求生成试卷设置', 'success');
              }
            })
            .catch(() => {});
        }

        // Send message to backend
        try {
          const payload = {
            content,
            chat_style: chatStyle,
            source_version_ids: sourceVersionIds,
            selection: selectionContext ? {
              text: selectionContext.text,
              anchor_id: selectionContext.anchor_id || null,
              source_version_id: selectionContext.source_version_id || null,
              question_id: selectionContext.question_id || null
            } : null,
            attachment_ids: attachmentIds
          };

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

          // Reload session messages
          if (activeSessionId) {
            const updatedSession = await api.getSession(activeSessionId);
            store.setState((s) => ({
              activeSession: updatedSession,
              sessions: s.sessions.map((sess) => (sess.id === activeSessionId ? updatedSession : sess))
            }));
          } else {
            const updatedChat = await api.getChat(activeSubjectId);
            store.setState({ chat: updatedChat });
          }
        } catch (err) {
          store.addToast(`发送失败: ${err.message}`, 'error');
        }
      },
      onStopGeneration: async () => {
        const { activeOperations, activeSubjectId } = store.getState();
        for (const [opId, op] of activeOperations.entries()) {
          if (op.status === 'running' || op.status === 'queued') {
            await api.cancelOperation(opId).catch(() => {});
          }
        }
        if (activeSubjectId) {
          await api.stopChat(activeSubjectId).catch(() => {});
        }
        store.setState({ activeOperations: new Map() });
        store.addToast('生成已停止', 'info');
      },
      onSwitchChatStyle: (style) => {
        store.setState((s) => ({
          activeSession: s.activeSession ? { ...s.activeSession, chat_style: style } : null,
          chat: { ...s.chat, chat_style: style }
        }));
      },
      onClearChat: async () => {
        const { activeSubjectId, activeSessionId } = store.getState();
        if (!confirm('确定要清空当前会话记录吗？')) return;
        if (activeSubjectId) {
          await api.clearChat(activeSubjectId).catch(() => {});
        }
        store.setState((s) => ({
          activeSession: s.activeSession ? { ...s.activeSession, messages: [] } : null,
          chat: { ...s.chat, messages: [] }
        }));
        store.addToast('会话已清空', 'info');
      },
      onClearSelectionContext: () => {
        store.setState({ selectionContext: null });
      },
      onUploadChatAttachment: async (file) => {
        const { activeSubjectId } = store.getState();
        if (!activeSubjectId) return;
        try {
          store.addToast('正在上传附件...', 'info');
          const att = await api.uploadChatAttachment(activeSubjectId, file);
          store.setState((s) => ({
            chatAttachments: [...s.chatAttachments, att]
          }));
          store.addToast('附件已添加', 'success');
        } catch (err) {
          store.addToast(`附件上传失败: ${err.message}`, 'error');
        }
      },
      onRemoveChatAttachment: (attId) => {
        store.setState((s) => ({
          chatAttachments: s.chatAttachments.filter((a) => a.id !== attId)
        }));
      },
      onInspectCitation: (citation) => {
        store.setState({
          citationModalOpen: true,
          activeCitation: citation
        });
      },

      // Session Management
      onSwitchSession: async (sessionId) => {
        try {
          const sess = await api.getSession(sessionId);
          store.setState({
            activeSessionId: sessionId,
            activeSession: sess
          });
        } catch (err) {
          store.addToast('切换会话失败', 'error');
        }
      },
      onCreateSession: async ({ title, source_version_ids }) => {
        const { activeSubjectId } = store.getState();
        if (!activeSubjectId) return;
        try {
          const sess = await api.createSession(activeSubjectId, { title, source_version_ids });
          store.setState((s) => ({
            sessions: [sess, ...s.sessions],
            activeSessionId: sess.id,
            activeSession: sess,
            createSessionModalOpen: false
          }));
          store.addToast(`已开启新会话「${title}」`, 'success');
        } catch (err) {
          store.addToast(`创建会话失败: ${err.message}`, 'error');
        }
      },
      onDeleteSession: async (sessionId) => {
        if (!confirm('确定要删除此会话吗？')) return;
        try {
          await api.deleteSession(sessionId);
          store.setState((s) => {
            const filtered = s.sessions.filter((sess) => sess.id !== sessionId);
            return {
              sessions: filtered,
              activeSessionId: filtered[0]?.id || null,
              activeSession: filtered[0] || null
            };
          });
          store.addToast('会话已删除', 'info');
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },

      // Learn View Actions
      onSelectSource: async (sourceId) => {
        store.setState({ activeSourceId: sourceId, activeAiDocument: null, activeAiDocumentId: null });
        await this.loadSourceVersions(sourceId);
      },
      onSelectAiDocument: async (docId) => {
        store.setState({ activeAiDocumentId: docId, activeSource: null, activeSourceId: null });
        await this.loadAiDocDetails(docId);
      },
      onTogglePinSource: (sourceId) => {
        store.setState((s) => {
          if (!s.activeSession) return {};
          const currentPins = s.activeSession.source_version_ids || [];
          const nextPins = currentPins.includes(sourceId)
            ? currentPins.filter((id) => id !== sourceId)
            : [...currentPins, sourceId];

          return {
            activeSession: { ...s.activeSession, source_version_ids: nextPins }
          };
        });
        store.addToast('已更新会话参考资料范围', 'info');
      },
      onClearActiveAnchor: () => {
        store.setState({ activeAnchor: null });
      },
      onExportCurrentDocument: () => {
        const { activeAiDocument, activeSource } = store.getState();
        const item = activeAiDocument || activeSource;
        if (!item) return;

        const content = item.content || item.text_content || '';
        const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${item.title || item.name || 'document'}.md`;
        a.click();
        URL.revokeObjectURL(url);
        store.addToast('已导出 Markdown 文件', 'success');
      },

      // Sources & AI Docs Actions
      onUploadSource: async (file) => {
        const { activeSubjectId } = store.getState();
        if (!activeSubjectId) return;
        try {
          store.addToast('正在上传并解析资料...', 'info');
          const accepted = await api.uploadSource(activeSubjectId, file);
          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          const sourcesList = await api.listSources(activeSubjectId);
          const sources = sourcesList.items || [];
          const created = sources[0];

          store.setState({
            sources,
            activeSourceId: created?.id || null,
            activeSource: created || null,
            sourcesTab: 'user_sources'
          });

          if (created?.id) {
            await this.loadSourceVersions(created.id);
          }
          store.addToast('资料上传与解析完毕', 'success');
        } catch (err) {
          store.addToast(`资料上传失败: ${err.message}`, 'error');
        }
      },
      onDeleteSource: async (sourceId) => {
        if (!confirm('确定要删除此资料吗？')) return;
        try {
          await api.deleteSource(sourceId);
          store.addToast('资料已删除', 'info');
          const { activeSubjectId } = store.getState();
          if (activeSubjectId) {
            const sourcesList = await api.listSources(activeSubjectId);
            const sources = sourcesList.items || [];
            store.setState({
              sources,
              activeSourceId: sources[0]?.id || null,
              activeSource: sources[0] || null
            });
          }
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onCreateAiDocument: async ({ title, content }) => {
        const { activeSubjectId } = store.getState();
        if (!activeSubjectId) return;
        try {
          store.addToast('正在创建 AI 文档...', 'info');
          const accepted = await api.createAiDocument(activeSubjectId, { title, content });
          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          const docsList = await api.listAiDocuments(activeSubjectId);
          const aiDocs = docsList.items || [];
          const created = aiDocs[0];

          store.setState({
            aiDocuments: aiDocs,
            activeAiDocumentId: created?.id || null,
            activeAiDocument: created || null,
            createAiDocModalOpen: false,
            sourcesTab: 'ai_documents'
          });

          if (created?.id) {
            await this.loadAiDocDetails(created.id);
          }
          store.addToast(`AI 文档「${title}」已创建`, 'success');
        } catch (err) {
          store.addToast(`创建文档失败: ${err.message}`, 'error');
        }
      },
      onProposeAiDocRevision: async (docId, instruction) => {
        try {
          store.addToast('AI 正在生成文档修改提案...', 'info');
          const accepted = await api.createAiDocumentRevisionProposal(docId, { instruction });
          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          await this.loadAiDocDetails(docId);
          store.setState({ aiDocRevisionModalOpen: false });
          store.addToast('修改提案已生成，请在右侧查看差异预览', 'success');
        } catch (err) {
          store.addToast(`生成修改提案失败: ${err.message}`, 'error');
        }
      },
      onApplyAiDocProposal: async (proposalId) => {
        try {
          const doc = await api.applyAiDocumentRevisionProposal(proposalId);
          store.setState({ activeAiDocument: doc, activeAiDocProposal: null });
          await this.loadAiDocDetails(doc.id);
          store.addToast('已应用修改，生成了新版本', 'success');
        } catch (err) {
          store.addToast(`应用修改失败: ${err.message}`, 'error');
        }
      },
      onDiscardAiDocProposal: async (proposalId) => {
        try {
          await api.discardAiDocumentRevisionProposal(proposalId);
          store.setState({ activeAiDocProposal: null });
          const { activeAiDocumentId } = store.getState();
          if (activeAiDocumentId) await this.loadAiDocDetails(activeAiDocumentId);
          store.addToast('已放弃修改提案', 'info');
        } catch (err) {
          store.addToast(err.message, 'error');
        }
      },
      onRestoreAiDocVersion: async (docId, versionId) => {
        try {
          const doc = await api.restoreAiDocumentVersion(docId, versionId);
          store.setState({ activeAiDocument: doc });
          await this.loadAiDocDetails(docId);
          store.addToast('已恢复至选定版本', 'success');
        } catch (err) {
          store.addToast(`恢复版本失败: ${err.message}`, 'error');
        }
      },

      // Quiz Gen Actions
      onCreateBlueprint: async ({ title, prompt }) => {
        const { activeSubjectId } = store.getState();
        if (!activeSubjectId) return;
        try {
          store.addToast('正在设计试卷蓝图...', 'info');
          const accepted = await api.parseBlueprint(activeSubjectId, prompt);
          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          const bpList = await api.listBlueprints(activeSubjectId);
          const bps = bpList.items || [];
          const created = bps[0];

          store.setState({
            blueprints: bps,
            activeBlueprintId: created?.id || null,
            activeBlueprint: created || null,
            blueprintModalOpen: false,
            examStudioSubTab: 'blueprint'
          });
          store.addToast('组卷蓝图已生成', 'success');
        } catch (err) {
          store.addToast(`生成蓝图失败: ${err.message}`, 'error');
        }
      },
      onConfirmBlueprint: async (blueprintId) => {
        try {
          const bp = await api.confirmBlueprint(blueprintId);
          store.setState((s) => ({
            activeBlueprint: bp,
            blueprints: s.blueprints.map((b) => (b.id === blueprintId ? bp : b))
          }));
          store.addToast('试卷设置已确认，可以开始组题', 'success');
        } catch (err) {
          store.addToast(`确认蓝图失败: ${err.message}`, 'error');
        }
      },
      onGenerateDraftFromBlueprint: async (blueprintId) => {
        try {
          store.addToast('正在按蓝图逐题生成试卷草稿...', 'info');
          const accepted = await api.generateDraftFromBlueprint(blueprintId);
          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          const { activeSubjectId } = store.getState();
          const draftsList = await api.listDrafts(activeSubjectId);
          const drafts = draftsList.items || [];
          const created = drafts[0];

          store.setState({
            drafts,
            activeDraftId: created?.id || null,
            activeDraft: created || null,
            examStudioSubTab: 'draft'
          });
          store.addToast('试题草稿生成完毕', 'success');
        } catch (err) {
          store.addToast(`生成草稿失败: ${err.message}`, 'error');
        }
      },
      onRetryDraftQuestion: async (draftId, questionId) => {
        try {
          store.addToast('正在重新生成该题目...', 'info');
          const accepted = await api.retryDraftQuestion(draftId, questionId);
          if (accepted.operation?.id) {
            store.trackOperation(accepted.operation);
            await api.pollOperation(accepted.operation.id, {
              onProgress: (op) => store.trackOperation(op)
            });
          }

          const updatedDraft = await api.getDraft(draftId);
          store.setState((s) => ({
            activeDraft: updatedDraft,
            drafts: s.drafts.map((d) => (d.id === draftId ? updatedDraft : d))
          }));
          store.addToast('题目已重新生成', 'success');
        } catch (err) {
          store.addToast(`重试题目失败: ${err.message}`, 'error');
        }
      },
      onPublishDraft: async (draftId) => {
        try {
          store.addToast('正在发布为正式试卷...', 'info');
          const exam = await api.publishDraft(draftId);
          const { activeSubjectId } = store.getState();
          const examsList = await api.listExams(activeSubjectId);

          store.setState({
            exams: examsList.items || [],
            activeExamId: exam.id,
            activeExam: exam,
            examStudioSubTab: 'exams'
          });
          store.addToast('试卷已正式发布！可在已发试卷或作答区查看', 'success');
        } catch (err) {
          store.addToast(`发布试卷失败: ${err.message}`, 'error');
        }
      },
      onSelectBlueprint: async (bpId) => {
        const bp = await api.getBlueprint(bpId).catch(() => null);
        store.setState({ activeBlueprintId: bpId, activeBlueprint: bp });
      },
      onSelectDraft: async (draftId) => {
        const draft = await api.getDraft(draftId).catch(() => null);
        store.setState({ activeDraftId: draftId, activeDraft: draft });
      },
      onSelectExam: async (examId) => {
        const exam = await api.getExam(examId).catch(() => null);
        store.setState({ activeExamId: examId, activeExam: exam, activeAttempt: null, activeAttemptReview: null });
      },
      onExportExam: async (examId, format = 'pdf', edition = 'questions') => {
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
          store.addToast('试卷排版已就绪', 'success');
        } catch (err) {
          store.addToast(`导出失败: ${err.message}`, 'error');
        }
      },

      // Attempts & Practice Actions (Ticket 10, 11, 21)
      onStartAttempt: async (examId, mode = 'practice') => {
        try {
          store.addToast(`正在初始化${mode === 'practice' ? '练习' : '考试'}答卷...`, 'info');
          const attempt = await api.createAttempt(examId, {
            mode,
            show_suggested_score: mode === 'practice'
          });

          store.setState((s) => ({
            activeNavTab: 'attempts',
            activeExamId: examId,
            activeAttemptId: attempt.id,
            activeAttempt: attempt,
            activeAttemptReview: null,
            attempts: [attempt, ...s.attempts]
          }));
        } catch (err) {
          store.addToast(`开启答卷失败: ${err.message}`, 'error');
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

            // Mark feedback as expired if answer modified after feedback
            const feedbacks = s.activeAttempt.feedback || [];
            const nextFeedbacks = feedbacks.map((f) =>
              f.question_id === questionId ? { ...f, is_expired: true } : f
            );

            return {
              activeAttempt: {
                ...s.activeAttempt,
                answers: nextAnswers,
                feedback: nextFeedbacks
              }
            };
          });
        } catch (err) {
          console.error('Auto-save answer error:', err);
        }
      },
      onRequestQuestionFeedback: async (attemptId, questionId) => {
        const { currentModelId } = store.getState();
        try {
          store.addToast('正在获取本题 AI 得分要点与解析...', 'info');
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
          store.addToast('本题解析与反馈已生成', 'success');
        } catch (err) {
          store.addToast(`获取解析失败: ${err.message}`, 'error');
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
      onSelectAttempt: async (attemptId) => {
        try {
          const att = await api.getAttempt(attemptId);
          if (att.is_completed || att.status === 'completed') {
            const review = await api.getAttemptReview(attemptId).catch(() => null);
            store.setState({ activeAttempt: att, activeAttemptReview: review });
            return;
          }
          store.setState({ activeAttempt: att, activeAttemptReview: null });
        } catch (err) {
          store.addToast('加载作答记录失败', 'error');
        }
      },
      onSelectTextForQuestion: (selectedText) => {
        store.setState({
          selectionContext: { text: selectedText }
        });
        const textarea = document.querySelector('#chat-input-textarea');
        if (textarea) {
          textarea.focus();
        }
        store.addToast('已将选中文字附加入对话上下文', 'info');
      },

      // Toast Dismiss
      onDismissToast: (toastId) => {
        store.removeToast(toastId);
      }
    };
  }
}

// Bootstrap Application
window.addEventListener('DOMContentLoaded', () => {
  const app = new App();
  app.init();
});
