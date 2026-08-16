import { icon } from '../icons.js';

export function renderToasts(stateOrToasts, container, handlers) {
  const toasts = Array.isArray(stateOrToasts) ? stateOrToasts : (stateOrToasts?.toasts || []);
  if (!container) return '';

  if (!toasts || toasts.length === 0) {
    container.innerHTML = '';
    return;
  }

  container.innerHTML = `
    <div class="toast-container" data-testid="toast-container">
      ${toasts
        .map((t) => {
          const iconName = t.type === 'error' ? 'alertTriangle' : t.type === 'success' ? 'check' : 'info';
          return `
          <div class="toast-item toast-${t.type}" data-toast-id="${t.id}">
            <span class="toast-icon">${icon(iconName, 16)}</span>
            <div class="toast-content" style="flex: 1;">${escapeHtml(t.message)}</div>
            <button type="button" class="btn-icon-hud btn-close-toast" data-toast-id="${t.id}" style="width: 20px; height: 20px; margin-left: 6px;" aria-label="关闭通知">
              ${icon('x', 12)}
            </button>
          </div>
        `;
        })
        .join('')}
    </div>
  `;

  container.querySelectorAll('.btn-close-toast').forEach((btn) => {
    btn.onclick = () => {
      const toastId = btn.getAttribute('data-toast-id');
      handlers?.onDismissToast?.(toastId);
    };
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}
