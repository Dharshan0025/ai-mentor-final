/**
 * Roadmap Page — Phase 6 V10 Personalized Study Roadmap
 * Week-by-week study plan with SM-2 + PYQ priorities
 */
import { useState, useEffect, useCallback } from 'react';
import {
    Map, Calendar, RefreshCw, Loader2, BookOpen, ChevronDown, ChevronUp,
    Zap, Clock, Target, CheckCircle2, Circle, Brain, AlertTriangle,
} from 'lucide-react';
import styles from './Roadmap.module.css';
import { generateRoadmap, getRoadmap, getTutorOptions } from '../../services/api';

const TYPE_CONFIG = {
    review: { color: '#10B981', label: 'SM-2 Review', icon: Brain },
    pyq_priority: { color: '#FF7A00', label: 'PYQ High-Weight', icon: Target },
    new: { color: '#3B82F6', label: 'New Topic', icon: BookOpen },
    practice: { color: '#8B5CF6', label: 'Practice', icon: Zap },
};

const PRIORITY_DOT = { high: '#EF4444', medium: '#F59E0B', low: '#6B7280' };

export default function Roadmap() {
    const [roadmap, setRoadmap] = useState(null);
    const [loading, setLoading] = useState(true);
    const [generating, setGenerating] = useState(false);
    const [subjects, setSubjects] = useState([]);
    const [selSubjects, setSelSubjects] = useState([]);
    const [weeks, setWeeks] = useState(4);
    const [examDate, setExamDate] = useState('');
    const [expanded, setExpanded] = useState({});
    const [checked, setChecked] = useState(() => {
        try { return JSON.parse(localStorage.getItem('roadmap_checked') || '{}'); } catch { return {}; }
    });
    const [showConfig, setShowConfig] = useState(false);
    const [error, setError] = useState('');

    // Load subjects and existing roadmap
    useEffect(() => {
        Promise.all([getTutorOptions(), getRoadmap().catch(() => null)])
            .then(([opts, rm]) => {
                setSubjects(opts.subjects || []);
                if (rm) {
                    setRoadmap(rm);
                    // Expand week 1 by default
                    setExpanded({ 1: true });
                }
            })
            .catch(() => { })
            .finally(() => setLoading(false));
    }, []);

    const saveChecked = useCallback((next) => {
        setChecked(next);
        localStorage.setItem('roadmap_checked', JSON.stringify(next));
    }, []);

    const toggleTopic = (weekNum, topicName) => {
        const key = `${weekNum}:${topicName}`;
        const next = { ...checked, [key]: !checked[key] };
        saveChecked(next);
    };

    const handleGenerate = async () => {
        setError(''); setGenerating(true);
        try {
            const rm = await generateRoadmap({
                subjects: selSubjects.length > 0 ? selSubjects : subjects.map(s => s.code),
                weeks,
                exam_date: examDate || undefined,
            });
            setRoadmap(rm);
            setExpanded({ 1: true });
            setShowConfig(false);
        } catch (e) {
            setError(e.response?.data?.detail || 'Generation failed.');
        }
        setGenerating(false);
    };

    const weekProgress = (weekNum) => {
        const wk = roadmap?.weeks?.find(w => w.week === weekNum);
        if (!wk || !wk.topics?.length) return 0;
        const done = wk.topics.filter(t => checked[`${weekNum}:${t.name}`]).length;
        return Math.round((done / wk.topics.length) * 100);
    };

    if (loading) return (
        <div className={styles.centerLoader}><Loader2 size={28} className={styles.spin} /></div>
    );

    return (
        <div className={styles.page}>
            <header className={styles.header}>
                <div className={styles.headerIcon}><Map size={22} /></div>
                <div>
                    <h1 className={styles.title}>My Study Roadmap</h1>
                    <p className={styles.subtitle}>AI-personalized week-by-week plan based on your SM-2 agenda and exam patterns</p>
                </div>
                <button
                    className={styles.genBtn}
                    onClick={() => setShowConfig(v => !v)}
                >
                    <RefreshCw size={15} /> {roadmap ? 'Regenerate' : 'Generate Plan'}
                </button>
            </header>

            {/* Legend */}
            <div className={styles.legend}>
                {Object.entries(TYPE_CONFIG).map(([k, v]) => {
                    const Icon = v.icon;
                    return (
                        <span key={k} className={styles.legendItem}>
                            <span style={{ background: v.color }} className={styles.legendDot} />
                            {v.label}
                        </span>
                    );
                })}
            </div>

            {/* Config Panel */}
            {showConfig && (
                <div className={styles.configPanel}>
                    <h3 className={styles.configTitle}>Generate New Roadmap</h3>
                    <div className={styles.configRow}>
                        <div className={styles.configField}>
                            <label>Weeks</label>
                            <select className={styles.select} value={weeks} onChange={e => setWeeks(+e.target.value)}>
                                {[2, 3, 4, 6, 8].map(w => (
                                    <option key={w} value={w}>{w} weeks</option>
                                ))}
                            </select>
                        </div>
                        <div className={styles.configField}>
                            <label>Exam Date (optional)</label>
                            <input
                                type="date"
                                className={styles.input}
                                value={examDate}
                                onChange={e => setExamDate(e.target.value)}
                            />
                        </div>
                    </div>

                    <div className={styles.subjectPicker}>
                        <label>Subjects (select or leave all)</label>
                        <div className={styles.subjectChips}>
                            {subjects.map(s => (
                                <button
                                    key={s.code}
                                    className={`${styles.chip} ${selSubjects.includes(s.code) ? styles.chipActive : ''}`}
                                    onClick={() => setSelSubjects(prev =>
                                        prev.includes(s.code) ? prev.filter(c => c !== s.code) : [...prev, s.code]
                                    )}
                                >
                                    {s.name}
                                </button>
                            ))}
                        </div>
                    </div>

                    {error && <p className={styles.err}>{error}</p>}

                    <button className={styles.buildBtn} onClick={handleGenerate} disabled={generating}>
                        {generating
                            ? <><Loader2 size={14} className={styles.spin} />Generating…</>
                            : <><Zap size={14} /> Build Roadmap</>}
                    </button>
                </div>
            )}

            {/* Roadmap Weeks */}
            {!roadmap && !showConfig && (
                <div className={styles.emptyState}>
                    <Map size={44} className={styles.emptyIcon} />
                    <p>No roadmap yet.</p>
                    <p className={styles.emptyHint}>Click "Generate Plan" to build a personalized study plan from your SM-2 agenda and past year questions.</p>
                    <button className={styles.buildBtn} onClick={() => setShowConfig(true)}>
                        <Zap size={14} /> Generate Plan
                    </button>
                </div>
            )}

            {roadmap && (
                <div className={styles.weeks}>
                    {/* Study Tips */}
                    {roadmap.study_tips?.length > 0 && (
                        <div className={styles.tipsBar}>
                            💡 {roadmap.study_tips[0]}
                        </div>
                    )}

                    {(roadmap.weeks || []).map(wk => {
                        const prog = weekProgress(wk.week);
                        const open = !!expanded[wk.week];

                        return (
                            <div key={wk.week} className={`${styles.weekCard} ${prog === 100 ? styles.weekDone : ''}`}>
                                {/* Week Header */}
                                <button
                                    className={styles.weekHeader}
                                    onClick={() => setExpanded(prev => ({ ...prev, [wk.week]: !prev[wk.week] }))}
                                >
                                    <div className={styles.weekNum}>
                                        {prog === 100
                                            ? <CheckCircle2 size={20} className={styles.doneIcon} />
                                            : <span className={styles.weekNumLabel}>W{wk.week}</span>}
                                    </div>
                                    <div className={styles.weekInfo}>
                                        <div className={styles.weekFocus}>{wk.focus}</div>
                                        <div className={styles.weekMeta}>
                                            <span>{wk.topics?.length || 0} topics</span>
                                            <span>·</span>
                                            <span>{wk.topics?.reduce((a, t) => a + (t.hours || 2), 0)}h estimated</span>
                                        </div>
                                    </div>
                                    <div className={styles.weekRight}>
                                        <div className={styles.progressRing}>
                                            <svg viewBox="0 0 36 36">
                                                <circle cx="18" cy="18" r="14" fill="none" stroke="#E8E0D5" strokeWidth="4" />
                                                <circle
                                                    cx="18" cy="18" r="14" fill="none"
                                                    stroke={prog === 100 ? '#10B981' : '#FF7A00'}
                                                    strokeWidth="4"
                                                    strokeDasharray={`${prog * 0.88} 88`}
                                                    strokeLinecap="round"
                                                    transform="rotate(-90 18 18)"
                                                />
                                            </svg>
                                            <span className={styles.progPct}>{prog}%</span>
                                        </div>
                                        {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                                    </div>
                                </button>

                                {/* Topics */}
                                {open && (
                                    <div className={styles.topicList}>
                                        {(wk.topics || []).map((t, i) => {
                                            const key = `${wk.week}:${t.name}`;
                                            const done = !!checked[key];
                                            const cfg = TYPE_CONFIG[t.type] || TYPE_CONFIG.new;
                                            const Icon = cfg.icon;

                                            return (
                                                <div
                                                    key={i}
                                                    className={`${styles.topicItem} ${done ? styles.topicDone : ''}`}
                                                    onClick={() => toggleTopic(wk.week, t.name)}
                                                >
                                                    <span className={done ? styles.checkDone : styles.checkEmpty}>
                                                        {done ? <CheckCircle2 size={16} /> : <Circle size={16} />}
                                                    </span>
                                                    <span className={styles.topicIcon} style={{ color: cfg.color }}>
                                                        <Icon size={13} />
                                                    </span>
                                                    <span className={styles.topicName}>{t.name}</span>
                                                    {t.subject && (
                                                        <span className={styles.topicSubject}>{t.subject}</span>
                                                    )}
                                                    <span className={styles.topicPriority} style={{ background: PRIORITY_DOT[t.priority] || '#ccc' }} />
                                                    <span className={styles.topicHours}>
                                                        <Clock size={11} /> {t.hours || 2}h
                                                    </span>
                                                    <span className={styles.topicBloom}>L{t.bloom_target}</span>
                                                </div>
                                            );
                                        })}

                                        {wk.milestone && (
                                            <div className={styles.milestone}>
                                                🏁 <strong>Goal:</strong> {wk.milestone}
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        );
                    })}

                    {/* Key Milestones */}
                    {roadmap.key_milestones?.length > 0 && (
                        <div className={styles.milestonesPanel}>
                            <h3 className={styles.mileSTitle}>Key Milestones</h3>
                            {roadmap.key_milestones.map((m, i) => (
                                <div key={i} className={styles.mileItem}>
                                    <span className={styles.mileWeek}>Week {m.week}</span>
                                    <span>{m.milestone}</span>
                                </div>
                            ))}
                        </div>
                    )}

                    {roadmap.generated_at && (
                        <p className={styles.genDate}>
                            Generated {new Date(roadmap.generated_at).toLocaleDateString()}
                        </p>
                    )}
                </div>
            )}
        </div>
    );
}
