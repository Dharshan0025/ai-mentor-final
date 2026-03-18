/**
 * Student Routes
 * Protected routes that proxy to the Python agent service.
 *
 * Security rule:
 * - student-scoped routes must resolve to the authenticated JWT student only
 * - `:studentId` aliases are kept for backward compatibility, but they cannot
 *   be used to access another student's data
 */
import { Router } from 'express';
import axios from 'axios';
import { requireAuth } from '../middleware/auth.js';

const router = Router();
const AGENT_SERVICE = process.env.AGENT_SERVICE_URL || 'http://localhost:8000';

function getAuthedStudentId(req) {
    return req.user?.studentId;
}

function ensureSelfAccess(req) {
    const authedId = getAuthedStudentId(req);
    const requestedId = req.params.studentId;

    if (!requestedId || requestedId === authedId) {
        return authedId;
    }

    throw Object.assign(new Error('Forbidden'), {
        status: 403,
        code: 'FORBIDDEN_STUDENT_SCOPE',
    });
}

function handleAgentError(err, next, res = null) {
    if (err.response?.data && res) {
        return res.status(err.response.status).json(err.response.data);
    }
    if (err.code === 'ECONNREFUSED') {
        return next(Object.assign(new Error('Agent service offline'), { status: 503 }));
    }
    next(err);
}

async function proxyGet(path, res, next, config = {}) {
    try {
        const response = await axios.get(`${AGENT_SERVICE}${path}`, {
            timeout: 90_000,
            ...config,
        });
        res.json(response.data);
    } catch (err) {
        handleAgentError(err, next, res);
    }
}

async function proxyPost(path, body, res, next, config = {}) {
    try {
        const response = await axios.post(`${AGENT_SERVICE}${path}`, body, {
            timeout: 90_000,
            ...config,
        });
        res.json(response.data);
    } catch (err) {
        handleAgentError(err, next, res);
    }
}

async function proxyDelete(path, res, next, config = {}) {
    try {
        const response = await axios.delete(`${AGENT_SERVICE}${path}`, {
            timeout: 30_000,
            ...config,
        });
        res.json(response.data);
    } catch (err) {
        handleAgentError(err, next, res);
    }
}

function pipeSse(req, res, upstream) {
    res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'X-Accel-Buffering': 'no',
    });
    upstream.data.pipe(res);
    req.on('close', () => upstream.data.destroy());
}

// GET /api/student/me
router.get('/me', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/profile`, res, next);
});

// GET /api/student/me/predictions
router.get('/me/predictions', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/predictions`, res, next);
});

// GET /api/student/me/schedule
router.get('/me/schedule', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/schedule`, res, next);
});

// GET /api/student/me/career
router.get('/me/career', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/career`, res, next);
});

// GET /api/student/me/mastery
router.get('/me/mastery', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/mastery`, res, next);
});

// GET /api/student/me/benchmark
router.get('/me/benchmark', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/benchmark`, res, next);
});

// GET /api/student/me/parent-summary
router.get('/me/parent-summary', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/parent-summary`, res, next);
});

// GET /api/student/me/tutor/options
router.get('/me/tutor/options', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/tutor/options`, res, next);
});

// GET /api/student/me/sentiment?limit=N
router.get('/me/sentiment', requireAuth, (req, res, next) => {
    const limit = req.query.limit || 30;
    proxyGet(`/student/${getAuthedStudentId(req)}/sentiment?limit=${limit}`, res, next);
});

// GET /api/student/me/briefing
router.get('/me/briefing', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/briefing`, res, next);
});

// GET /api/student/me/alerts
router.get('/me/alerts', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/alerts`, res, next);
});

// POST /api/student/me/alerts/:alertId/read
router.post('/me/alerts/:alertId/read', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/alerts/${req.params.alertId}/read`, {}, res, next, {
        timeout: 10_000,
    });
});

// GET /api/student/me/alerts/stream
router.get('/me/alerts/stream', requireAuth, async (req, res, next) => {
    try {
        const upstream = await axios.get(
            `${AGENT_SERVICE}/student/${getAuthedStudentId(req)}/alerts/stream`,
            { responseType: 'stream', timeout: 0 }
        );
        pipeSse(req, res, upstream);
    } catch (err) {
        handleAgentError(err, next);
    }
});

// POST /api/student/me/alerts/scan
router.post('/me/alerts/scan', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/alerts/scan`, {}, res, next, {
        timeout: 10_000,
    });
});

// GET /api/student/me/min-scores?target_cgpa=7.5
router.get('/me/min-scores', requireAuth, (req, res, next) => {
    const target = req.query.target_cgpa || 7.5;
    proxyGet(`/student/${getAuthedStudentId(req)}/min-scores?target_cgpa=${target}`, res, next);
});

// POST /api/student/me/simulate
router.post('/me/simulate', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/simulate`, req.body, res, next, {
        timeout: 20_000,
    });
});

// POST /api/student/quiz/generate
router.post('/quiz/generate', requireAuth, (req, res, next) => {
    proxyPost('/quiz/generate', req.body, res, next, {
        timeout: 30_000,
    });
});

// POST /api/student/me/tutor/teach
router.post('/me/tutor/teach', requireAuth, async (req, res, next) => {
    try {
        const upstream = await axios.post(
            `${AGENT_SERVICE}/student/${getAuthedStudentId(req)}/tutor/teach`,
            req.body,
            { responseType: 'stream', timeout: 0 }
        );
        pipeSse(req, res, upstream);
    } catch (err) {
        handleAgentError(err, next);
    }
});

// POST /api/student/me/tutor/ask
router.post('/me/tutor/ask', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/tutor/ask`, req.body, res, next);
});

// GET /api/student/me/tutor/lesson-plan
router.get('/me/tutor/lesson-plan', requireAuth, (req, res, next) => {
    const params = new URLSearchParams(req.query);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/student/${getAuthedStudentId(req)}/tutor/lesson-plan${qs}`, res, next);
});

// POST /api/student/me/tutor/checkpoint
router.post('/me/tutor/checkpoint', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/tutor/checkpoint`, req.body, res, next, {
        timeout: 30_000,
    });
});

// POST /api/student/me/tutor/session/clear
router.post('/me/tutor/session/clear', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/tutor/session/clear`, req.body, res, next, {
        timeout: 10_000,
    });
});

// GET /api/student/me/tutor/session/:sessionId/state
router.get('/me/tutor/session/:sessionId/state', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/tutor/session/${req.params.sessionId}/state`, res, next);
});

// GET /api/student/me/tutor/voice/settings
router.get('/me/tutor/voice/settings', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/tutor/voice/settings`, res, next);
});

// POST /api/student/me/tutor/voice/speak
router.post('/me/tutor/voice/speak', requireAuth, async (req, res, next) => {
    try {
        const response = await axios.post(
            `${AGENT_SERVICE}/student/${getAuthedStudentId(req)}/tutor/voice/speak`,
            req.body,
            { timeout: 60_000, responseType: 'arraybuffer' }
        );
        res.setHeader('Content-Type', response.headers['content-type'] || 'audio/wav');
        res.send(Buffer.from(response.data));
    } catch (err) {
        handleAgentError(err, next, res);
    }
});

// POST /api/student/me/tutor/voice/transcribe
router.post('/me/tutor/voice/transcribe', requireAuth, async (req, res, next) => {
    try {
        const response = await axios.post(
            `${AGENT_SERVICE}/student/${getAuthedStudentId(req)}/tutor/voice/transcribe`,
            req,
            {
                headers: { ...req.headers, host: undefined },
                timeout: 60_000,
            }
        );
        res.json(response.data);
    } catch (err) {
        handleAgentError(err, next, res);
    }
});

// POST /api/student/me/tutor/evaluate-adaptive
router.post('/me/tutor/evaluate-adaptive', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/tutor/evaluate-adaptive`, req.body, res, next, {
        timeout: 30_000,
    });
});

// POST /api/student/me/tutor/generate-quiz
router.post('/me/tutor/generate-quiz', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/tutor/generate-quiz`, req.body, res, next, {
        timeout: 30_000,
    });
});

// POST /api/student/me/tutor/checkpoint/record
router.post('/me/tutor/checkpoint/record', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/tutor/checkpoint/record`, req.body, res, next, {
        timeout: 30_000,
    });
});

// GET /api/student/me/tutor/due-topics
router.get('/me/tutor/due-topics', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/tutor/due-topics`, res, next);
});

// GET /api/student/me/tutor/due-topics/smart
router.get('/me/tutor/due-topics/smart', requireAuth, (req, res, next) => {
    const params = new URLSearchParams(req.query);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/student/${getAuthedStudentId(req)}/tutor/due-topics/smart${qs}`, res, next);
});

// GET /api/student/me/tutor/weak-areas
router.get('/me/tutor/weak-areas', requireAuth, (req, res, next) => {
    const params = new URLSearchParams(req.query);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/student/${getAuthedStudentId(req)}/tutor/weak-areas${qs}`, res, next);
});

// GET /api/student/me/tutor/progress
router.get('/me/tutor/progress', requireAuth, (req, res, next) => {
    const params = new URLSearchParams(req.query);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/student/${getAuthedStudentId(req)}/tutor/progress${qs}`, res, next);
});

// POST /api/student/me/tutor/rag-query
router.post('/me/tutor/rag-query', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/tutor/rag-query`, req.body, res, next, {
        timeout: 30_000,
    });
});

// POST /api/student/me/tutor/deep-evaluate
router.post('/me/tutor/deep-evaluate', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/tutor/deep-evaluate`, req.body, res, next, {
        timeout: 30_000,
    });
});

// POST /api/student/me/tutor/doubt-resolve
router.post('/me/tutor/doubt-resolve', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/tutor/doubt-resolve`, req.body, res, next, {
        timeout: 30_000,
    });
});

// GET /api/student/me/xp
router.get('/me/xp', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/xp`, res, next);
});

// POST /api/student/me/xp/award
router.post('/me/xp/award', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/xp/award`, req.body, res, next, {
        timeout: 15_000,
    });
});

// GET /api/student/me/tutor/timeline
router.get('/me/tutor/timeline', requireAuth, (req, res, next) => {
    const params = new URLSearchParams(req.query);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/student/${getAuthedStudentId(req)}/tutor/timeline${qs}`, res, next);
});

// GET /api/student/me/documents
router.get('/me/documents', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/documents`, res, next);
});

// DELETE /api/student/me/documents/:docId
router.delete('/me/documents/:docId', requireAuth, (req, res, next) => {
    proxyDelete(`/student/${getAuthedStudentId(req)}/documents/${req.params.docId}`, res, next);
});

// POST /api/student/me/documents/:docId/trigger-embed
router.post('/me/documents/:docId/trigger-embed', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/documents/${req.params.docId}/trigger-embed`, {}, res, next, {
        timeout: 60_000,
    });
});

// POST /api/student/me/documents/upload
router.post('/me/documents/upload', requireAuth, async (req, res, next) => {
    try {
        const response = await axios.post(
            `${AGENT_SERVICE}/student/${getAuthedStudentId(req)}/documents/upload`,
            req,
            {
                headers: { ...req.headers, host: undefined },
                timeout: 120_000,
                maxBodyLength: Infinity,
                maxContentLength: Infinity,
            }
        );
        res.json(response.data);
    } catch (err) {
        handleAgentError(err, next, res);
    }
});

// POST /api/student/me/rag/search
router.post('/me/rag/search', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/rag/search`, req.body, res, next, {
        timeout: 30_000,
    });
});

// Backward-compatible GET /api/rag/search
router.get('/rag/search', requireAuth, (req, res, next) => {
    const params = new URLSearchParams(req.query);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/rag/search${qs}`, res, next);
});

// POST /api/student/me/pyq/analyze
router.post('/me/pyq/analyze', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/pyq/analyze`, req.body, res, next, {
        timeout: 60_000,
    });
});

// GET /api/student/me/pyq/history
router.get('/me/pyq/history', requireAuth, (req, res, next) => {
    const params = new URLSearchParams(req.query);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/student/${getAuthedStudentId(req)}/pyq/history${qs}`, res, next);
});

// POST /api/student/me/concept-graph
router.post('/me/concept-graph', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/concept-graph`, req.body, res, next, {
        timeout: 60_000,
    });
});

// GET /api/student/me/concept-graph/:subjectCode
router.get('/me/concept-graph/:subjectCode', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/concept-graph/${req.params.subjectCode}`, res, next);
});

// GET /api/student/me/notes
router.get('/me/notes', requireAuth, (req, res, next) => {
    const params = new URLSearchParams();
    if (req.query.subject) params.set('subject_code', req.query.subject);
    if (req.query.limit) params.set('limit', req.query.limit);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/student/${getAuthedStudentId(req)}/notes${qs}`, res, next);
});

// GET /api/student/me/notes/:noteId
router.get('/me/notes/:noteId', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/notes/${req.params.noteId}`, res, next);
});

// POST /api/student/me/notes/generate
router.post('/me/notes/generate', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/notes/generate`, req.body, res, next, {
        timeout: 60_000,
    });
});

// DELETE /api/student/me/notes/:noteId
router.delete('/me/notes/:noteId', requireAuth, (req, res, next) => {
    proxyDelete(`/student/${getAuthedStudentId(req)}/notes/${req.params.noteId}`, res, next);
});

// GET /api/student/me/skill-gap
router.get('/me/skill-gap', requireAuth, (req, res, next) => {
    const params = new URLSearchParams(req.query);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/student/${getAuthedStudentId(req)}/skill-gap${qs}`, res, next);
});

// POST /api/student/me/roadmap/generate
router.post('/me/roadmap/generate', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/roadmap/generate`, req.body, res, next, {
        timeout: 90_000,
    });
});

// GET /api/student/me/roadmap
router.get('/me/roadmap', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/roadmap`, res, next);
});

// POST /api/student/me/career/resume-review
router.post('/me/career/resume-review', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/career/resume-review`, req.body, res, next, {
        timeout: 60_000,
    });
});

// POST /api/student/me/career/interview-prep
router.post('/me/career/interview-prep', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/career/interview-prep`, req.body, res, next, {
        timeout: 60_000,
    });
});

// POST /api/student/me/problems/generate
router.post('/me/problems/generate', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/problems/generate`, req.body, res, next, {
        timeout: 60_000,
    });
});

// GET /api/student/me/problems
router.get('/me/problems', requireAuth, (req, res, next) => {
    const params = new URLSearchParams();
    if (req.query.subject_code) params.set('subject_code', req.query.subject_code);
    if (req.query.topic) params.set('topic', req.query.topic);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/student/${getAuthedStudentId(req)}/problems${qs}`, res, next);
});

// POST /api/student/me/problems/:problemId/attempt
router.post('/me/problems/:problemId/attempt', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/problems/${req.params.problemId}/attempt`, req.body, res, next, {
        timeout: 10_000,
    });
});

// DELETE /api/student/me/problems/:problemId
router.delete('/me/problems/:problemId', requireAuth, (req, res, next) => {
    proxyDelete(`/student/${getAuthedStudentId(req)}/problems/${req.params.problemId}`, res, next);
});

// POST /api/student/me/session/break-log
router.post('/me/session/break-log', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/session/break-log`, req.body, res, next, {
        timeout: 5_000,
    });
});

// Backward-compatible student-scoped routes with self-access enforcement
router.use('/:studentId', requireAuth, (req, _res, next) => {
    try {
        ensureSelfAccess(req);
        next();
    } catch (err) {
        next(err);
    }
});

// GET /api/student/:studentId/documents
router.get('/:studentId/documents', (req, res, next) => {
    proxyGet(`/student/${ensureSelfAccess(req)}/documents`, res, next);
});

// DELETE /api/student/:studentId/documents/:docId
router.delete('/:studentId/documents/:docId', (req, res, next) => {
    proxyDelete(`/student/${ensureSelfAccess(req)}/documents/${req.params.docId}`, res, next);
});

// POST /api/student/:studentId/documents/:docId/trigger-embed
router.post('/:studentId/documents/:docId/trigger-embed', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/documents/${req.params.docId}/trigger-embed`, {}, res, next, {
        timeout: 60_000,
    });
});

// POST /api/student/:studentId/documents/upload
router.post('/:studentId/documents/upload', async (req, res, next) => {
    try {
        const response = await axios.post(
            `${AGENT_SERVICE}/student/${ensureSelfAccess(req)}/documents/upload`,
            req,
            {
                headers: { ...req.headers, host: undefined },
                timeout: 120_000,
                maxBodyLength: Infinity,
                maxContentLength: Infinity,
            }
        );
        res.json(response.data);
    } catch (err) {
        handleAgentError(err, next, res);
    }
});

// POST /api/student/:studentId/rag/search
router.post('/:studentId/rag/search', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/rag/search`, req.body, res, next, {
        timeout: 30_000,
    });
});

// POST /api/student/:studentId/pyq/analyze
router.post('/:studentId/pyq/analyze', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/pyq/analyze`, req.body, res, next, {
        timeout: 60_000,
    });
});

// GET /api/student/:studentId/pyq/history
router.get('/:studentId/pyq/history', (req, res, next) => {
    proxyGet(`/student/${ensureSelfAccess(req)}/pyq/history`, res, next);
});

// POST /api/student/:studentId/concept-graph/generate
router.post('/:studentId/concept-graph/generate', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/concept-graph`, req.body, res, next, {
        timeout: 60_000,
    });
});

// GET /api/student/:studentId/concept-graph/:subjectCode
router.get('/:studentId/concept-graph/:subjectCode', (req, res, next) => {
    proxyGet(`/student/${ensureSelfAccess(req)}/concept-graph/${req.params.subjectCode}`, res, next);
});

// GET /api/student/:studentId/notes
router.get('/:studentId/notes', (req, res, next) => {
    const params = new URLSearchParams();
    if (req.query.subject) params.set('subject_code', req.query.subject);
    if (req.query.limit) params.set('limit', req.query.limit);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/student/${ensureSelfAccess(req)}/notes${qs}`, res, next);
});

// GET /api/student/:studentId/notes/:noteId
router.get('/:studentId/notes/:noteId', (req, res, next) => {
    proxyGet(`/student/${ensureSelfAccess(req)}/notes/${req.params.noteId}`, res, next);
});

// POST /api/student/:studentId/notes/generate
router.post('/:studentId/notes/generate', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/notes/generate`, req.body, res, next, {
        timeout: 60_000,
    });
});

// DELETE /api/student/:studentId/notes/:noteId
router.delete('/:studentId/notes/:noteId', (req, res, next) => {
    proxyDelete(`/student/${ensureSelfAccess(req)}/notes/${req.params.noteId}`, res, next);
});

// POST /api/student/:studentId/tutor/evaluate-adaptive
router.post('/:studentId/tutor/evaluate-adaptive', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/tutor/evaluate-adaptive`, req.body, res, next, {
        timeout: 30_000,
    });
});

// POST /api/student/:studentId/tutor/generate-quiz
router.post('/:studentId/tutor/generate-quiz', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/tutor/generate-quiz`, req.body, res, next, {
        timeout: 30_000,
    });
});

// POST /api/student/:studentId/tutor/checkpoint/record
router.post('/:studentId/tutor/checkpoint/record', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/tutor/checkpoint/record`, req.body, res, next, {
        timeout: 30_000,
    });
});

// GET /api/student/:studentId/tutor/due-topics/smart
router.get('/:studentId/tutor/due-topics/smart', (req, res, next) => {
    const params = new URLSearchParams(req.query);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/student/${ensureSelfAccess(req)}/tutor/due-topics/smart${qs}`, res, next);
});

// GET /api/student/:studentId/tutor/weak-areas
router.get('/:studentId/tutor/weak-areas', (req, res, next) => {
    const params = new URLSearchParams(req.query);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/student/${ensureSelfAccess(req)}/tutor/weak-areas${qs}`, res, next);
});

// GET /api/student/:studentId/tutor/progress
router.get('/:studentId/tutor/progress', (req, res, next) => {
    const params = new URLSearchParams(req.query);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/student/${ensureSelfAccess(req)}/tutor/progress${qs}`, res, next);
});

// POST /api/student/:studentId/tutor/rag-query
router.post('/:studentId/tutor/rag-query', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/tutor/rag-query`, req.body, res, next, {
        timeout: 30_000,
    });
});

// POST /api/student/:studentId/tutor/deep-evaluate
router.post('/:studentId/tutor/deep-evaluate', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/tutor/deep-evaluate`, req.body, res, next, {
        timeout: 30_000,
    });
});

// POST /api/student/:studentId/tutor/doubt-resolve
router.post('/:studentId/tutor/doubt-resolve', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/tutor/doubt-resolve`, req.body, res, next, {
        timeout: 30_000,
    });
});

// GET /api/student/:studentId/skill-gap
router.get('/:studentId/skill-gap', (req, res, next) => {
    const domain = req.query.domain ? `?domain=${encodeURIComponent(req.query.domain)}` : '';
    proxyGet(`/student/${ensureSelfAccess(req)}/skill-gap${domain}`, res, next);
});

// POST /api/student/:studentId/roadmap/generate
router.post('/:studentId/roadmap/generate', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/roadmap/generate`, req.body, res, next, {
        timeout: 90_000,
    });
});

// GET /api/student/:studentId/roadmap
router.get('/:studentId/roadmap', (req, res, next) => {
    proxyGet(`/student/${ensureSelfAccess(req)}/roadmap`, res, next);
});

// POST /api/student/:studentId/career/resume-review
router.post('/:studentId/career/resume-review', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/career/resume-review`, req.body, res, next, {
        timeout: 60_000,
    });
});

// POST /api/student/:studentId/career/interview-prep
router.post('/:studentId/career/interview-prep', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/career/interview-prep`, req.body, res, next, {
        timeout: 60_000,
    });
});

// POST /api/student/:studentId/problems/generate
router.post('/:studentId/problems/generate', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/problems/generate`, req.body, res, next, {
        timeout: 60_000,
    });
});

// GET /api/student/:studentId/problems
router.get('/:studentId/problems', (req, res, next) => {
    const params = new URLSearchParams();
    if (req.query.subject_code) params.set('subject_code', req.query.subject_code);
    if (req.query.topic) params.set('topic', req.query.topic);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/student/${ensureSelfAccess(req)}/problems${qs}`, res, next);
});

// POST /api/student/:studentId/problems/:problemId/attempt
router.post('/:studentId/problems/:problemId/attempt', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/problems/${req.params.problemId}/attempt`, req.body, res, next, {
        timeout: 10_000,
    });
});

// DELETE /api/student/:studentId/problems/:problemId
router.delete('/:studentId/problems/:problemId', (req, res, next) => {
    proxyDelete(`/student/${ensureSelfAccess(req)}/problems/${req.params.problemId}`, res, next);
});

// GET /api/student/:studentId/xp
router.get('/:studentId/xp', (req, res, next) => {
    proxyGet(`/student/${ensureSelfAccess(req)}/xp`, res, next);
});

// POST /api/student/:studentId/xp/award
router.post('/:studentId/xp/award', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/xp/award`, req.body, res, next, {
        timeout: 15_000,
    });
});

// GET /api/student/:studentId/tutor/timeline
router.get('/:studentId/tutor/timeline', (req, res, next) => {
    const params = new URLSearchParams(req.query);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/student/${ensureSelfAccess(req)}/tutor/timeline${qs}`, res, next);
});

// POST /api/student/:studentId/session/break-log
router.post('/:studentId/session/break-log', (req, res, next) => {
    proxyPost(`/student/${ensureSelfAccess(req)}/session/break-log`, req.body, res, next, {
        timeout: 5_000,
    });
});

// ── Phase 8: V2 Diagram History ───────────────────────────────────────────────

// POST /api/student/me/tutor/session/diagrams
router.post('/me/tutor/session/diagrams', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/tutor/session/diagrams`, req.body, res, next, { timeout: 10_000 });
});

// GET /api/student/me/tutor/session/diagrams
router.get('/me/tutor/session/diagrams', requireAuth, (req, res, next) => {
    const params = new URLSearchParams(req.query);
    const qs = params.toString() ? `?${params}` : '';
    proxyGet(`/student/${getAuthedStudentId(req)}/tutor/session/diagrams${qs}`, res, next);
});

// ── Phase 8: V6 Session Replay ────────────────────────────────────────────────

// POST /api/student/me/tutor/session/event
router.post('/me/tutor/session/event', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/tutor/session/event`, req.body, res, next, { timeout: 10_000 });
});

// GET /api/student/me/tutor/session/:sessionId/events
router.get('/me/tutor/session/:sessionId/events', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/tutor/session/${req.params.sessionId}/events`, res, next);
});

// ── Phase 8: V6 Peer Learning Study Rooms ────────────────────────────────────

// POST /api/student/me/study-room/create
router.post('/me/study-room/create', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/study-room/create`, req.body, res, next, { timeout: 10_000 });
});

// ── Phase 8: V8 Analytics / Behavioral Intelligence ──────────────────────────

// POST /api/student/me/analytics/attention
router.post('/me/analytics/attention', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/analytics/attention`, req.body, res, next, { timeout: 5_000 });
});

// GET /api/student/me/analytics/burnout
router.get('/me/analytics/burnout', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/analytics/burnout`, res, next);
});

// POST /api/student/me/analytics/silence-alert
router.post('/me/analytics/silence-alert', requireAuth, (req, res, next) => {
    proxyPost(`/student/${getAuthedStudentId(req)}/analytics/silence-alert`, req.body, res, next, { timeout: 5_000 });
});

// GET /api/student/me/analytics/attention-score
router.get('/me/analytics/attention-score', requireAuth, (req, res, next) => {
    proxyGet(`/student/${getAuthedStudentId(req)}/analytics/attention-score`, res, next);
});

export default router;

