import { useEffect, useState } from 'react';
import { AlertTriangle, Info, X } from 'lucide-react';
import styles from './NotificationToast.module.css';

const SEVERITY = {
    critical: { icon: <AlertTriangle size={14} />, color: '#EF4444' },
    warning:  { icon: <AlertTriangle size={14} />, color: '#F59E0B' },
    notice:   { icon: <Info size={14} />,          color: '#3B82F6' },
};

function Toast({ alert, onClose }) {
    const [exiting, setExiting] = useState(false);
    const s = SEVERITY[alert.severity] || SEVERITY.notice;

    useEffect(() => {
        const timer = setTimeout(() => {
            setExiting(true);
            setTimeout(onClose, 300);
        }, 6000);
        return () => clearTimeout(timer);
    }, [onClose]);

    const handleClose = () => {
        setExiting(true);
        setTimeout(onClose, 300);
    };

    return (
        <div
            className={`${styles.toast} ${exiting ? styles.toastExit : ''}`}
            style={{ borderLeftColor: s.color }}
        >
            <span className={styles.toastIcon} style={{ color: s.color }}>{s.icon}</span>
            <div className={styles.toastBody}>
                {alert.subject_code && (
                    <span className={styles.toastLabel} style={{ color: s.color }}>
                        {alert.subject_code}
                    </span>
                )}
                <p className={styles.toastMsg}>{alert.message}</p>
            </div>
            <button className={styles.toastClose} onClick={handleClose}>
                <X size={12} />
            </button>
        </div>
    );
}

export default function NotificationToast({ toasts, onClear }) {
    if (!toasts || toasts.length === 0) return null;

    return (
        <div className={styles.container}>
            {toasts.slice(-3).map(t => (
                <Toast
                    key={t._ts}
                    alert={t}
                    onClose={() => onClear(t._ts)}
                />
            ))}
        </div>
    );
}
