import { useState, useEffect, useRef, useCallback } from 'react';

const BASE = import.meta.env.VITE_API_URL || 'http://localhost:3001/api';

/**
 * SSE hook that streams proactive alerts in real-time.
 * Falls back to polling if SSE connection fails.
 *
 * Returns: { alerts, unreadCount, hasCritical, dismiss, toasts, clearToast }
 */
export default function useAlertStream() {
    const [alerts, setAlerts] = useState([]);
    const [unreadCount, setUnreadCount] = useState(0);
    const [toasts, setToasts] = useState([]);
    const esRef = useRef(null);
    const retryRef = useRef(0);
    const fallbackRef = useRef(null);

    const token = localStorage.getItem('ai_mentor_token');

    const bootstrapAlerts = useCallback(async () => {
        try {
            const res = await fetch(`${BASE}/student/me/alerts`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) return;
            const data = await res.json();
            setAlerts(data.alerts || []);
            setUnreadCount(data.unread_count || 0);
        } catch { /* silent */ }
    }, [token]);

    const connect = useCallback(() => {
        if (!token) return;

        // EventSource doesn't support custom headers, so pass token as query param
        const url = `${BASE}/student/me/alerts/stream?token=${encodeURIComponent(token)}`;

        try {
            const es = new EventSource(url);
            esRef.current = es;

            es.addEventListener('count', (e) => {
                try {
                    const data = JSON.parse(e.data);
                    setUnreadCount(data.unread_count ?? 0);
                } catch { /* ignore parse errors */ }
            });

            es.addEventListener('alert', (e) => {
                try {
                    const alert = JSON.parse(e.data);
                    setAlerts(prev => {
                        if (prev.some(a => a.id === alert.id)) return prev;
                        return [alert, ...prev];
                    });
                    // Push to toast queue
                    setToasts(prev => [...prev, { ...alert, _ts: Date.now() }]);
                } catch { /* ignore */ }
            });

            es.onopen = () => {
                retryRef.current = 0;
                bootstrapAlerts();
            };

            es.onerror = () => {
                es.close();
                esRef.current = null;
                // Exponential backoff: 5s, 10s, 20s, cap at 30s
                const delay = Math.min(5000 * Math.pow(2, retryRef.current), 30000);
                retryRef.current += 1;
                setTimeout(connect, delay);
            };
        } catch {
            // SSE not supported — fall back to polling
            startPolling();
        }
    }, [bootstrapAlerts, token]);

    const startPolling = useCallback(() => {
        if (fallbackRef.current) return;
        const poll = async () => bootstrapAlerts();
        poll();
        fallbackRef.current = setInterval(poll, 30_000);
    }, [bootstrapAlerts]);

    useEffect(() => {
        connect();
        return () => {
            esRef.current?.close();
            if (fallbackRef.current) clearInterval(fallbackRef.current);
        };
    }, [connect]);

    const dismiss = useCallback(async (alertId) => {
        setAlerts(prev => prev.filter(a => a.id !== alertId));
        setUnreadCount(prev => Math.max(0, prev - 1));
        try {
            await fetch(`${BASE}/student/me/alerts/${alertId}/read`, {
                method: 'POST',
                headers: {
                    Authorization: `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
            });
        } catch { /* silent */ }
    }, [token]);

    const clearToast = useCallback((ts) => {
        setToasts(prev => prev.filter(t => t._ts !== ts));
    }, []);

    const hasCritical = alerts.some(a => a.severity === 'critical');

    return { alerts, unreadCount, hasCritical, dismiss, toasts, clearToast };
}
