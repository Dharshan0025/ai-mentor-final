import { useState, useEffect, useRef, useCallback } from 'react';
import { Line } from 'react-chartjs-2';
import {
    Chart as ChartJS, CategoryScale, LinearScale,
    PointElement, LineElement, Tooltip, Filler
} from 'chart.js';
import {
    TrendingUp, TrendingDown, Minus,
    Zap, Brain, AlertTriangle, ChevronRight,
    ChevronDown, Target, RefreshCw, CheckCircle2, Circle, Loader2
} from 'lucide-react';
import styles from './Prediction.module.css';
import { getMyProfile, simulateScenario, getMyPredictions } from '../../services/api';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Filler);

/* ── Helpers ──────────────────────────────────────────────────────────── */
const RISK_COLOR = { risk: '#EF4444', watch: '#F59E0B', safe: '#10B981', improving: '#10B981', declining: '#EF4444', stable: '#6B7280' };
const TRAJ_ICON = {
    improving: <TrendingUp size={14} />,
    declining: <TrendingDown size={14} />,
    stable: <Minus size={14} />,
};

function getRiskStyle(status) {
    if (status === 'safe' || status === 'improving') return { color: 'var(--safe)', pill: 'pill-safe', label: 'Safe' };
    if (status === 'watch' || status === 'stable') return { color: 'var(--watch)', pill: 'pill-watch', label: 'Watch' };
    return { color: 'var(--risk)', pill: 'pill-risk', label: 'At Risk' };
}

function RiskGauge({ score = 0 }) {
    const color = score >= 70 ? '#EF4444' : score >= 40 ? '#F59E0B' : '#10B981';
    const r = 26, circ = 2 * Math.PI * r;
    return (
        <div className={styles.gauge}>
            <svg width="68" height="68" viewBox="0 0 68 68">
                <circle cx="34" cy="34" r={r} fill="none" stroke="var(--border-light)" strokeWidth="6" />
                <circle cx="34" cy="34" r={r} fill="none" stroke={color} strokeWidth="6"
                    strokeDasharray={circ} strokeDashoffset={circ * (1 - score / 100)}
                    strokeLinecap="round"
                    style={{ transform: 'rotate(-90deg)', transformOrigin: '50% 50%', transition: 'stroke-dashoffset 1s ease' }}
                />
                <text x="34" y="39" textAnchor="middle" fontSize="13" fontWeight="800" fill={color}>{score}</text>
            </svg>
            <div className={styles.gaugeLabel} style={{ color }}>Risk</div>
        </div>
    );
}

/* ── Markdown renderer (lightweight) ─────────────────────────────────── */
function MarkdownProse({ text }) {
    if (!text) return null;
    const lines = text.split('\n');
    const elements = [];
    let listItems = [];
    let key = 0;

    const flushList = () => {
        if (listItems.length) {
            elements.push(<ul key={`ul-${key++}`} className={styles.proseList}>{listItems}</ul>);
            listItems = [];
        }
    };

    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) { flushList(); continue; }

        if (/^#{1,3}\s/.test(trimmed)) {
            flushList();
            const content = trimmed.replace(/^#{1,3}\s/, '');
            elements.push(<h3 key={key++} className={styles.proseH3} dangerouslySetInnerHTML={{ __html: renderInline(content) }} />);
        } else if (/^\*\*/.test(trimmed) && !trimmed.includes(' ')) {
            flushList();
            elements.push(<strong key={key++} className={styles.proseStrong} dangerouslySetInnerHTML={{ __html: renderInline(trimmed) }} />);
        } else if (/^[-*]\s/.test(trimmed) || /^\d+\.\s/.test(trimmed)) {
            listItems.push(<li key={key++} dangerouslySetInnerHTML={{ __html: renderInline(trimmed.replace(/^[-*\d.]\s*/, '')) }} />);
        } else {
            flushList();
            elements.push(<p key={key++} className={styles.prosePara} dangerouslySetInnerHTML={{ __html: renderInline(trimmed) }} />);
        }
    }
    flushList();
    return <div className={styles.prose}>{elements}</div>;
}

function renderInline(text) {
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code>$1</code>');
}

/* ── Agentic Processing Engine Spinner ───────────────────────────────── */
const PROCESSING_STEPS = [
    { id: 'fetch', label: 'Fetching ERP data', detail: 'Grades · attendance · bloom levels · syllabus coverage' },
    { id: 'phase1', label: 'Phase 1 — Structured analysis', detail: 'AI Mentor computing risk scores, arrear probability' },
    { id: 'deep', label: 'Diagnosing each subject', detail: 'Root causes · immediate actions · prognosis per subject' },
    { id: 'dna', label: 'Reading Learning DNA', detail: 'Peak hours · weak topics · preferred study style' },
    { id: 'phase2', label: 'Phase 2 — Narrative generation', detail: 'AI Mentor writing personalised tutor analysis' },
    { id: 'moves', label: 'Computing critical moves', detail: 'Top 3 high-impact interventions with timeline & CGPA impact' },
];

function ProcessingEngine() {
    const [step, setStep] = useState(0);

    useEffect(() => {
        if (step >= PROCESSING_STEPS.length - 1) return;
        const delay = step === 1 || step === 4 ? 4500 : 1800; // phase1/2 take longer
        const t = setTimeout(() => setStep(s => s + 1), delay);
        return () => clearTimeout(t);
    }, [step]);

    return (
        <div className={styles.processingEngine}>
            <div className={styles.processingHeader}>
                <Brain size={20} className={styles.processingBrainIcon} />
                <span>Prediction Analysis Engine</span>
                <span className={styles.processingBadge}>Running…</span>
            </div>
            <div className={styles.processingSteps}>
                {PROCESSING_STEPS.map((s, i) => {
                    const done = i < step;
                    const current = i === step;
                    return (
                        <div key={s.id} className={`${styles.processingStep} ${done ? styles.stepDone : current ? styles.stepActive : styles.stepPending}`}>
                            <div className={styles.stepIcon}>
                                {done
                                    ? <CheckCircle2 size={16} />
                                    : current
                                        ? <div className={styles.stepSpinner} />
                                        : <Circle size={16} />}
                            </div>
                            <div className={styles.stepBody}>
                                <div className={styles.stepLabel}>{s.label}</div>
                                {current && <div className={styles.stepDetail}>{s.detail}</div>}
                            </div>
                        </div>
                    );
                })}
            </div>
            <div className={styles.processingFooter}>
                This analysis typically takes 15–30 seconds
            </div>
        </div>
    );
}

/* ── Narrative reveal (word-chunk approach — no race condition) ────────── */
function TypingNarrative({ text, isLoading }) {
    // Reveal text word-by-word using stable setTimeout chain (not setInterval)
    // This avoids the React concurrent mode race condition with rapid setState calls.
    const [wordCount, setWordCount] = useState(0);
    const wordsRef = useRef([]);
    const timerRef = useRef(null);

    useEffect(() => {
        if (!text) { setWordCount(0); return; }
        wordsRef.current = text.split(' ');
        setWordCount(0);

        let w = 0;
        const reveal = () => {
            w++;
            setWordCount(w);
            if (w < wordsRef.current.length) {
                timerRef.current = setTimeout(reveal, 30); // 30ms per word — smooth, no flicker
            }
        };
        timerRef.current = setTimeout(reveal, 30);
        return () => clearTimeout(timerRef.current);
    }, [text]);

    if (isLoading) return <ProcessingEngine />;

    const words = wordsRef.current;
    const shown = words.slice(0, wordCount).join(' ');
    const done = wordCount >= words.length;

    return (
        <div className={styles.narrativeBody}>
            <MarkdownProse text={shown} />
            {!done && <span className={styles.cursor} />}
        </div>
    );
}

/* ── Subject Deep Dive Tab ────────────────────────────────────────────── */
function SubjectDeepDive({ subjects = [] }) {
    const [active, setActive] = useState(0);
    if (!subjects.length) return null;
    const s = subjects[active];
    const st = getRiskStyle(s.status);

    return (
        <div className={styles.deepDive}>
            {/* Tab strip */}
            <div className={styles.deepTabStrip}>
                {subjects.map((sub, i) => (
                    <button key={i} className={`${styles.deepTab} ${active === i ? styles.deepTabActive : ''}`}
                        onClick={() => setActive(i)}>
                        <div className={styles.deepTabDot} style={{ background: RISK_COLOR[sub.status] || '#6B7280' }} />
                        <span>{sub.name?.split(' ').slice(0, 2).join(' ')}</span>
                    </button>
                ))}
            </div>

            {/* Content */}
            <div className={styles.deepContent}>
                <div className={styles.deepHeader}>
                    <div>
                        <div className={styles.deepSubjectName}>{s.name}</div>
                        <div className={styles.deepSubjectCode}>{s.code}</div>
                    </div>
                    <div className={styles.deepHeaderRight}>
                        <RiskGauge score={s.risk_score ?? 0} />
                        <div>
                            <div className={styles.deepGradeLabel}>Current</div>
                            <div className={styles.deepGrade}>{s.current_grade ?? s.grade ?? '—'}<span>/10</span></div>
                        </div>
                        <div>
                            <div className={styles.deepGradeLabel}>Predicted</div>
                            <div className={styles.deepGrade} style={{ color: RISK_COLOR[s.status] }}>{s.predicted_grade ?? '—'}<span>/10</span></div>
                        </div>
                    </div>
                </div>

                <div className={styles.deepMeta}>
                    <span className={`pill ${st.pill}`}>{st.label}</span>
                    <span className={styles.deepBadge}>🎓 Bloom L{s.bloom_level ?? s.bloomLevel}</span>
                    <span className={styles.deepBadge}>📅 Att {s.attendance}%</span>
                    <span className={styles.deepBadge} style={{ color: s.arrear_probability > 0.5 ? 'var(--risk)' : 'inherit' }}>
                        ⚠ Arrear {Math.round((s.arrear_probability ?? 0) * 100)}%
                    </span>
                    <span className={styles.deepBadge}>📈 {s.prognosis}</span>
                </div>

                <div className={styles.deepGrid}>
                    {s.root_causes?.length > 0 && (
                        <div className={styles.deepSection}>
                            <div className={styles.deepSectionLabel}>🔍 Root Causes</div>
                            <ul className={styles.deepList}>
                                {s.root_causes.map((c, i) => <li key={i}>{c}</li>)}
                            </ul>
                        </div>
                    )}
                    {s.immediate_actions?.length > 0 && (
                        <div className={styles.deepSection}>
                            <div className={styles.deepSectionLabel}>⚡ Immediate Actions</div>
                            <ul className={styles.deepList}>
                                {s.immediate_actions.map((c, i) => <li key={i}>{c}</li>)}
                            </ul>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

/* ── Main Component ───────────────────────────────────────────────────── */
export default function Prediction() {
    const [pred, setPred] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [sliders, setSliders] = useState({ attendance: 0, assignments: 0, studyHours: 0 });
    const [targetCgpa, setTargetCgpa] = useState(8.5); // Macro Slider state
    const [simResult, setSimResult] = useState(null);
    const [simLoading, setSimLoading] = useState(false);
    const [simError, setSimError] = useState(null);
    const [selectedSubject, setSelectedSubject] = useState(null);
    const debounceRef = useRef(null);

    const fetchPrediction = useCallback(async (isRefresh = false) => {
        setLoading(true); setError(null);
        try {
            const data = await getMyPredictions({ forceRefresh: isRefresh === true });
            setPred(data);
        } catch (e) {
            setError('Could not load prediction data. Please try again.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { fetchPrediction(); }, [fetchPrediction]);

    // Debounced simulator — 600ms after sliders stop, fetch explanation when sliders are non-zero
    useEffect(() => {
        if (!pred) return;
        clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(async () => {
            setSimLoading(true); setSimError(null);
            try {
                const hasChanges = sliders.attendance > 0 || sliders.assignments > 0 || sliders.studyHours > 0;
                const res = await simulateScenario({
                    attendance_delta: sliders.attendance,
                    assignment_delta: sliders.assignments,
                    study_hours_delta: sliders.studyHours,
                    explain: hasChanges, // request AI Mentor explanation only when sliders are non-zero
                });
                setSimResult(res);
            } catch {
                setSimError('Simulation unavailable — check agent service');
            } finally {
                setSimLoading(false);
            }
        }, 600);
        return () => clearTimeout(debounceRef.current);
    }, [sliders, pred]);

    if (loading) return (
        <div className={styles.page}>
            <div className={styles.header}>
                <div>
                    <span className="section-label">🔮 AI Predictions</span>
                    <h1 className={styles.title}>How you'll perform <span className="text-accent">next semester</span></h1>
                    <p className={styles.sub}>2-phase AI Mentor analysis — real ERP data · bloom levels · learning DNA</p>
                </div>
            </div>
            <ProcessingEngine />
        </div>
    );

    if (error) return (
        <div className={styles.page}>
            <div className={styles.errorCard}>{error} <button className={styles.retryBtn} onClick={() => fetchPrediction(true)}>Retry</button></div>
        </div>
    );

    const subjects = pred?.subjects || [];
    const cgpaHist = pred?.cgpa_history || pred?.cgpaHistory || [];
    const trajectory = pred?.trajectory_signal || 'stable';
    const verdict = pred?.cgpa_verdict || {};
    const moves = pred?.critical_moves || [];
    const arrearRisk = pred?.arrear_risk || [];
    const narrative = pred?.analysis_narrative || '';
    const examDays = pred?.exam_days;

    // Chart data
    const historyData = cgpaHist.length ? cgpaHist : [];
    const projectedLabels = historyData.map((_, i) => `Sem ${i + 1}`).concat(['Sem (proj)']);
    const chartData = {
        labels: projectedLabels,
        datasets: [
            { label: 'Actual', data: [...historyData, null], borderColor: 'var(--text-1)', borderWidth: 2.5, pointBackgroundColor: 'var(--text-1)', pointRadius: 4, tension: 0.3, fill: false },
            { label: 'Projected', data: [...historyData.map((_, i, a) => i < a.length - 1 ? null : historyData[a.length - 1]), pred?.predicted_cgpa], borderColor: 'var(--accent)', borderWidth: 2.5, borderDash: [6, 3], pointBackgroundColor: 'var(--accent)', pointRadius: 5, tension: 0.3, fill: { target: 'origin', above: 'rgba(255,122,0,0.04)' } },
        ],
    };
    const chartOpts = {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { backgroundColor: 'var(--surface)', titleColor: 'var(--text-1)', bodyColor: 'var(--text-2)', borderColor: 'var(--border-light)', borderWidth: 1 } },
        scales: {
            x: { grid: { display: false }, ticks: { color: 'var(--text-3)', font: { size: 11 } }, border: { display: false } },
            y: { grid: { color: 'var(--border-light)' }, ticks: { color: 'var(--text-3)', font: { size: 11 } }, border: { display: false }, min: 6, max: 10 },
        },
    };

    return (
        <div className={styles.page}>
            {/* ── Header ────────────────────────────────────────────── */}
            <div className={styles.header}>
                <div>
                    <span className="section-label">🔮 AI Predictions</span>
                    <h1 className={styles.title}>How you'll perform <span className="text-accent">next semester</span></h1>
                    <p className={styles.sub}>2-phase AI Mentor analysis — real ERP data · bloom levels · learning DNA</p>
                </div>
                <button className={styles.regenBtn} onClick={() => fetchPrediction(true)} title="Refresh AI analysis">
                    <RefreshCw size={14} /> Refresh Analysis
                </button>
            </div>

            {/* ── Macro Slider: Target CGPA ─────────────────────────── */}
            <div className={styles.macroCard}>
                <div className={styles.macroHeader}>
                    <div className={styles.macroTitle}><Target size={18} /> Target CGPA</div>
                    <div className={styles.macroTarget}>{targetCgpa.toFixed(1)}</div>
                    {(() => {
                        const base = pred?.predicted_cgpa || (historyData.length ? historyData[historyData.length - 1] : 7.0);
                        const delta = targetCgpa - base;
                        let rLabel = 'On Track';
                        let rStyle = { borderColor: 'var(--safe)', color: 'var(--safe)', background: 'rgba(16,185,129,0.1)' };
                        
                        if (delta > 1.2) {
                            rLabel = 'Highly Unlikely';
                            rStyle = { borderColor: 'var(--risk)', color: 'var(--risk)', background: 'rgba(239,68,68,0.1)' };
                        } else if (delta > 0.6) {
                            rLabel = 'Stretch Goal';
                            rStyle = { borderColor: 'var(--watch)', color: 'var(--watch)', background: 'rgba(245,158,11,0.1)' };
                        } else if (delta > 0.2) {
                            rLabel = 'Challenging but Possible';
                            rStyle = { borderColor: 'var(--accent)', color: 'var(--accent)', background: 'rgba(204,255,0,0.1)' };
                        } else if (delta < -0.5) {
                            rLabel = 'Playing it Safe';
                            rStyle = { borderColor: 'var(--text-3)', color: 'var(--text-3)', background: 'var(--surface-2)' };
                        }

                        return (
                            <div className={styles.realityBadge} style={rStyle}>
                                {rLabel}
                            </div>
                        );
                    })()}
                </div>
                
                <div className={styles.macroSliderWrap}>
                    <input type="range" className={styles.macroSlider} min="5.0" max="10.0" step="0.1" 
                           value={targetCgpa} 
                           onChange={e => setTargetCgpa(parseFloat(e.target.value))} />
                    <div className={styles.macroSliderLabels}>
                        <span>5.0</span>
                        <span>10.0</span>
                    </div>
                </div>
            </div>

            {/* ── Stats bar ─────────────────────────────────────────── */}
            <div className={styles.statsBar}>
                {[
                    { label: 'Predicted CGPA', val: pred?.predicted_cgpa, color: 'var(--accent)', big: true },
                    { label: 'Confidence', val: `${Math.round((pred?.confidence ?? 0.7) * 100)}%` },
                    { label: 'At-Risk', val: pred?.risk_subject_count, color: 'var(--risk)' },
                    { label: 'Exam in', val: examDays ? `${examDays}d` : '—', color: '#6366F1' },
                    { label: 'Trajectory', val: <span className={styles.trajBadge} style={{ background: `${RISK_COLOR[trajectory]}20`, color: RISK_COLOR[trajectory] }}>{TRAJ_ICON[trajectory]}{trajectory}</span> },
                ].map((s, i) => (
                    <div key={i} className={`card ${styles.statCard}`}>
                        <div className={styles.statVal} style={{ color: s.color, fontSize: s.big ? '2.5rem' : '1.5rem' }}>{s.val ?? '—'}</div>
                        <div className={styles.statLbl}>{s.label}</div>
                    </div>
                ))}
            </div>

            {/* ── Trajectory reason ─────────────────────────────────── */}
            {pred?.trajectory_reason && (
                <div className={styles.trajectoryBanner} style={{ borderColor: `${RISK_COLOR[trajectory]}40`, background: `${RISK_COLOR[trajectory]}08` }}>
                    {TRAJ_ICON[trajectory]}
                    <span>{pred.trajectory_reason}</span>
                </div>
            )}

            {/* ── Arrear risk alert ─────────────────────────────────── */}
            {arrearRisk.length > 0 && (
                <div className={styles.arrearAlert}>
                    <AlertTriangle size={16} />
                    <strong>Arrear Risk Detected:</strong>
                    {arrearRisk.map((a, i) => (
                        <span key={i} className={styles.arrearTag}>{a.name} — {Math.round((a.probability) * 100)}% probability</span>
                    ))}
                </div>
            )}

            {/* ── Top row: Chart + Verdict ──────────────────────────── */}
            <div className={styles.topRow}>
                <div className={`card ${styles.chartCard}`}>
                    <div className={styles.cardHeader}>
                        <h2 className={styles.cardTitle}>CGPA Forecast</h2>
                        <div className={styles.legend}>
                            <span className={styles.legendItem}><span className={styles.legendLine} style={{ background: 'var(--text-1)' }} />Actual</span>
                            <span className={styles.legendItem}><span className={styles.legendLine} style={{ background: 'var(--accent)', opacity: 0.7 }} />Projected</span>
                        </div>
                    </div>
                    <div className={styles.chartWrap}><Line data={chartData} options={chartOpts} /></div>
                    {pred?.cgpa_range && (
                        <div className={styles.chartNote}>
                            Confidence interval: <strong>{pred.cgpa_range[0]} – {pred.cgpa_range[1]}</strong>
                        </div>
                    )}
                </div>

                <div className={`card ${styles.verdictCard}`}>
                    <h2 className={styles.cardTitle}>AI Diagnostic Verdict</h2>
                    <div className={styles.verdictRows}>
                        {[
                            { label: 'Pessimistic', val: verdict.pessimistic, color: 'var(--risk)' },
                            { label: 'Realistic', val: verdict.realistic, color: 'var(--accent)' },
                            { label: 'Optimistic', val: verdict.optimistic, color: 'var(--safe)' },
                        ].map((row, i) => (
                            <div key={i} className={styles.verdictRow}>
                                <span className={styles.verdictLabel}>{row.label}</span>
                                <div className={styles.verdictBar}>
                                    <div className={styles.verdictFill} style={{ width: `${((row.val ?? 7) - 6) / 4 * 100}%`, background: row.color }} />
                                </div>
                                <span className={styles.verdictNum} style={{ color: row.color }}>{row.val ?? '—'}</span>
                            </div>
                        ))}
                    </div>
                    {verdict.key_factor && <div className={styles.verdictFactor}>💡 {verdict.key_factor}</div>}
                    <hr className="divider" style={{ margin: '14px 0' }} />
                    <div className={styles.verdictInsights}>
                        <div className={styles.verdictInsight}><span>🔴 At-risk</span><strong>{pred?.risk_subject_count ?? '—'}</strong></div>
                        <div className={styles.verdictInsight}><span>🟡 Watch</span><strong>{pred?.watch_subject_count ?? '—'}</strong></div>
                    </div>
                </div>
            </div>

            {/* ── 🤖 Agent Analysis ─────────────────────────────────── */}
            <div className={`card ${styles.agentCard}`}>
                <div className={styles.agentHeader}>
                    <div className={styles.agentTitle}>
                        <Brain size={18} className={styles.agentIcon} />
                        <span>AI Mentor Analysis</span>
                        <span className={styles.agentProviderTag}>
                            {pred?.providers?.phase2 === 'fallback' ? '⚡ Basic Mode' : '🔶 Advanced AI'}
                        </span>
                    </div>
                    <div className={styles.agentMeta}>Updated just now · {subjects.length} subjects analyzed</div>
                </div>
                <TypingNarrative text={narrative} isLoading={!narrative} />
            </div>

            {/* ── Critical Moves ────────────────────────────────────── */}
            {moves.length > 0 && (
                <div className={`card ${styles.movesCard}`}>
                    <h2 className={styles.cardTitle}><Target size={16} style={{ color: 'var(--accent)' }} /> Your 3 Critical Moves</h2>
                    <div className={styles.moves}>
                        {moves.map((m, i) => (
                            <div key={i} className={styles.move}>
                                <div className={styles.movePriority}>{m.priority}</div>
                                <div className={styles.moveBody}>
                                    <div className={styles.moveAction}>{m.action}</div>
                                    <div className={styles.moveMeta}>
                                        <span className={styles.moveBadge} style={{ color: 'var(--safe)', background: 'rgba(16,185,129,0.1)' }}>📈 {m.impact}</span>
                                        <span className={styles.moveBadge}>⏱ {m.timeline}</span>
                                    </div>
                                </div>
                                <ChevronRight size={14} style={{ color: 'var(--text-3)' }} />
                            </div>
                        ))}
                    </div>
                    {pred?.study_dna_impact && (
                        <div className={styles.dnaTip}>
                            <Brain size={12} /> <em>{pred.study_dna_impact}</em>
                        </div>
                    )}
                </div>
            )}

            {/* ── Subject Risk Map ──────────────────────────────────── */}
            <div className={`card ${styles.riskMapCard}`}>
                <div className={styles.cardHeader}>
                    <h2 className={styles.cardTitle}>Subject Risk Assessment</h2>
                    <span className="pill pill-muted">Click to expand</span>
                </div>
                <div className={styles.riskMap}>
                    {subjects.map((s, i) => {
                        const pct = Math.round(((s.current_grade ?? s.grade ?? 5) / 10) * 100);
                        const st = getRiskStyle(s.status);
                        return (
                            <div key={i} className={`${styles.riskRow} ${selectedSubject === i ? styles.riskRowActive : ''}`}
                                onClick={() => setSelectedSubject(selectedSubject === i ? null : i)}>
                                <div className={styles.riskRowMain}>
                                    <span className={styles.riskSubjectName}>{s.name}</span>
                                    <div className={styles.riskBarWrap}>
                                        <div className={styles.riskBarTrack}>
                                            <div className={styles.riskBarFill} style={{ width: `${pct}%`, background: st.color }} />
                                        </div>
                                    </div>
                                    <span className={styles.riskScore} style={{ color: st.color }}>{s.current_grade ?? '—'}</span>
                                    <span className={`pill ${st.pill}`}>{st.label}</span>
                                    <div className={styles.riskScoreBar}>
                                        <div className={styles.riskScoreCircle} style={{ background: s.risk_score >= 70 ? 'var(--risk)' : s.risk_score >= 40 ? 'var(--watch)' : 'var(--safe)' }}>
                                            {s.risk_score ?? 0}
                                        </div>
                                    </div>
                                    <ChevronDown size={14} style={{ color: 'var(--text-3)', transform: selectedSubject === i ? 'rotate(180deg)' : '', transition: 'transform 200ms' }} />
                                </div>
                                {selectedSubject === i && (
                                    <div className={styles.riskDetail}>
                                        {s.root_causes?.map((c, j) => <div key={j} className={styles.riskDetailItem}>⚠ {c}</div>)}
                                        {s.immediate_actions?.map((a, j) => <div key={j} className={styles.riskDetailItem} style={{ color: 'var(--safe)' }}>✓ {a}</div>)}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>
            {/* ── Subject Deep Dive tabs ────────────────────────────── */}
            {subjects.length > 0 && (
                <div className={`card ${styles.deepDiveCard}`}>
                    <div className={styles.cardHeader}>
                        <h2 className={styles.cardTitle}>🎯 Subject Deep Dive</h2>
                        <span className="pill pill-accent">AI Diagnosis</span>
                    </div>
                    <SubjectDeepDive subjects={subjects} />
                </div>
            )}

            {/* ── Macro Target Setter ───────────────────────────────── */}
            <div className={`card ${styles.macroTargetCard}`}>
                <div className={styles.macroHeader}>
                    <h2 className={styles.cardTitle}>🎯 Set Your Target CGPA</h2>
                    <span className="pill pill-safe">Reality Check</span>
                </div>
                <div className={styles.macroBody}>
                    <p className={styles.simDesc}>Drag the slider to set your macro stretch goal. See your probability of hitting it based on current telemetry.</p>
                    <div className={styles.macroSliderArea}>
                        <div className={styles.macroSliderTrack}>
                            <div className={styles.macroSliderFill} style={{ width: `${((targetCgpa - 5) / 5) * 100}%` }} />
                            <input 
                                type="range" 
                                min="5.0" 
                                max="10.0" 
                                step="0.1" 
                                className={styles.macroSliderInput} 
                                value={targetCgpa} 
                                onChange={e => setTargetCgpa(parseFloat(e.target.value))} 
                            />
                            <div className={styles.macroSliderHandle} style={{ left: `${((targetCgpa - 5) / 5) * 100}%` }} />
                        </div>
                        <div className={styles.macroMarks}>
                            <span>5.0</span>
                            <span>7.5</span>
                            <span>10.0</span>
                        </div>
                    </div>
                    <div className={styles.macroResult}>
                        <div className={styles.macroValue}>{targetCgpa.toFixed(1)}</div>
                        {(() => {
                            const baseCgpa = pred?.predicted_cgpa || 7.5;
                            const diff = targetCgpa - baseCgpa;
                            if (diff > 0.8) return <span className={`${styles.macroConfidence} ${styles.confStretch}`}>⚠ Unlikely</span>;
                            if (diff > 0.3) return <span className={`${styles.macroConfidence} ${styles.confStretch}`}>⚠ Stretch Goal</span>;
                            if (diff > 0) return <span className={`${styles.macroConfidence} ${styles.confTrack}`}>📈 On Track</span>;
                            return <span className={`${styles.macroConfidence} ${styles.confEasy}`}>✓ Highly Likely</span>;
                        })()}
                    </div>
                </div>
            </div>

            <div className={`card ${styles.simulatorCard}`}>
                <div className={styles.cardHeader}>
                    <h2 className={styles.cardTitle}><Zap size={16} style={{ color: 'var(--accent)' }} /> What if…?</h2>
                    <span className="pill pill-accent">Scenario Simulator</span>
                </div>
                <p className={styles.simDesc}>Drag the sliders — the AI runs live CGPA predictions. Move any slider to get an AI Mentor explanation.</p>

                <div className={styles.sliders}>
                    {[
                        { key: 'attendance', label: 'Attendance improvement', unit: '%', max: 30 },
                        { key: 'assignments', label: 'Assignment completion', unit: '%', max: 40 },
                        { key: 'studyHours', label: 'Extra study hours / day', unit: 'h', max: 4 },
                    ].map(sl => (
                        <div key={sl.key} className={styles.sliderRow}>
                            <div className={styles.sliderLabel}>
                                <span>{sl.label}</span>
                                <strong className={sliders[sl.key] > 0 ? styles.sliderValActive : ''}>+{sliders[sl.key]}{sl.unit}</strong>
                            </div>
                            <input className={styles.slider} type="range" min={0} max={sl.max}
                                value={sliders[sl.key]}
                                onChange={e => setSliders(s => ({ ...s, [sl.key]: +e.target.value }))} />
                            <div className={styles.sliderTrackLabels}><span>0{sl.unit}</span><span>{sl.max}{sl.unit}</span></div>
                        </div>
                    ))}
                </div>

                <div className={styles.simDeltaCard}>
                    {simLoading ? (
                        <div className={styles.simDeltaLoading}><Loader2 size={18} className={`${styles.spin} ${styles.spinnerIcon}`} /><span>Recalculating…</span></div>
                    ) : simError ? (
                        <div className={styles.simDeltaError}>{simError}</div>
                    ) : simResult ? (
                        <>
                            <div className={styles.simDeltaRow}>
                                <div className={styles.simDeltaBlock}><span className={styles.simDeltaLabel}>Baseline CGPA</span><span className={styles.simDeltaNum}>{simResult.baseline_cgpa}</span></div>
                                <TrendingUp size={20} style={{ color: simResult.cgpa_delta > 0 ? 'var(--safe)' : 'var(--text-3)' }} />
                                <div className={styles.simDeltaBlock}><span className={styles.simDeltaLabel}>Simulated CGPA</span><span className={styles.simDeltaNum} style={{ color: simResult.cgpa_delta > 0 ? 'var(--safe)' : simResult.cgpa_delta < 0 ? 'var(--risk)' : 'var(--text-1)' }}>{simResult.simulated_cgpa}</span></div>
                                <div className={`${styles.simDeltaBadge} ${simResult.cgpa_delta > 0 ? styles.simDeltaPos : simResult.cgpa_delta < 0 ? styles.simDeltaNeg : styles.simDeltaNeutral}`}>
                                    {simResult.cgpa_delta > 0 ? '+' : ''}{simResult.cgpa_delta}
                                </div>
                            </div>
                            <div className={styles.simRange}>Confidence range: <strong>{simResult.simulated_range?.[0]} – {simResult.simulated_range?.[1]}</strong></div>

                            {/* AI sim explanation */}
                            {simResult.explanation && (
                                <div className={styles.simExplanation}>
                                    <Brain size={13} style={{ color: '#6366F1' }} />
                                    <span>{simResult.explanation}</span>
                                </div>
                            )}
                        </>
                    ) : (
                        <div className={styles.simDeltaHint}>Move a slider to run the simulation</div>
                    )}
                </div>

                {/* Per-subject diff table */}
                {simResult?.subjects && (
                    <div className={styles.simSubjectTable}>
                        <div className={styles.simSubjectHeader}><span>Subject</span><span>Current</span><span>Before</span><span>After</span><span>Δ</span></div>
                        {simResult.subjects.map((s, i) => (
                            <div key={i} className={`${styles.simSubjectRow} ${s.delta > 0 ? styles.simRowImproved : ''}`}>
                                <span className={styles.simSubjectName}>{s.name}</span>
                                <span className={styles.simSubjectGrade}>{s.current}</span>
                                <span className={styles.simSubjectBefore}>{s.before}</span>
                                <span className={styles.simSubjectAfter} style={{ color: s.delta > 0 ? 'var(--safe)' : 'var(--text-1)' }}>{s.after}</span>
                                <span className={`${styles.simSubjectDelta} ${s.delta > 0 ? styles.deltaPos : s.delta < 0 ? styles.deltaNeg : ''}`}>{s.delta > 0 ? '+' : ''}{s.delta !== 0 ? s.delta : '—'}</span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
