import { marked } from '../vendor/marked.esm.js';
import DOMPurify from '../vendor/purify.esm.js';
import katex from '../vendor/katex/katex.mjs';

marked.setOptions({ gfm: true, breaks: true });

DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank');
    node.setAttribute('rel', 'noreferrer');
  }
});

const MATH_PLACEHOLDER = '\x00MATH';

function extractMath(source) {
  const placeholders = [];
  let result = '';
  let i = 0;

  while (i < source.length) {
    if (source.startsWith('```', i)) {
      const end = source.indexOf('```', i + 3);
      if (end !== -1) {
        result += source.slice(i, end + 3);
        i = end + 3;
        continue;
      }
    }

    if (source[i] === '`' && source[i + 1] !== '`') {
      let j = i + 1;
      while (j < source.length && source[j] !== '`') j += 1;
      if (j < source.length) {
        result += source.slice(i, j + 1);
        i = j + 1;
        continue;
      }
    }

    if (source.startsWith('$$', i)) {
      const end = source.indexOf('$$', i + 2);
      if (end !== -1) {
        placeholders.push({ latex: source.slice(i + 2, end), displayMode: true });
        result += `${MATH_PLACEHOLDER}${placeholders.length - 1}\x00`;
        i = end + 2;
        continue;
      }
    }

    if (source.startsWith('\\[', i)) {
      const end = source.indexOf('\\]', i + 2);
      if (end !== -1) {
        placeholders.push({ latex: source.slice(i + 2, end), displayMode: true });
        result += `${MATH_PLACEHOLDER}${placeholders.length - 1}\x00`;
        i = end + 2;
        continue;
      }
    }

    if (source.startsWith('\\(', i)) {
      const end = source.indexOf('\\)', i + 2);
      if (end !== -1) {
        placeholders.push({ latex: source.slice(i + 2, end), displayMode: false });
        result += `${MATH_PLACEHOLDER}${placeholders.length - 1}\x00`;
        i = end + 2;
        continue;
      }
    }

    if (source[i] === '$' && source[i + 1] !== '$') {
      const prev = i > 0 ? source[i - 1] : '';
      const next = source[i + 1] || '';
      if (!/\d/.test(prev) && !/\d/.test(next)) {
        let j = i + 1;
        let closed = false;
        while (j < source.length) {
          if (source[j] === '$' && source[j - 1] !== '\\') {
            const after = source[j + 1] || '';
            if (!/\d/.test(after)) {
              placeholders.push({ latex: source.slice(i + 1, j), displayMode: false });
              result += `${MATH_PLACEHOLDER}${placeholders.length - 1}\x00`;
              i = j + 1;
              closed = true;
              break;
            }
          }
          j += 1;
        }
        if (closed) continue;
      }
    }

    result += source[i];
    i += 1;
  }

  return { text: result, placeholders };
}

function restoreMath(html, placeholders) {
  return html.replace(/\x00MATH(\d+)\x00/g, (_, id) => {
    const item = placeholders[Number(id)];
    if (!item) return '';
    try {
      return katex.renderToString(item.latex.trim(), {
        displayMode: item.displayMode,
        throwOnError: false,
      });
    } catch {
      const body = escapeHtml(item.latex);
      return item.displayMode ? `<pre class="latex-fallback">${body}</pre>` : `<code>${body}</code>`;
    }
  });
}

function sanitizeHtml(html) {
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true, mathMl: true, svg: true },
    ADD_ATTR: ['style', 'class', 'target', 'rel'],
  });
}

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

export function blocksArePlainText(blocks) {
  if (!Array.isArray(blocks) || !blocks.length) return true;
  return blocks.every((block) => !block || block.type === 'markdown' || (!block.type && block.text != null));
}

export function textToMarkdownBlocks(text, existing) {
  const value = String(text ?? '');
  const first = Array.isArray(existing) ? existing.find((block) => block?.type === 'markdown' || block?.text != null) : null;
  return [{ id: first?.id || crypto.randomUUID().replaceAll('-', ''), type: 'markdown', text: value }];
}

export function nextOptionId(options) {
  const used = new Set((options || []).map((item) => item.id));
  const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  for (const letter of letters) {
    if (!used.has(letter)) return letter;
  }
  return `opt-${(options || []).length + 1}`;
}

export const QUESTION_TYPE_ORDER = [
  'single-choice',
  'multiple-choice',
  'fill-blank',
  'true-false',
  'short-answer',
  'argumentation',
  'extended-response',
];

export function renderMarkdown(text) {
  const source = String(text || '').replace(/\r\n/g, '\n');
  if (!source.trim()) return '';
  const { text: masked, placeholders } = extractMath(source);
  const parsed = marked.parse(masked);
  const withMath = restoreMath(parsed, placeholders);
  return sanitizeHtml(withMath);
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
        const blockId = escapeHtml(block.id || '');
        const latex = block.latex || '';
        try {
          const rendered = katex.renderToString(latex, { displayMode: true, throwOnError: true });
          return `<div class="latex-block" data-block-id="${blockId}">${rendered}</div>`;
        } catch {
          return `<pre class="latex-block" data-block-id="${blockId}">${escapeHtml(latex)}</pre>`;
        }
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
  { id: 'default', label: '普通问答' },
  { id: 'socratic', label: '追问引导' },
  { id: 'crash-course', label: '章节速成' },
];

export const GROUNDING_MODES = [
  { id: 'general-knowledge', label: '常识' },
  { id: 'strict', label: '只用资料' },
  { id: 'supplemental', label: '资料+补充' },
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
    run: { running: '进行中', succeeded: '完成', failed: '失败', canceled: '已取消', queued: '排队中', complete: '完成' },
  };
  const label = maps[kind]?.[value];
  return label !== undefined ? label : value || '';
}

export function groundingLabel(value) {
  return GROUNDING_MODES.find((item) => item.id === value)?.label || '常识';
}

export function styleLabel(value) {
  return CHAT_STYLES.find((item) => item.id === value)?.label || '普通问答';
}

export function isUploadedSource(source) {
  return !String(source?.id || '').startsWith('ai-document-');
}

export function uploadedSources(sources) {
  return (sources || []).filter(isUploadedSource);
}

export function readySourceVersionIds(sources) {
  return (sources || [])
    .map((source) => source.current_version?.id)
    .filter(Boolean);
}

export function defaultGroundingMode(sources, saved) {
  if (!readySourceVersionIds(sources).length) return 'general-knowledge';
  return saved || 'supplemental';
}

export function currentAiVersion(doc) {
  if (!doc) return null;
  return (doc.versions || []).find((item) => item.id === doc.current_version_id) || doc.versions?.[0] || null;
}

export function pendingProposal(items) {
  return (items || []).find((item) => item.status === 'ready' || item.status === 'generating') || null;
}

export function sanitizeErrorMessage(message) {
  const text = String(message || '').trim();
  if (!text) return '操作失败';
  const lower = text.toLowerCase();
  if (lower.includes('api key') || lower.includes('incorrect api key') || text.includes('sk-')) {
    return '模型服务拒绝了请求，请检查 API Key';
  }
  if (text.includes('{') || text.includes('"error"') || /https?:\/\//.test(text)) {
    const status = text.match(/HTTP (\d{3})/);
    if (status?.[1] === '401') return '模型服务拒绝了请求，请检查 API Key';
    if (status?.[1] === '403') return '模型服务暂时不可用';
    if (status?.[1] === '429') return '模型服务请求过于频繁，请稍后再试';
    if (status) return `模型服务返回错误（HTTP ${status[1]}）`;
    return '模型服务返回了无法展示的错误';
  }
  if (lower.includes('blank')) return '填空题缺少填空定义，请重试生成';
  if (lower.includes('scoring_point')) return '主观题缺少得分点，请重试生成';
  if (lower.includes('content block')) return '题目正文格式无效，请重试生成';
  if (/^['"]?[a-z_]+['"]?$/i.test(text)) return '题目结构不完整，请重试生成';
  return text;
}

export function sourceAnchorLabel(anchor, index) {
  const label = String(anchor?.location?.label || '').trim();
  const firstLine = blocksToText(anchor?.content).split('\n').map((line) => line.replace(/^#+\s*/, '').trim()).find(Boolean) || '';
  const last = label.split('/').map((part) => part.trim()).filter(Boolean).pop() || '';
  if (!label || last === firstLine || firstLine.startsWith(last) || last.startsWith(firstLine)) {
    const kind = anchor?.location?.kind;
    if (kind === 'page' || kind === 'slide') return `第 ${index + 1} ${kind === 'slide' ? '张' : '页'}`;
    return `原文位置 ${index + 1}`;
  }
  return last || label;
}

export function draftPublishState(draft) {
  const questions = draft?.questions || [];
  if (!questions.length) return { canPublish: false, needsConfirm: false };
  if (questions.some((item) => ['failed', 'generating', 'queued'].includes(item.status) || !item.question)) {
    return { canPublish: false, needsConfirm: false };
  }
  if (questions.some((item) => item.status === 'needs-review')) {
    return { canPublish: true, needsConfirm: true };
  }
  return { canPublish: true, needsConfirm: false };
}

export function answerForQuestion(attempt, questionId) {
  return (attempt?.answers || []).find((item) => item.question_id === questionId) || null;
}

export function feedbackForQuestion(attempt, questionId) {
  return (attempt?.feedback || []).find((item) => item.question_id === questionId) || null;
}

export function blankIdsForQuestion(question) {
  if (Array.isArray(question?.blank_ids) && question.blank_ids.length) return question.blank_ids;
  const fromAnswer = (question?.answer?.blanks || []).map((item) => item.id).filter(Boolean);
  if (fromAnswer.length) return fromAnswer;
  const text = blocksToText(question?.stem);
  const marks = text.match(/_{3,}|（\s*）|\(\s*\)/g);
  const count = Math.max(1, marks?.length || 1);
  return Array.from({ length: count }, (_, index) => `blank-${index + 1}`);
}

export function countBlanks(question) {
  return blankIdsForQuestion(question).length;
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
    const ids = blankIdsForQuestion(question);
    return {
      kind: 'fill-blank',
      blanks: ids.map((blankId, index) => ({
        blank_id: blankId,
        value: String(form.get(`q-${question.id}-b${index}`) || ''),
      })),
    };
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
