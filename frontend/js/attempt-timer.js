export function formatElapsed(ms) {
  const total = Math.max(0, Math.floor(Number(ms) / 1000) || 0);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

export function attemptTimerRunning(attempt) {
  return attempt?.status === 'in-progress' && attempt?.completion_status !== 'completed';
}

export function attemptElapsedMs(attempt, now = Date.now()) {
  const elapsed = Number(attempt?.elapsed_ms) || 0;
  if (attemptTimerRunning(attempt) && attempt?.timing_started_at) {
    return elapsed + Math.max(0, now - Number(attempt.timing_started_at));
  }
  return elapsed;
}

export function attemptLimitMs(minutes) {
  const value = Number(minutes);
  if (!Number.isFinite(value) || value < 1) return 0;
  return Math.round(value * 60 * 1000);
}

export function attemptRemainingMs(attempt, limitMs, now = Date.now()) {
  if (!limitMs) return null;
  return Math.max(0, limitMs - attemptElapsedMs(attempt, now));
}

export function examDurationMinutes(exam, blueprints) {
  if (!exam?.source_blueprint_id) return null;
  const blueprint = (blueprints || []).find((item) => item.id === exam.source_blueprint_id);
  const minutes = Number(blueprint?.duration_minutes);
  return Number.isFinite(minutes) && minutes >= 1 ? minutes : null;
}
