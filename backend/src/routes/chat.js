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

        const { message, sessionId, lang = 'en', history = [] } = req.body;
        const studentId = req.user.studentId;

        const payload = {
            message,
            session_id: sessionId || uuidv4(),
            student_id: studentId,
            lang,
            history,
        };

        try {
            const agentResponse = await axios.post(`${AGENT_SERVICE}/chat`, payload, {
                timeout: 30_000,        // 30s — LLM can be slow
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

export default router;
