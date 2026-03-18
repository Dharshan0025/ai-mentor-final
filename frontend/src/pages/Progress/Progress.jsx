/**
 * Progress Dashboard — /learn/progress
 * V4 Memory Layer: SM-2 spaced repetition progress, weak areas, checkpoint history,
 * learning DNA profile. All cream/orange themed.
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
    Brain, Target, TrendingUp, AlertTriangle, CheckCircle,
    Clock, Zap, BarChart3, BookOpen, ChevronRight, RefreshCw,
} from 'lucide-react';
import { getTutorProgress, getWeakAreas, getDueTopics } from '../../services/api';
import styles from './Progress.module.css';

// ── API helpers ─────────────────────────────────────────────────────────────
async function fetchProgress() {
    return getTutorProgress();
}
async function fetchWeakAreasData() {
    return getWeakAreas(null, 8);
}
async function fetchDueTopicsData() {
    return getDueTopics(72);
}

// ── Stat card ───────────────────────────────────────────────────────────────
function StatCard({ icon: Icon, label, value, sub, accent = false, trend }) {
    return (
        <div className={`${styles.statCard} ${accent ? styles.statCardAccent : ''}`}>
            <div className={styles.statIcon}><Icon size={18} /></div>
            <div className={styles.statBody}>
                <div className={styles.statValue}>{value}</div>
                <div className={styles.statLabel}>{label}</div>
                {sub && <div className={styles.statSub}>{sub}</div>}
            </div>
            {trend !== undefined && (
                <div className={`${styles.statTrend} ${trend >= 0 ? styles.trendUp : styles.trendDown}`}>
                    <TrendingUp size={12} />
                    {Math.abs(trend)}%
                </div>
            )}
        </div>
    );
}

// ── Accuracy ring ────────────────────────────────────────────────────────────
function AccuracyRing({ value }) {
    const radius = 44;
    const circ = 2 * Math.PI * radius;
    const filled = (value / 100) * circ;
    const color = value >= 70 ? '#16A34A' : value >= 45 ? '#FF7A00' : '#EF4444';
    return (
        <div className={styles.ring}>
            <svg width="110" height="110" viewBox="0 0 110 110">
                <circle cx="55" cy="55" r={radius} fill="none" stroke="var(--border)" strokeWidth="10" />
                <circle cx="55" cy="55" r={radius} fill="none" stroke={color} strokeWidth="10"
                    strokeDasharray={`${filled} ${circ}`}
                    strokeLinecap="round"
                    transform="rotate(-90 55 55)"
                    style={{ transition: 'stroke-dasharray 0.8s ease' }}
                />
            </svg>
            <div className={styles.ringLabel}>
                <span className={styles.ringValue} style={{ color }}>{value}%</span>
                <span className={styles.ringText}>Accuracy</span>
            </div>
        </div>
    );
}

// ── Subject bar ──────────────────────────────────────────────────────────────
function SubjectBar({ subject_code, avg_score, mastered, topics, due_count }) {
    const pct = Math.round((avg_score || 0) * 100);
    const color = pct >= 70 ? '#16A34A' : pct >= 40 ? '#FF7A00' : '#EF4444';
    return (
        <div className={styles.subjectRow}>
            <div className={styles.subjectCode}>{subject_code}</div>
            <div className={styles.subjectBarWrap}>
                <div className={styles.subjectBarTrack}>
                    <div className={styles.subjectBarFill} style={{ width: `${pct}%`, background: color }} />
                </div>
                <span className={styles.subjectPct} style={{ color }}>{pct}%</span>
            </div>
            <div className={styles.subjectMeta}>
                <span className={styles.masteredBadge}>{mastered}/{topics} mastered</span>
                {due_count > 0 && <span className={styles.dueBadge}>{due_count} due</span>}
            </div>
        </div>
    );
}

// ── Due topic chip ───────────────────────────────────────────────────────────
function DueTopicChip({ topic, subject_code, urgency, avg_score, interval_days, onStudy }) {
    const isOverdue = urgency === 'overdue';
    return (
        <div className={`${styles.dueChip} ${isOverdue ? styles.dueChipOverdue : ''}`}>
            <div className={styles.dueChipLeft}>
                <Clock size={13} />
                <div>
                    <div className={styles.dueTopicName}>{topic}</div>
                    <div className={styles.dueSubject}>{subject_code}</div>
                </div>
            </div>
            <div className={styles.dueChipRight}>
                <div className={styles.dueInterval}>{isOverdue ? '⏰ Overdue' : `In ${interval_days}d`}</div>
                <div className={styles.dueScore}>{Math.round((avg_score || 0) * 100)}% avg</div>
                <button className={styles.studyBtn} onClick={() => onStudy?.(topic, subject_code)}>
                    Study <ChevronRight size={11} />
                </button>
            </div>
        </div>
    );
}

// ── Weak area row ────────────────────────────────────────────────────────────
function WeakAreaRow({ subject_code, topic, avg_score, times_wrong, confusion_count, difficulty_level }) {
    const pct = Math.round((avg_score || 0) * 100);
    const severity = difficulty_level >= 0.7 ? 'high' : difficulty_level >= 0.4 ? 'medium' : 'low';
    return (
        <div className={`${styles.weakRow} ${styles[`weakRow_${severity}`]}`}>
            <AlertTriangle size={13} className={styles.weakIcon} />
            <div className={styles.weakInfo}>
                <div className={styles.weakTopic}>{topic}</div>
                <div className={styles.weakSubject}>{subject_code}</div>
            </div>
            <div className={styles.weakStats}>
                <span className={styles.weakScore}>{pct}%</span>
                <span className={styles.weakWrong}>{times_wrong}✗</span>
            </div>
        </div>
    );
}

// ── Main page ────────────────────────────────────────────────────────────────
export default function Progress() {
    const navigate = useNavigate();

    const [progress, setProgress] = useState(null);
    const [weakAreas, setWeakAreas] = useState([]);
    const [dueTopics, setDueTopics] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [refreshing, setRefreshing] = useState(false);

    const load = useCallback(async (showRefresh = false) => {
        if (showRefresh) setRefreshing(true);
        else setLoading(true);
        setError(null);
        try {
            const [prog, weak, due] = await Promise.all([
                fetchProgress(),
                fetchWeakAreasData(),
                fetchDueTopicsData(),
            ]);
            setProgress(prog);
            setWeakAreas(weak.weak_areas || []);
            setDueTopics(due.due_topics || []);
        } catch (e) {
            setError('Could not load progress data. Start a lesson to generate your stats!');
        } finally {
            setLoading(false);
            setRefreshing(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    const handleStudyTopic = useCallback((topic, subjectCode) => {
        navigate('/tutor', { state: { autoTopic: topic, autoSubjectCode: subjectCode } });
    }, [navigate]);

    if (loading) {
        return (
            <div className={styles.loadingWrap}>
                <div className={styles.loadingOrb}><Brain size={28} /></div>
                <p>Loading your learning progress…</p>
            </div>
        );
    }

    const dna = progress?.learning_dna || {};
    const accuracy = progress?.overall_accuracy || 0;
    const passRate = progress?.checkpoint_pass_rate || 0;
    const bySubject = progress?.by_subject || [];

    return (
        <div className={styles.page}>
            {/* Header */}
            <div className={styles.header}>
                <div className={styles.headerLeft}>
                    <div className={styles.headerOrb}><Brain size={22} /></div>
                    <div>
                        <h1>Learning Progress</h1>
                        <p className={styles.headerSub}>SM-2 Spaced Repetition · LangChain RAG</p>
                    </div>
                </div>
                <button
                    className={styles.refreshBtn}
                    onClick={() => load(true)}
                    disabled={refreshing}
                    title="Refresh progress"
                >
                    <RefreshCw size={14} className={refreshing ? styles.spinning : ''} />
                    {refreshing ? 'Refreshing…' : 'Refresh'}
                </button>
            </div>

            {error && (
                <div className={styles.emptyState}>
                    <Brain size={36} className={styles.emptyIcon} />
                    <h3>No data yet</h3>
                    <p>{error}</p>
                    <button className={styles.startBtn} onClick={() => navigate('/tutor')}>
                        Start Learning
                    </button>
                </div>
            )}

            {progress && (
                <>
                    {/* ── Headline stats ── */}
                    <div className={styles.statsGrid}>
                        <StatCard icon={Target} label="Topics Studied" value={progress.total_topics} sub={`${progress.total_concepts} concepts`} />
                        <StatCard icon={CheckCircle} label="Mastered Concepts" value={progress.mastered_concepts} sub={`of ${progress.total_concepts}`} accent />
                        <StatCard icon={AlertTriangle} label="Struggling" value={progress.struggling_concepts} sub="need review" />
                        <StatCard icon={Clock} label="Due for Review" value={progress.due_for_review} sub="SM-2 queue" />
                        <StatCard icon={Zap} label="Total Checkpoints" value={progress.total_checkpoints} sub={`${passRate}% pass rate`} />
                        <StatCard icon={BookOpen} label="Quizzes Taken" value={dna.total_quizzes || 0} sub={`${dna.overall_accuracy || 0}% accuracy`} />
                    </div>

                    {/* ── Accuracy ring + DNA ── */}
                    <div className={styles.middleRow}>
                        <div className={styles.accuracyCard}>
                            <AccuracyRing value={Math.round(accuracy)} />
                            <div className={styles.accuracyMeta}>
                                <div className={styles.metaRow}>
                                    <span className={styles.metaLabel}>Checkpoint pass rate</span>
                                    <span className={styles.metaVal}>{passRate}%</span>
                                </div>
                                <div className={styles.metaRow}>
                                    <span className={styles.metaLabel}>Avg score per concept</span>
                                    <span className={styles.metaVal}>{Math.round((progress.overall_avg_score || 0) * 100)}%</span>
                                </div>
                                <div className={styles.metaRow}>
                                    <span className={styles.metaLabel}>Learning style</span>
                                    <span className={styles.metaVal}>{dna.preferred_style || '—'}</span>
                                </div>
                                {dna.peak_hour !== null && dna.peak_hour !== undefined && (
                                    <div className={styles.metaRow}>
                                        <span className={styles.metaLabel}>Peak study hour</span>
                                        <span className={styles.metaVal}>{dna.peak_hour}:00</span>
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* ── By subject ── */}
                        <div className={styles.subjectCard}>
                            <div className={styles.cardTitle}><BarChart3 size={15} /> By Subject</div>
                            {bySubject.length === 0 ? (
                                <p className={styles.emptyText}>No subject data yet</p>
                            ) : (
                                <div className={styles.subjectList}>
                                    {bySubject.map(s => (
                                        <SubjectBar key={s.subject_code} {...s} />
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>

                    {/* ── Due topics + weak areas ── */}
                    <div className={styles.bottomRow}>
                        {/* Due topics */}
                        <div className={styles.dueCard}>
                            <div className={styles.cardTitle}>
                                <Clock size={15} /> SM-2 Review Queue
                                <span className={styles.cardCount}>{dueTopics.length}</span>
                            </div>
                            {dueTopics.length === 0 ? (
                                <div className={styles.emptyText}>🎉 Nothing due right now!</div>
                            ) : (
                                <div className={styles.dueList}>
                                    {dueTopics.map((t, i) => (
                                        <DueTopicChip key={i} {...t} onStudy={handleStudyTopic} />
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* Weak areas */}
                        <div className={styles.weakCard}>
                            <div className={styles.cardTitle}>
                                <AlertTriangle size={15} /> Weak Areas
                                <span className={styles.cardCount}>{weakAreas.length}</span>
                            </div>
                            {weakAreas.length === 0 ? (
                                <div className={styles.emptyText}>No weak areas detected yet!</div>
                            ) : (
                                <div className={styles.weakList}>
                                    {weakAreas.map((w, i) => <WeakAreaRow key={i} {...w} />)}
                                </div>
                            )}
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}
