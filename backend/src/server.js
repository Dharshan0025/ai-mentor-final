/**
 * AI-Mentor API Gateway — Express Server
 * Thin proxy layer: Auth, rate limiting, ERP data, agent bridge
 * Clean layered architecture: routes → services → (DB | agent service)
 */
import 'dotenv/config';
import express from 'express';
import cors from 'cors';
import helmet from 'helmet';
import morgan from 'morgan';
import rateLimit from 'express-rate-limit';

import authRouter from './routes/auth.js';
import studentRouter from './routes/student.js';
import chatRouter from './routes/chat.js';

const app = express();
const PORT = process.env.PORT || 3001;

// ── Middleware ──────────────────────────────────────────────────────────────
app.use(helmet());
app.use(morgan('dev'));

app.use(cors({
    origin: [
        process.env.FRONTEND_ORIGIN || 'http://localhost:5173',
    ],
    credentials: true,
}));

app.use(express.json({ limit: '10mb' }));

// Global rate limit — 100 requests per minute per IP
app.use(rateLimit({
    windowMs: 60 * 1000,
    max: 100,
    standardHeaders: true,
    legacyHeaders: false,
    message: { error: 'Too many requests, please slow down.' },
}));

// ── Routes ──────────────────────────────────────────────────────────────────
app.use('/api/auth', authRouter);
app.use('/api/student', studentRouter);
app.use('/api/chat', chatRouter);

// Phase 7: AI Debugger (no auth for quick analysis)
import axios from 'axios';
app.post('/api/debug/analyze', async (req, res, next) => {
    try {
        const AGENT = process.env.AGENT_SERVICE_URL || 'http://127.0.0.1:8000';
        const { data } = await axios.post(`${AGENT}/debug/analyze`, req.body, { timeout: 30_000 });
        res.json(data);
    } catch (err) {
        if (err.response?.data) return res.status(err.response.status).json(err.response.data);
        next(err);
    }
});

// Phase 7: Leaderboard (public – no auth needed)
app.get('/api/leaderboard', async (req, res, next) => {
    try {
        const AGENT = process.env.AGENT_SERVICE_URL || 'http://127.0.0.1:8000';
        const qs = req.query.subject_code ? `?subject_code=${req.query.subject_code}` : '';
        const { data } = await axios.get(`${AGENT}/leaderboard${qs}`, { timeout: 10_000 });
        res.json(data);
    } catch (err) {
        if (err.response?.data) return res.status(err.response.status).json(err.response.data);
        next(err);
    }
});

// Health
app.get('/health', (_req, res) => {
    res.json({ status: 'ok', service: 'ai-mentor-backend', version: '0.1.0' });
});

// ── Centralized Error Handler ───────────────────────────────────────────────
app.use((err, _req, res, _next) => {
    const status = err.status || 500;
    const message = status < 500 ? err.message : 'Internal server error';

    if (status >= 500) console.error('[ERROR]', err);

    res.status(status).json({
        error: message,
        code: err.code || 'UNKNOWN_ERROR',
    });
});

// ── Start ───────────────────────────────────────────────────────────────────
app.listen(PORT, () => {
    console.log(`🚀 AI-Mentor backend listening on http://localhost:${PORT}`);
    console.log(`🤖 Agent service: ${process.env.AGENT_SERVICE_URL}`);
});

export default app;
