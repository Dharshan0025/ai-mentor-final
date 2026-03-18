/**
 * AI-Mentor Frontend — API Service
 * Centralized HTTP client for all backend calls.
 * Usage: import api from './services/api'
 */
import axios from 'axios';

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:3001/api';

const api = axios.create({
    baseURL: BASE,
    timeout: 30_000,
    headers: { 'Content-Type': 'application/json' },
});

// Attach JWT token to every request
api.interceptors.request.use((config) => {
    const token = localStorage.getItem('ai_mentor_token');
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
});

// Handle 401 globally — redirect to login
api.interceptors.response.use(
    (res) => res,
    (err) => {
        if (err.response?.status === 401) {
            localStorage.removeItem('ai_mentor_token');
            localStorage.removeItem('ai_mentor_student');
            window.location.href = '/';
        }
        return Promise.reject(err);
    }
);

// ── Auth ─────────────────────────────────────────────────────────────────────
export async function login(collegeId, password) {
    const { data } = await api.post('/auth/login', { collegeId, password });
    // Persist token + student data
    localStorage.setItem('ai_mentor_token', data.token);
    localStorage.setItem('ai_mentor_student', JSON.stringify(data.student));
    // Store college ID separately for V4 memory API functions
    const id = data.student?.college_id || data.student?.collegeId || collegeId;
    if (id) localStorage.setItem('ai_mentor_college_id', id);
    return data;
}

export function logout() {
    localStorage.removeItem('ai_mentor_token');
    localStorage.removeItem('ai_mentor_student');
    localStorage.removeItem('ai_mentor_college_id');
    api.post('/auth/logout').catch(() => { });
}

export function getStoredStudent() {
    const raw = localStorage.getItem('ai_mentor_student');
    return raw ? JSON.parse(raw) : null;
}

function mePath(path = '') {
    return `/student/me${path}`;
}

export function isAuthenticated() {
    return Boolean(localStorage.getItem('ai_mentor_token'));
}

// ── Chat ──────────────────────────────────────────────────────────────────────
/**
 * Send a chat message — returns agent response
 * @param {Object} opts
 * @param {string} opts.message
 * @param {string} opts.sessionId
 * @param {string} opts.lang
 * @param {Array}  opts.history
 */
export async function sendChatMessage({ message, sessionId, lang = 'en', history = [] }) {
    const { data } = await api.post('/chat', { message, sessionId, lang, history });
    return data; // { agent, content, citations, tokens_used, model_used }
}

// ── Student ───────────────────────────────────────────────────────────────────
export async function getMyProfile() {
    const { data } = await api.get('/student/me');
    return data;
}

export async function getMyPredictions() {
    const { data } = await api.get('/student/me/predictions');
    return data;
}


export async function getMySchedule() {
    const { data } = await api.get('/student/me/schedule');
    return data;
}

export async function getMyCareer() {
    const { data } = await api.get('/student/me/career');
    return data;
}

export async function getMyMastery() {
    const { data } = await api.get('/student/me/mastery');
    return data;
}

export async function getMyBenchmark() {
    const { data } = await api.get('/student/me/benchmark');
    return data;
}

export async function getParentSummary() {
    const { data } = await api.get('/student/me/parent-summary');
    return data;
}

export async function generateQuiz({ subject, topic, bloom_level }) {
    const stored = getStoredStudent();
    const student_id = stored?.id || stored?.studentId || null;
    const { data } = await api.post('/student/quiz/generate', {
        subject,
        topic,
        bloom_level,
        student_id, // backend uses this to cap bloom_level to student's actual profile level
    });
    return data;
}

export async function getMySentiment(limit = 30) {
    const { data } = await api.get(`/student/me/sentiment?limit=${limit}`);
    return data;
}

export async function simulateScenario({ attendance_delta = 0, assignment_delta = 0, study_hours_delta = 0, explain = false }) {
    const { data } = await api.post('/student/me/simulate', {
        attendance_delta,
        assignment_delta,
        study_hours_delta,
        explain,
    });
    return data;
}


// ── Proactive Intelligence ─────────────────────────────────────────────────────
export async function getBriefing() {
    const { data } = await api.get('/student/me/briefing');
    return data; // { briefing: [], summary: {}, student_name, exam_days, ai_brief }
}

export async function getMyAlerts() {
    const { data } = await api.get('/student/me/alerts');
    return data; // { unread_count, alerts: [], has_critical }
}

export async function markAlertRead(alertId) {
    const stored = getStoredStudent();
    const student_id = stored?.id || stored?.college_id || '';
    const { data } = await api.post(`/student/me/alerts/${alertId}/read`);
    return data;
}

export async function triggerAlertScan() {
    const { data } = await api.post('/student/me/alerts/scan');
    return data;
}

export async function getMinScores(targetCgpa = 7.5) {
    const { data } = await api.get(`/student/me/min-scores?target_cgpa=${targetCgpa}`);
    return data;
}

// ── Student Profile ───────────────────────────────────────────────────────────
export async function getStudentProfile() {
    try {
        const { data } = await api.get('/student/me');
        return data;
    } catch {
        return getStoredStudent() || {};
    }
}

// ── AI Visual Tutor ──────────────────────────────────────────────────────────
export function startTutorLesson({ subjectCode, topic, mode = 'visual', sessionId = null }) {
    const token = localStorage.getItem('ai_mentor_token');
    const body = { subject_code: subjectCode, topic, mode };
    if (sessionId) body.session_id = sessionId;
    return fetch(`${BASE}/student/me/tutor/teach`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
    });
}

/** Tutor options from DB only (subjects + topics per subject). No hardcoded data. */
export async function getTutorOptions() {
    const { data } = await api.get('/student/me/tutor/options');
    return data; // { subjects: [...], topics_by_subject: { "CODE": ["topic1", ...] } }
}

export async function askTutorQuestion({ subjectCode, topic, question, history = [], sessionId = null }) {
    const body = { subject_code: subjectCode, topic, question, history };
    if (sessionId) body.session_id = sessionId;
    const { data } = await api.post('/student/me/tutor/ask', body);
    return data; // { answer, mermaid? }
}

/** Clear server-side tutor session (for "New conversation"). */
export async function clearTutorSession(sessionId) {
    if (!sessionId) return;
    await api.post('/student/me/tutor/session/clear', { session_id: sessionId });
}

// ── V1 Teaching Core ──────────────────────────────────────────────────────────

/**
 * Fetch a structured lesson plan BEFORE streaming the lesson.
 * Returns { steps, total_steps, estimated_total_minutes, checkpoints, bloom_level }
 */
export async function getLessonPlan({ subjectCode, topic }) {
    const params = new URLSearchParams({ subject_code: subjectCode, topic });
    const { data } = await api.get(`/student/me/tutor/lesson-plan?${params}`);
    return data;
}

/**
 * Submit a checkpoint answer for LLM evaluation.
 * Body: { question, student_answer, correct_answer, subject_code, topic,
 *         question_type, correct_index?, selected_index?, session_id? }
 * Returns: { correct, score, feedback, misconceptions, unlock_next }
 */
export async function evaluateCheckpoint(body) {
    const { data } = await api.post('/student/me/tutor/checkpoint', body);
    return data;
}

/**
 * Get topics due for spaced repetition review (SM-2 smart endpoint).
 * Returns: { due_count, due_topics, horizon_hours }
 */
export async function getDueTopics(horizonHours = 24) {
    const { data } = await api.get(
        `${mePath('/tutor/due-topics/smart')}?horizon_hours=${horizonHours}&limit=10`
    );
    return data;
}

/**
 * Record a checkpoint attempt to the SM-2 memory layer.
 * Called after evaluateCheckpoint — non-blocking, best-effort.
 * body: { subject_code, topic, question, question_type, student_answer,
 *         correct_answer, is_correct, score, feedback?, response_time_ms?,
 *         bloom_level?, after_step?, session_id? }
 */
export async function recordCheckpointMemory(body) {
    const { data } = await api.post(mePath('/tutor/checkpoint/record'), body);
    return data; // { checkpoint_id, sm2_update: { interval_days, next_review_at } }
}

/**
 * Get full tutor progress summary for the Progress Dashboard.
 * Returns: { total_topics, mastered_concepts, struggling_concepts, due_for_review,
 *             overall_accuracy, checkpoint_pass_rate, by_subject, learning_dna }
 */
export async function getTutorProgress(subjectCode = null) {
    const params = subjectCode ? `?subject_code=${subjectCode}` : '';
    const { data } = await api.get(`${mePath('/tutor/progress')}${params}`);
    return data;
}

/**
 * Get weak areas based on SM-2 difficulty_level, avg_score, confusion_count.
 * Returns: { weak_areas: [{ subject_code, topic, concept, avg_score, ... }] }
 */
export async function getWeakAreas(subjectCode = null, topN = 10) {
    const params = new URLSearchParams({ top_n: topN });
    if (subjectCode) params.set('subject_code', subjectCode);
    const { data } = await api.get(`${mePath('/tutor/weak-areas')}?${params}`);
    return data;
}

/**
 * Semantic RAG search over study materials + syllabus.
 * body: { query, subject_code?, top_k? }
 * Returns: { chunks, syllabus_context, chunk_count }
 */
export async function ragQuery(body) {
    const { data } = await api.post(mePath('/tutor/rag-query'), body);
    return data;
}

/**
 * Get current tutor session state (for resume after refresh).
 * Returns: { exists, last_step, checkpoints_passed, lesson_summary }
 */
export async function getSessionState(sessionId) {
    if (!sessionId) return { exists: false };
    const { data } = await api.get(`/student/me/tutor/session/${sessionId}/state`);
    return data;
}

// ── V3 Voice Teaching — Nova Sonic TTS/STT ───────────────────────────────────

/** Get available voice personalities and TTS provider info. */
export async function getVoiceSettings() {
    const { data } = await api.get('/student/me/tutor/voice/settings');
    return data; // { tts_provider, voices, default_voice, sample_rate }
}

/**
 * Call Nova Sonic TTS — returns an AudioBuffer or null (fallback to browser TTS).
 * body: { text, voice: "professor"|"coach"|"friend", max_chars? }
 */
export async function tutorVoiceSpeak({ text, voice = 'professor', maxChars = 500 }) {
    const token = localStorage.getItem('ai_mentor_token');
    const res = await fetch(`${BASE}/student/me/tutor/voice/speak`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ text, voice, max_chars: maxChars }),
    });
    // 204 = no AWS creds, use browser TTS
    if (res.status === 204) return null;
    if (!res.ok) return null;
    const arrayBuffer = await res.arrayBuffer();
    return arrayBuffer; // caller decodes via AudioContext
}

/**
 * Send raw audio blob to backend for STT transcription.
 * Returns transcript string (empty if AWS STT unavailable → use browser STT).
 */
export async function tutorVoiceTranscribe(audioBlob) {
    const token = localStorage.getItem('ai_mentor_token');
    const res = await fetch(`${BASE}/student/me/tutor/voice/transcribe`, {
        method: 'POST',
        headers: {
            'Content-Type': audioBlob.type || 'audio/webm',
            Authorization: `Bearer ${token}`,
        },
        body: audioBlob,
    });
    if (!res.ok) return '';
    const data = await res.json();
    return data.transcript || '';
}

export default api;

// ── V6 Gamification + Classroom Experience — Phase 4 ─────────────────────────

/**
 * Award XP for an action. Returns { total_xp, level, xp_gained, badges_earned }.
 * action: 'lesson_complete' | 'checkpoint_pass' | 'exam_complete' | 'exam_perfect'
 */
export async function awardXp({ action, amount, metadata } = {}) {
    const { data } = await api.post(mePath('/xp/award'), { action, amount, metadata });
    return data;
}

/**
 * Get full XP summary for the logged-in student.
 * Returns { total_xp, level, streak_days, level_progress, xp_to_next_level, badges, recent_ledger }.
 */
export async function getStudentXp() {
    const { data } = await api.get(mePath('/xp'));
    return data;
}

/**
 * Get paginated lesson history / progress timeline.
 * Returns { total, events: [{ topic, subject_code, steps_completed, bloom_level, completed_at }] }.
 */
export async function getLessonTimeline({ limit = 20, offset = 0 } = {}) {
    const { data } = await api.get(mePath('/tutor/timeline'), { params: { limit, offset } });
    return data;
}

/**
 * Generate a quiz for exam mode.
 * body: { subject, topic, bloom_level, count }
 * Returns: { questions: [{ question, options, correct_index }] }
 */
export async function generateExamQuiz(body) {
    const { data } = await api.post(mePath('/tutor/generate-quiz'), body);
    return data;
}


/**
 * Deep checkpoint evaluation via EvaluatorAgent.
 * Returns is_correct, score, feedback, misconception, recommendation, bloom_achievement.
 * body: { subject_code, topic, question, student_answer, correct_answer,
 *         question_type?, response_time_ms?, prev_score?, wrong_count? }
 */
export async function deepEvaluate(body) {
    const { data } = await api.post(mePath('/tutor/deep-evaluate'), body);
    return data;
}

/**
 * Doubt resolution via DoubtResolverAgent.
 * Triggered when student answers same concept wrong ≥2 times.
 * Returns { mode, explanation, mini_question, key_insight, diagram?, rag_context? }
 * body: { subject_code, topic, concept, wrong_count?, last_wrong_answer?,
 *         misconception?, confusion_context? }
 */
export async function doubtResolve(body) {
    const { data } = await api.post(mePath('/tutor/doubt-resolve'), body);
    return data;
}


// ── Phase 5: V7 Knowledge Engine ─────────────────────────────────────────────

/** Semantic RAG search across syllabus + uploaded documents */
export async function ragSearch(query, subject = null, topK = 6) {
    const { data } = await api.post(mePath('/rag/search'), {
        query,
        subject_code: subject,
        top_k: topK,
    });
    return data;
}

/** List uploaded documents for the student */
export async function getDocuments() {
    const { data } = await api.get(mePath('/documents'));
    return data;
}

/** Upload a PDF document (multipart form) */
export async function uploadDocument(file, subjectCode = '') {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('subject_code', subjectCode);
    const { data } = await api.post(mePath('/documents/upload'), formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
}

/** Delete an uploaded document */
export async function deleteDocument(docId) {
    const { data } = await api.delete(mePath(`/documents/${docId}`));
    return data;
}

/** Analyze a Past Year Question paper */
export async function analyzePYQ(body) {
    const { data } = await api.post(mePath('/pyq/analyze'), body);
    return data;
}

/** Get PYQ analysis history */
export async function getPYQHistory(limit = 10) {
    const { data } = await api.get(`${mePath('/pyq/history')}?limit=${limit}`);
    return data;
}

/** Build a new concept graph for a subject */
export async function buildConceptGraph(body) {
    const { data } = await api.post(mePath('/concept-graph'), body);
    return data;
}

/** Get cached concept graph for a subject */
export async function getConceptGraph(subjectCode) {
    const { data } = await api.get(mePath(`/concept-graph/${subjectCode}`));
    return data;
}

/** Generate AI notes from a topic / lesson session */
export async function generateNotes(body) {
    const { data } = await api.post(mePath('/notes/generate'), body);
    return data;
}

/** List saved notes */
export async function getNotes(limit = 20) {
    const { data } = await api.get(`${mePath('/notes')}?limit=${limit}`);
    return data;
}

/** Fetch a single note with full content */
export async function getNote(noteId) {
    const { data } = await api.get(mePath(`/notes/${noteId}`));
    return data;
}

/** Delete a note */
export async function deleteNote(noteId) {
    const { data } = await api.delete(mePath(`/notes/${noteId}`));
    return data;
}


// ── Phase 6: V8–V10 Advanced Intelligence ────────────────────────────────────

/** Hesitation-aware adaptive checkpoint evaluation */
export async function evaluateAdaptive(body) {
    const { data } = await api.post(mePath('/tutor/evaluate-adaptive'), body);
    return data;
}

/** Analyze skill gap for career domain */
export async function getSkillGap(domain = null) {
    const params = domain ? `?domain=${encodeURIComponent(domain)}` : '';
    const { data } = await api.get(`${mePath('/skill-gap')}${params}`);
    return data;
}

/** Generate a personalized study roadmap */
export async function generateRoadmap(body) {
    const { data } = await api.post(mePath('/roadmap/generate'), body);
    return data;
}

/** Get the student's most recent roadmap */
export async function getRoadmap() {
    const { data } = await api.get(mePath('/roadmap'));
    return data;
}

/** AI-powered resume ATS review */
export async function reviewResume(resumeText) {
    const { data } = await api.post(mePath('/career/resume-review'), { resume_text: resumeText });
    return data;
}

/** Generate domain-specific interview Q&A */
export async function generateInterviewPrep(body) {
    const { data } = await api.post(mePath('/career/interview-prep'), body);
    return data;
}

// ── Phase 7: Problem Bank, AI Debugger, Leaderboard ──────────────────────────

/** Generate practice problems for a topic */
export async function generateProblems(body) {
    const { data } = await api.post(mePath('/problems/generate'), body);
    return data;
}

/** Get student's saved problem bank */
export async function getProblems(subjectCode = null, topic = null) {
    const params = new URLSearchParams();
    if (subjectCode) params.set('subject_code', subjectCode);
    if (topic)       params.set('topic', topic);
    const qs = params.toString() ? `?${params}` : '';
    const { data } = await api.get(`${mePath('/problems')}${qs}`);
    return data;
}

/** Record a problem attempt */
export async function attemptProblem(problemId, isCorrect) {
    const { data } = await api.post(mePath(`/problems/${problemId}/attempt`), { is_correct: isCorrect });
    return data;
}

/** Delete a problem from problem bank */
export async function deleteProblems(problemId) {
    const { data } = await api.delete(mePath(`/problems/${problemId}`));
    return data;
}

/** AI code debugger — analyze error */
export async function analyzeDebug(body) {
    const { data } = await api.post('/debug/analyze', body);
    return data;
}

/** Get leaderboard (top students by XP) */
export async function getLeaderboard(subjectCode = null) {
    const params = subjectCode ? `?subject_code=${subjectCode}` : '';
    const { data } = await api.get(`/leaderboard${params}`);
    return data;
}

/** Log a study break for session analytics */
export async function logBreak(sessionMinutes) {
    await api.post(mePath('/session/break-log'), { session_minutes: sessionMinutes }).catch(() => {});
}


// ── Phase 8: V2 Diagram History ──────────────────────────────────────────────

/** Save a diagram from a tutor session for visual memory */
export async function saveDiagram(body) {
    await api.post(mePath('/tutor/session/diagrams'), body).catch(() => {});
}

/** Get saved diagrams for the current session or recent sessions */
export async function getSessionDiagrams(sessionId = null, limit = 20) {
    const params = new URLSearchParams({ limit });
    if (sessionId) params.set('session_id', sessionId);
    const { data } = await api.get(`${mePath('/tutor/session/diagrams')}?${params}`);
    return data;
}


// ── Phase 8: V6 Session Replay ────────────────────────────────────────────────

/** Save a single lesson SSE event for replay */
export async function saveSessionEvent(body) {
    await api.post(mePath('/tutor/session/event'), body).catch(() => {});
}

/** Fetch all events for a session (for replay) */
export async function getSessionEvents(sessionId) {
    const { data } = await api.get(mePath(`/tutor/session/${sessionId}/events`));
    return data;
}


// ── Phase 8: V6 Peer Learning ─────────────────────────────────────────────────

/** Create a study room and get a room code */
export async function createStudyRoom(body) {
    const { data } = await api.post(mePath('/study-room/create'), body);
    return data;
}

/** Get study room info and messages */
export async function getStudyRoom(roomCode) {
    const { data } = await api.get(`/study-room/${roomCode}`);
    return data;
}

/** Post a message to a study room */
export async function postRoomMessage(roomCode, body) {
    const { data } = await api.post(`/study-room/${roomCode}/message`, body);
    return data;
}


// ── Phase 8: V8 Behavioral Intelligence ──────────────────────────────────────

/** Send a visibility heartbeat — fire-and-forget */
export function sendAttentionHeartbeat(isVisible, sessionId = '') {
    api.post(mePath('/analytics/attention'), { is_visible: isVisible, session_id: sessionId }).catch(() => {});
}

/** Get burnout risk analysis */
export async function getBurnoutAnalysis() {
    const { data } = await api.get(mePath('/analytics/burnout'));
    return data;
}

/** Report a silence-confusion alert */
export async function reportSilenceAlert(body) {
    const { data } = await api.post(mePath('/analytics/silence-alert'), body);
    return data;
}

/** Get attention score from heartbeats */
export async function getAttentionScore() {
    const { data } = await api.get(mePath('/analytics/attention-score'));
    return data;
}


// ── Phase 8: V9 Study Modes + V3 Languages ────────────────────────────────────

/** List all study mode profiles */
export async function getStudyModes() {
    const { data } = await api.get('/tutor/study-modes');
    return data;
}

/** Get languages supported by the AI tutor */
export async function getSupportedLanguages() {
    const { data } = await api.get('/tutor/supported-languages');
    return data;
}
