export function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

export function formatTime(ts) {
  if (!ts) return '';
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return '';
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  const hh = String(date.getHours()).padStart(2, '0');
  const mm = String(date.getMinutes()).padStart(2, '0');
  if (sameDay) return `${hh}:${mm}`;
  const md = `${date.getMonth() + 1}/${date.getDate()}`;
  return `${md} ${hh}:${mm}`;
}

export function truncate(text, max = 80) {
  const value = String(text || '').replace(/\s+/g, ' ').trim();
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

export function blocksToText(blocks) {
  if (typeof blocks === 'string') return blocks;
  if (!Array.isArray(blocks)) return '';
  return blocks
    .map((block) => {
      if (!block) return '';
      if (block.type === 'markdown' || block.text) return block.text || '';
      if (block.type === 'latex') return block.latex || '';
      if (block.type === 'table') {
        const head = (block.columns || []).join(' | ');
        const rows = (block.rows || []).map((row) => (row || []).join(' | ')).join('\n');
        return [head, rows].filter(Boolean).join('\n');
      }
      if (block.type === 'image') return block.alt || block.caption || '';
      return '';
    })
    .filter(Boolean)
    .join('\n');
}

export function renderInlineMarkdown(text) {
  let html = escapeHtml(text);
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/(^|[^\*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  html = html.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
  return html;
}

export function renderMarkdown(text) {
  const source = String(text || '').replace(/\r\n/g, '\n');
  if (!source.trim()) return '';
  const parts = source.split(/```([\s\S]*?)```/);
  return parts
    .map((part, index) => {
      if (index % 2 === 1) {
        const newline = part.indexOf('\n');
        const code = newline === -1 ? part : part.slice(newline + 1);
        return `<pre><code>${escapeHtml(code.replace(/\n$/, ''))}</code></pre>`;
      }
      return part
        .split(/\n{2,}/)
        .map((chunk) => {
          const lines = chunk.split('\n');
          if (lines.every((line) => /^\s*[-*]\s+/.test(line))) {
            const items = lines
              .map((line) => `<li>${renderInlineMarkdown(line.replace(/^\s*[-*]\s+/, ''))}</li>`)
              .join('');
            return `<ul>${items}</ul>`;
          }
          const heading = chunk.match(/^(#{1,3})\s+(.+)$/);
          if (heading && lines.length === 1) {
            const tag = `h${heading[1].length + 2}`;
            return `<${tag}>${renderInlineMarkdown(heading[2])}</${tag}>`;
          }
          return `<p>${renderInlineMarkdown(chunk).replaceAll('\n', '<br />')}</p>`;
        })
        .join('');
    })
    .join('');
}

export function renderBlocks(blocks, { examMode = false } = {}) {
  if (typeof blocks === 'string') return `<div class="prose">${renderMarkdown(blocks)}</div>`;
  if (!Array.isArray(blocks) || blocks.length === 0) return '';
  return blocks
    .map((block) => {
      if (!block) return '';
      if (block.type === 'markdown' || (!block.type && block.text)) {
        return `<div class="prose" data-block-id="${escapeHtml(block.id || '')}">${renderMarkdown(block.text || '')}</div>`;
      }
      if (block.type === 'latex') {
        return `<pre class="latex-block" data-block-id="${escapeHtml(block.id || '')}">${escapeHtml(block.latex || '')}</pre>`;
      }
      if (block.type === 'table') {
        const head = (block.columns || [])
          .map((col) => `<th>${escapeHtml(col)}</th>`)
          .join('');
        const rows = (block.rows || [])
          .map((row) => `<tr>${(row || []).map((cell) => `<td>${escapeHtml(cell)}</td>`).join('')}</tr>`)
          .join('');
        return `<table class="content-table" data-block-id="${escapeHtml(block.id || '')}"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table>`;
      }
      if (block.type === 'image' && block.asset && !examMode) {
        const src = `/api/source-versions/${encodeURIComponent(block.asset.source_version_id)}/assets/${encodeURIComponent(block.asset.asset_id)}`;
        return `<figure class="content-image" data-block-id="${escapeHtml(block.id || '')}"><img src="${src}" alt="${escapeHtml(block.alt || '')}" />${
          block.caption ? `<figcaption>${escapeHtml(block.caption)}</figcaption>` : ''
        }</figure>`;
      }
      return '';
    })
    .join('');
}

export function sessionVisible(session) {
  return Array.isArray(session?.messages) && session.messages.length > 0;
}

export function titleFromMessage(text, max = 24) {
  const line = String(text || '').replace(/\s+/g, ' ').trim();
  if (!line) return '对话';
  return line.length <= max ? line : line.slice(0, max);
}

export const CHAT_STYLES = [
  { id: 'default', label: '普通' },
  { id: 'socratic', label: '苏格拉底' },
  { id: 'crash-course', label: '章节速成' },
];

export const GROUNDING_MODES = [
  { id: 'general-knowledge', label: '常识' },
  { id: 'strict', label: '严格' },
  { id: 'supplemental', label: '补充' },
];

export const API_FORMATS = [
  { id: 'openai-chat-completions', label: 'Chat Completions', baseUrl: 'https://api.openai.com/v1', hint: '调用 /chat/completions' },
  { id: 'openai-responses', label: 'Responses', baseUrl: 'https://api.openai.com/v1', hint: '调用 /responses' },
  { id: 'ollama', label: 'Ollama', baseUrl: 'http://localhost:11434', hint: '调用原生 /api/chat' },
];

export function normalizeBaseUrl(value) {
  let url = String(value || '')
    .trim()
    .replace(/[。．]/g, '.')
    .replace(/／/g, '/');
  if (!url) return '';
  if (!/^https?:\/\//i.test(url)) url = `https://${url}`;
  url = url.replace(/\/+$/, '');
  for (const suffix of ['/chat/completions', '/completions', '/responses', '/api/chat', '/api/tags']) {
    if (url.endsWith(suffix)) {
      url = url.slice(0, -suffix.length);
      break;
    }
  }
  return url;
}

export const QUESTION_TYPES = {
  'single-choice': '单选',
  'multiple-choice': '多选',
  'fill-blank': '填空',
  'true-false': '判断',
  'short-answer': '简答',
  argumentation: '辨析',
  'extended-response': '大题',
};

export const DIFFICULTY = { easy: '较易', medium: '中等', hard: '较难' };

export function statusLabel(kind, value) {
  const maps = {
    source: { processing: '处理中', ready: '可用', failed: '失败', unavailable: '不可用' },
    blueprint: { parsing: '解析中', draft: '待确认', confirmed: '已确认', failed: '失败' },
    draft: { generating: '组题中', editable: '可编辑', failed: '失败', published: '已发布', queued: '排队中', complete: '已生成', 'needs-review': '待复查' },
    attempt: { 'in-progress': '作答中', paused: '已暂停', grading: '批改中', submitted: '已提交' },
    completion: { 'in-progress': '未完成', completed: '已完成' },
    grading: {
      'not-requested': '未批改',
      queued: '排队中',
      grading: '批改中',
      completed: '已批改',
      failed: '批改失败',
      stale: '需重评',
    },
    proposal: { generating: '生成中', ready: '待确认', applied: '已应用', discarded: '已放弃', failed: '失败' },
    message: { queued: '排队中', generating: '生成中', complete: '', stopped: '已停止', error: '失败' },
    validation: { unknown: '未验证', checking: '验证中', ok: '可用', error: '失败' },
  };
  return maps[kind]?.[value] || value || '';
}

export function groundingLabel(value) {
  return GROUNDING_MODES.find((item) => item.id === value)?.label || '常识';
}

export function styleLabel(value) {
  return CHAT_STYLES.find((item) => item.id === value)?.label || '普通';
}

export function looksLikeGenerate(text) {
  return /出一套|组一卷|组卷|出题|生成试卷|蓝图|来一套|做一套|出一份|帮我出|出张卷/.test(text);
}

export function looksLikeEdit(text) {
  return /改成|修改|换成|删掉|删除第|把.+改|调整|重写|补充|润色|把第/.test(text);
}

export function looksLikeCreateDoc(text) {
  return /整理|生成文档|写一份|做成笔记|摘要|提纲|复习材料/.test(text);
}

export function readySourceVersionIds(sources) {
  return (sources || [])
    .map((source) => source.current_version?.id)
    .filter(Boolean);
}

export function currentAiVersion(doc) {
  if (!doc) return null;
  return (doc.versions || []).find((item) => item.id === doc.current_version_id) || doc.versions?.[0] || null;
}

export function pendingProposal(items) {
  return (items || []).find((item) => item.status === 'ready' || item.status === 'generating') || null;
}

export function answerForQuestion(attempt, questionId) {
  return (attempt?.answers || []).find((item) => item.question_id === questionId) || null;
}

export function feedbackForQuestion(attempt, questionId) {
  return (attempt?.feedback || []).find((item) => item.question_id === questionId) || null;
}

export function countBlanks(question) {
  const text = blocksToText(question?.stem);
  const marks = text.match(/_{3,}|（\s*）|\(\s*\)/g);
  return Math.max(1, marks?.length || question?.answer_area?.lines || 1);
}

export function buildAnswerPayload(question, form) {
  const type = question.type;
  if (type === 'single-choice' || type === 'multiple-choice') {
    const optionIds = type === 'single-choice'
      ? [form.get(`q-${question.id}`)].filter(Boolean)
      : form.getAll(`q-${question.id}`);
    return { kind: 'choice', option_ids: optionIds };
  }
  if (type === 'true-false') {
    const value = form.get(`q-${question.id}`);
    if (value !== 'true' && value !== 'false') return null;
    return { kind: 'true-false', value: value === 'true' };
  }
  if (type === 'fill-blank') {
    const blanks = [];
    const count = countBlanks(question);
    for (let index = 0; index < count; index += 1) {
      blanks.push({
        blank_id: `blank-${index + 1}`,
        value: String(form.get(`q-${question.id}-b${index}`) || ''),
      });
    }
    return { kind: 'fill-blank', blanks };
  }
  return { kind: 'text', text: String(form.get(`q-${question.id}`) || '') };
}

export function officialSelection(selection) {
  if (!selection?.selected_text || !selection.document_kind || !selection.document_id || !selection.version_id) {
    return null;
  }
  if (!['exam', 'exam-draft', 'learning-artifact'].includes(selection.document_kind)) {
    return null;
  }
  return {
    document_kind: selection.document_kind,
    document_id: selection.document_id,
    version_id: selection.version_id,
    question_id: selection.question_id || null,
    block_id: selection.block_id || null,
    selected_text: selection.selected_text,
  };
}

export function bind(root, selector, event, handler) {
  root.querySelectorAll(selector).forEach((node) => {
    node.addEventListener(event, handler);
  });
}

export function closestAction(event, attr = 'data-action') {
  const target = event.target.closest(`[${attr}]`);
  if (!target) return null;
  return {
    el: target,
    action: target.getAttribute(attr),
    ...Object.fromEntries([...target.attributes].map((item) => [item.name.replace(/^data-/, '').replace(/-([a-z])/g, (_, ch) => ch.toUpperCase()), item.value])),
  };
}
