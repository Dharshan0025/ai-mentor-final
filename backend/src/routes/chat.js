/**
 * Chat Routes — POST /api/chat
 * Proxies to Python agent service + handles streaming
 */
import { Router } from 'express';
import axios from 'axios';
import { v4 as uuidv4 } from 'uuid';
import { body, validationResult } from 'express-validator';
import { requireAuth } from '../middleware/auth.js';

const router = Router();

const AGENT_SERVICE = process.env.AGENT_SERVICE_URL || 'http://localhost:8000';

/**
 * POST /api/chat
 * Protected: requires JWT
 * Body: { message, sessionId?, lang?, history? }
 */
router.post(
    '/',
    requireAuth,
    [
        body('message').trim().notEmpty().isLength({ max: 4000 }),
        body('lang').optional().isIn(['en', 'ta']),
    ],
    async (req, res, next) => {
        const errors = validationResult(req);
        if (!errors.isEmpty()) {
            return res.status(400).json({ error: 'Invalid request', details: errors.array() });
        }

        const { message, sessionId, lang = 'en', history = [], show_pipeline = true } = req.body;
        const studentId = req.user.studentId;

        const payload = {
            message,
            session_id: sessionId || uuidv4(),
            student_id: studentId,
            lang,
            history,
            show_pipeline,
        };

        try {
            const agentResponse = await axios.post(`${AGENT_SERVICE}/chat`, payload, {
                timeout: 120_000,        // 2 minutes — multi-agent processing can be slow
                headers: { 'Content-Type': 'application/json' },
            });

            res.json(agentResponse.data);
        } catch (err) {
            if (err.code === 'ECONNREFUSED') {
                return next(Object.assign(new Error('Agent service is offline'), { status: 503 }));
            }
            if (err.response?.status >= 400) {
                return next(Object.assign(new Error('Agent service error'), { status: 502 }));
            }
            next(err);
        }
    }
);

/**
 * GET /api/chat/sessions
 * Protected: requires JWT
 */
router.get(
    '/sessions',
    requireAuth,
    async (req, res, next) => {
        try {
            const studentId = req.user.studentId;
            const response = await axios.get(`${AGENT_SERVICE}/student/${studentId}/chat/sessions`, {
                timeout: 10_000
            });
            res.json(response.data);
        } catch (err) {
            next(err);
        }
    }
);

/**
 * GET /api/chat/:sessionId/history
 * Protected: requires JWT
 */
router.get(
    '/:sessionId/history',
    requireAuth,
    async (req, res, next) => {
        try {
            const { sessionId } = req.params;
            const studentId = req.user.studentId;
            const response = await axios.get(`${AGENT_SERVICE}/student/${studentId}/chat/${sessionId}/history`, {
                timeout: 10_000
            });
            res.json(response.data);
        } catch (err) {
            next(err);
        }
    }
);

export default router;
