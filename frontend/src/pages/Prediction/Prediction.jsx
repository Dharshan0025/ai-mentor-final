import { useState, useEffect, useRef } from 'react';
import { Line } from 'react-chartjs-2';
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Filler } from 'chart.js';
import { ArrowRight, ChevronDown, Zap, TrendingUp, Loader2 } from 'lucide-react';
import styles from './Prediction.module.css';
import { getMyProfile, simulateScenario } from '../../services/api';
import { mockCurrentStudent } from '../../data/mockData';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Filler);

export default function Prediction() {
    const [student, setStudent] = useState(null);
    const [loading, setLoading] = useState(true);
    const [sliders, setSliders] = useState({ attendance: 0, assignments: 0, studyHours: 0 });
    const [selectedSubject, setSelectedSubject] = useState(null);

    // Simulator live state
    const [simResult, setSimResult] = useState(null);
    const [simLoading, setSimLoading] = useState(false);
    const [simError, setSimError] = useState(null);
    const debounceRef = useRef(null);

    useEffect(() => {
        getMyProfile()
            .then(data => setStudent(data))
            .catch(err => {
                console.error('Failed to fetch prediction profile', err);
                setStudent(mockCurrentStudent);
            })
            .finally(() => setLoading(false));
    }, []);

    // Debounced simulator API call — fires 400ms after sliders stop changing
    useEffect(() => {
        if (!student) return;
        clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(async () => {
            setSimLoading(true);
            setSimError(null);
            try {
                const result = await simulateScenario({
                    attendance_delta: sliders.attendance,
                    assignment_delta: sliders.assignments,
                    study_hours_delta: sliders.studyHours,
                });
                setSimResult(result);
            } catch (e) {
                setSimError('Simulation unavailable — check agent service');
            } finally {
                setSimLoading(false);
            }
        }, 400);
        return () => clearTimeout(debounceRef.current);
    }, [sliders, student]);

    if (loading || !student) {
        return (
            <div className={styles.page} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}>
                <p style={{ color: 'var(--text-3)' }}>Running prediction models...</p>
            </div>
        );
    }

    // Projected future semesters
    const futureData = [student.predictedCGPA, Math.min(10, student.predictedCGPA + 0.15)];
    const allLabels = student.cgpaHistory.map((_, i) => `Sem ${i + 1}`).concat(['Sem 8 (proj)', 'Sem 9 (proj)']);
    const nPast = student.cgpaHistory.length;

    const chartData = {
        labels: allLabels,
        datasets: [
            {
                label: 'Actual CGPA',
                data: [...student.cgpaHistory, null, null],
                borderColor: '#1A1A1A',
                borderWidth: 2.5,
                pointBackgroundColor: '#1A1A1A',
                pointRadius: 4,
                tension: 0.35,
                fill: false,
            },
            {
                label: 'Projected CGPA',
                data: [...student.cgpaHistory.map(() => null).slice(0, -1), student.cgpaHistory.at(-1), ...futureData],
                borderColor: '#FF7A00',
                borderWidth: 2.5,
                borderDash: [6, 3],
                pointBackgroundColor: '#FF7A00',
                pointRadius: 4,
                tension: 0.35,
                fill: {
                    target: 'origin',
                    above: 'rgba(255,122,0,0.05)',
                }
            }
        ]
    };

    const chartOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { display: false },
            tooltip: {
                backgroundColor: '#fff',
                titleColor: '#1A1A1A',
                bodyColor: '#6B6B6B',
                borderColor: '#E8E4DE',
                borderWidth: 1,
            }
        },
        scales: {
            x: { grid: { display: false }, ticks: { color: '#9A9A9A', font: { size: 11 } }, border: { display: false } },
            y: { grid: { color: '#F0ECE6' }, ticks: { color: '#9A9A9A', font: { size: 11 } }, border: { display: false }, min: 6, max: 10 }
        }
    };

    // Baseline subject scores from student profile (for the grid)
    const subjectScores = student.subjects;

    return (
        <div className={styles.page}>
            {/* Header */}
            <div className={styles.header}>
                <span className="section-label">🔮 AI Predictions</span>
                <h1 className={styles.title}>
                    How you'll perform <span className="text-accent">next semester</span>
                </h1>
                <p className={styles.sub}>Based on {nPast} semesters of real ERP data — updated weekly by the Prediction Agent.</p>
            </div>

            {/* Trajectory + Predicted CGPA */}
            <div className={styles.topRow}>
                <div className={`card ${styles.chartCard}`}>
                    <div className={styles.cardHeader}>
                        <h2 className={styles.cardTitle}>CGPA Forecast</h2>
                        <div className={styles.legend}>
                            <span className={styles.legendItem}><span className={styles.legendLine} style={{ background: '#1A1A1A' }} />Actual</span>
                            <span className={styles.legendItem}><span className={styles.legendLine} style={{ background: '#FF7A00', opacity: 0.7 }} />Projected</span>
                        </div>
                    </div>
                    <div className={styles.chartWrap}>
                        <Line data={chartData} options={chartOptions} />
                    </div>
                    <div className={styles.chartNote}>
                        Confidence interval: <strong>{student.predictedCGPARange[0]} – {student.predictedCGPARange[1]}</strong>
                    </div>
                </div>

                <div className={`card ${styles.projectedCard}`}>
                    <h2 className={styles.cardTitle}>Projected CGPA</h2>
                    <div className={styles.bigCGPA}>{student.predictedCGPA}</div>
                    <div className={styles.cgpaRange}>Range: {student.predictedCGPARange.join(' – ')}</div>
                    <hr className="divider" style={{ margin: '16px 0' }} />
                    <div className={styles.cgpaInsights}>
                        <div className={styles.cgpaInsight}><span>🔴 High-risk</span><span className={styles.insightVal}>2 subjects</span></div>
                        <div className={styles.cgpaInsight}><span>🟡 Monitor</span><span className={styles.insightVal}>1 subject</span></div>
                        <div className={styles.cgpaInsight}><span>🟢 On track</span><span className={styles.insightVal}>3 subjects</span></div>
                    </div>
                </div>
            </div>

            {/* Subject risk map */}
            <div className={`card ${styles.riskMapCard}`}>
                <div className={styles.cardHeader}>
                    <h2 className={styles.cardTitle}>Subject Risk Assessment</h2>
                    <span className="pill pill-muted">Predicted scores</span>
                </div>
                <div className={styles.riskMap}>
                    {student.subjects.map((s, i) => {
                        const pct = Math.round((s.predicted / 10) * 100);
                        const st = getRiskStyle(s.status);
                        return (
                            <div
                                key={i}
                                className={`${styles.riskRow} ${selectedSubject === i ? styles.riskRowActive : ''}`}
                                onClick={() => setSelectedSubject(selectedSubject === i ? null : i)}
                            >
                                <div className={styles.riskRowMain}>
                                    <span className={styles.riskSubjectName}>{s.name}</span>
                                    <div className={styles.riskBarWrap}>
                                        <div className={styles.riskBarTrack}>
                                            <div className={styles.riskBarFill} style={{ width: `${pct}%`, background: st.color }} />
                                        </div>
                                    </div>
                                    <span className={styles.riskScore} style={{ color: st.color }}>{s.predicted.toFixed(1)}</span>
                                    <span className={`pill ${st.pill}`}>{st.label}</span>
                                    <ChevronDown size={14} style={{ color: 'var(--text-3)', transform: selectedSubject === i ? 'rotate(180deg)' : '', transition: 'transform 200ms' }} />
                                </div>
                                {selectedSubject === i && (
                                    <div className={styles.riskDetail}>
                                        <div className={styles.riskDetailItem}>📊 Current grade: <strong>{s.grade}</strong></div>
                                        <div className={styles.riskDetailItem}>📅 Attendance: <strong>{s.attendance}%</strong> {s.attendance < 75 && <span style={{ color: 'var(--risk)' }}>(below 75% threshold)</span>}</div>
                                        <div className={styles.riskDetailItem}>🎓 Bloom level: <strong>{s.bloomLevel}/6</strong></div>
                                        <div className={styles.riskDetailItem}>💳 Credit weight: <strong>{s.creditWeight} credits</strong></div>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* Scenario Simulator — wired to real compute_predicted_cgpa() */}
            <div className={`card ${styles.simulatorCard}`}>
                <div className={styles.cardHeader}>
                    <h2 className={styles.cardTitle}>
                        <Zap size={16} style={{ color: '#FF7A00' }} /> What if...?
                    </h2>
                    <span className="pill pill-accent">Scenario Simulator</span>
                </div>
                <p className={styles.simDesc}>
                    Drag the sliders — the AI runs <strong>live CGPA predictions</strong> from your real academic data in real-time.
                </p>

                {/* Sliders */}
                <div className={styles.sliders}>
                    {[
                        { key: 'attendance', label: 'Attendance improvement', unit: '%', max: 30 },
                        { key: 'assignments', label: 'Assignment completion', unit: '%', max: 40 },
                        { key: 'studyHours', label: 'Extra study hours / day', unit: 'hrs', max: 4 },
                    ].map(sl => (
                        <div key={sl.key} className={styles.sliderRow}>
                            <div className={styles.sliderLabel}>
                                <span>{sl.label}</span>
                                <strong className={sliders[sl.key] > 0 ? styles.sliderValActive : ''}>
                                    +{sliders[sl.key]}{sl.unit}
                                </strong>
                            </div>
                            <input
                                className={styles.slider}
                                type="range" min={0} max={sl.max}
                                value={sliders[sl.key]}
                                onChange={e => setSliders(s => ({ ...s, [sl.key]: +e.target.value }))}
                            />
                            <div className={styles.sliderTrackLabels}>
                                <span>0{sl.unit}</span>
                                <span>{sl.max}{sl.unit}</span>
                            </div>
                        </div>
                    ))}
                </div>

                {/* Live CGPA Delta Card */}
                <div className={styles.simDeltaCard}>
                    {simLoading ? (
                        <div className={styles.simDeltaLoading}>
                            <Loader2 size={18} className={styles.spinnerIcon} />
                            <span>Recalculating...</span>
                        </div>
                    ) : simError ? (
                        <div className={styles.simDeltaError}>{simError}</div>
                    ) : simResult ? (
                        <>
                            <div className={styles.simDeltaRow}>
                                <div className={styles.simDeltaBlock}>
                                    <span className={styles.simDeltaLabel}>Baseline CGPA</span>
                                    <span className={styles.simDeltaNum}>{simResult.baseline_cgpa}</span>
                                </div>
                                <div className={styles.simDeltaArrow}>
                                    <TrendingUp size={20} style={{ color: simResult.cgpa_delta > 0 ? '#10B981' : '#9A9A9A' }} />
                                </div>
                                <div className={styles.simDeltaBlock}>
                                    <span className={styles.simDeltaLabel}>Simulated CGPA</span>
                                    <span className={styles.simDeltaNum} style={{ color: simResult.cgpa_delta > 0 ? '#10B981' : simResult.cgpa_delta < 0 ? '#EF4444' : '#1A1A1A' }}>
                                        {simResult.simulated_cgpa}
                                    </span>
                                </div>
                                <div className={`${styles.simDeltaBadge} ${simResult.cgpa_delta > 0 ? styles.simDeltaPos : simResult.cgpa_delta < 0 ? styles.simDeltaNeg : styles.simDeltaNeutral}`}>
                                    {simResult.cgpa_delta > 0 ? '+' : ''}{simResult.cgpa_delta}
                                </div>
                            </div>
                            <div className={styles.simRange}>
                                Confidence range: <strong>{simResult.simulated_range?.[0]} – {simResult.simulated_range?.[1]}</strong>
                            </div>
                        </>
                    ) : (
                        <div className={styles.simDeltaHint}>Move a slider to run the simulation</div>
                    )}
                </div>

                {/* Per-subject score diff table */}
                {simResult?.subjects && (
                    <div className={styles.simSubjectTable}>
                        <div className={styles.simSubjectHeader}>
                            <span>Subject</span>
                            <span>Current</span>
                            <span>Before</span>
                            <span>After</span>
                            <span>Delta</span>
                        </div>
                        {simResult.subjects.map((s, i) => {
                            const st = getRiskStyle(s.status);
                            return (
                                <div key={i} className={`${styles.simSubjectRow} ${s.delta > 0 ? styles.simRowImproved : ''}`}>
                                    <span className={styles.simSubjectName}>{s.name}</span>
                                    <span className={styles.simSubjectGrade}>{s.current}</span>
                                    <span className={styles.simSubjectBefore}>{s.before}</span>
                                    <span className={styles.simSubjectAfter} style={{ color: s.delta > 0 ? '#10B981' : '#1A1A1A' }}>
                                        {s.after}
                                    </span>
                                    <span className={`${styles.simSubjectDelta} ${s.delta > 0 ? styles.deltaPos : s.delta < 0 ? styles.deltaNeg : ''}`}>
                                        {s.delta > 0 ? '+' : ''}{s.delta !== 0 ? s.delta : '—'}
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}

function getRiskStyle(status) {
    if (status === 'safe') return { color: 'var(--safe)', pill: 'pill-safe', label: 'Safe' };
    if (status === 'watch') return { color: 'var(--watch)', pill: 'pill-watch', label: 'Watch' };
    return { color: 'var(--risk)', pill: 'pill-risk', label: 'At Risk' };
}
