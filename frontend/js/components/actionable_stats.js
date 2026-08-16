/**
 * Actionable Overview Statistics Bar
 * Replaces vanity counters with real operational metrics and direct jump CTAs.
 */

import { icons } from '../icons.js';

export function renderActionableStats(state, container, handlers) {
  const { drafts, attempts, sources, exams } = state;

  // Calculate actionable counts
  let needsReviewQuestions = 0;
  drafts?.forEach((d) => {
    d.questions?.forEach((q) => {
      if (q.status === 'needs-review' || q.reliability === 'needs-review') {
        needsReviewQuestions++;
      }
    });
  });

  const inProgressAttempts = attempts?.filter((a) => a.status === 'in-progress').length || 0;
  const sourceCount = sources?.length || 0;
  const examCount = exams?.length || 0;
  const totalQuestions = exams?.reduce((acc, e) => acc + (e.document?.questions?.length || 0), 0) || 0;

  container.innerHTML = `
    <div class="actionable-stats-bar" data-testid="actionable-stats-bar">
      <!-- 1. Needs Review / Quality Alert -->
      <div class="action-stat-card ${needsReviewQuestions > 0 ? 'stat-card-warning' : ''}" data-jump="exam_studio" data-subtab="draft" title="点击直达题目工坊审核">
        <div class="stat-left">
          <span class="stat-title">待审核试题</span>
          <span class="stat-number">${needsReviewQuestions} <small style="font-size: 13px; font-weight: 500;">道</small></span>
        </div>
        <div class="stat-tag-icon">
          ${needsReviewQuestions > 0 ? icons.alertTriangle(18) : icons.checkSquare(18)}
        </div>
      </div>

      <!-- 2. In-Progress Exam Attempts -->
      <div class="action-stat-card ${inProgressAttempts > 0 ? 'stat-card-warning' : ''}" data-jump="practice_exam" data-viewmode="attempt" title="点击继续作答">
        <div class="stat-left">
          <span class="stat-title">进行中的作答</span>
          <span class="stat-number">${inProgressAttempts} <small style="font-size: 13px; font-weight: 500;">份</small></span>
        </div>
        <div class="stat-tag-icon">
          ${icons.clock(18)}
        </div>
      </div>

      <!-- 3. Sources Ready -->
      <div class="action-stat-card" data-jump="sources" title="点击查看与上传讲义资料">
        <div class="stat-left">
          <span class="stat-title">资料库就绪</span>
          <span class="stat-number">${sourceCount} <small style="font-size: 13px; font-weight: 500;">份</small></span>
        </div>
        <div class="stat-tag-icon">
          ${icons.folder(18)}
        </div>
      </div>

      <!-- 4. Exams & Question Bank -->
      <div class="action-stat-card" data-jump="practice_exam" data-viewmode="library" title="点击进入试卷中心">
        <div class="stat-left">
          <span class="stat-title">正式试卷 / 题库</span>
          <span class="stat-number">${examCount} <small style="font-size: 12px; font-weight: 500;">卷</small> · ${totalQuestions} <small style="font-size: 12px; font-weight: 500;">题</small></span>
        </div>
        <div class="stat-tag-icon">
          ${icons.target(18)}
        </div>
      </div>
    </div>
  `;

  container.querySelectorAll('.action-stat-card').forEach((card) => {
    card.onclick = () => {
      const tab = card.getAttribute('data-jump');
      const subtab = card.getAttribute('data-subtab');
      const viewmode = card.getAttribute('data-viewmode');

      if (tab) {
        handlers.onSelectNavTab?.(tab);
        if (subtab) handlers.onSelectExamStudioSubTab?.(subtab);
        if (viewmode) handlers.onSelectPracticeViewMode?.(viewmode);
      }
    };
  });
}
