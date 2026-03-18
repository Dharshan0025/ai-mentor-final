import { useState } from 'react';
import { Outlet, NavLink } from 'react-router-dom';
import {
    LayoutDashboard, MessageCircle, TrendingUp, BookOpen,
    Calendar, Briefcase, User, LogOut, Bell, X, AlertTriangle, Info,
    GraduationCap, BarChart3, Timer, Brain, Map, Puzzle
} from 'lucide-react';
import styles from './AppLayout.module.css';
import { useAuth } from '../../context/AuthContext';
import useAlertStream from '../../hooks/useAlertStream';
import NotificationToast from '../NotificationToast/NotificationToast';

const NAV_ITEMS = [
    { to: '/dashboard', icon: <LayoutDashboard size={20} />, label: 'Dashboard' },
    { to: '/chat', icon: <MessageCircle size={20} />, label: 'Mentor Chat' },
    { to: '/prediction', icon: <TrendingUp size={20} />, label: 'Predictions' },
    { to: '/learning', icon: <BookOpen size={20} />, label: 'Learning' },
    { to: '/schedule', icon: <Calendar size={20} />, label: 'Schedule' },
    { to: '/career', icon: <Briefcase size={20} />, label: 'Career' },
    { to: '/tutor', icon: <GraduationCap size={20} />, label: 'AI Tutor' },
    { to: '/learn/progress', icon: <BarChart3 size={20} />, label: 'My Progress' },
    { to: '/learn/exam', icon: <Timer size={20} />, label: 'Exam Mode' },
    { to: '/knowledge', icon: <Brain size={20} />, label: 'Knowledge Hub' },
    { to: '/roadmap', icon: <Map size={20} />, label: 'Study Roadmap' },
    { to: '/problems', icon: <Puzzle size={20} />, label: 'Problem Bank' },
    { to: '/profile', icon: <User size={20} />, label: 'Profile' },
];

const SEVERITY_STYLE = {
    critical: { bg: '#EF444415', border: '#EF4444', text: '#EF4444', icon: <AlertTriangle size={14} /> },
    warning: { bg: '#F59E0B15', border: '#F59E0B', text: '#F59E0B', icon: <AlertTriangle size={14} /> },
    notice: { bg: '#3B82F615', border: '#3B82F6', text: '#3B82F6', icon: <Info size={14} /> },
};

export default function AppLayout() {
    const { user, logout } = useAuth();
    const [alertsOpen, setAlertsOpen] = useState(false);

    const name = user?.name || 'Student';
    const dept = user?.dept || user?.department || 'CSBS';
    const semester = user?.current_semester || user?.semester || '—';
    const cgpa = user?.cgpa || '—';

    // Realtime SSE alert stream (replaces polling)
    const { alerts, unreadCount, hasCritical, dismiss, toasts, clearToast } = useAlertStream();

    return (
        <div className={styles.layout}>
            {/* Sidebar */}
            <aside className={styles.sidebar}>
                {/* Logo */}
                <div className={styles.logo}>
                    <div className={styles.logoIcon}>✦</div>
                    <span className={styles.logoText}>AI Mentor</span>
                </div>

                {/* Student avatar */}
                <div className={styles.studentInfo}>
                    <div className={styles.avatarWrap}>
                        <div className={styles.avatarFallback}>{name.charAt(0)}</div>
                    </div>
                    <div className={styles.studentMeta}>
                        <span className={styles.studentName}>{name}</span>
                        <span className={styles.studentSub}>{dept} · Sem {semester}</span>
                    </div>
                    <div className={styles.cgpaChip}>{cgpa}</div>
                </div>

                <hr className={`divider ${styles.divider}`} />

                {/* Nav */}
                <nav className={styles.nav}>
                    {NAV_ITEMS.map(item => (
                        <NavLink
                            key={item.to}
                            to={item.to}
                            className={({ isActive }) =>
                                `${styles.navItem} ${isActive ? styles.navItemActive : ''}`
                            }
                        >
                            <span className={styles.navIcon}>{item.icon}</span>
                            <span className={styles.navLabel}>{item.label}</span>
                        </NavLink>
                    ))}
                </nav>

                {/* Alert Bell */}
                <button
                    className={styles.alertBell}
                    onClick={() => setAlertsOpen(o => !o)}
                    title={unreadCount > 0 ? `${unreadCount} proactive alert${unreadCount > 1 ? 's' : ''}` : 'No alerts'}
                    style={{ borderColor: hasCritical ? '#EF4444' : 'var(--border)' }}
                >
                    <Bell size={16} color={hasCritical ? '#EF4444' : 'var(--text-2)'} />
                    <span>Alerts</span>
                    {unreadCount > 0 && (
                        <span className={styles.alertBadge} style={{
                            background: hasCritical ? '#EF4444' : '#F59E0B',
                        }}>
                            {unreadCount}
                        </span>
                    )}
                </button>

                {/* Footer */}
                <div className={styles.sidebarFooter}>
                    <div className={styles.langToggle}>
                        <button className={`${styles.langBtn} ${styles.langActive}`}>EN</button>
                        <button className={styles.langBtn}>தா</button>
                    </div>
                    <button
                        className={styles.logoutBtn}
                        onClick={logout}
                        title="Sign out"
                        id="logout-btn"
                    >
                        <LogOut size={15} />
                        Sign out
                    </button>
                </div>
            </aside>

            {/* Main content */}
            <main className={styles.main}>
                <Outlet />
            </main>

            {/* Proactive Alerts Panel */}
            {alertsOpen && (
                <>
                    <div
                        className={styles.alertsOverlay}
                        onClick={() => setAlertsOpen(false)}
                    />
                    <div className={styles.alertsPanel}>
                        <div className={styles.alertsPanelHeader}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <Bell size={16} color="var(--accent)" />
                                <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>
                                    Proactive Alerts
                                </span>
                                {unreadCount > 0 && (
                                    <span style={{
                                        background: hasCritical ? '#EF4444' : '#F59E0B',
                                        color: '#fff', borderRadius: 999,
                                        padding: '1px 7px', fontSize: '0.7rem', fontWeight: 700,
                                    }}>
                                        {unreadCount}
                                    </span>
                                )}
                            </div>
                            <button
                                onClick={() => setAlertsOpen(false)}
                                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}
                            >
                                <X size={16} color="var(--text-2)" />
                            </button>
                        </div>

                        <div className={styles.alertsList}>
                            {alerts.length === 0 && (
                                <div style={{ padding: '24px 16px', textAlign: 'center' }}>
                                    <p style={{ fontSize: '1.5rem', margin: '0 0 6px' }}>🎉</p>
                                    <p style={{ color: 'var(--text-2)', fontSize: '0.85rem' }}>
                                        No active alerts. All systems clear!
                                    </p>
                                </div>
                            )}
                            {alerts.map(alert => {
                                const s = SEVERITY_STYLE[alert.severity] || SEVERITY_STYLE.notice;
                                return (
                                    <div
                                        key={alert.id}
                                        className={styles.alertItem}
                                        style={{ background: s.bg, borderLeft: `3px solid ${s.border}` }}
                                    >
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                                            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                                                <span style={{ color: s.text, flexShrink: 0, paddingTop: 1 }}>
                                                    {s.icon}
                                                </span>
                                                <div>
                                                    {alert.subject_code && (
                                                        <span style={{
                                                            fontSize: '0.65rem', fontWeight: 700,
                                                            color: s.text, textTransform: 'uppercase',
                                                            letterSpacing: '0.05em',
                                                        }}>
                                                            {alert.subject_code}
                                                        </span>
                                                    )}
                                                    <p style={{ margin: 0, fontSize: '0.8rem', lineHeight: 1.4, color: 'var(--text-1)' }}>
                                                        {alert.message}
                                                    </p>
                                                </div>
                                            </div>
                                            <button
                                                onClick={() => dismiss(alert.id)}
                                                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px 4px', flexShrink: 0 }}
                                                title="Dismiss"
                                            >
                                                <X size={12} color="var(--text-3)" />
                                            </button>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>

                        <div style={{ padding: '10px 16px', borderTop: '1px solid var(--border)', fontSize: '0.72rem', color: 'var(--text-3)', display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10B981', display: 'inline-block', animation: 'pulse-dot 2s ease-in-out infinite' }} />
                            Live — streaming via SSE
                        </div>
                    </div>
                </>
            )}

            {/* Realtime notification toasts */}
            <NotificationToast toasts={toasts} onClear={clearToast} />
        </div>
    );
}
