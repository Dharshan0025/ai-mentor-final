/**
 * Auth Middleware — JWT token verification
 * Attaches req.user = { studentId, name, dept }
 */
import jwt from 'jsonwebtoken';

export function requireAuth(req, res, next) {
    const authHeader = req.headers.authorization;
    // Support token as query param for SSE (EventSource can't set headers)
    const queryToken = req.query.token;

    if (!authHeader?.startsWith('Bearer ') && !queryToken) {
        return res.status(401).json({ error: 'Missing auth token', code: 'NO_TOKEN' });
    }

    const token = authHeader ? authHeader.slice(7) : queryToken;
    const secret = process.env.JWT_SECRET || 'dev_secret_change_in_production';

    try {
        const payload = jwt.verify(token, secret);
        req.user = payload;
        next();
    } catch (err) {
        const code = err.name === 'TokenExpiredError' ? 'TOKEN_EXPIRED' : 'INVALID_TOKEN';
        return res.status(401).json({ error: 'Invalid or expired token', code });
    }
}
