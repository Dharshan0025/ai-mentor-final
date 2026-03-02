/**
 * Student Routes — GET /api/student/me, /me/predictions, /me/schedule
 * Protected routes that proxy to the Python agent service
 */
import { Router } from 'express';
import axios from 'axios';
import { requireAuth } from '../middleware/auth.js';

const router = Router();
const AGENT_SERVICE = process.env.AGENT_SERVICE_URL || 'http://localhost:8000';

async function proxyGet(path, res, next) {
    try {
        const response = await axios.get(`${AGENT_SERVICE}${path}`, { timeout: 15_000 });
        res.json(response.data);
    } catch (err) {
        if (err.code === 'ECONNREFUSED') {
            return next(Object.assign(new Error('Agent service offline'), { status: 503 }));
        }
        next(err);
    }
}

// GET /api/student/me
router.get('/me', requireAuth, (req, res, next) => {
    proxyGet(`/student/${req.user.studentId}/profile`, res, next);
});

// GET /api/student/me/predictions
router.get('/me/predictions', requireAuth, (req, res, next) => {
    proxyGet(`/student/${req.user.studentId}/predictions`, res, next);
});

// GET /api/student/me/schedule
router.get('/me/schedule', requireAuth, (req, res, next) => {
    proxyGet(`/student/${req.user.studentId}/schedule`, res, next);
});

// GET /api/student/me/career
router.get('/me/career', requireAuth, (req, res, next) => {
    proxyGet(`/student/${req.user.studentId}/career`, res, next);
});

// GET /api/student/me/mastery — Topic-level mastery summary
router.get('/me/mastery', requireAuth, (req, res, next) => {
    proxyGet(`/student/${req.user.studentId}/mastery`, res, next);
});

// GET /api/student/me/benchmark — Peer benchmarking (CGPA/attendance percentiles)
router.get('/me/benchmark', requireAuth, (req, res, next) => {
    proxyGet(`/student/${req.user.studentId}/benchmark`, res, next);
});

// GET /api/student/me/parent-summary — Parent engagement summary
router.get('/me/parent-summary', requireAuth, (req, res, next) => {
    proxyGet(`/student/${req.user.studentId}/parent-summary`, res, next);
});

// GET /api/student/me/tutor/options — Tutor subjects + topics from DB only
router.get('/me/tutor/options', requireAuth, (req, res, next) => {
    proxyGet(`/student/${req.user.studentId}/tutor/options`, res, next);
});

// GET /api/student/me/sentiment?limit=N
router.get('/me/sentiment', requireAuth, (req, res, next) => {
    const limit = req.query.limit || 30;
    proxyGet(`/student/${req.user.studentId}/sentiment?limit=${limit}`, res, next);
});

// GET /api/student/me/briefing — Proactive Intelligence Briefing
router.get('/me/briefing', requireAuth, (req, res, next) => {
    proxyGet(`/student/${req.user.studentId}/briefing`, res, next);
});

// GET /api/student/me/alerts — Proactive alerts (attendance cliff, sentiment crash)
router.get('/me/alerts', requireAuth, (req, res, next) => {
    proxyGet(`/student/${req.user.studentId}/alerts`, res, next);
});

// POST /api/student/me/alerts/:alertId/read — Dismiss an alert
router.post('/me/alerts/:alertId/read', requireAuth, async (req, res, next) => {
    try {
        const response = await axios.post(
            `${AGENT_SERVICE}/student/${req.user.studentId}/alerts/${req.params.alertId}/read`,
            {},
            { timeout: 10_000 }
        );
        res.json(response.data);
    } catch (err) {
        if (err.code === 'ECONNREFUSED') return next(Object.assign(new Error('Agent service offline'), { status: 503 }));
        next(err);
    }
});

// GET /api/student/me/alerts/stream — SSE stream for realtime alerts
router.get('/me/alerts/stream', requireAuth, async (req, res, next) => {
    try {
        const upstream = await axios.get(
            `${AGENT_SERVICE}/student/${req.user.studentId}/alerts/stream`,
            { responseType: 'stream', timeout: 0 }
        );
        res.writeHead(200, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        });
        upstream.data.pipe(res);
        req.on('close', () => upstream.data.destroy());
    } catch (err) {
        if (err.code === 'ECONNREFUSED') return next(Object.assign(new Error('Agent service offline'), { status: 503 }));
        next(err);
    }
});

// POST /api/student/me/alerts/scan — Manual trigger for testing
router.post('/me/alerts/scan', requireAuth, async (req, res, next) => {
    try {
        const response = await axios.post(
            `${AGENT_SERVICE}/student/${req.user.studentId}/alerts/scan`,
            {},
            { timeout: 10_000 }
        );
        res.json(response.data);
    } catch (err) {
        if (err.code === 'ECONNREFUSED') return next(Object.assign(new Error('Agent service offline'), { status: 503 }));
        next(err);
    }
});

// GET /api/student/me/min-scores?target_cgpa=7.5 — Minimum Score Calculator
router.get('/me/min-scores', requireAuth, (req, res, next) => {
    const target = req.query.target_cgpa || 7.5;
    proxyGet(`/student/${req.user.studentId}/min-scores?target_cgpa=${target}`, res, next);
});


// POST /api/student/me/simulate
router.post('/me/simulate', requireAuth, async (req, res, next) => {
    try {
        const response = await axios.post(
            `${AGENT_SERVICE}/student/${req.user.studentId}/simulate`,
            req.body,
            { timeout: 20_000 }
        );
        res.json(response.data);
    } catch (err) {
        if (err.code === 'ECONNREFUSED') return next(Object.assign(new Error('Agent service offline'), { status: 503 }));
        next(err);
    }
});

// POST /api/student/quiz/generate
router.post('/quiz/generate', requireAuth, async (req, res, next) => {
    try {
        const response = await axios.post(`${AGENT_SERVICE}/quiz/generate`, req.body, { timeout: 30_000 });
        res.json(response.data);
    } catch (err) {
        if (err.code === 'ECONNREFUSED') return next(Object.assign(new Error('Agent service offline'), { status: 503 }));
        next(err);
    }
});

// POST /api/student/me/tutor/teach — AI Visual Tutor (SSE stream)
router.post('/me/tutor/teach', requireAuth, async (req, res, next) => {
    try {
        const upstream = await axios.post(
            `${AGENT_SERVICE}/student/${req.user.studentId}/tutor/teach`,
            req.body,
            { responseType: 'stream', timeout: 0 }
        );
        res.writeHead(200, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        });
        upstream.data.pipe(res);
        req.on('close', () => upstream.data.destroy());
    } catch (err) {
        if (err.code === 'ECONNREFUSED') return next(Object.assign(new Error('Agent service offline'), { status: 503 }));
        next(err);
    }
});

// POST /api/student/me/tutor/ask — Follow-up Q&A in tutor session
router.post('/me/tutor/ask', requireAuth, async (req, res, next) => {
    try {
        const { data } = await axios.post(
            `${AGENT_SERVICE}/student/${req.user.studentId}/tutor/ask`,
            req.body
        );
        res.json(data);
    } catch (err) {
        if (err.response?.data) return res.status(err.response.status).json(err.response.data);
        if (err.code === 'ECONNREFUSED') return next(Object.assign(new Error('Agent service offline'), { status: 503 }));
        next(err);
    }
});

export default router;
