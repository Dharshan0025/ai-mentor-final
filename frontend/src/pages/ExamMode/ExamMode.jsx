/**
 * ExamMode — Phase 4 V6 Classroom Experience
 * Timed MCQ quiz with countdown, score report, and SM-2 update.
 *
 * Flow:
 *  1. Config screen: choose subject, question count (5/10/20), time limit
 *  2. Timed quiz: countdown timer, one question at a time, progress bar
 *  3. Score report: % correct, time taken, per-question review, XP awarded
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Timer, CheckCircle, XCircle, Trophy, RotateCcw, BookOpen, Zap } from 'lucide-react';
import styles from './ExamMode.module.css';
import { generateExamQuiz, recordCheckpointMemory, awardXp } from '../../services/api';
import XpToast from '../../components/XpToast/XpToast';

const TIME_LIMITS = [
    { label: '5 min', value: 300 },
    { label: '10 min', value: 600 },
    { label: '15 min', value: 900 },
    { label: 'No limit', value: 0 },
];

const QUESTION_COUNTS = [5, 10, 20];

export default function ExamMode() {
    const navigate = useNavigate();

    // Config state
    const [phase, setPhase] = useState('config');   // config | quiz | result
    const [subjects, setSubjects] = useState([]);
    const [selSubject, setSelSubject] = useState(null);
    const [selTopic, setSelTopic] = useState('');
    const [qCount, setQCount] = useState(10);
    const [timeLimit, setTimeLimit] = useState(600);
    const [loadErr, setLoadErr] = useState('');

    // Quiz state
    const [questions, setQuestions] = useState([]);
    const [current, setCurrent] = useState(0);
    const [answers, setAnswers] = useState([]);       // { selected, correct, time_ms }
    const [timeLeft, setTimeLeft] = useState(0);
    const [loading, setLoading] = useState(false);
    const [startedAt, setStartedAt] = useState(null);
    const questionStartRef = useRef(null);
    const timerRef = useRef(null);

    // XP toast
    const [xpToast, setXpToast] = useState(null);

    // Load subjects on mount
    useEffect(() => {
        import('../../services/api').then(({ getTutorOptions }) =>
            getTutorOptions().then(d => setSubjects(d.subjects || [])).catch(() => { })
        );
    }, []);

    // Countdown timer
    useEffect(() => {
        if (phase !== 'quiz' || timeLimit === 0) return;
        timerRef.current = setInterval(() => {
            setTimeLeft(t => {
                if (t <= 1) { clearInterval(timerRef.current); finishExam(); return 0; }
                return t - 1;
            });
        }, 1000);
        return () => clearInterval(timerRef.current);
    }, [phase]);

    const startExam = useCallback(async () => {
        if (!selSubject) { setLoadErr('Please select a subject'); return; }
        setLoadErr(''); setLoading(true);
        try {
            const data = await generateExamQuiz({
                subject: selSubject.code,
                topic: selTopic || selSubject.name,
                bloom_level: selSubject.bloomLevel || 2,
                count: qCount,
            });
            setQuestions(data.questions || []);
            setPhase('quiz');
            setTimeLeft(timeLimit);
            setStartedAt(Date.now());
            setCurrent(0);
            setAnswers([]);
            questionStartRef.current = Date.now();
        } catch (e) {
            setLoadErr(e.response?.data?.detail || 'Failed to generate questions');
        } finally {
            setLoading(false);
        }
    }, [selSubject, selTopic, qCount, timeLimit]);

    const handleAnswer = useCallback((optionIndex) => {
        const q = questions[current];
        const timeTaken = Date.now() - (questionStartRef.current || Date.now());
        const isCorrect = optionIndex === q.correct_index;
        const newAnswers = [...answers, {
            question: q.question,
            selected: optionIndex,
            correct: q.correct_index,
            is_correct: isCorrect,
            time_ms: timeTaken,
            options: q.options,
        }];
        setAnswers(newAnswers);

        // Move to next or finish
        if (current + 1 < questions.length) {
            setCurrent(p => p + 1);
            questionStartRef.current = Date.now();
        } else {
            clearInterval(timerRef.current);
            finishExamWith(newAnswers);
        }
    }, [questions, current, answers]);

    const finishExam = () => finishExamWith(answers);

    const finishExamWith = useCallback(async (finalAnswers) => {
        setPhase('result');
        const correct = finalAnswers.filter(a => a.is_correct).length;
        const total = questions.length;
        const isPerfect = correct === total;

        // Award XP (non-blocking)
        try {
            const action = isPerfect ? 'exam_perfect' : 'exam_complete';
            const xpData = await awardXp({ action, metadata: { subject_code: selSubject?.code } });
            if (xpData?.xp_gained) {
                setXpToast({ xp: xpData.xp_gained, action: isPerfect ? 'Perfect Exam! 🎯' : 'Exam Complete!', badges: xpData.badges_earned || [] });
            }
        } catch { }

        // Record checkpoint memory for wrong answers (non-blocking, parallel)
        finalAnswers.forEach(a => {
            if (!a.is_correct) {
                recordCheckpointMemory({
                    subject_code: selSubject?.code || '',
                    topic: selTopic || selSubject?.name || '',
                    question: a.question,
                    question_type: 'mcq',
                    student_answer: a.options?.[a.selected] || '',
                    correct_answer: a.options?.[a.correct] || '',
                    is_correct: false,
                    score: 0,
                    response_time_ms: a.time_ms,
                    bloom_level: selSubject?.bloomLevel || 2,
                }).catch(() => { });
            }
        });
    }, [questions, selSubject, selTopic]);

    const formatTime = (secs) => {
        const m = Math.floor(secs / 60);
        const s = secs % 60;
        return `${m}:${s.toString().padStart(2, '0')}`;
    };

    const scorePct = answers.length ? Math.round((answers.filter(a => a.is_correct).length / questions.length) * 100) : 0;
    const totalTime = startedAt ? Math.round((Date.now() - startedAt) / 1000) : 0;
    const timePct = timeLimit > 0 ? Math.round((timeLeft / timeLimit) * 100) : 100;

    // ── CONFIG SCREEN ────────────────────────────────────────────────────────
    if (phase === 'config') return (
        <div className={styles.page}>
            <div className={styles.configCard}>
                <div className={styles.configHeader}>
                    <Timer size={28} className={styles.headerIcon} />
                    <div>
                        <h1 className={styles.configTitle}>Exam Mode</h1>
                        <p className={styles.configSub}>Test your knowledge with a timed quiz</p>
                    </div>
                </div>

                <div className={styles.configSection}>
                    <label className={styles.configLabel}>Subject</label>
                    <div className={styles.subjectGrid}>
                        {subjects.map(s => (
                            <button
                                key={s.code}
                                className={`${styles.subjectBtn} ${selSubject?.code === s.code ? styles.active : ''}`}
                                onClick={() => setSelSubject(s)}
                            >
                                <BookOpen size={14} />
                                <span>{s.name}</span>
                            </button>
                        ))}
                    </div>
                </div>

                <div className={styles.configSection}>
                    <label className={styles.configLabel}>Questions</label>
                    <div className={styles.pillRow}>
                        {QUESTION_COUNTS.map(n => (
                            <button
                                key={n}
                                className={`${styles.pill} ${qCount === n ? styles.pillActive : ''}`}
                                onClick={() => setQCount(n)}
                            >{n} Q</button>
                        ))}
                    </div>
                </div>

                <div className={styles.configSection}>
                    <label className={styles.configLabel}>Time Limit</label>
                    <div className={styles.pillRow}>
                        {TIME_LIMITS.map(t => (
                            <button
                                key={t.value}
                                className={`${styles.pill} ${timeLimit === t.value ? styles.pillActive : ''}`}
                                onClick={() => setTimeLimit(t.value)}
                            >{t.label}</button>
                        ))}
                    </div>
                </div>

                {loadErr && <p className={styles.error}>{loadErr}</p>}
                <button className={styles.startBtn} onClick={startExam} disabled={loading || !selSubject}>
                    {loading ? 'Generating…' : '⚡ Start Exam'}
                </button>
            </div>
        </div>
    );

    // ── QUIZ SCREEN ──────────────────────────────────────────────────────────
    if (phase === 'quiz') {
        const q = questions[current];
        return (
            <div className={styles.page}>
                <div className={styles.quizCard}>
                    {/* Header bar */}
                    <div className={styles.quizHeader}>
                        <span className={styles.qProgress}>{current + 1} / {questions.length}</span>
                        {timeLimit > 0 && (
                            <span className={`${styles.timer} ${timeLeft < 60 ? styles.timerWarn : ''}`}>
                                <Timer size={14} /> {formatTime(timeLeft)}
                            </span>
                        )}
                    </div>

                    {/* Progress bar */}
                    <div className={styles.progressBar}>
                        <div className={styles.progressFill} style={{ width: `${((current) / questions.length) * 100}%` }} />
                    </div>

                    {/* Question */}
                    <p className={styles.question}>{q?.question}</p>

                    {/* Options */}
                    <div className={styles.options}>
                        {(q?.options || []).map((opt, i) => (
                            <button
                                key={i}
                                className={styles.option}
                                onClick={() => handleAnswer(i)}
                            >
                                <span className={styles.optionLetter}>{String.fromCharCode(65 + i)}</span>
                                <span>{opt}</span>
                            </button>
                        ))}
                    </div>

                    <button className={styles.skipBtn} onClick={() => handleAnswer(-1)}>Skip →</button>
                </div>
            </div>
        );
    }

    // ── RESULT SCREEN ────────────────────────────────────────────────────────
    const correct = answers.filter(a => a.is_correct).length;
    return (
        <div className={styles.page}>
            {xpToast && <XpToast {...xpToast} onDone={() => setXpToast(null)} />}
            <div className={styles.resultCard}>
                <div className={styles.scoreRing}>
                    <svg viewBox="0 0 120 120" className={styles.ringsvg}>
                        <circle cx="60" cy="60" r="50" fill="none" stroke="var(--border)" strokeWidth="10" />
                        <circle
                            cx="60" cy="60" r="50" fill="none"
                            stroke={scorePct >= 80 ? 'var(--safe)' : scorePct >= 50 ? 'var(--watch)' : 'var(--risk)'}
                            strokeWidth="10"
                            strokeLinecap="round"
                            strokeDasharray={`${(scorePct / 100) * 314} 314`}
                            transform="rotate(-90 60 60)"
                        />
                    </svg>
                    <div className={styles.scoreLabel}>{scorePct}%</div>
                </div>

                <h2 className={styles.resultTitle}>
                    {scorePct === 100 ? '🎯 Perfect Score!' : scorePct >= 80 ? '🏆 Excellent!' : scorePct >= 50 ? '📚 Keep Going!' : '💪 Not Yet — Review!'}
                </h2>
                <p className={styles.resultSub}>
                    {correct} / {questions.length} correct · {formatTime(totalTime)} taken
                </p>

                {/* Per-question review */}
                <div className={styles.reviewList}>
                    {answers.map((a, i) => (
                        <div key={i} className={`${styles.reviewItem} ${a.is_correct ? styles.correct : styles.wrong}`}>
                            {a.is_correct ? <CheckCircle size={14} /> : <XCircle size={14} />}
                            <div className={styles.reviewContent}>
                                <p className={styles.reviewQ}>{a.question}</p>
                                {!a.is_correct && (
                                    <p className={styles.reviewAns}>
                                        ✓ {a.options?.[a.correct]} &nbsp;·&nbsp;
                                        ✗ {a.selected >= 0 ? a.options?.[a.selected] : 'Skipped'}
                                    </p>
                                )}
                            </div>
                        </div>
                    ))}
                </div>

                <div className={styles.resultBtns}>
                    <button className={styles.retryBtn} onClick={() => { setPhase('config'); setAnswers([]); }}>
                        <RotateCcw size={16} /> Try Again
                    </button>
                    <button className={styles.homeBtn} onClick={() => navigate('/tutor')}>
                        <BookOpen size={16} /> Go to Tutor
                    </button>
                </div>
            </div>
        </div>
    );
}
