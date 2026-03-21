import { useState, useEffect, useCallback, useRef } from 'react';
import { getMySchedule } from '../../services/api';
import { AlertTriangle, RefreshCw, Brain, Clock, BookOpen, BarChart2, Calendar, Target, ChevronRight, X, Play, Pause, RotateCcw } from 'lucide-react';
import styles from './Schedule.module.css';

/* ── Color maps ───────────────────────────────────────────────────────── */
const TYPE_COLORS = {
    risk: { bg: 'rgba(239,68,68,0.12)', border: 'var(--risk)', text: '#B91C1C', label: 'At-Risk' },
    watch: { bg: 'rgba(245,158,11,0.12)', border: 'var(--watch)', text: '#92400E', label: 'Watch' },
    safe: { bg: 'rgba(34,197,94,0.12)', border: 'var(--safe)', text: '#15803D', label: 'Safe' },
};
const BLOOM_LABELS = ['', 'Remember', 'Understand', 'Apply', 'Analyze', 'Evaluate', 'Create'];
const BLOOM_COLOR = ['', '#6B7280', '#3B82F6', '#F59E0B', '#8B5CF6', '#EF4444', '#10B981'];
const DAYS_ORDER = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

/* ── Helpers ──────────────────────────────────────────────────────────── */
const todayName = () => ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][new Date().getDay()];

function fmt(min) {
    const h = Math.floor(min / 60), m = min % 60;
    return h ? (m ? `${h}h ${m}m` : `${h}h`) : `${m}m`;
}

/* ── Week skeleton ────────────────────────────────────────────────────── */
function WeekSkeleton() {
    return (
        <div className={styles.calendar}>
            {DAYS_ORDER.map(d => (
                <div key={d} className={styles.dayColumn}>
                    <div className={`${styles.dayHeader} ${styles.skeletonBar}`} style={{ width: '60%', height: 14, margin: '0 auto 8px' }} />
                    {[90, 60, 45].map((h, i) => (
                        <div key={i} className={styles.skeletonSlot} style={{ minHeight: Math.round(h * 0.55) }} />
                    ))}
                </div>
            ))}
        </div>
    );
}

/* ── Pomodoro Timer ───────────────────────────────────────────────────── */
function PomodoroTimer({ pomodoro_count = 2, subject }) {
    const WORK = 25 * 60, BREAK = 5 * 60;
    const [secs, setSecs] = useState(WORK);
    const [running, setRunning] = useState(false);
    const [phase, setPhase] = useState('work'); // 'work' | 'break'
    const [done, setDone] = useState(0);
    const ref = useRef(null);

    useEffect(() => {
        if (running) {
            ref.current = setInterval(() => {
                setSecs(s => {
                    if (s <= 1) {
                        if (phase === 'work') { setPhase('break'); setSecs(BREAK); setDone(d => d + 1); }
                        else { setPhase('work'); setSecs(WORK); }
                        return phase === 'work' ? BREAK : WORK;
                    }
                    return s - 1;
                });
            }, 1000);
        }
        return () => clearInterval(ref.current);
    }, [running, phase]);

    const mm = String(Math.floor(secs / 60)).padStart(2, '0');
    const ss = String(secs % 60).padStart(2, '0');
    const pct = phase === 'work' ? ((WORK - secs) / WORK) * 100 : ((BREAK - secs) / BREAK) * 100;

    return (
        <div className={styles.pomodoroBox}>
            <div className={styles.pomodoroLabel}>{phase === 'work' ? '🍅 Focus' : '☕ Break'}</div>
            <div className={styles.pomodoroRing}>
                <svg viewBox="0 0 64 64" className={styles.pomodoroSvg}>
                    <circle cx="32" cy="32" r="28" fill="none" stroke="var(--border-light)" strokeWidth="4" />
                    <circle cx="32" cy="32" r="28" fill="none"
                        stroke={phase === 'work' ? '#EF4444' : '#10B981'} strokeWidth="4"
                        strokeDasharray={`${2 * Math.PI * 28}`}
                        strokeDashoffset={`${2 * Math.PI * 28 * (1 - pct / 100)}`}
                        strokeLinecap="round"
                        style={{ transition: 'stroke-dashoffset 1s linear', transform: 'rotate(-90deg)', transformOrigin: '50% 50%' }}
                    />
                </svg>
                <div className={styles.pomodoroTime}>{mm}:{ss}</div>
            </div>
            <div className={styles.pomodoroControls}>
                <button onClick={() => setRunning(r => !r)} className={styles.pomodoroBtn}>
                    {running ? <Pause size={14} /> : <Play size={14} />}
                    {running ? 'Pause' : 'Start'}
                </button>
                <button onClick={() => { setRunning(false); setSecs(WORK); setPhase('work'); }} className={`${styles.pomodoroBtn} ${styles.pomodoroBtnGhost}`}>
                    <RotateCcw size={13} />
                </button>
            </div>
            <div className={styles.pomodoroPills}>
                {Array.from({ length: pomodoro_count }).map((_, i) => (
                    <div key={i} className={`${styles.pomodoroPill} ${i < done ? styles.pomodoroDone : ''}`} />
                ))}
            </div>
            <div className={styles.pomodoroSub}>studying {subject}</div>
        </div>
    );
}

/* ── Slot Detail Panel ────────────────────────────────────────────────── */
function SlotPanel({ slot, tips, onClose }) {
    if (!slot) return null;
    const c = TYPE_COLORS[slot.type] || TYPE_COLORS.safe;
    const tip = tips?.[slot.subject_code];
    return (
        <div className={styles.panelOverlay} onClick={onClose}>
            <div className={styles.panel} onClick={e => e.stopPropagation()}>
                <button className={styles.panelClose} onClick={onClose}><X size={16} /></button>
                <div className={styles.panelHeader} style={{ borderLeft: `4px solid ${c.border}` }}>
                    <div className={styles.panelSubject} style={{ color: c.text }}>{slot.subject}</div>
                    <div className={styles.panelCode}>{slot.subject_code}</div>
                </div>
                <div className={styles.panelTopic}>{slot.topic}</div>
                <div className={styles.panelMeta}>
                    <span className={styles.panelBadge} style={{ background: c.bg, color: c.text }}>{c.label}</span>
                    <span className={styles.panelBadge} style={{ background: `${BLOOM_COLOR[slot.bloom_level]}22`, color: BLOOM_COLOR[slot.bloom_level] }}>
                        L{slot.bloom_level} {BLOOM_LABELS[slot.bloom_level]}
                    </span>
                    <span className={styles.panelBadge}>{fmt(slot.duration_min)}</span>
                    <span className={styles.panelBadge}>🍅 ×{slot.pomodoro_count}</span>
                </div>
                {tip && <div className={styles.panelTip}>💡 {tip}</div>}
                {slot.study_tip && <div className={styles.panelStudyTip}>📌 {slot.study_tip}</div>}
                <PomodoroTimer pomodoro_count={slot.pomodoro_count} subject={slot.subject} />
            </div>
        </div>
    );
}

/* ── TAB: Week View ───────────────────────────────────────────────────── */
function WeekTab({ week, tips, today }) {
    const [active, setActive] = useState(null);
    return (
        <>
            <div className={styles.calendar}>
                {DAYS_ORDER.map(dayName => {
                    const day = week.find(d => d.day === dayName);
                    const isToday = dayName === today;
                    return (
                        <div key={dayName} className={`${styles.dayColumn} ${isToday ? styles.todayCol : ''}`}>
                            <div className={styles.dayHeader}>
                                <span className={styles.dayName}>{dayName}</span>
                                {day?.date && <span className={styles.dayDate}>{day.date}</span>}
                                {isToday && <span className={styles.todayBadge}>Today</span>}
                            </div>
                            <div className={styles.daySlots}>
                                {(day?.slots || []).length === 0
                                    ? <div className={styles.restSlot}>🛌 Rest</div>
                                    : (day?.slots || []).map((slot, si) => {
                                        const c = TYPE_COLORS[slot.type] || TYPE_COLORS.safe;
                                        return (
                                            <div key={si} className={styles.slot}
                                                style={{ background: c.bg, borderLeft: `3px solid ${c.border}`, minHeight: Math.round((slot.duration_min ?? 60) * 0.55) }}
                                                onClick={() => setActive(slot)}
                                            >
                                                <div className={styles.slotTime}>{slot.time}</div>
                                                <div className={styles.slotSubject} style={{ color: c.text }}>{slot.subject}</div>
                                                <div className={styles.slotTopic}>{slot.topic}</div>
                                                <div className={styles.slotFooter}>
                                                    <span className={styles.slotDuration}>{fmt(slot.duration_min ?? 60)}</span>
                                                    <span className={styles.bloomDot} style={{ background: BLOOM_COLOR[slot.bloom_level] || '#6B7280' }} title={BLOOM_LABELS[slot.bloom_level]} />
                                                    <ChevronRight size={10} className={styles.slotArrow} />
                                                </div>
                                            </div>
                                        );
                                    })
                                }
                            </div>
                        </div>
                    );
                })}
            </div>
            <SlotPanel slot={active} tips={tips} onClose={() => setActive(null)} />
        </>
    );
}

/* ── TAB: Today Focus ─────────────────────────────────────────────────── */
function TodayTab({ week, tips, today }) {
    const [active, setActive] = useState(null);
    const dayPlan = week.find(d => d.day === today);
    const slots = dayPlan?.slots || [];

    if (!slots.length) return <p className={styles.emptyNote}>No sessions scheduled for today — enjoy a rest day! 🎉</p>;

    const totalMins = slots.reduce((s, sl) => s + (sl.duration_min ?? 60), 0);
    const riskSlots = slots.filter(s => s.type === 'risk').length;

    return (
        <div className={styles.todayWrap}>
            <div className={styles.todaySummary}>
                <div className={styles.todayStat}><span className={styles.todayStatVal}>{fmt(totalMins)}</span><span className={styles.todayStatLbl}>today</span></div>
                <div className={styles.todayStat}><span className={styles.todayStatVal}>{slots.length}</span><span className={styles.todayStatLbl}>sessions</span></div>
                <div className={styles.todayStat}><span className={styles.todayStatVal} style={{ color: 'var(--risk)' }}>{riskSlots}</span><span className={styles.todayStatLbl}>high-priority</span></div>
            </div>

            <div className={styles.todaySlots}>
                {slots.map((slot, i) => {
                    const c = TYPE_COLORS[slot.type] || TYPE_COLORS.safe;
                    const tip = tips?.[slot.subject_code];
                    return (
                        <div key={i} className={styles.todaySlot} style={{ borderLeft: `4px solid ${c.border}` }}>
                            <div className={styles.todaySlotHeader}>
                                <div>
                                    <div className={styles.todaySlotTime}>{slot.time}</div>
                                    <div className={styles.todaySlotSubject} style={{ color: c.text }}>{slot.subject}</div>
                                    <div className={styles.todaySlotTopic}>{slot.topic}</div>
                                </div>
                                <div className={styles.todaySlotRight}>
                                    <span className={styles.panelBadge} style={{ background: c.bg, color: c.text }}>{fmt(slot.duration_min ?? 60)}</span>
                                    <span className={styles.panelBadge} style={{ background: `${BLOOM_COLOR[slot.bloom_level]}22`, color: BLOOM_COLOR[slot.bloom_level] }}>
                                        {BLOOM_LABELS[slot.bloom_level]}
                                    </span>
                                </div>
                            </div>
                            {slot.study_tip && <div className={styles.todayTip}>📌 {slot.study_tip}</div>}
                            {tip && <div className={styles.todayAITip}>💡 <strong>AI Tip:</strong> {tip}</div>}
                            <PomodoroTimer pomodoro_count={slot.pomodoro_count} subject={slot.subject} />
                        </div>
                    );
                })}
            </div>
            <SlotPanel slot={active} tips={tips} onClose={() => setActive(null)} />
        </div>
    );
}

/* ── TAB: Subjects ────────────────────────────────────────────────────── */
function SubjectsTab({ subjectBreakdown, tips, coverageGaps, overdueAssignments }) {
    if (!subjectBreakdown?.length) return <p className={styles.emptyNote}>No subject data available.</p>;

    const byCode = Object.fromEntries((coverageGaps || []).map(g => [g.subject_code, g]));

    return (
        <div className={styles.subjectsGrid}>
            {subjectBreakdown.map((sub, i) => {
                const c = TYPE_COLORS[sub.type] || TYPE_COLORS.safe;
                const tip = tips?.[sub.subject_code];
                const gap = byCode[sub.subject_code];
                const overdue = (overdueAssignments || []).filter(a => a.subject_code === sub.subject_code);
                return (
                    <div key={i} className={styles.subjectCard} style={{ borderTop: `3px solid ${c.border}` }}>
                        <div className={styles.subjectCardHeader}>
                            <div>
                                <div className={styles.subjectCardName}>{sub.subject}</div>
                                <div className={styles.subjectCardCode}>{sub.subject_code}</div>
                            </div>
                            <span className={styles.subjectTypeBadge} style={{ background: c.bg, color: c.text }}>{c.label}</span>
                        </div>
                        <div className={styles.subjectStats}>
                            <div className={styles.subjectStat}>
                                <span className={styles.subjectStatVal}>{sub.total_hours}h</span>
                                <span className={styles.subjectStatLbl}>this week</span>
                            </div>
                            <div className={styles.subjectStat}>
                                <span className={styles.subjectStatVal}>{sub.sessions}</span>
                                <span className={styles.subjectStatLbl}>sessions</span>
                            </div>
                            {gap && (
                                <div className={styles.subjectStat}>
                                    <span className={styles.subjectStatVal} style={{ color: gap.coverage_pct < 40 ? 'var(--risk)' : 'var(--watch)' }}>
                                        {gap.coverage_pct}%
                                    </span>
                                    <span className={styles.subjectStatLbl}>covered</span>
                                </div>
                            )}
                        </div>
                        {gap && (
                            <div className={styles.coverageBar}>
                                <div className={styles.coverageFill} style={{ width: `${gap.coverage_pct}%`, background: gap.coverage_pct < 40 ? 'var(--risk)' : gap.coverage_pct < 70 ? 'var(--watch)' : 'var(--safe)' }} />
                            </div>
                        )}
                        {overdue.length > 0 && (
                            <div className={styles.overdueChip}>⚠️ {overdue.length} overdue assignment{overdue.length > 1 ? 's' : ''}</div>
                        )}
                        {tip && <div className={styles.subjectTipBox}>💡 {tip}</div>}
                    </div>
                );
            })}
        </div>
    );
}

/* ── TAB: Stats ───────────────────────────────────────────────────────── */
function StatsTab({ week, totalHours, riskHours, examDays, riskCount, watchCount }) {
    const byType = { risk: 0, watch: 0, safe: 0 };
    const byDay = {};
    for (const day of week) {
        let dayMin = 0;
        for (const sl of (day.slots || [])) {
            const m = sl.duration_min ?? 60;
            byType[sl.type] = (byType[sl.type] || 0) + m;
            dayMin += m;
        }
        byDay[day.day] = dayMin;
    }
    const maxDay = Math.max(...Object.values(byDay), 1);

    const ring = (val, max, color, label, sub) => {
        const pct = Math.min(100, (val / max) * 100);
        const r = 28;
        const circ = 2 * Math.PI * r;
        return (
            <div className={styles.ringWrap}>
                <svg viewBox="0 0 64 64" className={styles.ringSvg}>
                    <circle cx="32" cy="32" r={r} fill="none" stroke="var(--border-light)" strokeWidth="5" />
                    <circle cx="32" cy="32" r={r} fill="none" stroke={color} strokeWidth="5"
                        strokeDasharray={circ} strokeDashoffset={circ * (1 - pct / 100)}
                        strokeLinecap="round"
                        style={{ transform: 'rotate(-90deg)', transformOrigin: '50% 50%', transition: 'stroke-dashoffset 0.8s ease' }} />
                    <text x="32" y="36" textAnchor="middle" fontSize="11" fontWeight="700" fill="var(--text-1)">{label}</text>
                </svg>
                <div className={styles.ringLabel}>{sub}</div>
            </div>
        );
    };

    return (
        <div className={styles.statsWrap}>
            {/* Ring charts */}
            <div className={`card ${styles.statsRings}`}>
                <div className={styles.cardTitle}>Weekly Breakdown</div>
                <div className={styles.ringsRow}>
                    {ring(byType.risk / 60, totalHours || 1, '#EF4444', `${(byType.risk / 60).toFixed(1)}h`, 'At-Risk')}
                    {ring(byType.watch / 60, totalHours || 1, '#F59E0B', `${(byType.watch / 60).toFixed(1)}h`, 'Watch')}
                    {ring(byType.safe / 60, totalHours || 1, '#10B981', `${(byType.safe / 60).toFixed(1)}h`, 'Safe')}
                    {ring(totalHours, 35, '#6366F1', `${totalHours}h`, 'Total')}
                </div>
            </div>

            {/* Daily load bars */}
            <div className={`card ${styles.statsBars}`}>
                <div className={styles.cardTitle}>Daily Study Load</div>
                <div className={styles.barsWrap}>
                    {DAYS_ORDER.map(d => (
                        <div key={d} className={styles.barCol}>
                            <div className={styles.barOuter}>
                                <div className={styles.barFill} style={{ height: `${((byDay[d] || 0) / maxDay) * 100}%`, background: d === todayName() ? 'var(--accent)' : 'var(--safe)' }} />
                            </div>
                            <div className={styles.barHrs}>{byDay[d] ? fmt(byDay[d]) : '—'}</div>
                            <div className={styles.barDay}>{d}</div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Key metrics */}
            <div className={styles.statsMetrics}>
                {[
                    { label: 'Total hrs', val: `${totalHours}h`, color: '#6366F1' },
                    { label: 'At-risk hrs', val: `${riskHours}h`, color: '#EF4444' },
                    { label: 'Risk subjs', val: riskCount, color: '#F59E0B' },
                    { label: 'Watch subjs', val: watchCount, color: '#3B82F6' },
                    { label: 'Exam in', val: examDays ? `${examDays}d` : '—', color: '#10B981' },
                ].map((m, i) => (
                    <div key={i} className={`card ${styles.metricCard}`}>
                        <div className={styles.metricVal} style={{ color: m.color }}>{m.val}</div>
                        <div className={styles.metricLbl}>{m.label}</div>
                    </div>
                ))}
            </div>
        </div>
    );
}

/* ── Main Component ───────────────────────────────────────────────────── */
export default function Schedule() {
    const [schedule, setSchedule] = useState(null);
    const [loading, setLoading] = useState(true);
    const [regenerating, setRegenerating] = useState(false);
    const [error, setError] = useState(null);
    const [tab, setTab] = useState('week');
    const today = todayName();

    const fetchSchedule = useCallback(async (isRegen = false) => {
        if (isRegen) setRegenerating(true);
        else { setLoading(true); setSchedule(null); }
        setError(null);
        try {
            const data = await getMySchedule({ forceRefresh: isRegen === true });
            setSchedule(data);
        } catch {
            setError('Could not load your schedule. Please try again.');
        } finally {
            setLoading(false);
            setRegenerating(false);
        }
    }, []);

    useEffect(() => { fetchSchedule(); }, [fetchSchedule]);

    const week = schedule?.week || [];
    const tips = schedule?.tips || {};
    const subBrk = schedule?.subject_breakdown || [];
    const gaps = schedule?.coverage_gaps || [];
    const overdue = schedule?.overdue_assignments || [];
    const examDays = schedule?.exam_days;
    const totalHrs = schedule?.total_study_hours ?? 0;
    const riskHrs = schedule?.risk_subject_hours ?? 0;
    const riskCnt = schedule?.risk_subject_count ?? 0;
    const watchCnt = schedule?.watch_subject_count ?? 0;
    const peakHour = schedule?.peak_hour;
    const rationale = schedule?.ai_rationale;
    const style = schedule?.preferred_style;

    const todayPlan = week.find(d => d.day === today);
    const firstRiskToday = todayPlan?.slots?.find(s => s.type === 'risk');

    const TABS = [
        { id: 'week', icon: <Calendar size={15} />, label: 'Week View' },
        { id: 'today', icon: <Target size={15} />, label: 'Today' },
        { id: 'subjects', icon: <BookOpen size={15} />, label: 'Subjects' },
        { id: 'stats', icon: <BarChart2 size={15} />, label: 'Stats' },
    ];

    return (
        <div className={styles.page}>
            {/* ── Header ──────────────────────────────────────────────── */}
            <div className={styles.header}>
                <div>
                    <span className="section-label">📅 Study Schedule</span>
                    <h1 className={styles.title}>AI-Generated Study Plan</h1>
                    <p className={styles.sub}>
                        {loading ? 'AI is generating your personalized plan…' : 'Built by Groq AI using your real ERP data, bloom levels, and study DNA.'}
                    </p>
                </div>

                <div className={styles.headerRight}>
                    {/* Stat pills */}
                    {!loading && schedule && (
                        <div className={styles.stats}>
                            {[
                                { label: 'Study hrs/week', val: `${totalHrs}h` },
                                { label: 'At-risk', val: riskCnt },
                                { label: 'Exam in', val: examDays != null ? `${examDays}d` : '—' },
                                ...(peakHour != null ? [{ label: 'Peak', val: `${peakHour}:00` }] : []),
                            ].map((s, i) => (
                                <div key={i} className={styles.statPill}>
                                    <span className={styles.statVal}>{s.val}</span>
                                    <span className={styles.statLabel}>{s.label}</span>
                                </div>
                            ))}
                        </div>
                    )}
                    <button className={styles.regenBtn} onClick={() => fetchSchedule(true)} disabled={loading || regenerating} title="Regenerate with fresh AI">
                        <RefreshCw size={14} className={regenerating ? styles.spinning : ''} />
                        {regenerating ? 'Generating…' : 'Regenerate'}
                    </button>
                </div>
            </div>

            {/* ── AI Rationale ─────────────────────────────────────────── */}
            {rationale && !loading && (
                <div className={styles.rationaleStrip}>
                    <Brain size={14} className={styles.rationaleIcon} />
                    <span dangerouslySetInnerHTML={{ __html: rationale.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') }} />
                    {style && <span className={styles.stylePill}><Clock size={10} /> {style}</span>}
                </div>
            )}

            {/* ── Overdue nudge ────────────────────────────────────────── */}
            {!loading && overdue.length > 0 && (
                <div className={styles.nudge}>
                    <AlertTriangle size={14} />
                    <strong>{overdue.length} overdue assignment{overdue.length > 1 ? 's' : ''}:</strong>
                    {overdue.slice(0, 3).map((a, i) => <span key={i} className={styles.overdueTag}>{a.subject_code}: {a.title}</span>)}
                </div>
            )}

            {/* ── Today nudge (if no overdue) ──────────────────────────── */}
            {!loading && !overdue.length && firstRiskToday && (
                <div className={styles.nudge} style={{ borderColor: 'var(--risk)', background: 'rgba(239,68,68,0.06)' }}>
                    <AlertTriangle size={14} />
                    Start today with <strong>{firstRiskToday.subject}</strong> at {firstRiskToday.time} — {firstRiskToday.topic}
                </div>
            )}

            {/* ── Legend ──────────────────────────────────────────────── */}
            {!loading && !error && (
                <div className={styles.legend}>
                    {Object.entries(TYPE_COLORS).map(([k, c]) => (
                        <div key={k} className={styles.legendItem}>
                            <div className={styles.legendBlock} style={{ background: c.bg, borderLeft: `3px solid ${c.border}` }} />
                            <span>{c.label}</span>
                        </div>
                    ))}
                    <div className={styles.legendBloomRow}>
                        {[1, 2, 3, 4, 5, 6].map(l => (
                            <div key={l} className={styles.legendBloom} title={BLOOM_LABELS[l]}>
                                <div className={styles.bloomDot2} style={{ background: BLOOM_COLOR[l] }} />
                                <span>{BLOOM_LABELS[l]}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* ── Error ───────────────────────────────────────────────── */}
            {error && (
                <div className={styles.errorCard}>
                    ⚠️ {error}
                    <button className={styles.retryBtn} onClick={() => fetchSchedule()}>Retry</button>
                </div>
            )}

            {/* ── Tab nav ─────────────────────────────────────────────── */}
            {!error && (
                <div className={styles.tabNav}>
                    {TABS.map(t => (
                        <button key={t.id} className={`${styles.tabBtn} ${tab === t.id ? styles.tabActive : ''}`} onClick={() => setTab(t.id)}>
                            {t.icon}{t.label}
                        </button>
                    ))}
                </div>
            )}

            {/* ── Tab content ─────────────────────────────────────────── */}
            <div className={`card ${styles.calendarCard}`}>
                {loading ? <WeekSkeleton /> : error ? <p className={styles.emptyNote}>No schedule to display.</p> : (
                    <>
                        {tab === 'week' && <WeekTab week={week} tips={tips} today={today} />}
                        {tab === 'today' && <TodayTab week={week} tips={tips} today={today} />}
                        {tab === 'subjects' && <SubjectsTab subjectBreakdown={subBrk} tips={tips} coverageGaps={gaps} overdueAssignments={overdue} />}
                        {tab === 'stats' && <StatsTab week={week} totalHours={totalHrs} riskHours={riskHrs} examDays={examDays} riskCount={riskCnt} watchCount={watchCnt} />}
                    </>
                )}
            </div>

            {/* ── Pomodoro tip ─────────────────────────────────────────── */}
            {!loading && tab !== 'today' && (
                <div className={styles.tip}>
                    <span>💡</span>
                    <span>Use the <strong>Pomodoro technique</strong> — 25 min focused study, 5 min break. Each slot shows 🍅 count. Click any slot to open the built-in timer.</span>
                </div>
            )}
        </div>
    );
}
