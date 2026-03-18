/**
 * Problems Page — Phase 7 V10 Interactive Problem Builder
 * Generate, attempt, and manage a personal problem bank
 */
import { useState, useEffect, useCallback } from 'react';
import { Puzzle, Zap, BookOpen, Code2, Loader2, CheckCircle2, XCircle, ChevronDown, ChevronUp, Trash2, Trophy, Layers } from 'lucide-react';
import styles from './Problems.module.css';
import { generateProblems, getProblems, deleteProblems, attemptProblem, getTutorOptions } from '../../services/api';

const MODE_CONFIG = {
    mixed:    { label: 'Mixed', icon: Layers, color: '#6366F1', desc: 'MCQ + Short + Coding' },
    olympiad: { label: 'Olympiad 🏆', icon: Trophy, color: '#D97706', desc: 'Proof & derivation' },
    hackathon:{ label: 'Hackathon 🚀', icon: Zap, color: '#059669', desc: 'System design focus' },
    mcq:      { label: 'MCQ', icon: CheckCircle2, color: '#2563EB', desc: 'Multiple choice' },
    coding:   { label: 'Coding', icon: Code2, color: '#DC2626', desc: 'Programming' },
    short:    { label: 'Short Answer', icon: BookOpen, color: '#7C3AED', desc: '2-3 sentence answers' },
};

const DIFFICULTY = ['easy', 'medium', 'hard', 'olympiad'];

export default function Problems() {
    const [subjects, setSubjects]     = useState([]);
    const [problems, setProblems]     = useState([]);
    const [loading, setLoading]       = useState(true);
    const [generating, setGenerating] = useState(false);
    const [expanded, setExpanded]     = useState({});
    const [answered, setAnswered]     = useState({});  // { problemId: { selected, submitted } }
    const [error, setError]           = useState('');

    // Config form
    const [subjectCode, setSubjectCode] = useState('');
    const [topic, setTopic]             = useState('');
    const [count, setCount]             = useState(5);
    const [mode, setMode]               = useState('mixed');
    const [difficulty, setDifficulty]   = useState('medium');
    const [showConfig, setShowConfig]   = useState(true);

    useEffect(() => {
        Promise.all([getTutorOptions(), getProblems()])
            .then(([opts, pb]) => {
                setSubjects(opts.subjects || []);
                setProblems(pb.problems || []);
            })
            .catch(() => {})
            .finally(() => setLoading(false));
    }, []);

    const handleGenerate = async () => {
        if (!subjectCode || !topic.trim()) { setError('Select a subject and enter a topic.'); return; }
        setError(''); setGenerating(true);
        try {
            const result = await generateProblems({ subject_code: subjectCode, topic: topic.trim(), count, mode, difficulty });
            setProblems(prev => [...(result.problems || []).map(p => ({ ...p, fresh: true })), ...prev]);
            setShowConfig(false);
        } catch (e) {
            setError(e.response?.data?.detail || 'Generation failed.');
        }
        setGenerating(false);
    };

    const handleAnswer = useCallback(async (problem, selectedIdx) => {
        const key = problem.id;
        if (answered[key]?.submitted) return;
        const isCorrect = problem.type === 'mcq'
            ? selectedIdx === problem.correct_index
            : true; // short/coding — mark manually
        setAnswered(prev => ({ ...prev, [key]: { selected: selectedIdx, submitted: true, correct: isCorrect } }));
        attemptProblem(problem.id, isCorrect).catch(() => {});
    }, [answered]);

    const handleDelete = async (id) => {
        await deleteProblems(id).catch(() => {});
        setProblems(prev => prev.filter(p => p.id !== id));
    };

    const stats = {
        total:    problems.length,
        attempted: problems.filter(p => p.attempted || answered[p.id]?.submitted).length,
        correct:  problems.filter(p => p.correct || answered[p.id]?.correct).length,
    };

    if (loading) return <div className={styles.centerLoader}><Loader2 size={28} className={styles.spin} /></div>;

    return (
        <div className={styles.page}>
            <header className={styles.header}>
                <div className={styles.headerIcon}><Puzzle size={22} /></div>
                <div>
                    <h1 className={styles.title}>Problem Bank</h1>
                    <p className={styles.subtitle}>AI-generated practice problems tailored to your subjects</p>
                </div>
                <button className={styles.genBtn} onClick={() => setShowConfig(v => !v)}>
                    <Zap size={14} /> {showConfig ? 'Hide' : 'Generate Problems'}
                </button>
            </header>

            {/* Stats */}
            <div className={styles.statsRow}>
                {[
                    { label: 'Total', value: stats.total, color: '#6366F1' },
                    { label: 'Attempted', value: stats.attempted, color: '#FF7A00' },
                    { label: 'Correct', value: stats.correct, color: '#10B981' },
                    { label: 'Accuracy', value: stats.attempted ? `${Math.round(stats.correct/stats.attempted*100)}%` : '—', color: '#2563EB' },
                ].map(s => (
                    <div key={s.label} className={styles.statCard}>
                        <span className={styles.statVal} style={{ color: s.color }}>{s.value}</span>
                        <span className={styles.statLabel}>{s.label}</span>
                    </div>
                ))}
            </div>

            {/* Config Panel */}
            {showConfig && (
                <div className={styles.configPanel}>
                    <h3 className={styles.configTitle}>Generate New Problems</h3>
                    <div className={styles.configGrid}>
                        <div className={styles.field}>
                            <label>Subject</label>
                            <select className={styles.select} value={subjectCode} onChange={e => setSubjectCode(e.target.value)}>
                                <option value="">Select subject…</option>
                                {subjects.map(s => <option key={s.code} value={s.code}>{s.name}</option>)}
                            </select>
                        </div>
                        <div className={styles.field}>
                            <label>Topic</label>
                            <input className={styles.input} placeholder="e.g. Binary Trees, Newton's Laws…" value={topic} onChange={e => setTopic(e.target.value)} />
                        </div>
                        <div className={styles.field}>
                            <label>Count</label>
                            <select className={styles.select} value={count} onChange={e => setCount(+e.target.value)}>
                                {[3,5,7,10].map(n => <option key={n} value={n}>{n} problems</option>)}
                            </select>
                        </div>
                        <div className={styles.field}>
                            <label>Difficulty</label>
                            <div className={styles.chipRow}>
                                {DIFFICULTY.map(d => (
                                    <button key={d} className={`${styles.chip} ${difficulty === d ? styles.chipActive : ''}`} onClick={() => setDifficulty(d)}>{d}</button>
                                ))}
                            </div>
                        </div>
                    </div>

                    <div className={styles.modeRow}>
                        <label>Mode</label>
                        <div className={styles.modeCards}>
                            {Object.entries(MODE_CONFIG).map(([k, v]) => {
                                const Icon = v.icon;
                                return (
                                    <button
                                        key={k}
                                        className={`${styles.modeCard} ${mode === k ? styles.modeActive : ''}`}
                                        style={mode === k ? { borderColor: v.color, background: `${v.color}12` } : {}}
                                        onClick={() => setMode(k)}
                                    >
                                        <Icon size={15} style={{ color: v.color }} />
                                        <span className={styles.modeLabel}>{v.label}</span>
                                        <span className={styles.modeDesc}>{v.desc}</span>
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    {error && <p className={styles.err}>{error}</p>}

                    <button className={styles.buildBtn} onClick={handleGenerate} disabled={generating}>
                        {generating ? <><Loader2 size={14} className={styles.spin} /> Generating…</> : <><Zap size={14} /> Generate</>}
                    </button>
                </div>
            )}

            {/* Problem List */}
            <div className={styles.problemList}>
                {problems.length === 0 && (
                    <div className={styles.empty}>
                        <Puzzle size={40} className={styles.emptyIcon} />
                        <p>No problems yet. Generate some above!</p>
                    </div>
                )}

                {problems.map((p, idx) => {
                    const ans    = answered[p.id] || {};
                    const open   = !!expanded[p.id];
                    const done   = ans.submitted || p.attempted;
                    const cfg    = MODE_CONFIG[p.mode] || MODE_CONFIG.mixed;

                    return (
                        <div key={p.id || idx} className={`${styles.card} ${p.fresh ? styles.cardNew : ''}`}>
                            <button className={styles.cardHeader} onClick={() => setExpanded(prev => ({ ...prev, [p.id]: !prev[p.id] }))}>
                                <span className={styles.qNum}>Q{idx + 1}</span>
                                <span className={styles.typeBadge} style={{ background: `${cfg.color}15`, color: cfg.color }}>{p.type}</span>
                                <span className={styles.diffBadge}>{p.difficulty}</span>
                                <span className={styles.qText}>{p.question.slice(0, 80)}{p.question.length > 80 ? '…' : ''}</span>
                                <span className={styles.bloom}>L{p.bloom_level}</span>
                                {done && (ans.correct || p.correct ? <CheckCircle2 size={15} className={styles.doneOk} /> : <XCircle size={15} className={styles.doneFail} />)}
                                {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                            </button>

                            {open && (
                                <div className={styles.cardBody}>
                                    <p className={styles.fullQ}>{p.question}</p>

                                    {/* MCQ options */}
                                    {p.type === 'mcq' && p.options?.length > 0 && (
                                        <div className={styles.options}>
                                            {p.options.map((o, i) => {
                                                let cls = styles.option;
                                                if (ans.submitted) {
                                                    if (i === p.correct_index) cls += ` ${styles.optCorrect}`;
                                                    else if (i === ans.selected) cls += ` ${styles.optWrong}`;
                                                } else if (i === ans.selected) cls += ` ${styles.optSelected}`;
                                                return (
                                                    <button key={i} className={cls} onClick={() => handleAnswer(p, i)} disabled={!!ans.submitted}>
                                                        <span className={styles.optLetter}>{String.fromCharCode(65+i)}</span>
                                                        <span>{o}</span>
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    )}

                                    {/* Short/Coding — show answer reveal */}
                                    {p.type !== 'mcq' && (
                                        <div className={styles.answerBlock}>
                                            {!ans.submitted
                                                ? <button className={styles.revealBtn} onClick={() => handleAnswer(p, 0)}>Reveal Answer</button>
                                                : <div className={styles.answerText}><strong>Answer:</strong> {p.correct_answer}</div>}
                                        </div>
                                    )}

                                    {p.hint && !ans.submitted && (
                                        <p className={styles.hint}>💡 <em>{p.hint}</em></p>
                                    )}

                                    {ans.submitted && p.explanation && (
                                        <div className={styles.explanation}>
                                            <strong>Explanation:</strong> {p.explanation}
                                        </div>
                                    )}

                                    <button className={styles.deleteBtn} onClick={() => handleDelete(p.id)}>
                                        <Trash2 size={12} /> Remove
                                    </button>
                                </div>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}
