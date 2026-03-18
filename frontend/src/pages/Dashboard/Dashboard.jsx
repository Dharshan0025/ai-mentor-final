/**
 * Comprehensive ERP Dashboard — Student Intelligence Hub
 *
 * Sections:
 *  1. Header (identity + quick badges)
 *  2. Metric strip (5 KPIs)
 *  3. CGPA chart + AI Intelligence Briefing
 *  4. Subject Intelligence Grid (current sem)
 *  5. Assignment Board + Attendance bars
 *  6. Historical Semester Records (accordion)
 *  7. Next Semester Preview
 *  8. Activities timeline | Arrear tracker | Library + Mentoring
 *  9. Fee timeline
 * 10. Placement Zone (Y4+ only)
 * 11. Chat entry + Quick actions
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { Line } from 'react-chartjs-2';
import { Link, useNavigate } from 'react-router-dom';
import {
    Chart as ChartJS, CategoryScale, LinearScale, PointElement,
    LineElement, Tooltip, Filler
} from 'chart.js';
import {
    AlertTriangle, ArrowRight, Send, TrendingUp, BookOpen,
    Calendar, Briefcase, Activity, ClipboardList, Award,
    CheckCircle, Clock, XCircle, GraduationCap, Users,
    ChevronDown, ChevronRight, Eye, Star, BookMarked,
    MessageSquare, IndianRupee, Zap
} from 'lucide-react';
import styles from './Dashboard.module.css';
import { DashboardSkeleton } from '../../components/Skeleton/Skeleton';
import { getMyProfile, getBriefing, getMyBenchmark } from '../../services/api';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Filler);

/* ─── helpers ─────────────────────────────────────────────────────── */

function getHour() {
    const h = new Date().getHours();
    if (h < 12) return 'morning';
    if (h < 17) return 'afternoon';
    return 'evening';
}

function formatDue(dateLike) {
    if (!dateLike) return null;
    const date = new Date(dateLike);
    if (Number.isNaN(date.getTime())) return null;
    return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

function daysUntil(dateLike) {
    if (!dateLike) return null;
    const date = new Date(dateLike);
    if (Number.isNaN(date.getTime())) return null;
    return Math.ceil((date - new Date()) / 864e5);
}

const BLOOM = {
    1: { label: 'Remember', color: '#6B7280' },
    2: { label: 'Understand', color: '#3B82F6' },
    3: { label: 'Apply', color: '#10B981' },
    4: { label: 'Analyze', color: '#F59E0B' },
    5: { label: 'Evaluate', color: '#8B5CF6' },
    6: { label: 'Create', color: '#EC4899' },
};

function BloomPill({ level }) {
    const b = BLOOM[level] || BLOOM[1];
    return (
        <span style={{
            fontSize: '0.6rem', fontWeight: 700, padding: '2px 6px',
            borderRadius: 999, background: b.color + '18', color: b.color,
            whiteSpace: 'nowrap',
        }}>L{level} {b.label}</span>
    );
}

function AttPill({ pct }) {
    const n = Number(pct || 0);
    const color = n < 75 ? '#EF4444' : n < 85 ? '#F59E0B' : '#10B981';
    return <span style={{ fontSize: '0.75rem', fontWeight: 700, color }}>{n.toFixed(0)}%</span>;
}

function StatusDot({ status }) {
    const map = { safe: '#10B981', watch: '#F59E0B', risk: '#EF4444' };
    return (
        <span style={{
            display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
            background: map[status] || '#9CA3AF', flexShrink: 0,
        }} />
    );
}

function GradePill({ grade, status }) {
    const color = status === 'risk' ? '#EF4444' : status === 'watch' ? '#F59E0B' : '#10B981';
    return (
        <span style={{
            fontSize: '1rem', fontWeight: 800, color,
            fontFamily: "'Inter', sans-serif",
        }}>
            {Number(grade || 0).toFixed(1)}
        </span>
    );
}

const SUBJECT_TYPE_COLOR = {
    'theory': '#3B82F6',
    'lab': '#10B981',
    'elective': '#8B5CF6',
    'project': '#F59E0B',
    'management': '#EC4899',
};

const ACTIVITY_ICON = {
    'certification': <Award size={14} />,
    'online_course': <BookOpen size={14} />,
    'hackathon': <Zap size={14} />,
    'paper': <Eye size={14} />,
    'sports': <Star size={14} />,
    'cultural': <Star size={14} />,
};

/* ─── sub-components ─────────────────────────────────────────────── */

function SectionHeader({ title, icon, badge, extra }) {
    return (
        <div className={styles.secHeader}>
            <div className={styles.secTitle}>
                {icon}
                <h2>{title}</h2>
                {badge && <span className={styles.secBadge}>{badge}</span>}
            </div>
            {extra}
        </div>
    );
}

function SubjectCard({ sub }) {
    const att = sub.live_attendance || sub.attendance || 0;
    const attColor = att < 75 ? '#EF4444' : att < 85 ? '#F59E0B' : '#10B981';
    const statusBorder = {
        risk: '#EF4444',
        watch: '#F59E0B',
        safe: '#E5E7EB',
    }[sub.status] || '#E5E7EB';

    return (
        <div className={styles.subjectCard} style={{ borderTopColor: statusBorder }}>
            <div className={styles.subjectCardTop}>
                <span className={styles.subjectCode}>{sub.code}</span>
                <GradePill grade={sub.grade} status={sub.status} />
            </div>
            <div className={styles.subjectName}>{sub.name}</div>

            {/* Attendance bar */}
            <div className={styles.attBar}>
                <div
                    className={styles.attBarFill}
                    style={{ width: `${Math.min(att, 100)}%`, background: attColor }}
                />
                <div className={styles.attLine75} />
            </div>
            <div className={styles.subjectMeta}>
                <AttPill pct={att} />
                <BloomPill level={sub.bloomLevel} />
                {sub.predicted > 0 && (
                    <span style={{ fontSize: '0.65rem', color: '#9CA3AF' }}>
                        →{Number(sub.predicted).toFixed(1)}
                    </span>
                )}
            </div>
            <div className={styles.subjectCredits}>
                {sub.creditWeight}cr · <StatusDot status={sub.status} />
                {' '}{sub.status}
            </div>
        </div>
    );
}

function AssignRow({ a }) {
    const icon = {
        submitted: <CheckCircle size={13} color="#10B981" />,
        late: <Clock size={13} color="#F59E0B" />,
        not_submitted: <XCircle size={13} color="#EF4444" />,
    }[a.submission_status] || <Clock size={13} color="#9CA3AF" />;

    const scoreColor = (a.scored_marks / a.max_marks) >= 0.75 ? '#10B981' : '#F59E0B';

    return (
        <div className={styles.assignRow}>
            {icon}
            <div className={styles.assignInfo}>
                <span className={styles.assignTitle}>{a.title}</span>
                <span className={styles.assignSub}>{a.subject_code} · {a.type}</span>
            </div>
            {a.submission_status === 'submitted' && a.max_marks > 0 && (
                <span style={{ fontSize: '0.8125rem', fontWeight: 700, color: scoreColor, flexShrink: 0 }}>
                    {a.scored_marks}/{a.max_marks}
                </span>
            )}
            {a.submission_status !== 'submitted' && a.due_date && (
                <span style={{ fontSize: '0.7rem', color: '#EF4444', flexShrink: 0 }}>
                    {new Date(a.due_date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                </span>
            )}
        </div>
    );
}

function HistoricalSem({ semKey, subjects }) {
    const [open, setOpen] = useState(false);
    const avgGrade = subjects.length
        ? (subjects.reduce((s, x) => s + x.grade, 0) / subjects.length).toFixed(2)
        : '—';

    return (
        <div className={styles.histBlock}>
            <button className={styles.histToggle} onClick={() => setOpen(o => !o)}>
                <span className={styles.histSemLabel}>Semester {semKey}</span>
                <span className={styles.histAvg}>Avg: {avgGrade}</span>
                <span style={{ fontSize: '0.7rem', color: '#9CA3AF' }}>{subjects.length} subjects</span>
                {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>
            {open && (
                <div className={styles.histTable}>
                    <div className={styles.histTableHeader}>
                        <span>Code</span>
                        <span>Subject</span>
                        <span>Grade</span>
                        <span>Att%</span>
                        <span>Credits</span>
                    </div>
                    {subjects.map((sub, i) => (
                        <div key={i} className={styles.histTableRow}>
                            <span className={styles.histCode}>{sub.code}</span>
                            <span className={styles.histName}>{sub.name}</span>
                            <span style={{
                                fontWeight: 700,
                                color: sub.status === 'risk' ? '#EF4444' : sub.grade >= 8 ? '#10B981' : '#1A1A1A'
                            }}>{Number(sub.grade).toFixed(1)}</span>
                            <span style={{ color: (sub.attendance || 0) < 75 ? '#EF4444' : '#6B7280' }}>
                                {sub.attendance || '—'}%
                            </span>
                            <span style={{ color: '#9CA3AF' }}>{sub.creditWeight}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

/* ─── Main Dashboard ─────────────────────────────────────────────── */

export default function Dashboard() {
    const navigate = useNavigate();
    const [student, setStudent] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [chatInput, setChatInput] = useState('');
    const [aiBrief, setAiBrief] = useState(null);
    const [briefLoading, setBriefLoading] = useState(true);
    const [learningBadge, setLearningBadge] = useState(null);
    const [benchmark, setBenchmark] = useState(null);

    const load = useCallback(async () => {
        setLoading(true); setError(null);
        try {
            setStudent(await getMyProfile());
        } catch {
            setError('Could not load profile. Is the backend running?');
        } finally {
            setLoading(false);
        }
    }, []);

    // Fetch AI morning brief independently (doesn't block profile load)
    useEffect(() => {
        setBriefLoading(true);
        getBriefing()
            .then(d => {
                setAiBrief(d);
                // Derive a simple learning style badge from AI brief metadata if present
                const style = d?.learning_style || d?.profile_style;
                if (style) setLearningBadge(style);
            })
            .catch(() => {
                setAiBrief(null);
                setLearningBadge(null);
            })
            .finally(() => setBriefLoading(false));
    }, []);

    // Peer benchmarking — "Where you stand"
    useEffect(() => {
        getMyBenchmark()
            .then(setBenchmark)
            .catch(() => setBenchmark(null));
    }, []);

    useEffect(() => { load(); }, [load]);

    // AI Briefing — derived from real data
    const briefing = useMemo(() => {
        if (!student) return [];
        const s = student;
        const items = [];
        const riskSubs = (s.subjects || []).filter(x => x.status === 'risk');
        const lowAtt = (s.subjects || []).filter(x => (x.live_attendance || 0) < 75);
        const pending = (s.assignments || []).filter(x => x.submission_status === 'not_submitted');
        const expiring = (s.library || []).filter(x => {
            if (!x.due_date) return false;
            const d = (new Date(x.due_date) - new Date()) / 864e5;
            return d >= 0 && d <= 5;
        });

        if (riskSubs.length > 0)
            items.push({ type: 'risk', text: `${riskSubs[0].name} is at risk — grade ${Number(riskSubs[0].grade).toFixed(1)}, predicted ${Number(riskSubs[0].predicted).toFixed(1)}. Needs immediate focus.` });
        if (lowAtt.length > 0)
            items.push({ type: 'warning', text: `${lowAtt.length} subject${lowAtt.length > 1 ? 's are' : ' is'} below 75% attendance — ${lowAtt[0].name} at ${Number(lowAtt[0].live_attendance).toFixed(0)}%.` });
        if (pending.length > 0)
            items.push({ type: 'deadline', text: `${pending.length} assignment${pending.length > 1 ? 's' : ''} pending this semester. Nearest: ${pending[0]?.title || 'check schedule'}.` });
        if (expiring.length > 0)
            items.push({ type: 'info', text: `Library book "${expiring[0].book_title}" is due in ${Math.ceil((new Date(expiring[0].due_date) - new Date()) / 864e5)} days.` });
        if (s.nextSemesterSubjects?.length > 0)
            items.push({ type: 'opportunity', text: `Next semester (Sem ${(s.semester || 0) + 1}) has ${s.nextSemesterSubjects.length} subjects. Preview them below to plan ahead.` });
        if (s.feeDue > 0)
            items.push({ type: 'warning', text: `Fee due: ₹${s.feeDue.toLocaleString('en-IN')} — one or more semester fees are pending.` });

        return items.slice(0, 4);
    }, [student]);

    if (loading) return <DashboardSkeleton />;
    if (error) return (
        <div className={styles.loadState}>
            <AlertTriangle size={26} color="#EF4444" />
            <p style={{ color: '#EF4444' }}>{error}</p>
            <button className={styles.retryBtn} onClick={load}>Retry</button>
        </div>
    );

    const s = student;
    const cgpaHistory = s.cgpaHistory || [];
    const subjects = s.subjects || [];
    const assignments = s.assignments || [];
    const activities = s.activities || [];
    const arrears = s.arrears || [];
    const placement = s.placement || [];
    const feeRecords = s.feeRecords || [];
    const mentoring = s.mentoring || [];
    const library = s.library || [];
    const historicalSemesters = s.historicalSemesters || {};
    const nextSemSubjects = s.nextSemesterSubjects || [];
    const assignHealth = s.assignmentHealth || { total: 0, not_submitted: 0, submission_rate: 100 };
    const placementElig = s.placementEligibility;
    const riskSubs = subjects.filter(x => x.status !== 'safe');
    const activeArrears = arrears.filter(a => !a.cleared);
    const histSemKeys = Object.keys(historicalSemesters).sort((a, b) => Number(b) - Number(a));
    const orderedSubjects = [...subjects].sort((a, b) => {
        const statusScore = { risk: 0, watch: 1, safe: 2 };
        const left = statusScore[a.status] ?? 3;
        const right = statusScore[b.status] ?? 3;
        if (left !== right) return left - right;
        return (a.live_attendance || a.attendance || 100) - (b.live_attendance || b.attendance || 100);
    });
    const orderedAssignments = [...assignments].sort((a, b) => {
        const statusScore = { not_submitted: 0, late: 1, submitted: 2 };
        const left = statusScore[a.submission_status] ?? 3;
        const right = statusScore[b.submission_status] ?? 3;
        if (left !== right) return left - right;
        return new Date(a.due_date || '2999-12-31') - new Date(b.due_date || '2999-12-31');
    });
    const attendanceWatchlist = [...subjects].sort(
        (a, b) => (a.live_attendance || a.attendance || 100) - (b.live_attendance || b.attendance || 100)
    );
    const actionHub = (() => {
        // Fallback or loading state
        if (!aiBrief || !aiBrief.primaryAction) {
             const topRisk = orderedSubjects[0];
             return {
                 primaryAction: topRisk ? {
                     eyebrow: topRisk.status === 'risk' ? 'Priority recovery' : 'Best next move',
                     title: `Stabilize ${topRisk.name} this ${getHour()}`,
                     text: `${topRisk.name} is your highest-leverage subject right now. Give it your first focused block today before lower-risk work.`,
                     chips: [topRisk.code, `Bloom L${topRisk.bloomLevel || 1}`],
                     ctas: [
                         { label: `Tutor ${topRisk.code}`, to: '/tutor', state: { autoSubjectCode: topRisk.code, autoTopic: topRisk.name } },
                         { label: 'Ask mentor for a rescue plan', to: '/chat', state: { initialMessage: `Build me a recovery plan for ${topRisk.name}.` } },
                     ],
                 } : {
                     eyebrow: 'Momentum mode',
                     title: 'You are clear to compound strengths',
                     text: 'No subject is in immediate danger. Use today to lock in consistency, finish pending work early.',
                     chips: ['All core subjects stable'],
                     ctas: [{ label: 'Plan today', to: '/schedule' }, { label: 'Ask mentor what to focus on', to: '/chat' }],
                 },
                 secondary: [],
                 wins: []
             };
        }

        // Map from backend response
        const mappedPrimary = {
             eyebrow: aiBrief.primaryAction.type === 'critical' || aiBrief.primaryAction.type === 'warning' ? 'Priority Action' : 'Mission Control',
             title: aiBrief.primaryAction.title.split('—')[0] || aiBrief.primaryAction.title,
             text: aiBrief.primaryAction.title,
             chips: [aiBrief.primaryAction.context].filter(Boolean),
             ctas: [
                 { label: aiBrief.primaryAction.actionText, to: aiBrief.primaryAction.link, state: { initialMessage: `Help me with: ${aiBrief.primaryAction.title}` } }
             ]
        };
        
        const mappedSecondary = (aiBrief.secondaryActions || []).map(action => {
            let IconComponent;
            switch(action.icon) {
                 case '🚨': IconComponent = <AlertTriangle size={15} />; break;
                 case '⚠️': IconComponent = <AlertTriangle size={15} />; break;
                 case '📝': IconComponent = <ClipboardList size={15} />; break;
                 case '🚀': IconComponent = <Briefcase size={15} />; break;
                 case '📚': IconComponent = <BookOpen size={15} />; break;
                 default: IconComponent = <MessageSquare size={15}/>; break;
            }
            return {
                icon: IconComponent,
                label: action.context || action.type,
                title: action.title.split(':')[0] || 'Alert',
                text: action.title,
                cta: action.link ? { label: action.actionText, to: action.link } : null
            };
        });

        return {
             primaryAction: mappedPrimary,
             secondary: mappedSecondary,
             wins: aiBrief.momentumWins || []
        };
    })();

    // CGPA chart
    const chartData = {
        labels: cgpaHistory.map((_, i) => `S${i + 1}`),
        datasets: [{
            data: cgpaHistory,
            borderColor: '#FF7A00', borderWidth: 2.5,
            pointBackgroundColor: '#FF7A00', pointRadius: 4, pointHoverRadius: 6,
            tension: 0.35, fill: true,
            backgroundColor: ctx => {
                const g = ctx.chart.ctx.createLinearGradient(0, 0, 0, 160);
                g.addColorStop(0, 'rgba(255,122,0,.13)');
                g.addColorStop(1, 'rgba(255,122,0,.00)');
                return g;
            }
        }]
    };
    const chartOpts = {
        responsive: true, maintainAspectRatio: false,
        plugins: {
            legend: { display: false }, tooltip: {
                backgroundColor: '#fff', titleColor: '#1A1A1A', bodyColor: '#6B6B6B',
                borderColor: '#E8E4DE', borderWidth: 1,
                callbacks: { label: ctx => `CGPA: ${ctx.raw}` }
            }
        },
        scales: {
            x: { grid: { display: false }, ticks: { color: '#9A9A9A', font: { size: 10 } }, border: { display: false } },
            y: { grid: { color: '#F0ECE6' }, ticks: { color: '#9A9A9A', font: { size: 10 } }, border: { display: false }, min: 5, max: 10 }
        }
    };

    const briefingStyle = { risk: '#EF4444', warning: '#F59E0B', deadline: '#8B5CF6', opportunity: '#10B981', info: '#3B82F6' };
    const briefingIcon = { risk: '🚨', warning: '⚠️', deadline: '⏰', opportunity: '🚀', info: '📚' };

    return (
        <div className={styles.page}>

            {/* ① Header ──────────────────────────────────────────── */}
            <div className={styles.header}>
                <div className={styles.headerLeft}>
                    <div className={styles.headerAvatar}>{s.name?.[0] || '?'}</div>
                    <div>
                        <h1 className={styles.greeting}>Good {getHour()}, {s.name?.split(' ')[0]} 👋</h1>
                        <p className={styles.greetingSub}>
                            {s.id} · {s.college} · {s.department} · Y{s.year} Sem {s.semester}
                        </p>
                        {learningBadge && (
                            <p style={{ fontSize: '0.75rem', color: 'var(--text-3)', marginTop: 2 }}>
                                Learns best with <strong>{learningBadge}</strong> explanations.
                            </p>
                        )}
                    </div>
                </div>
                <div className={styles.headerBadges}>
                    {s.isPlaced && <span className={styles.badge} style={{ background: '#10B98118', color: '#10B981' }}><CheckCircle size={12} />Placed @ {s.placedAt}</span>}
                    {activeArrears.length > 0 && <span className={styles.badge} style={{ background: '#EF444418', color: '#EF4444' }}><XCircle size={12} />{activeArrears.length} Active Arrear{activeArrears.length > 1 ? 's' : ''}</span>}
                    {s.feeDue > 0 && <span className={styles.badge} style={{ background: '#F59E0B18', color: '#F59E0B' }}><IndianRupee size={12} />₹{s.feeDue.toLocaleString('en-IN')} Due</span>}
                    <span className={styles.badge} style={{ background: 'var(--surface-2)', color: 'var(--text-2)' }}>
                        {s.total_credits_earned}/{s.total_credits_required} credits
                    </span>
                </div>
            </div>

            {/* ② Metric Strip ─────────────────────────────────────── */}
            <div className={styles.actionGrid}>
                <div className={styles.primaryActionCard}>
                    <span className={styles.actionEyebrow}>{actionHub.primaryAction.eyebrow}</span>
                    <h2 className={styles.actionTitle}>{actionHub.primaryAction.title}</h2>
                    <p className={styles.actionText}>{actionHub.primaryAction.text}</p>
                    <div className={styles.actionChips}>
                        {actionHub.primaryAction.chips.map((chip, index) => (
                            <span key={index} className={styles.actionChip}>{chip}</span>
                        ))}
                    </div>
                    <div className={styles.actionButtons}>
                        {actionHub.primaryAction.ctas.map((cta, index) => (
                            <button
                                key={index}
                                type="button"
                                className={index === 0 ? styles.primaryCta : styles.secondaryCta}
                                onClick={() => navigate(cta.to, cta.state ? { state: cta.state } : undefined)}
                            >
                                {cta.label}
                            </button>
                        ))}
                    </div>
                </div>

                <div className={styles.secondaryActionRail}>
                    {actionHub.secondary.map((item, index) => (
                        <div key={index} className={styles.secondaryActionCard}>
                            <div className={styles.secondaryActionHead}>
                                <span className={styles.secondaryActionIcon}>{item.icon}</span>
                                <span className={styles.secondaryActionLabel}>{item.label}</span>
                            </div>
                            <div className={styles.secondaryActionTitle}>{item.title}</div>
                            <p className={styles.secondaryActionText}>{item.text}</p>
                            {item.cta && (
                                <button
                                    type="button"
                                    className={styles.secondaryActionButton}
                                    onClick={() => navigate(item.cta.to, item.cta.state ? { state: item.cta.state } : undefined)}
                                >
                                    {item.cta.label}
                                    <ArrowRight size={12} />
                                </button>
                            )}
                        </div>
                    ))}
                </div>

                <div className={styles.momentumCard}>
                    <SectionHeader title="Momentum" icon={<TrendingUp size={15} />} badge="Keep this going" />
                    <div className={styles.momentumList}>
                        {actionHub.wins.length === 0 && <p className={styles.empty}>No major momentum signals yet</p>}
                        {actionHub.wins.map((win, index) => (
                            <div key={index} className={styles.momentumItem}>
                                <CheckCircle size={14} color="#10B981" />
                                <span>{win}</span>
                            </div>
                        ))}
                    </div>
                    <button
                        type="button"
                        className={styles.momentumAsk}
                        onClick={() => navigate('/chat', {
                            state: {
                                initialMessage: 'Given my dashboard, what should I protect and what should I improve next?',
                            },
                        })}
                    >
                        Ask for next best move
                        <ArrowRight size={12} />
                    </button>
                </div>
            </div>

            <div className={styles.metricStrip}>
                {[
                    { label: 'CGPA', value: Number(s.currentCGPA).toFixed(2), sub: `→ ${Number(s.predictedCGPA).toFixed(2)} predicted`, accent: '#FF7A00', icon: <GraduationCap size={15} /> },
                    { label: 'Attendance', value: `${s.attendanceOverall}%`, sub: `${riskSubs.filter(x => (x.live_attendance || 0) < 75).length} subjects low`, accent: s.attendanceOverall < 75 ? '#EF4444' : '#10B981', icon: <Activity size={15} /> },
                    { label: 'At Risk', value: riskSubs.length, sub: `of ${subjects.length} subjects`, accent: riskSubs.length > 0 ? '#EF4444' : '#10B981', icon: <AlertTriangle size={15} /> },
                    { label: 'Assignments', value: `${assignHealth.submission_rate}%`, sub: `${assignHealth.not_submitted} pending`, accent: '#3B82F6', icon: <ClipboardList size={15} /> },
                    { label: 'Activities', value: activities.length, sub: `${s.certCount || 0} certified`, accent: '#8B5CF6', icon: <Award size={15} /> },
                ].map((m, i) => (
                    <div key={i} className={styles.metricCard}>
                        <div className={styles.metricTop}>
                            <span className={styles.metricLabel}>{m.label}</span>
                            <span className={styles.metricIcon} style={{ color: m.accent, background: m.accent + '15' }}>{m.icon}</span>
                        </div>
                        <div className={styles.metricValue} style={{ color: m.accent }}>{m.value}</div>
                        <div className={styles.metricSub}>{m.sub}</div>
                    </div>
                ))}
            </div>

            {/* ②b Where you stand (peer benchmarking) ───────────────────────────────── */}
            {benchmark && benchmark.peer_count > 0 && (
                <div className={`card ${styles.benchmarkCard}`} style={{
                    padding: '12px 16px',
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 16,
                    alignItems: 'center',
                    background: 'linear-gradient(135deg, #FF7A0008 0%, #FF7A0002 100%)',
                    border: '1px solid #FF7A0020',
                }}>
                    <div className={styles.benchmarkHeader}>
                        <Users size={15} style={{ color: '#FF7A00' }} />
                        <h2>Where you stand</h2>
                        <span className={styles.secBadge}>{benchmark.peer_count} peers</span>
                    </div>
                    <div className={styles.benchmarkStats}>
                        <div className={styles.benchmarkStat}>
                            <span className={styles.benchmarkLabel}>CGPA</span>
                            <span className={styles.benchmarkValue} style={{ color: '#FF7A00' }}>{benchmark.cgpa}</span>
                            <span className={styles.benchmarkText}>
                                Top {Math.round(100 - benchmark.cgpa_percentile)}% · Dept avg {benchmark.dept_avg_cgpa}
                                {benchmark.cgpa_vs_avg > 0 && <span style={{ color: '#10B981' }}> (+{benchmark.cgpa_vs_avg})</span>}
                                {benchmark.cgpa_vs_avg < 0 && <span style={{ color: '#EF4444' }}> ({benchmark.cgpa_vs_avg})</span>}
                            </span>
                        </div>
                        <div className={styles.benchmarkStat}>
                            <span className={styles.benchmarkLabel}>Attendance</span>
                            <span className={styles.benchmarkValue} style={{ color: benchmark.attendance >= 75 ? '#10B981' : '#F59E0B' }}>{benchmark.attendance}%</span>
                            <span className={styles.benchmarkText}>
                                Top {Math.round(100 - benchmark.attendance_percentile)}% · Dept avg {benchmark.dept_avg_attendance}%
                                {benchmark.attendance_vs_avg > 0 && <span style={{ color: '#10B981' }}> (+{benchmark.attendance_vs_avg})</span>}
                                {benchmark.attendance_vs_avg < 0 && <span style={{ color: '#EF4444' }}> ({benchmark.attendance_vs_avg})</span>}
                            </span>
                        </div>
                    </div>
                </div>
            )}

            {/* ③ CGPA Chart + AI Briefing ─────────────────────────── */}
            <div className={styles.row2}>
                <div className={`card ${styles.chartCard}`}>
                    <SectionHeader
                        title="Academic Trajectory"
                        icon={<TrendingUp size={15} />}
                        badge={`${cgpaHistory.length} sems`}
                        extra={
                            <div className={styles.cgpaChips}>
                                <span>Now <strong>{Number(s.currentCGPA).toFixed(2)}</strong></span>
                                <ArrowRight size={12} style={{ color: 'var(--text-3)' }} />
                                <span style={{ color: '#FF7A00' }}>Pred <strong>{Number(s.predictedCGPA).toFixed(2)}</strong></span>
                            </div>
                        }
                    />
                    {cgpaHistory.length > 0
                        ? <div className={styles.chartWrap}><Line data={chartData} options={chartOpts} /></div>
                        : <p className={styles.empty}>No CGPA history yet</p>
                    }
                </div>

                <div className={`card ${styles.briefingCard}`}>
                    <SectionHeader title="Mission Control" icon={<Zap size={15} />} badge="AI" />

                    {/* AI-Generated Morning Brief */}
                    <div style={{
                        background: 'linear-gradient(135deg, #FF7A0012 0%, #FF7A0006 100%)',
                        border: '1px solid #FF7A0025',
                        borderRadius: 10,
                        padding: '12px 14px',
                        marginBottom: 10,
                        minHeight: 56,
                    }}>
                        {briefLoading ? (
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <div style={{ width: 16, height: 16, borderRadius: '50%', border: '2px solid #FF7A00', borderTopColor: 'transparent', animation: 'spin 0.8s linear infinite' }} />
                                <span style={{ fontSize: '0.8rem', color: 'var(--text-3)' }}>AI is reading your data…</span>
                            </div>
                        ) : aiBrief?.ai_brief ? (
                            <p style={{ fontSize: '0.875rem', lineHeight: 1.5, color: 'var(--text-1)', margin: 0, fontStyle: 'normal' }}>
                                🤖 <strong style={{ color: '#FF7A00' }}>AI Mentor:</strong>{' '}{aiBrief.ai_brief}
                            </p>
                        ) : (
                            <p style={{ fontSize: '0.8rem', color: 'var(--text-3)', margin: 0 }}>
                                🎉 All clear — no critical alerts today!
                            </p>
                        )}
                    </div>

                    {/* Quick action: jump to chat with today's mission */}
                    <div className={styles.aiBriefActionRow}>
                        <button
                            type="button"
                            onClick={() => navigate('/chat', {
                                state: {
                                    initialMessage: "Given my current profile, alerts, and upcoming exams, what should I focus on today?"
                                }
                            })}
                            className={styles.aiBriefAction}
                        >
                            <Send size={12} />
                            Ask “What should I do today?”
                        </button>
                    </div>

                    {/* Data-driven alert items */}
                    <div className={styles.briefingList}>
                        {briefing.length === 0 && !briefLoading && <p className={styles.empty}>All metrics look healthy 👍</p>}
                        {briefing.map((b, i) => (
                            <div key={i} className={styles.briefingItem} style={{ borderLeftColor: briefingStyle[b.type] }}>
                                <span>{briefingIcon[b.type]}</span>
                                <p>{b.text}</p>
                            </div>
                        ))}
                    </div>
                </div>

            </div>

            {/* ④ Subject Intelligence Grid ────────────────────────── */}
            <div className="card" style={{ padding: 'var(--sp-4)' }}>
                <SectionHeader
                    title={`Current Semester (Sem ${s.semester}) — ${orderedSubjects.length} Subjects`}
                    icon={<BookOpen size={15} />}
                    badge={riskSubs.length > 0 ? `${riskSubs.length} at risk` : '✓ All safe'}
                    extra={
                        <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                            <button 
                                className={styles.secondaryActionButton} 
                                style={{ padding: '4px 10px', fontSize: '0.75rem', marginTop: 0 }}
                                onClick={() => navigate('/chat', { state: { initialMessage: "How should I structure my study plan for this semester's subjects?" } })}
                            >
                                Study Plan <ArrowRight size={12} />
                            </button>
                            <Link to="/prediction" className={styles.viewAll}>Predict <ArrowRight size={12} /></Link>
                        </div>
                    }
                />
                {orderedSubjects.length === 0
                    ? <p className={styles.empty}>No subjects this semester</p>
                    : (
                        <div className={styles.subjectGrid}>
                            {orderedSubjects.map((sub, i) => <SubjectCard key={i} sub={sub} />)}
                        </div>
                    )
                }
            </div>

            {/* ⑤ Assignment Board + Attendance per Subject ──────────── */}
            <div className={styles.row2}>
                {/* Assignments */}
                <div className={`card ${styles.assignCard}`}>
                    <SectionHeader
                        title="Assignments"
                        icon={<ClipboardList size={15} />}
                        badge={`Sem ${s.semester}`}
                        extra={
                           <button 
                                className={styles.secondaryActionButton} 
                                style={{ padding: '4px 10px', fontSize: '0.75rem', marginTop: 0 }}
                                onClick={() => navigate('/schedule')}
                            >
                                Submit & Plan <ArrowRight size={12} />
                            </button>
                        }
                    />
                    <div className={styles.assignTabs}>
                        {['submitted', 'late', 'not_submitted'].map(tab => {
                            const count = assignments.filter(a => a.submission_status === tab).length;
                            const col = { submitted: '#10B981', late: '#F59E0B', not_submitted: '#EF4444' }[tab];
                            return count > 0 && (
                                <span key={tab} style={{ fontSize: '0.7rem', fontWeight: 700, color: col, background: col + '18', padding: '2px 8px', borderRadius: 999 }}>
                                    {count} {tab.replace('_', ' ')}
                                </span>
                            );
                        })}
                    </div>
                    <div className={styles.assignList}>
                        {orderedAssignments.length === 0
                            ? <p className={styles.empty}>No assignments this semester</p>
                            : orderedAssignments.map((a, i) => <AssignRow key={i} a={a} />)
                        }
                    </div>
                    <div className={styles.progressBarWrap}>
                        <div style={{ width: `${assignHealth.submission_rate}%` }} className={styles.progressBarFill} />
                    </div>
                    <p className={styles.progressLabel}>{assignHealth.submission_rate}% submission rate</p>
                </div>

                {/* Attendance per subject */}
                <div className={`card ${styles.attCard}`}>
                    <SectionHeader 
                        title="Attendance per Subject" 
                        icon={<Users size={15} />} 
                        badge="75% threshold" 
                        extra={
                            <button 
                                className={styles.secondaryActionButton} 
                                style={{ padding: '4px 10px', fontSize: '0.75rem', marginTop: 0 }}
                                onClick={() => navigate('/chat', { state: { initialMessage: "How can I improve my low attendance subjects before exams?" } })}
                            >
                                Get Recovery Plan <ArrowRight size={12} />
                            </button>
                        }
                    />
                    <div className={styles.attList}>
                        {attendanceWatchlist.map((sub, i) => {
                            const att = Number(sub.live_attendance || sub.attendance || 0);
                            const color = att < 75 ? '#EF4444' : att < 85 ? '#F59E0B' : '#10B981';
                            return (
                                <div key={i} className={styles.attRow}>
                                    <span className={styles.attSubName} title={sub.name}>{sub.name}</span>
                                    <div className={styles.attTrack}>
                                        <div className={styles.attThreshold} />
                                        <div className={styles.attFill} style={{ width: `${Math.min(att, 100)}%`, background: color }} />
                                    </div>
                                    <AttPill pct={att} />
                                </div>
                            );
                        })}
                        {attendanceWatchlist.length === 0 && <p className={styles.empty}>No subjects</p>}
                    </div>
                </div>
            </div>

            {/* ⑥ Historical Semester Records ─────────────────────────── */}
            {histSemKeys.length > 0 && (
                <div className="card" style={{ padding: 'var(--sp-4)' }}>
                    <SectionHeader 
                        title="Previous Semester Records" 
                        icon={<Eye size={15} />} 
                        badge={`${histSemKeys.length} sems`} 
                        extra={
                            <button 
                                className={styles.secondaryActionButton} 
                                style={{ padding: '4px 10px', fontSize: '0.75rem', marginTop: 0 }}
                                onClick={() => navigate('/chat', { state: { initialMessage: "Can you analyze my performance trends and marks across my previous semesters?" } })}
                            >
                                Analyze Trends <ArrowRight size={12} />
                            </button>
                        }
                    />
                    <div className={styles.histList}>
                        {histSemKeys.map(sem => (
                            <HistoricalSem
                                key={sem}
                                semKey={sem}
                                subjects={historicalSemesters[sem]}
                            />
                        ))}
                    </div>
                </div>
            )}

            {/* ⑦ Next Semester Preview ───────────────────────────────── */}
            {nextSemSubjects.length > 0 && (
                <div className="card" style={{ padding: 'var(--sp-4)' }}>
                    <SectionHeader
                        title={`Next Semester Preview (Sem ${(s.semester || 0) + 1})`}
                        icon={<ChevronRight size={15} />}
                        badge={`${nextSemSubjects.length} subjects`}
                        extra={
                            <button 
                                className={styles.secondaryActionButton} 
                                style={{ padding: '4px 10px', fontSize: '0.75rem', marginTop: 0 }}
                                onClick={() => navigate('/chat', { state: { initialMessage: "What should I know to prepare for next semester's subjects?" } })}
                            >
                                Prep Advice <ArrowRight size={12} />
                            </button>
                        }
                    />
                    <div className={styles.nextSemGrid}>
                        {nextSemSubjects.map((sub, i) => {
                            const typeColor = SUBJECT_TYPE_COLOR[sub.type] || '#9CA3AF';
                            return (
                                <div key={i} className={styles.nextSemCard}>
                                    <div className={styles.nextSemCode}>{sub.code}</div>
                                    <div className={styles.nextSemName}>{sub.name}</div>
                                    <div className={styles.nextSemMeta}>
                                        <span style={{ color: typeColor, background: typeColor + '18', padding: '1px 6px', borderRadius: 999, fontSize: '0.65rem', fontWeight: 700 }}>
                                            {sub.type}
                                        </span>
                                        <span style={{ fontSize: '0.7rem', color: '#9CA3AF' }}>{sub.credits}cr</span>
                                        {sub.elective_vertical && (
                                            <span style={{ fontSize: '0.65rem', color: '#8B5CF6' }}>{sub.elective_vertical}</span>
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* ⑧ Activities | Arrears | Library + Mentoring ─────────── */}
            <div className={styles.row3}>
                {/* Activities */}
                <div className={`card ${styles.actCard}`}>
                    <SectionHeader 
                        title="Activities" 
                        icon={<Award size={15} />} 
                        badge={`${s.certCount || 0} certified`} 
                        extra={
                            <button 
                                className={styles.secondaryActionButton} 
                                style={{ padding: '4px 10px', fontSize: '0.75rem', marginTop: 0 }}
                                onClick={() => navigate('/chat', { state: { initialMessage: "I want to log a new extracurricular activity or certification." } })}
                            >
                                Log Activity <ArrowRight size={12} />
                            </button>
                        }
                    />
                    <div className={styles.actList}>
                        {activities.length === 0 && <p className={styles.empty}>No activities recorded</p>}
                        {activities.map((a, i) => (
                            <div key={i} className={styles.actRow}>
                                <span className={styles.actIcon} style={{ color: a.verified ? '#10B981' : '#9CA3AF' }}>
                                    {ACTIVITY_ICON[a.activity_type] || <Star size={14} />}
                                </span>
                                <div className={styles.actInfo}>
                                    <span className={styles.actTitle}>{a.title}</span>
                                    <span className={styles.actMeta}>
                                        {a.activity_type} · {a.level} · {a.grade_or_score}
                                        {a.verified && <span style={{ color: '#10B981', marginLeft: 4 }}>✓</span>}
                                    </span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Arrears */}
                <div className={`card ${styles.arrearCard}`}>
                    <SectionHeader
                        title="Arrear History"
                        icon={<XCircle size={15} />}
                        badge={activeArrears.length > 0 ? `${activeArrears.length} Active` : '✓ Clear'}
                        extra={
                            activeArrears.length > 0 && (
                                <button 
                                    className={styles.secondaryActionButton} 
                                    style={{ padding: '4px 10px', fontSize: '0.75rem', marginTop: 0 }}
                                    onClick={() => navigate('/chat', { state: { initialMessage: "Help me create a study plan to clear my active arrears." } })}
                                >
                                    Clear Arrears <ArrowRight size={12} />
                                </button>
                            )
                        }
                    />
                    {arrears.length === 0
                        ? <p className={styles.empty}>No arrears — clean record! 🎉</p>
                        : arrears.map((a, i) => (
                            <div key={i} className={styles.arrearRow}>
                                <div className={styles.arrearInfo}>
                                    <span className={styles.arrearName}>{a.subject_name || a.subject_code}</span>
                                    <span className={styles.arrearMeta}>Sem {a.semester_failed} · Attempt {a.attempt_number || 1}</span>
                                </div>
                                <span style={{
                                    fontSize: '0.7rem', fontWeight: 700, padding: '2px 8px', borderRadius: 999,
                                    background: a.cleared ? '#10B98118' : '#EF444418',
                                    color: a.cleared ? '#10B981' : '#EF4444',
                                }}>
                                    {a.cleared ? `Cleared (${a.cleared_grade ?? '—'})` : 'Active'}
                                </span>
                            </div>
                        ))
                    }
                </div>

                {/* Library + Mentoring */}
                <div className={styles.stackCol}>
                    <div className={`card ${styles.libraryCard}`}>
                        <SectionHeader 
                            title="Library" 
                            icon={<BookMarked size={15} />} 
                            extra={
                                <button 
                                    className={styles.secondaryActionButton} 
                                    style={{ padding: '4px 10px', fontSize: '0.75rem', marginTop: 0 }}
                                    onClick={() => navigate('/chat', { state: { initialMessage: "I need to renew my library books or find new ones related to my courses." } })}
                                >
                                    Manage <ArrowRight size={12} />
                                </button>
                            }
                        />
                        {library.length === 0
                            ? <p className={styles.empty}>No books issued</p>
                            : library.map((b, i) => {
                                const overdue = b.due_date && new Date(b.due_date) < new Date();
                                return (
                                    <div key={i} className={styles.libRow}>
                                        <BookOpen size={12} color={overdue ? '#EF4444' : '#9CA3AF'} />
                                        <div className={styles.libInfo}>
                                            <span className={styles.libTitle}>{b.book_title}</span>
                                            {b.due_date && (
                                                <span style={{ fontSize: '0.65rem', color: overdue ? '#EF4444' : '#9CA3AF' }}>
                                                    Due: {new Date(b.due_date).toLocaleDateString('en-IN')}
                                                    {overdue ? ' — OVERDUE' : ''}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                );
                            })
                        }
                    </div>

                    {mentoring.length > 0 && (
                        <div className={`card ${styles.mentorCard}`}>
                            <SectionHeader 
                                title="Mentoring" 
                                icon={<MessageSquare size={15} />} 
                                badge={mentoring.length} 
                                extra={
                                    <button 
                                        className={styles.secondaryActionButton} 
                                        style={{ padding: '4px 10px', fontSize: '0.75rem', marginTop: 0 }}
                                        onClick={() => navigate('/chat', { state: { initialMessage: "I'd like to schedule a meeting with my mentor to discuss my academic progress." } })}
                                    >
                                        Schedule <ArrowRight size={12} />
                                    </button>
                                }
                            />
                            {mentoring.slice(0, 2).map((m, i) => (
                                <div key={i} className={styles.mentorRow}>
                                    <span className={styles.mentorDate}>
                                        {new Date(m.date).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                                    </span>
                                    <div className={styles.mentorInfo}>
                                        <span className={styles.mentorTitle}>{m.agenda}</span>
                                        <span className={styles.mentorSub}>with {m.mentor}{m.parent_present ? ' · Parent present' : ''}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* ⑨ Fee Timeline ─────────────────────────────────────────── */}
            {feeRecords.length > 0 && (
                <div className="card" style={{ padding: 'var(--sp-4)' }}>
                    <SectionHeader
                        title="Fee Status"
                        icon={<IndianRupee size={15} />}
                        badge={s.feeDue > 0 ? `₹${s.feeDue.toLocaleString('en-IN')} due` : '✓ Paid up'}
                        extra={
                            s.feeDue > 0 && (
                                <button 
                                    className={styles.secondaryActionButton} 
                                    style={{ padding: '4px 10px', fontSize: '0.75rem', marginTop: 0 }}
                                    onClick={() => navigate('/chat', { state: { initialMessage: "I need to view details about my pending fees and payment options." } })}
                                >
                                    Pay Now <ArrowRight size={12} />
                                </button>
                            )
                        }
                    />
                    <div className={styles.feeGrid}>
                        {feeRecords.map((f, i) => {
                            const col = f.status === 'paid' ? '#10B981' : f.status === 'overdue' ? '#EF4444' : '#F59E0B';
                            const pct = f.amount_due > 0 ? Math.round((f.amount_paid / f.amount_due) * 100) : 100;
                            return (
                                <div key={i} className={styles.feeCard}>
                                    <div className={styles.feeTop}>
                                        <span className={styles.feeSem}>Sem {f.semester}</span>
                                        <span style={{ fontSize: '0.65rem', fontWeight: 700, color: col, background: col + '18', padding: '2px 7px', borderRadius: 999 }}>
                                            {f.status}
                                        </span>
                                    </div>
                                    <div className={styles.feeType}>{f.fee_type?.replace(/_/g, ' ')}</div>
                                    <div className={styles.feePct}>
                                        <div style={{ width: `${pct}%`, height: '100%', background: col, borderRadius: 999 }} />
                                    </div>
                                    <div className={styles.feeNums}>
                                        <span>₹{Number(f.amount_paid || 0).toLocaleString('en-IN')}</span>
                                        <span style={{ color: '#9CA3AF' }}>/ ₹{Number(f.amount_due || 0).toLocaleString('en-IN')}</span>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* ⑩ Placement Zone (Y3/Y4 only) ──────────────────────────── */}
            {(s.year >= 3 || placement.length > 0) && (
                <div className="card" style={{ padding: 'var(--sp-4)' }}>
                    <SectionHeader
                        title="Placement Status"
                        icon={<Briefcase size={15} />}
                        extra={
                            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                                <button 
                                    className={styles.secondaryActionButton} 
                                    style={{ padding: '4px 10px', fontSize: '0.75rem', marginTop: 0 }}
                                    onClick={() => navigate('/chat', { state: { initialMessage: "How should I prepare for my upcoming placement drives?" } })}
                                >
                                    Prep Strategies <ArrowRight size={12} />
                                </button>
                                <Link to="/career" className={styles.viewAll}>Career <ArrowRight size={12} /></Link>
                            </div>
                        }
                    />
                    <div className={styles.placementRow_}>
                        {/* Eligibility checklist */}
                        {placementElig && (
                            <div className={styles.eligBox}>
                                <p className={styles.eligTitle}>Eligibility</p>
                                {[
                                    { key: 'cgpa_eligible', label: `CGPA ≥ ${placementElig.cgpa_threshold}` },
                                    { key: 'arrear_free', label: 'No Active Arrears' },
                                    { key: 'attendance_ok', label: 'Attendance ≥ 75%' },
                                ].map(({ key, label }) => (
                                    <div key={key} className={styles.eligRow}>
                                        {placementElig[key]
                                            ? <CheckCircle size={14} color="#10B981" />
                                            : <XCircle size={14} color="#EF4444" />
                                        }
                                        <span style={{ fontSize: '0.8125rem', color: placementElig[key] ? '#1A1A1A' : '#EF4444' }}>
                                            {label}
                                        </span>
                                    </div>
                                ))}
                                <div style={{ marginTop: 8, fontSize: '0.75rem', fontWeight: 700, color: placementElig.is_eligible ? '#10B981' : '#EF4444' }}>
                                    {placementElig.is_eligible ? '✓ Eligible for campus placements' : '✗ Not yet eligible'}
                                </div>
                            </div>
                        )}

                        {/* Drives table */}
                        {placement.length > 0 && (
                            <div className={styles.drivesTable}>
                                {placement.map((p, i) => {
                                    const col = { offered: '#10B981', shortlisted: '#3B82F6', rejected: '#EF4444', appeared: '#9CA3AF' }[p.status] || '#9CA3AF';
                                    return (
                                        <div key={i} className={styles.driveRow}>
                                            <div className={styles.driveCompany}>{p.company_name}</div>
                                            <div className={styles.driveRole}>{p.role}</div>
                                            <div style={{ fontWeight: 700, color: '#FF7A00', fontSize: '0.875rem' }}>{p.package_lpa} LPA</div>
                                            <span style={{ fontSize: '0.7rem', fontWeight: 700, padding: '2px 8px', borderRadius: 999, background: col + '18', color: col }}>
                                                {p.status}
                                            </span>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                        {placement.length === 0 && !placementElig &&
                            <p className={styles.empty}>No placement drives recorded yet</p>
                        }
                    </div>
                </div>
            )}

            {/* ⑪ Chat entry ───────────────────────────────────────────── */}
            <div className={`card ${styles.chatCard}`}>
                <div className={styles.chatCardHeader}>
                    <span className="section-label">✦ Ask your AI Mentor</span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-3)' }}>8 specialist agents active</span>
                </div>
                <div className={styles.chatInputRow}>
                    <input
                        id="dashboard-chat-input"
                        className={`input ${styles.chatInput}`}
                        value={chatInput}
                        onChange={e => setChatInput(e.target.value)}
                        placeholder={riskSubs.length > 0
                            ? `Ask about your ${riskSubs[0]?.name} risk or study plan…`
                            : `Ask about ${subjects[0]?.name || 'your subjects'}, predictions, career…`
                        }
                        onKeyDown={e => e.key === 'Enter' && navigate('/chat', { state: { initialMessage: chatInput } })}
                    />
                    <button
                        className={`btn btn-primary ${styles.chatSend}`}
                        onClick={() => navigate('/chat', { state: { initialMessage: chatInput } })}
                    >
                        <Send size={16} />
                    </button>
                </div>
            </div>

            {/* Quick Actions */}
            <div className={styles.quickActions}>
                {[
                    { icon: <TrendingUp size={17} />, label: 'Predict', to: '/prediction', color: '#FF7A00' },
                    { icon: <BookOpen size={17} />, label: 'Learn', to: '/learning', color: '#10B981' },
                    { icon: <Calendar size={17} />, label: 'Schedule', to: '/schedule', color: '#3B82F6' },
                    { icon: <Briefcase size={17} />, label: 'Career', to: '/career', color: '#8B5CF6' },
                ].map((a, i) => (
                    <Link key={i} to={a.to} className={`card card--interactive ${styles.quickAction}`}>
                        <div style={{ width: 34, height: 34, borderRadius: 8, background: a.color + '18', color: a.color, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            {a.icon}
                        </div>
                        <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>{a.label}</span>
                        <ArrowRight size={13} style={{ color: 'var(--text-3)', marginLeft: 'auto' }} />
                    </Link>
                ))}
            </div>

        </div>
    );
}
