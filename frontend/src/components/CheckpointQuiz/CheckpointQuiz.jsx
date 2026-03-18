/**
 * CheckpointQuiz — Interactive checkpoint quiz overlay (V4 upgrade)
 * - MCQ (client-side) + short-answer (LLM-evaluated)
 * - response_time_ms tracked from question mount
 * - Records checkpoint attempt to SM-2 memory via /checkpoint/record
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import { CheckCircle2, XCircle, Loader2, ChevronRight, SkipForward, Clock } from 'lucide-react';
import { evaluateCheckpoint, recordCheckpointMemory } from '../../services/api';
import styles from './CheckpointQuiz.module.css';

export default function CheckpointQuiz({
    checkpoint,
    subjectCode,
    sessionId,
    onPass,
    onSkip,
    onWrong,        // V4: called with topic string when answer is incorrect
}) {
    const { question, type, options = [], correct_index, explanation, after_step } = checkpoint;

    const [selected, setSelected] = useState(null);
    const [shortAnswer, setShortAnswer] = useState('');
    const [submitted, setSubmitted] = useState(false);
    const [result, setResult] = useState(null);
    const [loading, setLoading] = useState(false);
    const [elapsed, setElapsed] = useState(0);       // seconds shown to student

    const topic = checkpoint.topic || '';
    const bloomLevel = checkpoint.bloom_level || 2;

    // Timer — tracks time since question mounted
    const startTime = useRef(Date.now());
    const intervalId = useRef(null);

    // ── V8 Hesitation Tracking ───────────────────────────────────────────────
    const firstKeyTime = useRef(null);  // ms from mount to first keystroke
    const totalKeys = useRef(0);     // total keystrokes (incl. backspace)
    const backspaces = useRef(0);     // backspace count
    const lastKeyTime = useRef(null);  // for pause detection
    const pauseCount = useRef(0);     // pauses >1500ms

    const handleKeyEvent = useCallback((e) => {
        const now = Date.now();
        if (!firstKeyTime.current) firstKeyTime.current = now;  // blank stare ends
        if (lastKeyTime.current && now - lastKeyTime.current > 1500) pauseCount.current += 1;
        totalKeys.current += 1;
        if (e.key === 'Backspace' || e.key === 'Delete') backspaces.current += 1;
        lastKeyTime.current = now;
    }, []);

    useEffect(() => {
        startTime.current = Date.now();
        intervalId.current = setInterval(() => {
            setElapsed(Math.floor((Date.now() - startTime.current) / 1000));
        }, 1000);
        return () => clearInterval(intervalId.current);
    }, []);

    const handleMcqSelect = useCallback((idx) => {
        if (submitted) return;
        setSelected(idx);
    }, [submitted]);

    const handleSubmit = useCallback(async () => {
        if (loading || submitted) return;
        clearInterval(intervalId.current);
        const responseMs = Date.now() - startTime.current;

        // ── Build hesitation_data ──────────────────────────────────────────
        const blankStareMs = firstKeyTime.current
            ? firstKeyTime.current - startTime.current
            : responseMs; // never typed = full time = blanked out
        const wordCount = shortAnswer.trim().split(/\s+/).filter(Boolean).length || 1;
        const delRatio = totalKeys.current > 0
            ? Math.min(1, backspaces.current / totalKeys.current)
            : 0;
        const hesScore = Math.min(100, Math.round(
            (delRatio * 35) +
            (Math.min(pauseCount.current, 5) / 5 * 35) +
            (Math.min(blankStareMs, 15000) / 15000 * 30)
        ));
        const hesitation_data = {
            hesitation_score: hesScore,
            deletion_ratio: parseFloat(delRatio.toFixed(2)),
            pause_count: pauseCount.current,
            blank_stare_ms: blankStareMs,
            total_keystrokes: totalKeys.current,
            backspace_count: backspaces.current,
        };

        setLoading(true);

        try {
            let res;
            const studentAns = type === 'mcq' ? (options[selected] || '') : shortAnswer;

            if (type === 'mcq') {
                res = await evaluateCheckpoint({
                    question,
                    student_answer: studentAns,
                    correct_answer: explanation,
                    subject_code: subjectCode,
                    topic,
                    question_type: 'mcq',
                    correct_index,
                    selected_index: selected ?? -1,
                    session_id: sessionId,
                    hesitation_data,    // V8 behavioral data
                });
            } else {
                res = await evaluateCheckpoint({
                    question,
                    student_answer: studentAns,
                    correct_answer: explanation,
                    subject_code: subjectCode,
                    topic,
                    question_type: 'short',
                    session_id: sessionId,
                    hesitation_data,    // V8 behavioral data
                });
            }

            setResult(res);
            setSubmitted(true);

            // ── SM-2 memory record (non-blocking, best-effort) ──────────────
            recordCheckpointMemory({
                subject_code: subjectCode,
                topic,
                question,
                question_type: type,
                student_answer: studentAns,
                correct_answer: explanation || (options[correct_index] || ''),
                is_correct: !!res?.correct,
                score: res?.score ?? (res?.correct ? 1.0 : 0.0),
                feedback: res?.feedback || '',
                response_time_ms: responseMs,
                bloom_level: bloomLevel,
                after_step,
                session_id: sessionId,
            }).catch(console.warn); // never block lesson flow on memory errors

            // ── Confusion detection callback ─────────────────────────────────
            if (!res?.correct && topic && onWrong) {
                onWrong(topic);
            }

            if (res?.correct) {
                setTimeout(() => onPass(), 1800);
            }
        } catch {
            setResult({ correct: false, feedback: 'Could not evaluate your answer. You may proceed.', unlock_next: true });
            setSubmitted(true);
        } finally {
            setLoading(false);
        }
    }, [loading, submitted, type, question, options, selected, shortAnswer,
        correct_index, explanation, subjectCode, topic, sessionId, onPass,
        after_step, bloomLevel]);

    const canSubmit = type === 'mcq' ? selected !== null : shortAnswer.trim().length > 0;

    return (
        <div className={styles.overlay}>
            <div className={styles.card}>
                {/* Header */}
                <div className={styles.header}>
                    <div className={styles.pulse} />
                    <span className={styles.badge}>Checkpoint — After Step {after_step}</span>

                    {/* Live timer */}
                    <span className={styles.timer}>
                        <Clock size={11} />
                        {elapsed}s
                    </span>

                    <button className={styles.skipBtn} onClick={onSkip} title="Skip this checkpoint">
                        <SkipForward size={13} /> Skip
                    </button>
                </div>

                {/* Question */}
                <p className={styles.question}>{question}</p>

                {/* MCQ */}
                {type === 'mcq' && (
                    <div className={styles.options}>
                        {options.map((opt, i) => {
                            let cls = styles.option;
                            if (submitted) {
                                if (i === correct_index) cls += ` ${styles.optionCorrect}`;
                                else if (i === selected) cls += ` ${styles.optionWrong}`;
                            } else if (i === selected) cls += ` ${styles.optionSelected}`;
                            return (
                                <button key={i} className={cls} onClick={() => handleMcqSelect(i)} disabled={submitted}>
                                    <span className={styles.optionLetter}>{String.fromCharCode(65 + i)}</span>
                                    <span>{opt}</span>
                                    {submitted && i === correct_index && <CheckCircle2 size={14} className={styles.iconCorrect} />}
                                    {submitted && i === selected && i !== correct_index && <XCircle size={14} className={styles.iconWrong} />}
                                </button>
                            );
                        })}
                    </div>
                )}

                {/* Short answer */}
                {type === 'short' && (
                    <textarea
                        className={styles.textarea}
                        placeholder="Type your answer here…"
                        value={shortAnswer}
                        onChange={e => setShortAnswer(e.target.value)}
                        onKeyDown={handleKeyEvent}
                        disabled={submitted}
                        rows={3}
                    />
                )}

                {/* Feedback */}
                {result && (
                    <div className={`${styles.feedback} ${result.correct ? styles.feedbackPass : styles.feedbackFail}`}>
                        {result.correct ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
                        <span>{result.feedback}</span>
                    </div>
                )}

                {/* SM-2 update badge */}
                {result && submitted && (
                    <div className={styles.sm2Badge}>
                        {result.correct
                            ? `✅ Great! Memory updated — next review scheduled`
                            : `🔁 Topic flagged for earlier review`}
                    </div>
                )}

                {/* Actions */}
                {!submitted && (
                    <button
                        className={styles.submitBtn}
                        onClick={handleSubmit}
                        disabled={!canSubmit || loading}
                    >
                        {loading
                            ? <><Loader2 size={14} className={styles.spin} /> Evaluating…</>
                            : <>Submit Answer <ChevronRight size={14} /></>}
                    </button>
                )}

                {submitted && !result?.correct && (
                    <button className={styles.continueBtn} onClick={onPass}>
                        Continue anyway <ChevronRight size={14} />
                    </button>
                )}
            </div>
        </div>
    );
}
