/**
 * Login Page — Dedicated /login route
 * Split layout: left = branding/stats, right = login card
 * Quick-fill student chips | show/hide password | real-time validation
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye, EyeOff, ArrowRight, Zap, TrendingUp, Users, BookOpen } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import styles from './Login.module.css';

const DEMO_STUDENTS = [
    { id: '22CSBS001', name: 'Dharshan B', year: 'Y4', tag: 'high' },
    { id: '22CSBS015', name: 'Meena S', year: 'Y4', tag: 'avg' },
    { id: '22CSBS042', name: 'Rahul T', year: 'Y4', tag: 'risk' },
    { id: '23CSBS004', name: 'Sneha M', year: 'Y3', tag: 'high' },
    { id: '24CSBS007', name: 'Vikram S', year: 'Y2', tag: 'high' },
    { id: '25CSBS001', name: 'Ananya R', year: 'Y1', tag: 'high' },
];

const STATS = [
    { icon: <Users size={18} />, label: 'Students', value: '12' },
    { icon: <BookOpen size={18} />, label: 'Subjects', value: '164' },
    { icon: <TrendingUp size={18} />, label: 'Semesters', value: '8' },
    { icon: <Zap size={18} />, label: 'AI Agents', value: '8' },
];

const TAG_LABELS = { high: '⭐ Top', avg: '📊 Avg', risk: '⚠️ Risk' };
const TAG_COLORS = { high: '#10B981', avg: '#3B82F6', risk: '#EF4444' };

export default function Login() {
    const navigate = useNavigate();
    const { login } = useAuth();

    const [collegeId, setCollegeId] = useState('');
    const [password, setPassword] = useState('');
    const [showPass, setShowPass] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [shake, setShake] = useState(false);

    const fillDemo = (id) => {
        setCollegeId(id);
        setPassword('Test@1234');
        setError('');
    };

    const triggerShake = () => {
        setShake(true);
        setTimeout(() => setShake(false), 600);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');

        const id = collegeId.trim().toUpperCase();
        if (!id) { setError('Please enter your College ID.'); triggerShake(); return; }
        if (!password) { setError('Please enter your password.'); triggerShake(); return; }

        setLoading(true);
        try {
            await login(id, password);
            navigate('/dashboard', { replace: true });
        } catch (err) {
            const status = err.response?.status;
            if (status === 401) {
                setError('Invalid College ID or password. Check your credentials.');
            } else if (status === 503) {
                setError('Server is starting up — please wait a moment and try again.');
            } else {
                setError('Cannot connect to server. Make sure backend is running.');
            }
            triggerShake();
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className={styles.page}>
            {/* ── Left Panel ─────────────────────────────── */}
            <div className={styles.left}>
                <div className={styles.leftInner}>
                    {/* Logo */}
                    <div className={styles.logo}>
                        <div className={styles.logoIcon}>✦</div>
                        <span className={styles.logoText}>AI Mentor</span>
                    </div>

                    <div className={styles.tagline}>
                        <h1 className={styles.headline}>
                            Your smartest<br />
                            <span className={styles.accent}>academic mentor</span>
                        </h1>
                        <p className={styles.sub}>
                            ERP-powered AI that knows your full academic history,
                            predicts performance, and builds a personalised path to success.
                        </p>
                    </div>

                    {/* Stats bar */}
                    <div className={styles.statsRow}>
                        {STATS.map(s => (
                            <div key={s.label} className={styles.stat}>
                                <div className={styles.statIcon}>{s.icon}</div>
                                <div className={styles.statVal}>{s.value}</div>
                                <div className={styles.statLbl}>{s.label}</div>
                            </div>
                        ))}
                    </div>

                    {/* Decorative glow */}
                    <div className={styles.glow} />
                </div>
            </div>

            {/* ── Right Panel ─────────────────────────────── */}
            <div className={styles.right}>
                <div className={styles.card}>
                    <div className={styles.cardHeader}>
                        <h2 className={styles.cardTitle}>Sign in</h2>
                        <p className={styles.cardSub}>
                            Use your institutional College ID and password
                        </p>
                    </div>

                    {/* Quick-fill chips */}
                    <div className={styles.chips}>
                        <span className={styles.chipsLabel}>Quick demo:</span>
                        <div className={styles.chipRow}>
                            {DEMO_STUDENTS.map(s => (
                                <button
                                    key={s.id}
                                    type="button"
                                    className={`${styles.chip} ${collegeId === s.id ? styles.chipActive : ''}`}
                                    onClick={() => fillDemo(s.id)}
                                    style={{ '--chip-color': TAG_COLORS[s.tag] }}
                                >
                                    <span className={styles.chipYear}>{s.year}</span>
                                    {s.name}
                                    <span className={styles.chipTag}>{TAG_LABELS[s.tag]}</span>
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Login form */}
                    <form
                        className={`${styles.form} ${shake ? styles.shake : ''}`}
                        onSubmit={handleSubmit}
                        noValidate
                        id="login-form"
                    >
                        <div className={styles.field}>
                            <label className={styles.label} htmlFor="college-id">
                                College ID
                            </label>
                            <input
                                id="college-id"
                                className={`${styles.input} ${error ? styles.inputError : ''}`}
                                type="text"
                                placeholder="e.g. 22CSBS001"
                                value={collegeId}
                                onChange={e => { setCollegeId(e.target.value.toUpperCase()); setError(''); }}
                                autoComplete="username"
                                spellCheck={false}
                            />
                        </div>

                        <div className={styles.field}>
                            <label className={styles.label} htmlFor="password">
                                Password
                            </label>
                            <div className={styles.passWrap}>
                                <input
                                    id="password"
                                    className={`${styles.input} ${error ? styles.inputError : ''}`}
                                    type={showPass ? 'text' : 'password'}
                                    placeholder="Enter your password"
                                    value={password}
                                    onChange={e => { setPassword(e.target.value); setError(''); }}
                                    autoComplete="current-password"
                                />
                                <button
                                    type="button"
                                    className={styles.eyeBtn}
                                    onClick={() => setShowPass(v => !v)}
                                    aria-label={showPass ? 'Hide password' : 'Show password'}
                                >
                                    {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                                </button>
                            </div>
                        </div>

                        {error && (
                            <div className={styles.errorBox} role="alert">
                                <span className={styles.errorDot}>●</span>
                                {error}
                            </div>
                        )}

                        <button
                            id="login-submit"
                            type="submit"
                            className={styles.submitBtn}
                            disabled={loading}
                        >
                            {loading
                                ? <span className={styles.spinner} />
                                : <>Sign in <ArrowRight size={16} /></>
                            }
                        </button>

                        <p className={styles.hint}>
                            Demo password for all students: <strong>Test@1234</strong>
                        </p>
                    </form>
                </div>

                <p className={styles.footer}>
                    © 2026 AI Mentor · DPDP Act 2023 Compliant
                </p>
            </div>
        </div>
    );
}
