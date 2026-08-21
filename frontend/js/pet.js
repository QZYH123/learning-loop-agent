/**
 * 桌宠「小墨」：住在书桌上的一滴活墨水。
 * 自足模块：自己挂载、自己取数、自己动；后端不可用时静默隐藏。
 * 形象随主题换装：纸面主题是墨团（--bubble-user），黑板主题自动变粉笔团。
 */
import { api } from './api.js';
import { icons } from './icons.js';

const STAGE_SIZE = [54, 58, 68, 78];
const STAGE_TITLE = ['神秘的蛋', '小墨滴', '墨团', '大墨团'];
const BADGES = [
  { id: 'exam_1', label: '首份试卷', icon: 'book' },
  { id: 'attempt_1', label: '首次交卷', icon: 'checkSquare' },
  { id: 'streak_7', label: '七日连学', icon: 'zap' },
  { id: 'ink_100', label: '百滴墨水', icon: 'sparkles' },
];
const PHRASES = {
  pat: ['墨墨在呢', '呼呼——', '蹭蹭你', '今天也要加油', '嘿嘿'],
  patEgg: ['里面好像有动静…', '小心轻放', '再学一点就孵化了'],
  patLimit: ['摸太多要化啦', '够啦够啦'],
  correct: ['答对啦！', '就是这样', '厉害'],
  feedback: ['错题也是墨水', '记下来了', '下次就会了'],
  attemptCompleted: ['交卷辛苦了！', '给你鼓掌'],
  examPublished: ['新卷子出炉', '去做做看？'],
  levelup: ['小墨长大了！'],
  hatch: ['你好呀，我是小墨'],
  comeback: ['好久不见！', '想你了'],
};

const state = {
  data: null,
  root: null,
  sleeping: false,
  cardOpen: false,
  renaming: false,
  dragging: false,
  reduced: false,
  idleTimer: null,
  blinkTimer: null,
  tagTimer: null,
  bubbleTimer: null,
  refreshTimer: null,
  failed: false,
};

function esc(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function pick(list) {
  return list[Math.floor(Math.random() * list.length)];
}

// ---------- SVG 形象 ----------

function faceSvg({ eyeY, mouthY, blushY }) {
  const L = 50 - 9.5;
  const R = 50 + 9.5;
  return `
    <g class="pet-face">
      <ellipse class="pet-blush" cx="33" cy="${blushY}" rx="4.6" ry="2.4"/>
      <ellipse class="pet-blush" cx="67" cy="${blushY}" rx="4.6" ry="2.4"/>
      <g class="pet-eyes">
        <g class="pet-eye">
          <ellipse class="pet-eye-white" cx="${L}" cy="${eyeY}" rx="5.6" ry="6.4"/>
          <circle class="pet-pupil" cx="${L}" cy="${eyeY + 0.6}" r="2.7"/>
          <circle class="pet-glint" cx="${L - 1.6}" cy="${eyeY - 1.8}" r="1.1"/>
        </g>
        <g class="pet-eye">
          <ellipse class="pet-eye-white" cx="${R}" cy="${eyeY}" rx="5.6" ry="6.4"/>
          <circle class="pet-pupil" cx="${R}" cy="${eyeY + 0.6}" r="2.7"/>
          <circle class="pet-glint" cx="${R - 1.6}" cy="${eyeY - 1.8}" r="1.1"/>
        </g>
        <g class="pet-lids">
          <path d="M${L - 4.8} ${eyeY} q4.8 3.6 9.6 0"/>
          <path d="M${R - 4.8} ${eyeY} q4.8 3.6 9.6 0"/>
        </g>
      </g>
      <path class="pet-mouth" d="M46.4 ${mouthY} Q50 ${mouthY + 3.4} 53.6 ${mouthY}"/>
    </g>`;
}

function bodySvg(stage) {
  if (stage === 0) {
    return `
      <g class="pet-body pet-egg">
        <path class="pet-shell" d="M50 20 C37 20 29 40 29 58 C29 75 38 87 50 87 C62 87 71 75 71 58 C71 40 63 20 50 20 Z"/>
        <circle class="pet-speck" cx="44" cy="46" r="1.6"/>
        <circle class="pet-speck" cx="57" cy="52" r="1.2"/>
        <circle class="pet-speck" cx="48" cy="64" r="1.4"/>
        <circle class="pet-speck" cx="58" cy="70" r="1"/>
        <circle class="pet-speck" cx="41" cy="58" r="1"/>
      </g>`;
  }
  if (stage === 1) {
    return `
      <g class="pet-body">
        <path class="pet-ink" d="M50 16 C46 26 26 42 26 61 C26 77 36.5 88 50 88 C63.5 88 74 77 74 61 C74 42 54 26 50 16 Z"/>
        <path class="pet-sheen" d="M36 46 C33 54 34 62 37 67 C33 61 31.5 52 34.5 45 C35 44 36.5 44.5 36 46 Z"/>
        ${faceSvg({ eyeY: 58, mouthY: 68, blushY: 66 })}
      </g>`;
  }
  if (stage === 2) {
    return `
      <g class="pet-body">
        <path class="pet-ink" d="M50 22 C33 22 21 35 20 51 C19 68 30 86 50 86 C70 86 81 68 80 51 C79 35 67 22 50 22 Z"/>
        <path class="pet-ink pet-flick" d="M50 22 C51 16 55 12.5 59 10.5 C55.5 15 54 19 53.6 22.6 Z"/>
        <path class="pet-sheen" d="M31 40 C27 48 27 58 31 65 C25.5 58 25 46 29.5 39 C30.2 38 31.5 38.8 31 40 Z"/>
        ${faceSvg({ eyeY: 52, mouthY: 63, blushY: 61 })}
      </g>`;
  }
  return `
    <g class="pet-body">
      <path class="pet-ink" d="M50 20 C31 20 17.5 34 16.5 51 C15.5 70 28 88 50 88 C72 88 84.5 70 83.5 51 C82.5 34 69 20 50 20 Z"/>
      <path class="pet-ink pet-flick" d="M52 20 C53 14 57 10.5 61 8.5 C57.5 13 56 17 55.6 20.6 Z"/>
      <path class="pet-sheen" d="M28 38 C23.5 47 23.5 59 28 67 C21.5 59 21 45 26.5 37 C27.2 36 28.6 36.8 28 38 Z"/>
      <g class="pet-hat">
        <path class="pet-hat-paper" d="M33 29 L50 13 L67 29 Q50 35.5 33 29 Z"/>
        <path class="pet-hat-fold" d="M50 13 L50 30.5"/>
        <circle class="pet-hat-dot" cx="58.5" cy="25" r="1.9"/>
      </g>
      ${faceSvg({ eyeY: 50, mouthY: 62, blushY: 60 })}
    </g>`;
}

function petSvg(stage) {
  return `
    <svg class="pet-svg" viewBox="0 0 100 100" aria-hidden="true">
      <ellipse class="pet-shadow" cx="50" cy="93" rx="25" ry="4.5"/>
      ${bodySvg(stage)}
    </svg>`;
}

// ---------- 渲染 ----------

function stageOf() {
  return state.data?.stage ?? 0;
}

const CLAMP = { x: [2, 98], y: [16, 100] };

function clamp(value, [min, max]) {
  return Math.min(max, Math.max(min, Number(value)));
}

function applyPosition() {
  if (!state.root || !state.data) return;
  if (state.data.hidden) {
    // 收纳态贴边，不做常规夹取
    state.root.style.left = `${clamp(state.data.position_x ?? 78, [0, 100])}%`;
    state.root.style.top = `calc(${clamp(state.data.position_y ?? 100, [0, 100])}% - 4px)`;
    return;
  }
  const x = clamp(state.data.position_x ?? 78, CLAMP.x);
  const y = clamp(state.data.position_y ?? 100, CLAMP.y);
  state.root.style.left = `${x}%`;
  state.root.style.top = `calc(${y}% - 4px)`;
  // 靠上时台词与名片翻到脚下，避免顶出视口
  state.root.classList.toggle('is-low', (y / 100) * window.innerHeight < 380);
}

function dockEdge() {
  const x = Number(state.data?.position_x ?? 78);
  const y = Number(state.data?.position_y ?? 100);
  if (y >= 99) return 'bottom';
  if (x <= 1) return 'left';
  if (x >= 99) return 'right';
  return 'bottom';
}

function render() {
  const { root, data } = state;
  if (!root || !data) return;
  if (data.hidden) {
    root.className = `pet is-peek is-dock-${dockEdge()}`;
    root.innerHTML = `
      <button type="button" class="pet-peek" title="叫${esc(data.name)}出来">
        <svg viewBox="0 0 40 22" aria-hidden="true">
          <path class="pet-ink" d="M20 2 C9 2 3 10 3 22 L37 22 C37 10 31 2 20 2 Z"/>
          <path class="pet-peek-lid" d="M11 14 q3 2.6 6 0"/>
          <path class="pet-peek-lid" d="M23 14 q3 2.6 6 0"/>
        </svg>
      </button>`;
    applyPosition();
    bindPetEvents();
    return;
  }
  const size = STAGE_SIZE[stageOf()];
  root.style.setProperty('--pet-h', `${size}px`);
  root.className = `pet${state.reduced ? ' is-reduced' : ''}${state.sleeping ? ' is-sleeping' : ''}`;
  root.innerHTML = `
    <div class="pet-bubble" hidden></div>
    <button type="button" class="pet-tag" hidden>
      <span class="pet-tag-name"></span><span class="pet-tag-stage"></span>
    </button>
    <div class="pet-zz" hidden><span>z</span><span>z</span></div>
    <div class="pet-stage" style="width:${size}px;height:${size}px">${petSvg(stageOf())}</div>
    <div class="pet-fx"></div>
    <div class="pet-card-slot"></div>
  `;
  syncTag();
  applyPosition();
  bindPetEvents();
}

function syncTag() {
  const tag = state.root?.querySelector('.pet-tag');
  if (!tag || !state.data) return;
  tag.querySelector('.pet-tag-name').textContent = state.data.name;
  tag.querySelector('.pet-tag-stage').textContent = STAGE_TITLE[stageOf()];
}

// ---------- 台词气泡与粒子 ----------

function say(text, ms = 2800) {
  const bubble = state.root?.querySelector('.pet-bubble');
  if (!bubble || !text) return;
  bubble.textContent = text;
  bubble.hidden = false;
  bubble.classList.remove('is-in');
  void bubble.offsetWidth;
  bubble.classList.add('is-in');
  clearTimeout(state.bubbleTimer);
  state.bubbleTimer = setTimeout(() => { bubble.hidden = true; }, ms);
}

function burst(kind) {
  if (state.reduced) return;
  const fx = state.root?.querySelector('.pet-fx');
  if (!fx) return;
  const count = kind === 'confetti' ? 8 : 5;
  for (let i = 0; i < count; i += 1) {
    const bit = document.createElement('span');
    const x = (Math.random() - 0.5) * 52;
    const delay = Math.random() * 120;
    bit.style.setProperty('--fx-x', `${x}px`);
    bit.style.animationDelay = `${delay}ms`;
    if (kind === 'confetti') {
      bit.className = 'pet-bit pet-bit-confetti';
      bit.style.setProperty('--fx-c', ['var(--blue)', 'var(--emerald)', 'var(--amber)', 'var(--crimson)'][i % 4]);
    } else if (kind === 'heart') {
      bit.className = 'pet-bit pet-bit-heart';
      bit.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 21s-7.5-4.9-10-9.6C.4 8 2.4 4.5 6 4.5c2.3 0 3.9 1.3 6 3.8 2.1-2.5 3.7-3.8 6-3.8 3.6 0 5.6 3.5 4 6.9C19.5 16.1 12 21 12 21Z"/></svg>';
    } else {
      bit.className = 'pet-bit pet-bit-drop';
      bit.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 3 C10 8 6 11 6 15 a6 6 0 0 0 12 0 C18 11 14 8 12 3 Z"/></svg>';
    }
    fx.appendChild(bit);
    setTimeout(() => bit.remove(), 1100 + delay);
  }
}

// ---------- 动作 ----------

function play(anim) {
  const stageEl = state.root?.querySelector('.pet-stage');
  if (!stageEl || state.reduced) return;
  const cls = `is-${anim}`;
  stageEl.classList.remove(cls);
  void stageEl.offsetWidth;
  stageEl.classList.add(cls);
  stageEl.addEventListener('animationend', () => stageEl.classList.remove(cls), { once: true });
}

function wake() {
  if (!state.sleeping) return;
  state.sleeping = false;
  state.root?.classList.remove('is-sleeping');
  const zz = state.root?.querySelector('.pet-zz');
  if (zz) zz.hidden = true;
}

function fallAsleep() {
  if (state.sleeping || state.cardOpen || !state.data || state.data.hidden) return;
  state.sleeping = true;
  state.root?.classList.add('is-sleeping');
  const zz = state.root?.querySelector('.pet-zz');
  if (zz) zz.hidden = false;
}

function resetIdle() {
  clearTimeout(state.idleTimer);
  state.idleTimer = setTimeout(fallAsleep, 4 * 60 * 1000);
}

function scheduleBlink() {
  clearTimeout(state.blinkTimer);
  state.blinkTimer = setTimeout(() => {
    if (!state.sleeping && !state.reduced && stageOf() > 0) {
      state.root?.classList.add('is-blink');
      setTimeout(() => state.root?.classList.remove('is-blink'), 150);
    }
    scheduleBlink();
  }, 2500 + Math.random() * 3500);
}

function showTag(ms = 4000) {
  const tag = state.root?.querySelector('.pet-tag');
  if (!tag) return;
  tag.hidden = false;
  clearTimeout(state.tagTimer);
  state.tagTimer = setTimeout(() => {
    if (!state.cardOpen) tag.hidden = true;
  }, ms);
}

async function pat() {
  wake();
  resetIdle();
  play('squish');
  showTag();
  let grew = false;
  try {
    const before = state.data;
    state.data = await api.patPet();
    grew = detectStageChange(before, state.data);
  } catch { /* 后端不可用时保持纯本地反应 */ }
  if (!grew) {
    const egg = stageOf() === 0;
    const over = (state.data?.pats_today ?? 0) > 5;
    say(egg ? pick(PHRASES.patEgg) : over ? pick(PHRASES.patLimit) : pick(PHRASES.pat));
    burst(Math.random() < 0.34 ? 'heart' : 'drop');
  }
  syncTag();
}

// ---------- 名片 ----------

function moodLine() {
  const d = state.data;
  if (!d) return '';
  if (state.sleeping) return 'Zzz…';
  if (d.stage === 0) return '多学一点，它就会孵化';
  if (d.ink_today > 0 && d.streak_days >= 3) return '状态正好，继续保持';
  if (d.ink_today > 0) return '今天也有在学，真好';
  if (d.streak_days > 0) return '等你来滴一滴墨';
  return '从一道题开始吧';
}

function cardHtml() {
  const d = state.data;
  const nextLine = d.ink_to_next == null
    ? `墨水 ${d.ink_total} · 已经很棒啦`
    : `墨水 ${d.ink_total} · 还差 ${d.ink_to_next} 长大`;
  const span = d.ink_to_next == null ? 1 : d.ink_total / (d.ink_total + d.ink_to_next);
  const dots = (d.recent_days || []).slice(-7).map((day) => (
    `<i class="pet-dot${day.ink > 0 ? ' is-on' : ''}" title="${esc(day.date)}${day.ink > 0 ? ` +${day.ink}` : ''}"></i>`
  )).join('');
  const answers = (d.today?.correct_answers ?? 0) + (d.today?.feedback_received ?? 0);
  const badges = BADGES.map((meta) => {
    const earned = (d.badges || []).some((item) => item.id === meta.id && item.earned);
    return `<span class="pet-badge${earned ? ' is-earned' : ''}" title="${meta.label}">${icons[meta.icon](12)}<i>${meta.label}</i></span>`;
  }).join('');
  return `
    <div class="pet-card" role="dialog" aria-label="桌宠名片">
      <div class="pet-card-head">
        ${state.renaming
          ? `<input class="pet-card-input" maxlength="12" value="${esc(d.name)}" aria-label="改名">`
          : `<span class="pet-card-name">${esc(d.name)}</span>
             <button type="button" class="ghost-icon" data-pet="rename" title="改名">${icons.edit3(13)}</button>`}
        <span class="pet-card-stage">${STAGE_TITLE[d.stage]}</span>
      </div>
      <div class="pet-card-bar"><i style="width:${Math.round(span * 100)}%"></i></div>
      <div class="pet-card-sub">${esc(nextLine)}</div>
      <div class="pet-card-row"><span>连续学习 ${d.streak_days} 天</span><span class="pet-dots">${dots}</span></div>
      <div class="pet-card-row pet-card-today">今日 +${d.ink_today} 墨水 · 答题 ${answers} · 对话 ${d.today?.chat_messages ?? 0}</div>
      <div class="pet-card-badges">${badges}</div>
      <div class="pet-card-foot">
        <span class="pet-card-mood">「${esc(moodLine())}」</span>
        <button type="button" class="btn btn-ghost btn-sm" data-pet="hide">藏起来</button>
      </div>
    </div>`;
}

function closeCard() {
  state.cardOpen = false;
  state.renaming = false;
  const slot = state.root?.querySelector('.pet-card-slot');
  if (slot) slot.innerHTML = '';
  document.removeEventListener('pointerdown', onOutsidePointer, true);
  document.removeEventListener('keydown', onCardKey, true);
}

function onOutsidePointer(event) {
  if (!state.root?.contains(event.target)) closeCard();
}

function onCardKey(event) {
  if (event.key === 'Escape') closeCard();
}

async function openCard() {
  wake();
  resetIdle();
  try {
    state.data = await api.getPet();
  } catch { /* 展示已有数据 */ }
  state.cardOpen = true;
  const tag = state.root?.querySelector('.pet-tag');
  if (tag) tag.hidden = true;
  const slot = state.root?.querySelector('.pet-card-slot');
  if (!slot) return;
  slot.innerHTML = cardHtml();
  clampCard();
  document.addEventListener('pointerdown', onOutsidePointer, true);
  document.addEventListener('keydown', onCardKey, true);
}

function clampCard() {
  const card = state.root?.querySelector('.pet-card');
  if (!card) return;
  const rect = card.getBoundingClientRect();
  if (rect.left < 8) card.style.transform = `translateX(${8 - rect.left}px)`;
  else if (rect.right > window.innerWidth - 8) card.style.transform = `translateX(${window.innerWidth - 8 - rect.right}px)`;
}

async function commitRename(input) {
  const name = String(input.value || '').trim();
  state.renaming = false;
  if (name && name !== state.data.name) {
    if (name.length > 12) { say('名字要 1–12 字'); }
    else {
      try {
        state.data = await api.updatePet({ name });
      } catch { say('改名没成功'); }
    }
  }
  if (state.cardOpen) { await openCard(); }
  syncTag();
}

// ---------- 拖拽与点击 ----------

function bindPetEvents() {
  const { root } = state;
  if (!root) return;
  const peek = root.querySelector('.pet-peek');
  if (peek) {
    peek.addEventListener('click', async () => {
      // 从贴边处把小墨拉回视口内
      const edge = dockEdge();
      const patch = { hidden: false };
      if (edge === 'left') patch.position_x = 7;
      else if (edge === 'right') patch.position_x = 93;
      else patch.position_y = 100;
      try {
        state.data = await api.updatePet(patch);
      } catch { return; }
      render();
      play('land');
      say(pick(PHRASES.pat));
    });
    return;
  }
  const stageEl = root.querySelector('.pet-stage');
  const tag = root.querySelector('.pet-tag');

  stageEl.addEventListener('pointerenter', () => { if (!state.cardOpen) showTag(2600); });
  stageEl.addEventListener('pointerdown', (event) => {
    event.preventDefault();
    const start = { x: event.clientX, y: event.clientY };
    const rect = root.getBoundingClientRect();
    const anchor = { x: rect.left, y: rect.top + 4 };
    let moved = false;
    const onMove = (ev) => {
      const dx = ev.clientX - start.x;
      const dy = ev.clientY - start.y;
      if (!moved && Math.abs(dx) < 4 && Math.abs(dy) < 4) return;
      moved = true;
      state.dragging = true;
      root.classList.add('is-dragging');
      state.data.position_x = clamp(((anchor.x + dx) / window.innerWidth) * 100, CLAMP.x);
      state.data.position_y = clamp(((anchor.y + dy) / window.innerHeight) * 100, CLAMP.y);
      applyPosition();
    };
    const onUp = async () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      root.classList.remove('is-dragging');
      if (moved) {
        state.dragging = false;
        play('land');
        try {
          state.data = await api.updatePet({
            position_x: state.data.position_x,
            position_y: state.data.position_y,
          });
        } catch { /* 下次再存 */ }
      } else {
        await pat();
      }
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  });

  tag.addEventListener('click', (event) => {
    event.stopPropagation();
    if (state.cardOpen) closeCard();
    else openCard();
  });

  root.addEventListener('click', async (event) => {
    const action = event.target.closest('[data-pet]')?.dataset.pet;
    if (!action) return;
    if (action === 'rename') {
      state.renaming = true;
      const slot = root.querySelector('.pet-card-slot');
      slot.innerHTML = cardHtml();
      clampCard();
      const input = slot.querySelector('.pet-card-input');
      input?.focus();
      input?.select();
      input?.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') input.blur(); });
      input?.addEventListener('blur', () => commitRename(input));
    } else if (action === 'hide') {
      closeCard();
      // 吸附到最近的不遮挡操作的边框（左/右/下），点边上的小墨角随时回来
      const rect = root.getBoundingClientRect();
      const xPx = rect.left;
      const yPx = rect.top + 4;
      const distances = [
        ['left', xPx],
        ['right', window.innerWidth - xPx],
        ['bottom', window.innerHeight - yPx],
      ].sort((a, b) => a[1] - b[1]);
      const edge = distances[0][0];
      const patch = { hidden: true };
      if (edge === 'left') patch.position_x = 0;
      else if (edge === 'right') patch.position_x = 100;
      else patch.position_y = 100;
      try {
        state.data = await api.updatePet(patch);
      } catch { return; }
      render();
    }
  });
}

// ---------- 瞳孔跟随 ----------

let lastFollow = 0;
function followPointer(event) {
  const now = Date.now();
  if (now - lastFollow < 60 || state.sleeping || state.dragging || !state.root || stageOf() === 0) return;
  lastFollow = now;
  const stageEl = state.root.querySelector('.pet-stage');
  if (!stageEl) return;
  const rect = stageEl.getBoundingClientRect();
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2;
  const dx = Math.max(-1, Math.min(1, (event.clientX - cx) / 240));
  const dy = Math.max(-1, Math.min(1, (event.clientY - cy) / 240));
  for (const pupil of state.root.querySelectorAll('.pet-pupil, .pet-glint')) {
    pupil.style.transform = `translate(${(dx * 2.2).toFixed(2)}px, ${(dy * 1.6).toFixed(2)}px)`;
  }
}

// ---------- 成长与事件 ----------

function detectStageChange(before, after) {
  if (!before || !after || after.stage === before.stage) return false;
  render();
  if (before.stage === 0 && after.stage >= 1) {
    play('hatch');
    say(pick(PHRASES.hatch), 3600);
    burst('drop');
  } else if (after.stage > before.stage) {
    play('tada');
    say(pick(PHRASES.levelup), 3600);
    burst('confetti');
  }
  return after.stage > before.stage;
}

function scheduleRefresh() {
  clearTimeout(state.refreshTimer);
  state.refreshTimer = setTimeout(async () => {
    try {
      const before = state.data;
      state.data = await api.getPet();
      detectStageChange(before, state.data);
      if (state.data.hidden !== before?.hidden) render();
      syncTag();
    } catch { /* 保持现状 */ }
  }, 2500);
}

/** app.js 在学习事件发生时调用；桌宠不可用时静默无操作。 */
export function petNotify(type) {
  if (!state.root || !state.data || state.data.hidden || state.failed) return;
  wake();
  resetIdle();
  if (type === 'chat') {
    if (Math.random() < 0.3) play('wiggle');
  } else if (type === 'correct') {
    play('hop');
    say(pick(PHRASES.correct));
  } else if (type === 'feedback') {
    play('wiggle');
    say(pick(PHRASES.feedback));
  } else if (type === 'attempt-completed') {
    play('tada');
    say(pick(PHRASES.attemptCompleted), 3200);
    burst('confetti');
  } else if (type === 'exam-published') {
    play('hop');
    say(pick(PHRASES.examPublished));
    burst('drop');
  }
  scheduleRefresh();
}

// ---------- 启动 ----------

export async function initPet() {
  if (state.root) return;
  try {
    state.data = await api.getPet();
  } catch {
    state.failed = true;
    return;
  }
  state.reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const root = document.createElement('div');
  root.id = 'pet-root';
  document.body.appendChild(root);
  state.root = root;
  render();
  scheduleBlink();
  resetIdle();
  window.addEventListener('pointermove', followPointer, { passive: true });
  window.addEventListener('pointerdown', resetIdle, { passive: true, capture: true });
  window.addEventListener('keydown', resetIdle, { passive: true, capture: true });

  const days = (state.data.recent_days || []).slice(0, -1);
  const idleWeek = days.length >= 3 && days.slice(-3).every((day) => !day.ink);
  if (!state.data.hidden && state.data.ink_total > 0 && idleWeek) {
    setTimeout(() => say(pick(PHRASES.comeback), 3600), 1200);
  }
}
