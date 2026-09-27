import { blocksToText, citationButton, escapeHtml, renderBlocks, visibleCitations } from '../util.js';

const BASIS_LABEL = {
  'general-knowledge': '常识',
  supplemental: '补充',
};

export function formatKey(answer) {
  if (!answer) return '';
  if (answer.kind === 'choice') return `答案 ${(answer.option_ids || []).join('、')}`;
  if (answer.kind === 'true-false') return `答案 ${answer.value ? '对' : '错'}`;
  if (answer.kind === 'fill-blank') {
    return `答案 ${(answer.blanks || []).map((item) => (item.acceptable_answers || []).join('/')).join('；')}`;
  }
  if (answer.reference_answer) return blocksToText(answer.reference_answer);
  return '';
}

export function renderSolution(question, options = {}) {
  if (!question) return '';
  const parts = [];
  if (options.showAnswer && question.answer) {
    const key = formatKey(question.answer);
    if (key) parts.push(`<div class="answer-key">${escapeHtml(key)}</div>`);
  }
  if (question.explanation?.length) {
    parts.push(`<div class="solution-section"><div class="solution-label">解析</div>${renderBlocks(question.explanation)}</div>`);
  }
  const points = (question.knowledge_points || []).filter(Boolean);
  if (points.length) {
    parts.push(`<div class="solution-section"><div class="solution-label">考点</div><div>${escapeHtml(points.join('、'))}</div></div>`);
  }
  const sources = renderSources(question.evidence, question.reliability);
  if (sources) parts.push(sources);
  return parts.length ? `<div class="solution">${parts.join('')}</div>` : '';
}

export function renderReview(feedback, options = {}) {
  if (!feedback) return '';
  const rows = [];
  const verdict = reviewVerdict(feedback);
  if (verdict) rows.push(`<div class="feedback-verdict">${escapeHtml(verdict)}</div>`);
  if (options.showSuggestedScore && feedback.suggested_score != null) {
    rows.push(`<div>建议分 ${escapeHtml(String(feedback.suggested_score))}</div>`);
  }
  const matched = pointTexts(feedback.matched_points);
  const missed = pointTexts(feedback.missed_points);
  if (matched.length) rows.push(reviewSection('已写到', matched));
  if (missed.length) rows.push(reviewSection('漏了', missed));
  if ((feedback.reasoning_issues || []).length) rows.push(reviewSection('思路', feedback.reasoning_issues));
  if ((feedback.suggestions || []).length) rows.push(reviewSection('建议', feedback.suggestions));
  if (feedback.reference_answer?.length) {
    rows.push(`<div class="feedback-section"><div class="solution-label">参考答案</div>${renderBlocks(feedback.reference_answer)}</div>`);
  }
  if (!rows.length) return '';
  return `<div class="feedback ${reviewTone(feedback)}">${rows.join('')}</div>`;
}

function renderSources(evidence, reliability) {
  const chips = visibleCitations(evidence?.citations).map(citationButton).filter(Boolean);
  if (!chips.length && BASIS_LABEL[evidence?.basis]) {
    chips.push(`<span class="cite">${BASIS_LABEL[evidence.basis]}</span>`);
  }
  if (evidence?.status === 'needs-review' || reliability === 'needs-review') {
    chips.push('<span class="status status-warn">待核查</span>');
  }
  if (!chips.length) return '';
  return `<div class="solution-section"><div class="solution-label">出处</div><div class="cite-row">${chips.join('')}</div></div>`;
}

function reviewVerdict(feedback) {
  if (feedback.status === 'unable-to-assess') return '无法判断';
  if (feedback.status === 'needs-review') return '待核查';
  if (feedback.correct === true) return '正确';
  if (feedback.correct === false) return '不正确';
  return '';
}

function reviewTone(feedback) {
  if (feedback.status === 'unable-to-assess' || feedback.status === 'needs-review') return 'is-warn';
  if (feedback.correct === false) return 'is-wrong';
  if (feedback.correct === true) return 'is-ok';
  return '';
}

function pointTexts(points) {
  return (points || []).map((item) => item?.description).filter(Boolean);
}

function reviewSection(label, items) {
  return `<div class="feedback-section"><div class="solution-label">${escapeHtml(label)}</div>${items
    .map((item) => `<div>${escapeHtml(item)}</div>`)
    .join('')}</div>`;
}
