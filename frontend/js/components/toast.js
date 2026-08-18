import { icons } from '../icons.js';
import { escapeHtml } from '../util.js';

export function renderToasts(state, root, handlers) {
  const toasts = state.toasts || [];
  root.innerHTML = toasts.length
    ? `<div class="toasts">${toasts
        .map(
          (toast) => `
        <div class="toast toast-${toast.type}">
          ${toast.type === 'error' ? icons.alertTriangle(16) : toast.type === 'success' ? icons.check(16) : icons.info(16)}
          <div>${escapeHtml(toast.message)}</div>
          <button type="button" class="ghost-icon" data-id="${toast.id}" aria-label="关闭">${icons.x(12)}</button>
        </div>
      `,
        )
        .join('')}</div>`
    : '';
  root.onclick = (event) => {
    const btn = event.target.closest('[data-id]');
    if (btn) handlers.onDismissToast(btn.dataset.id);
  };
}
