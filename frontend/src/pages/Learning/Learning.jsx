import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
    CheckCircle, ChevronRight, Zap, BookOpen,
    RotateCcw, Trophy, Clock, Brain, Loader2,
    Layers, TrendingUp, AlertTriangle
} from 'lucide-react';
import styles from './Learning.module.css';
import { LearningSkeleton } from '../../components/Skeleton/Skeleton';
import { generateQuiz, getStudentProfile, getMyMastery, getTutorOptions } from '../../services/api';

// ── Real syllabus topics per subject code ─────────────────────────────────────
// Aligned with Anna University CSBS Regulation 2021, Sem 4-7
const TOPICS = {
    // OS — AL3452
    'CS701': [
        'Process & Thread Concepts',
        'CPU Scheduling Algorithms',
        'Deadlock Detection & Avoidance',
        'Memory Management & Paging',
        'Virtual Memory & Demand Paging',
        'File System Interface & Implementation',
        'I/O Systems & Device Management',
        'Security & Protection Mechanisms',
    ],
    // Machine Learning — AL3451
    'CS702': [
        'Supervised Learning — Regression',
        'Supervised Learning — Classification',
        'Unsupervised Learning & Clustering',
        'Decision Trees & Random Forests',
        'Support Vector Machines',
        'Neural Networks & Backpropagation',
        'Deep Learning Fundamentals',
        'Model Evaluation & Validation',
        'Feature Engineering & Selection',
    ],
    // DBMS — CS3492
    'CS703': [
        'ER Modeling & Relational Model',
        'SQL — DDL, DML, DCL',
        'Joins, Views & Stored Procedures',
        'Normalization — 1NF to BCNF',
        'Indexing & B+ Trees',
        'Transactions & ACID Properties',
        'Concurrency Control Protocols',
        'Query Processing & Optimization',
        'NoSQL Databases',
    ],
    // Computer Networks — CS3491
    'CS704': [
        'OSI & TCP/IP Reference Models',
        'Physical Layer & Data Encoding',
        'Data Link Layer & Error Control',
        'MAC Protocols & Ethernet',
        'Network Layer & IP Addressing',
        'Routing Algorithms',
        'Transport Layer — TCP & UDP',
        'Application Layer — DNS, HTTP, SMTP',
        'Network Security Fundamentals',
    ],
    // Software Engineering — CCS356
    'CS705': [
        'SDLC Models — Waterfall, Agile',
        'Requirements Engineering & SRS',
        'UML Diagrams — Use Case, Class',
        'Software Design Patterns',
        'Testing Strategies — Unit to E2E',
        'Agile & Scrum Methodology',
        'Project Management & COCOMO',
        'Software Maintenance',
    ],
    // Cloud Computing — Elective
    'CS706': [
        'Cloud Service Models — IaaS, PaaS, SaaS',
        'Virtualization Technologies',
        'AWS Core Services',
        'Containerization — Docker',
        'Container Orchestration — Kubernetes',
        'Serverless Architecture',
        'Cloud Security & Compliance',
        'Microservices Architecture',
    ],
};

// ── Bloom level info ─────────────────────────────────────────────────────────
const BLOOM_INFO = [
    { level: 1, verb: 'Remember', color: '#64748b', desc: 'Recall facts and basic concepts' },
    { level: 2, verb: 'Understand', color: '#3b82f6', desc: 'Explain ideas in your own words' },
    { level: 3, verb: 'Apply', color: '#f59e0b', desc: 'Use information in new situations' },
    { level: 4, verb: 'Analyze', color: '#f97316', desc: 'Draw connections and relationships' },
    { level: 5, verb: 'Evaluate', color: '#10b981', desc: 'Justify decisions and critique ideas' },
    { level: 6, verb: 'Create', color: '#8b5cf6', desc: 'Produce new work from learned concepts' },
];

const QUIZ_STATES = { IDLE: 'idle', LOADING: 'loading', PLAYING: 'playing', FINISHED: 'finished', ERROR: 'error' };

// ── Components ────────────────────────────────────────────────────────────────
function BloomBadge({ level }) {
    const info = BLOOM_INFO[level - 1] || BLOOM_INFO[0];
    return (
        <span className={styles.bloomBadge} style={{ background: `${info.color}15`, color: info.color, borderColor: `${info.color}25` }}>
            <Brain size={10} /> L{level} — {info.verb}
        </span>
    );
}

function BloomLadder({ current }) {
    return (
        <div className={styles.bloomLadder}>
            {BLOOM_INFO.map(b => (
                <div key={b.level} className={`${styles.bloomRung} ${b.level <= current ? styles.bloomActive : ''} ${b.level === current ? styles.bloomCurrent : ''}`}>
                    <div className={styles.bloomRungDot} style={{ '--bc': b.color }} />
                    <span className={styles.bloomRungLabel}>{b.verb}</span>
                    {b.level === current && <span className={styles.bloomYouAreHere}>← you</span>}
                </div>
            ))}
        </div>
    );
}

// ── Quiz Player ───────────────────────────────────────────────────────────────
function QuizPlayer({ subject, topic, bloomLevel, onBack }) {
    const [state, setState] = useState(QUIZ_STATES.LOADING);
    const [quizData, setQuizData] = useState(null);
    const [idx, setIdx] = useState(0);
    const [selected, setSelected] = useState(null);
    const [score, setScore] = useState(0);
    const [answers, setAnswers] = useState([]);
    const [error, setError] = useState(null);

    async function fetchQuiz() {
        setState(QUIZ_STATES.LOADING);
        setIdx(0); setSelected(null); setScore(0); setAnswers([]);
        try {
            const data = await generateQuiz({ subject, topic, bloom_level: bloomLevel });
            setQuizData(data);
            setState(QUIZ_STATES.PLAYING);
        } catch (e) {
            setError(e.message || 'Failed to load quiz');
            setState(QUIZ_STATES.ERROR);
        }
    }

    useEffect(() => { fetchQuiz(); }, [subject, topic, bloomLevel]);

    const q = quizData?.questions?.[idx];

    function handleAnswer(optIdx) {
        if (selected !== null) return;
        setSelected(optIdx);
        const correct = optIdx === q.answer_index;
        if (correct) setScore(s => s + 1);
        setAnswers(a => [...a, { q: q.question, correct, chosen: q.options[optIdx], right: q.options[q.answer_index] }]);
    }

    function nextQuestion() {
        if (idx + 1 >= quizData.total) setState(QUIZ_STATES.FINISHED);
        else { setIdx(i => i + 1); setSelected(null); }
    }

    const pct = quizData ? Math.round((score / quizData.total) * 100) : 0;
    const color = pct >= 80 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#ef4444';

    if (state === QUIZ_STATES.LOADING) return (
        <div className={styles.quizCenter}>
            <Loader2 size={32} className={styles.spinner} />
            <p>Generating <strong>{topic}</strong> quiz...</p>
            <span className={styles.quizSub}>Groq LLaMA-70B · Bloom L{bloomLevel}</span>
        </div>
    );

    if (state === QUIZ_STATES.ERROR) return (
        <div className={styles.quizCenter}>
            <span className={styles.errorIcon}>⚠️</span>
            <p>{error}</p>
            <button className={styles.retryBtn} onClick={fetchQuiz}>Retry</button>
        </div>
    );

    if (state === QUIZ_STATES.FINISHED) return (
        <div className={styles.resultsCard}>
            <div className={styles.resultsTrophy}>
                <Trophy size={40} style={{ color }} />
                <div className={styles.resultsScore} style={{ color }}>{score}/{quizData.total}</div>
                <div className={styles.resultsPct}>{pct}%</div>
            </div>
            <div className={styles.resultsMeta}>
                <span>
                    {pct >= 80 ? `🎉 Excellent! You're ready for Bloom L${Math.min(6, bloomLevel + 1)}.`
                        : pct >= 50 ? '📈 Good effort. Review weak areas below.'
                            : '📚 Review this topic before moving on.'}
                </span>
            </div>
            <div className={styles.reviewList}>
                {answers.map((a, i) => (
                    <div key={i} className={`${styles.reviewRow} ${a.correct ? styles.reviewCorrect : styles.reviewWrong}`}>
                        <span className={styles.reviewIcon}>{a.correct ? '✓' : '✗'}</span>
                        <div className={styles.reviewText}>
                            <span className={styles.reviewQ}>{a.q}</span>
                            {!a.correct && <span className={styles.reviewAns}>Correct: {a.right}</span>}
                        </div>
                    </div>
                ))}
            </div>
            <div className={styles.resultsActions}>
                <button className={styles.btnSecondary} onClick={fetchQuiz}><RotateCcw size={14} /> Retake</button>
                <button className={styles.btnPrimary} onClick={onBack}>← Back to Topics</button>
            </div>
        </div>
    );

    return (
        <div className={styles.quizActiveCard}>
            <div className={styles.quizProgressBar}>
                <div className={styles.quizProgressFill} style={{ width: `${(idx / quizData.total) * 100}%` }} />
            </div>
            <div className={styles.quizMeta}>
                <span className={styles.quizCounter}>Question {idx + 1} of {quizData.total}</span>
                <BloomBadge level={bloomLevel} />
                <span className={styles.scoreChip}>Score: {score}/{idx}</span>
            </div>
            <h2 className={styles.quizQuestion}>{q?.question}</h2>
            <div className={styles.optionsGrid}>
                {q?.options?.map((opt, i) => {
                    let cls = styles.option;
                    if (selected !== null) {
                        if (i === q.answer_index) cls += ` ${styles.optionCorrect}`;
                        else if (i === selected && i !== q.answer_index) cls += ` ${styles.optionWrong}`;
                        else cls += ` ${styles.optionDimmed}`;
                    }
                    return (
                        <button key={i} className={cls} onClick={() => handleAnswer(i)} disabled={selected !== null}>
                            <span className={styles.optionLetter}>{String.fromCharCode(65 + i)}</span>
                            <span>{opt}</span>
                            {selected !== null && i === q.answer_index && <CheckCircle size={16} className={styles.checkIcon} />}
                        </button>
                    );
                })}
            </div>
            {selected !== null && (
                <div className={`${styles.explanationBox} ${selected === q.answer_index ? styles.explCorrect : styles.explWrong}`}>
                    <strong>{selected === q.answer_index ? '✓ Correct!' : '✗ Incorrect'}</strong>
                    <p>{q?.explanation}</p>
                    <button className={styles.nextBtn} onClick={nextQuestion}>
                        {idx + 1 < quizData.total ? 'Next →' : 'See Results →'}
                    </button>
                </div>
            )}
        </div>
    );
}

// ── Main Learning Page ────────────────────────────────────────────────────────
export default function Learning() {
    const [subjects, setSubjects] = useState([]);
    const [topicsBySubject, setTopicsBySubject] = useState({});
    const [loading, setLoading] = useState(true);
    const [mastery, setMastery] = useState({ topics: [], attempts: [] });
    const [masteryLoading, setMasteryLoading] = useState(true);
    const [selectedSubject, setSelectedSubject] = useState(null);
    const [selectedTopic, setSelectedTopic] = useState(null);
    const [viewMode, setViewMode] = useState('learn');

    // Load real subjects from ERP profile
    useEffect(() => {
        getStudentProfile()
            .then(data => {
                const subs = (data.subjects || []).map(s => ({
                    ...s,
                    bloomLevel: s.bloom_level ?? s.bloomLevel ?? 1,
                }));
                setSubjects(subs);
                if (subs.length > 0) {
                    // Default to first at-risk subject
                    const atRisk = subs.find(s => s.status === 'risk') || subs[0];
                    setSelectedSubject(atRisk);
                }
            })
            .catch(() => {
                // Fallback — empty, user sees empty state
            })
            .finally(() => setLoading(false));

        getMyMastery()
            .then(data => setMastery({ topics: data.topics || [], attempts: data.attempts || [] }))
            .catch(() => setMastery({ topics: [], attempts: [] }))
            .finally(() => setMasteryLoading(false));

        getTutorOptions()
            .then(data => setTopicsBySubject(data.topics_by_subject || {}))
            .catch(() => setTopicsBySubject({}));
    }, []);

    const topics = selectedSubject ? (topicsBySubject[selectedSubject.code] || []) : [];
    const masteryTopics = selectedSubject
        ? (mastery.topics || []).filter(t => t.subject_code === selectedSubject.code)
        : [];

    if (loading) return <LearningSkeleton />;

    return (
        <div className={styles.layout}>
            {/* Subject sidebar */}
            <aside className={styles.subjectPanel}>
                <h2 className={styles.panelTitle}><BookOpen size={14} /> Subjects</h2>
                {subjects.length === 0 && (
                    <p className={styles.emptyMsg}>No subjects loaded</p>
                )}
                {subjects.map((s, i) => {
                    const bloom = BLOOM_INFO[(s.bloomLevel ?? 1) - 1];
                    return (
                        <button key={i}
                            className={`${styles.subjectItem} ${selectedSubject?.code === s.code ? styles.subjectActive : ''}`}
                            onClick={() => { setSelectedSubject(s); setSelectedTopic(null); setViewMode('learn'); }}>
                            <div className={styles.subjectItemLeft}>
                                <div className={styles.subjectNameRow}>
                                    <span className={styles.subjectName}>{s.name}</span>
                                    {s.status === 'risk' && <AlertTriangle size={11} className={styles.riskIcon} />}
                                </div>
                                {/* Bloom progress blocks */}
                                <div className={styles.bloomBlocks}>
                                    {[1, 2, 3, 4, 5, 6].map(l => (
                                        <div key={l} className={`${styles.bloomBlock} ${l <= (s.bloomLevel ?? 1) ? styles.bloomFilled : ''}`}
                                            style={l <= (s.bloomLevel ?? 1) ? { '--bc': bloom?.color } : {}} />
                                    ))}
                                </div>
                            </div>
                            <div className={styles.subjectRight}>
                                <span className={`${styles.statusPill} ${styles['status_' + s.status]}`}>
                                    {s.attendance ?? s.live_attendance ?? '—'}%
                                </span>
                                <span className={styles.bloomIndicator} style={{ color: bloom?.color }}>L{s.bloomLevel ?? 1}</span>
                            </div>
                        </button>
                    );
                })}

                {/* Live stats summary */}
                {subjects.length > 0 && (
                    <div className={styles.sideStats}>
                        <div className={styles.sideStat}>
                            <TrendingUp size={11} />
                            <span>{subjects.filter(s => s.status === 'safe').length} safe</span>
                        </div>
                        <div className={styles.sideStat}>
                            <AlertTriangle size={11} style={{ color: '#ef4444' }} />
                            <span style={{ color: '#ef4444' }}>{subjects.filter(s => s.status === 'risk').length} at risk</span>
                        </div>
                        <div className={styles.sideStat}>
                            <Layers size={11} />
                            <span>Avg Bloom: {Math.round(subjects.reduce((a, b) => a + (b.bloomLevel ?? 1), 0) / subjects.length * 10) / 10}</span>
                        </div>
                    </div>
                )}
            </aside>

            {/* Main content */}
            <div className={styles.content}>
                {!selectedSubject ? (
                    <div className={styles.emptyContent}>
                        <Brain size={36} style={{ color: 'var(--accent)', opacity: 0.4 }} />
                        <p>Select a subject to begin</p>
                    </div>
                ) : !selectedTopic ? (
                    /* Topic grid */
                    <div className={styles.topicPicker}>
                        <div className={styles.subjectHeader}>
                            <div>
                                <span className={styles.sectionLabel}>📚 {selectedSubject.name}</span>
                                <h1 className={styles.subjectTitle}>Choose a Topic</h1>
                                <p className={styles.subjectSub}>AI quiz calibrated to your <strong>Bloom L{selectedSubject.bloomLevel ?? 1} — {BLOOM_INFO[(selectedSubject.bloomLevel ?? 1) - 1]?.verb}</strong></p>
                            </div>
                            <BloomBadge level={selectedSubject.bloomLevel ?? 1} />
                        </div>

                        {/* Bloom ladder panel */}
                        <div className={styles.bloomPanel}>
                            <span className={styles.bloomPanelTitle}>Your Bloom Journey</span>
                            <BloomLadder current={selectedSubject.bloomLevel ?? 1} />
                        </div>

                        {/* Learning Intelligence: topic mastery summary */}
                        <div className={styles.masteryPanel}>
                            <span className={styles.masteryTitle}>Learning Intelligence</span>
                            {masteryLoading ? (
                                <p className={styles.masteryHint}>Analyzing your quiz and topic history…</p>
                            ) : masteryTopics.length === 0 ? (
                                <p className={styles.masteryHint}>
                                    Start taking quizzes to see topic-wise strengths and revision suggestions here.
                                </p>
                            ) : (
                                <div className={styles.masteryList}>
                                    {masteryTopics.slice(0, 5).map((m, i) => {
                                        const strong = m.achieved || m.avg_score >= 0.75;
                                        return (
                                            <div key={i} className={styles.masteryRow}>
                                                <span className={styles.masteryDot} style={{ background: strong ? '#10b981' : '#f59e0b' }} />
                                                <span className={styles.masteryTopic}>{m.topic || 'Unit concept'}</span>
                                                <span className={styles.masteryMeta}>
                                                    L{m.bloom_level} · {(m.avg_score * 100).toFixed(0)}%
                                                    {!strong && ' • needs revision'}
                                                </span>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>

                        <div className={styles.topicGrid}>
                            {topics.map((topic, i) => (
                                <div key={i} className={styles.topicCard}
                                    onClick={() => { setSelectedTopic(topic); setViewMode('learn'); }}>
                                    <div className={styles.topicCardHeader}>
                                        <span className={styles.topicNum}>{String(i + 1).padStart(2, '0')}</span>
                                        <span className={styles.topicName}>{topic}</span>
                                        <ChevronRight size={16} className={styles.topicArrow} />
                                    </div>
                                    <div className={styles.topicCardFooter}>
                                        <span className={styles.topicQuizTag}><Zap size={10} /> AI Quiz</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                ) : (
                    /* Topic detail */
                    <div className={styles.topicView}>
                        <div className={styles.topicViewHeader}>
                            <button className={styles.backBtn} onClick={() => setSelectedTopic(null)}>← Back</button>
                            <div className={styles.topicMeta}>
                                <span className={styles.topicViewName}>{selectedTopic}</span>
                                <BloomBadge level={selectedSubject.bloomLevel ?? 1} />
                            </div>
                            <div className={styles.viewToggle}>
                                <button className={`${styles.toggleBtn} ${viewMode === 'learn' ? styles.toggleActive : ''}`}
                                    onClick={() => setViewMode('learn')}>📖 Learn</button>
                                <button className={`${styles.toggleBtn} ${viewMode === 'quiz' ? styles.toggleActive : ''}`}
                                    onClick={() => setViewMode('quiz')}>
                                    <Zap size={12} /> AI Quiz
                                </button>
                            </div>
                        </div>

                        {viewMode === 'learn' ? (
                            <div className={styles.learnPanel}>
                                <div className={styles.learnHero}>
                                    <h2>{selectedTopic}</h2>
                                    <p>Ask the Mentor to explain this topic, then test yourself. Quiz difficulty adapts to your <strong>Bloom L{selectedSubject.bloomLevel ?? 1}</strong>.</p>
                                    <div className={styles.learnActions}>
                                        <Link to={`/chat?q=${encodeURIComponent(`explain ${selectedTopic} in ${selectedSubject.name}`)}`} className={styles.chatLink}>
                                            💬 Ask Mentor to explain {selectedTopic}
                                        </Link>
                                        <button className={styles.quizStartBtn} onClick={() => setViewMode('quiz')}>
                                            <Zap size={14} /> Start AI Quiz
                                        </button>
                                    </div>
                                </div>
                                <div className={styles.learnStats}>
                                    <div className={styles.statRow}><Brain size={14} /><span>Bloom L{selectedSubject.bloomLevel ?? 1} questions</span></div>
                                    <div className={styles.statRow}><Clock size={14} /><span>~3 minutes · 5 questions</span></div>
                                    <div className={styles.statRow}><Zap size={14} /><span>Generated by Groq LLaMA-70B</span></div>
                                </div>
                            </div>
                        ) : (
                            <QuizPlayer
                                subject={selectedSubject.name}
                                topic={selectedTopic}
                                bloomLevel={selectedSubject.bloomLevel ?? 1}
                                onBack={() => { setSelectedTopic(null); setViewMode('learn'); }}
                            />
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
