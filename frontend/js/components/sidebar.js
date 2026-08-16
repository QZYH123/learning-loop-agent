import { icons } from '../icons.js';

export function renderSidebar(state, container, handlers) {
  const tabs = [
    { id: 'sources', label: '资料金库', icon: icons.layers(16), count: state.sources?.length || 0 },
    { id: 'blueprint', label: '组卷蓝图', icon: icons.compass(16), count: state.blueprints?.length || 0 },
    { id: 'drafts', label: '题目工坊', icon: icons.sparkles(16), count: state.drafts?.length || 0 },
    { id: 'attempts', label: '试卷作答', icon: icons.target(16), count: state.exams?.length || 0 },
    { id: 'revisions', label: '差异比对', icon: icons.gitCompare(16), count: state.revisionProposals?.length || 0 },
    { id: 'renderer', label: '统一排版', icon: icons.printer(16) },
    { id: 'observability', label: '编排观测', icon: icons.activity(16), count: state.orchestrationRuns?.length || 0 }
  ];

  container.innerHTML = `
    <nav class="studio-tab-bar">
      <div class="studio-tab-list">
        ${tabs
          .map(
            (tab) => `
          <button class="studio-tab-btn ${state.activeTab === tab.id ? 'is-active' : ''}" data-tab="${tab.id}">
            <span>${tab.icon}</span>
            <span>${tab.label}</span>
            ${tab.count !== undefined && tab.count > 0 ? `<span class="tab-count-pill">${tab.count}</span>` : ''}
          </button>
        `
          )
          .join('')}
      </div>
    </nav>
  `;

  container.querySelectorAll('.studio-tab-btn').forEach((btn) => {
    btn.onclick = () => {
      const tabId = btn.getAttribute('data-tab');
      handlers.onSelectTab?.(tabId);
    };
  });
}
