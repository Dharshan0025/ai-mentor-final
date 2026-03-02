/**
 * Auth Routes — POST /api/auth/login, /logout, /me
 * Delegates credential verification to the Python agent (bcrypt in DB).
 * JWT is issued here after the agent confirms valid credentials.
 */
import { Router } from 'express';
import jwt from 'jsonwebtoken';
import axios from 'axios';
import { body, validationResult } from 'express-validator';
import { requireAuth } from '../middleware/auth.js';

const router = Router();
const AGENT_SERVICE = process.env.AGENT_SERVICE_URL || 'http://localhost:8000';
const JWT_SECRET = process.env.JWT_SECRET || 'dev_secret_change_in_production';
const JWT_EXPIRES_IN = process.env.JWT_EXPIRES_IN || '7d';

/**
 * POST /api/auth/login
 * Body: { collegeId, password }
 * Returns: { token, student: <full ERP profile> }
 */
router.post(
    '/login',
    [
        body('collegeId').trim().notEmpty().withMessage('College ID is required'),
        body('password').notEmpty().withMessage('Password is required'),
    ],
    async (req, res, next) => {
        const errors = validationResult(req);
        if (!errors.isEmpty()) {
            return res.status(400).json({ error: 'Validation failed', details: errors.array() });
        }

        const { collegeId, password } = req.body;

        try {
            // Delegate bcrypt verification to the Python agent
            const { data: studentProfile } = await axios.post(
                `${AGENT_SERVICE}/auth/login`,
                { college_id: collegeId.toUpperCase(), password },
                { timeout: 8000 }
            );

            const token = jwt.sign(
                {
                    studentId: studentProfile.college_id || collegeId,
                    name: studentProfile.name,
                    dept: studentProfile.dept || studentProfile.department,
                },
                JWT_SECRET,
                { expiresIn: JWT_EXPIRES_IN }
            );

            return res.json({ token, student: studentProfile });

        } catch (err) {
            if (err.response?.status === 401) {
                return res.status(401).json({
                    error: 'Invalid College ID or password',
                    code: 'INVALID_CREDENTIALS',
                });
            }
            if (err.response?.status === 400) {
                return res.status(400).json({ error: 'College ID and password are required' });
            }
            if (err.code === 'ECONNREFUSED' || err.code === 'ETIMEDOUT') {
                return res.status(503).json({
                    error: 'Authentication service unavailable. Please try again.',
                    code: 'SERVICE_UNAVAILABLE',
                });
            }
            next(err);
        }
    }
);

/**
 * POST /api/auth/logout
 * Stateless JWT — client discards token.
 */
router.post('/logout', (_req, res) => {
    res.json({ message: 'Logged out successfully' });
});

/**
 * GET /api/auth/me
 * Returns the student profile for the authenticated user.
 * Useful for refreshing the frontend state on page load.
 */
router.get('/me', requireAuth, async (req, res, next) => {
    try {
        const { data } = await axios.get(
            `${AGENT_SERVICE}/student/${req.user.studentId}/profile`,
            { timeout: 8000 }
        );
        res.json(data);
    } catch (err) {
        if (err.code === 'ECONNREFUSED') {
            return next(Object.assign(new Error('Agent service offline'), { status: 503 }));
        }
        next(err);
    }
});

export default router;
