/**
 * VoiceQuiz — Voice-driven quiz mode (Phase 7 V3)
 * Reads MCQ questions aloud via TTS, captures voice answer via STT
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import { Mic, MicOff, Volume2, ChevronRight, CheckCircle2, XCircle, Loader2, Square } from 'lucide-react';
import styles from './VoiceQuiz.module.css';

const PERSONALITY_RATE = { professor: 0.85, coach: 1.1, friend: 0.95 };
const PERSONALITY_PITCH = { professor: 0.9, coach: 1.1, friend: 1.05 };

function speak(text, personality, rate = 1.0) {
    return new Promise((resolve) => {
        window.speechSynthesis.cancel();
        const u = new SpeechSynthesisUtterance(text);
        const voices = window.speechSynthesis.getVoices();
        u.voice = voices.find(v => v.lang.startsWith('en') && v.localService) || voices[0];
        u.rate = (PERSONALITY_RATE[personality] ?? 1.0) * rate;
        u.pitch = PERSONALITY_PITCH[personality] ?? 1.0;
        u.onend = resolve;
        u.onerror = resolve;
        window.speechSynthesis.speak(u);
    });
}

function browserSTT(onResult) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return null;
    const r = new SR();
    r.continuous = false;
    r.interimResults = false;
    r.lang = 'en-US';
    r.onresult = e => onResult(e.results[0][0].transcript);
    r.onerror = () => onResult('');
    r.start();
    return r;
}

export default function VoiceQuiz({ questions = [], personality = 'professor', speedRate = 1.0, onClose }) {
    const [qIndex, setQIndex]   = useState(0);
    const [phase, setPhase]     = useState('intro');   // intro | reading | listening | result | done
    const [transcript, setTx]   = useState('');
    const [result, setResult]   = useState(null);       // { correct, expected }
    const [score, setScore]     = useState({ correct: 0, total: 0 });
    const stRef = useRef(null);

    const q = questions[qIndex];

    const readQuestion = useCallback(async () => {
        if (!q) return;
        setPhase('reading');
        const optText = q.options?.length
            ? ` Options: ${q.options.map((o, i) => `${String.fromCharCode(65+i)}: ${o}`).join('. ')}`
            : '';
        await speak(`Question ${qIndex + 1}. ${q.question}${optText}. Please speak your answer.`, personality, speedRate);
        setPhase('listening');
        stRef.current = browserSTT((ans) => {
            stRef.current = null;
            handleAnswer(ans);
        });
    }, [q, qIndex, personality, speedRate]);

    const handleAnswer = useCallback(async (ans) => {
        setTx(ans);
        setPhase('result');

        let correct = false;
        const expected = q.correct_answer || (q.options?.[q.correct_index] ?? '');

        if (q.type === 'mcq') {
            // Check if spoken answer matches option letter or text
            const letter = ans.trim().toLowerCase().charAt(0);
            const idx = letter.charCodeAt(0) - 97;
            correct = idx === q.correct_index ||
                q.options?.[q.correct_index]?.toLowerCase()?.includes(ans.toLowerCase().slice(0, 15));
        } else {
            // Fuzzy: if answer contains key words from correct answer
            const keyWords = expected.toLowerCase().split(/\s+/).filter(w => w.length > 4).slice(0, 5);
            const ansLower = ans.toLowerCase();
            correct = keyWords.filter(w => ansLower.includes(w)).length >= Math.min(2, keyWords.length);
        }

        setResult({ correct, expected });
        setScore(s => ({ correct: s.correct + (correct ? 1 : 0), total: s.total + 1 }));

        const resp = correct
            ? `Correct! ${q.explanation || 'Well done!'}`
            : `Not quite. The correct answer is: ${expected}. ${q.explanation || ''}`;
        await speak(resp, personality, speedRate);
    }, [q, personality, speedRate]);

    const nextQuestion = useCallback(() => {
        setTx('');
        setResult(null);
        if (qIndex + 1 >= questions.length) {
            setPhase('done');
            speak(`Quiz complete! You scored ${score.correct + (result?.correct ? 0 : 0)} out of ${questions.length}. Great work!`, personality, speedRate);
        } else {
            setQIndex(i => i + 1);
            setPhase('intro');
        }
    }, [qIndex, questions.length, score, result, personality, speedRate]);

    useEffect(() => {
        if (phase === 'intro') readQuestion();
    }, [qIndex, phase]);

    useEffect(() => {
        return () => {
            window.speechSynthesis.cancel();
            stRef.current?.abort?.();
        };
    }, []);

    if (!q && phase !== 'done') return null;

    return (
        <div className={styles.overlay}>
            <div className={styles.card}>
                <div className={styles.topRow}>
                    <span className={styles.badge}>🎧 Voice Quiz</span>
                    <span className={styles.progress}>{qIndex + 1} / {questions.length}</span>
                    <button className={styles.closeBtn} onClick={onClose}><Square size={13} /> End Quiz</button>
                </div>

                {phase === 'done' ? (
                    <div className={styles.donePanel}>
                        <div className={styles.scoreRing}>
                            <span className={styles.scoreNum}>{score.correct}</span>
                            <span className={styles.scoreDen}>/{questions.length}</span>
                        </div>
                        <p className={styles.doneMsg}>Quiz Complete! 🎉</p>
                        <button className={styles.closeBtn2} onClick={onClose}>Close</button>
                    </div>
                ) : (
                    <>
                        <div className={styles.questionBox}>
                            {phase === 'reading' && <p className={styles.statusLabel}><Volume2 size={14} /> Reading question…</p>}
                            {phase === 'listening' && <p className={`${styles.statusLabel} ${styles.listening}`}><Mic size={14} /> Listening for your answer…</p>}
                            <p className={styles.question}>{q?.question}</p>
                            {q?.options?.length > 0 && (
                                <div className={styles.options}>
                                    {q.options.map((o, i) => (
                                        <span key={i} className={`${styles.optChip} ${result && i === q.correct_index ? styles.optCorrect : ''}`}>
                                            {String.fromCharCode(65+i)}: {o}
                                        </span>
                                    ))}
                                </div>
                            )}
                        </div>

                        {transcript && (
                            <div className={styles.transcriptBox}>
                                <span className={styles.txLabel}>You said:</span> "{transcript}"
                            </div>
                        )}

                        {result && (
                            <div className={`${styles.resultBar} ${result.correct ? styles.correct : styles.wrong}`}>
                                {result.correct ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
                                <span>{result.correct ? 'Correct!' : `Correct answer: ${result.expected}`}</span>
                            </div>
                        )}

                        {result && (
                            <button className={styles.nextBtn} onClick={nextQuestion}>
                                {qIndex + 1 < questions.length ? <><ChevronRight size={14} /> Next Question</> : '🏁 Finish Quiz'}
                            </button>
                        )}

                        {phase === 'listening' && (
                            <button className={styles.skipBtn} onClick={() => handleAnswer('')}>
                                Skip (no answer)
                            </button>
                        )}
                    </>
                )}

                <div className={styles.scoreBar}>
                    Score: <strong>{score.correct}</strong> / {score.total}
                </div>
            </div>
        </div>
    );
}
