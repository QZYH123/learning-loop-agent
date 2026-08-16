/**
 * Global Toast Notifications Component
 */

import { icons } from '../icons.js';

export function renderToasts(state, container, handlers) {
  const toasts = state.toasts || [];
  if (toasts.length === 0) {
    container.innerHTML = '';
    return;
  }

  container.innerHTML = `
    <div class="toast-container" role="region" aria-label="通知提示">
      ${toasts
        .map((t) => {
          let icon = icons.info(16);
          if (t.type === 'success') icon = icons.checkCircle(16);
          else if (t.type === 'error') icon = icons.alertTriangle(16);
          else if (t.type === 'warning') icon = icons.alertTriangle(16);

          return `
            <div class="toast-item toast-${t.type || 'info'}" role="alert">
              <span class="toast-icon">${icon}</span>
              <span class="toast-message">${escapeHtml(t.message || '')}</span>
              <button type="button" class="toast-close-btn" data-toast-id="${t.id}" title="关闭">
                ${icons.x(14)}
              </button>
            </div>
          `;
        })
        .join('')}
    </div>
  `;

  container.querySelectorAll('.toast-close-btn').forEach((btn) => {
    btn.onclick = () => {
      const id = btn.getAttribute('data-toast-id');
      handlers.onDismissToast?.(id);
    };
  });
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
