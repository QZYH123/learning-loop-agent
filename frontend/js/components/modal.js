import { escapeHtml } from '../util.js';

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
    const action = event.target.closest('[data-action]')?.dataset.action;
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
    if (event.key === 'Enter' && modal !== 'confirm') {
      event.preventDefault();
      const name = root.querySelector('#subject-name')?.value.trim();
      if (modal === 'rename-subject') handlers.onRenameSubject(name);
      else handlers.onCreateSubject(name);
    }
  };
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
