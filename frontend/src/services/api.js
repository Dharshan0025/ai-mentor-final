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
    // Persist token
    localStorage.setItem('ai_mentor_token', data.token);
    localStorage.setItem('ai_mentor_student', JSON.stringify(data.student));
    return data;
}

export function logout() {
    localStorage.removeItem('ai_mentor_token');
    localStorage.removeItem('ai_mentor_student');
    api.post('/auth/logout').catch(() => { });
}

export function getStoredStudent() {
    const raw = localStorage.getItem('ai_mentor_student');
    return raw ? JSON.parse(raw) : null;
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
    const { data } = await api.get('/student/me/prediction');
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

export async function simulateScenario({ attendance_delta = 0, assignment_delta = 0, study_hours_delta = 0 }) {
    const { data } = await api.post('/student/me/simulate', {
        attendance_delta,
        assignment_delta,
        study_hours_delta,
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

export default api;
