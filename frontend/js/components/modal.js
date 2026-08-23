import { escapeHtml, formatTime, statusLabel } from '../util.js';

export function renderModals(state, root, handlers) {
  const modal = state.modal;
  if (!modal) {
    root.innerHTML = '';
    root.onclick = null;
    return;
  }

  if (modal === 'subject' || modal === 'rename-subject') {
    const current = state.subjects.find((item) => item.id === state.activeSubjectId);
    const title = modal === 'rename-subject' ? '重命名科目' : '新建科目';
    root.innerHTML = dialog(
      title,
      `<label class="field"><span class="field-label">名称</span>
        <input class="input" id="subject-name" maxlength="80" value="${escapeHtml(modal === 'rename-subject' ? current?.name || '' : '')}" />
      </label>`,
      `<button type="button" class="btn btn-ghost" data-action="close">取消</button>
       <button type="button" class="btn btn-primary" data-action="save-subject">${modal === 'rename-subject' ? '保存' : '创建'}</button>`,
    );
  } else if (modal === 'confirm') {
    root.innerHTML = dialog(
      state.confirmTitle || '确认',
      `<p>${escapeHtml(state.confirmMessage || '')}</p>`,
      `<button type="button" class="btn btn-ghost" data-action="close">取消</button>
       <button type="button" class="btn btn-danger" data-action="confirm-ok">${escapeHtml(state.confirmOk || '确认')}</button>`,
    );
  } else if (modal === 'runs') {
    root.innerHTML = runsDialog(state);
  } else if (modal === 'exam-edition') {
    const selected = state.examEdition === 'solutions' ? 'solutions' : 'questions';
    root.innerHTML = dialog(
      state.examEditionTitle || '选择版别',
      `<p class="field-hint">答案版包含答案与解析</p>
       <label class="option"><input type="radio" name="exam-edition" value="questions" ${selected === 'questions' ? 'checked' : ''} /><span>题目版</span></label>
       <label class="option"><input type="radio" name="exam-edition" value="solutions" ${selected === 'solutions' ? 'checked' : ''} /><span>答案版</span></label>`,
      `<button type="button" class="btn btn-ghost" data-action="close">取消</button>
       <button type="button" class="btn btn-primary" data-action="confirm-exam-edition">确认</button>`,
    );
  } else {
    root.innerHTML = '';
    return;
  }

  root.querySelector('#subject-name')?.focus();
  const overlay = root.querySelector('.overlay');
  let closeArmed = false;
  overlay.addEventListener('pointerdown', (event) => {
    closeArmed = event.target === overlay;
  });
  overlay.addEventListener('click', (event) => {
    event.stopPropagation();
    const btn = event.target.closest('[data-action]');
    const action = btn?.dataset.action;
    if (action === 'close' || (event.target === overlay && closeArmed)) {
      handlers.onCloseModal();
      return;
    }
    if (action === 'save-subject') {
      const name = root.querySelector('#subject-name')?.value.trim();
      if (modal === 'rename-subject') handlers.onRenameSubject(name);
      else handlers.onCreateSubject(name);
    }
    if (action === 'confirm-ok') handlers.onConfirmModal();
    if (action === 'confirm-exam-edition') {
      const edition = root.querySelector('input[name="exam-edition"]:checked')?.value || 'questions';
      handlers.onConfirmExamEdition(edition);
    }
    if (action === 'run-evaluation') handlers.onRunEvaluation(btn.dataset.id);
    closeArmed = false;
  });
  root.onkeydown = (event) => {
    if (event.key === 'Escape') handlers.onCloseModal();
    if (event.key === 'Enter' && modal === 'exam-edition') {
      event.preventDefault();
      const edition = root.querySelector('input[name="exam-edition"]:checked')?.value || 'questions';
      handlers.onConfirmExamEdition(edition);
      return;
    }
    if (event.key === 'Enter' && (modal === 'subject' || modal === 'rename-subject')) {
      event.preventDefault();
      const name = root.querySelector('#subject-name')?.value.trim();
      if (modal === 'rename-subject') handlers.onRenameSubject(name);
      else handlers.onCreateSubject(name);
    }
  };
}

const RUN_LABELS = {
  'model-verification': '测试连接',
  'source-parsing': '资料解析',
  'chat-generation': '问答',
  'crash-course-generation': '章节速成',
  'blueprint-parsing': '解析蓝图',
  'exam-generation': '组题',
  'question-retry': '重试题目',
  'subjective-feedback': '题目反馈',
  'attempt-grading': '提交批改',
  'exam-revision': '改卷',
  'ai-document-generation': '生成文档',
  'ai-document-revision': '改文档',
  'exam-export': '导出',
  evaluation: '评估',
};

function runsDialog(state) {
  const runs = (state.orchestrationRuns || []).slice(0, 20);
  const suites = state.evaluationSuites || [];
  const evalRun = state.evaluationRun;
  const busy = state.runsBusy;
  const obs = evalRun?.model_observations || {};
  const metrics = evalRun?.orchestration_metrics || {};
  const body = `
    <p class="field-hint">外层耗时是软件编排，模型等待是生成时间，两者分开看。</p>
    <div class="run-list">
      ${
        runs.length
          ? runs
              .map(
                (item) => `
        <div class="run-row">
          <div>
            <div class="item-title">${escapeHtml(RUN_LABELS[item.category] || item.category)}</div>
            <div class="item-sub"><span>${statusLabel('run', item.status) || item.status}</span><span>外层 ${item.outer_elapsed_ms || 0} ms</span><span>模型 ${item.model_wait_ms || 0} ms</span><span>${formatTime(item.created_at)}</span></div>
          </div>
        </div>`,
              )
              .join('')
          : '<p class="item-sub">还没有运行记录</p>'
      }
    </div>
    ${
      suites.length
        ? `<div class="run-eval">
            <div class="item-title">固定评估</div>
            ${suites
              .map(
                (suite) => `
              <div class="run-row">
                <div>
                  <div class="item-title">${escapeHtml(suite.name)}</div>
                  <div class="item-sub">${suite.sample_count} 条样例</div>
                </div>
                <button type="button" class="btn btn-ghost btn-sm" data-action="run-evaluation" data-id="${suite.id}" ${busy ? 'disabled' : ''}>${busy === suite.id ? '评估中' : '跑一遍'}</button>
              </div>`,
              )
              .join('')}
          </div>`
        : ''
    }
    ${
      evalRun
        ? `<div class="run-eval">
            <div class="item-title">最近评估</div>
            <p class="item-sub">外层 ${metrics.outer_elapsed_ms || 0} ms · 模型 ${metrics.model_wait_ms || 0} ms</p>
            <p class="item-sub">模型结果：正确率 ${fmtRate(obs.answer_accuracy)} · 引用 ${fmtRate(obs.citation_accuracy)} · 得分点 ${fmtRate(obs.scoring_point_coverage)} · 泄漏 ${fmtRate(obs.answer_leakage_rate)}</p>
          </div>`
        : ''
    }
  `;
  return dialog(
    '运行记录',
    body,
    `<button type="button" class="btn btn-ghost" data-action="close">关闭</button>`,
  );
}

function fmtRate(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return `${Math.round(Number(value) * 100)}%`;
}

function dialog(title, body, actions) {
  return `
    <div class="overlay">
      <div class="dialog" role="dialog" aria-modal="true">
        <h2>${escapeHtml(title)}</h2>
        ${body}
        <div class="dialog-actions">${actions}</div>
      </div>
    </div>
  `;
}
