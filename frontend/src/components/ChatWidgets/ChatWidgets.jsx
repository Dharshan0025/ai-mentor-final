/**
 * ChatWidgets — polymorphic renderer for structured UI cards returned by the orchestrator.
 * Supports: schedule_card, prediction_card, quiz_widget, subject_status
 */
import { useState } from 'react';
import styles from './ChatWidgets.module.css';

// ── Schedule Card ─────────────────────────────────────────────────────────────
function ScheduleCard({ data }) {
    const days = data?.days || [];
    if (!days.length) return null;
    return (
        <div className={styles.card}>
            <div className={styles.cardHeader}>
                <span>📅</span>
                <h4>7-Day Study Plan</h4>
            </div>
            <div className={styles.scheduleGrid}>
                {days.map((day, i) => (
                    <div key={i} className={styles.dayBlock}>
                        <div className={styles.dayLabel}>{day.day || `Day ${i + 1}`}</div>
                        <div className={styles.daySlots}>
                            {(day.slots || []).map((slot, j) => (
                                <div
                                    key={j}
                                    className={`${styles.slot} ${styles[`slot_${slot.type || 'safe'}`]}`}
                                >
                                    <span className={styles.slotSubject}>{slot.subject}</span>
                                    <span className={styles.slotTime}>{slot.time}</span>
                                </div>
                            ))}
                            {!day.slots?.length && (
                                <div className={styles.slot}>
                                    <span className={styles.slotSubject}>{day.focus || 'Study'}</span>
                                </div>
                            )}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ── Prediction Card ───────────────────────────────────────────────────────────
function PredictionCard({ data }) {
    const current = data?.current ?? '—';
    const predicted = data?.predicted ?? '—';
    const diff = typeof predicted === 'number' && typeof current === 'number'
        ? (predicted - current).toFixed(2)
        : null;
    const positive = diff !== null && parseFloat(diff) >= 0;

    return (
        <div className={styles.card}>
            <div className={styles.cardHeader}>
                <span>📊</span>
                <h4>CGPA Forecast</h4>
            </div>
            <div className={styles.predictionRow}>
                <div className={styles.predStat}>
                    <div className={styles.predValue}>{current}</div>
                    <div className={styles.predLabel}>Current</div>
                </div>
                <div className={styles.predArrow}>{positive ? '↑' : '↓'}</div>
                <div className={styles.predStat}>
                    <div className={`${styles.predValue} ${positive ? styles.pos : styles.neg}`}>
                        {predicted}
                    </div>
                    <div className={styles.predLabel}>Predicted</div>
                </div>
                {diff !== null && (
                    <div className={`${styles.predDiff} ${positive ? styles.pos : styles.neg}`}>
                        {positive ? '+' : ''}{diff}
                    </div>
                )}
            </div>
        </div>
    );
}

// ── Quiz Widget ───────────────────────────────────────────────────────────────
function QuizWidget({ data, onAnswer }) {
    const [answer, setAnswer] = useState('');
    return (
        <div className={`${styles.card} ${styles.quizCard}`}>
            <div className={styles.cardHeader}>
                <span>🧪</span>
                <h4>Quick Check — {data?.subject || 'Concept'}</h4>
            </div>
            <p className={styles.quizQuestion}>{data?.question}</p>
            <textarea
                className={styles.quizInput}
                placeholder="Type your answer..."
                rows={3}
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
            />
            <button
                className={styles.quizSubmit}
                onClick={() => {
                    if (answer.trim()) onAnswer?.(answer);
                }}
            >
                Submit Answer
            </button>
        </div>
    );
}

// ── Subject Status Card ────────────────────────────────────────────────────────
function SubjectStatusCard({ data }) {
    const subjects = data?.subjects || [];
    return (
        <div className={styles.card}>
            <div className={styles.cardHeader}>
                <span>📝</span>
                <h4>Subject Status</h4>
            </div>
            <table className={styles.subjectTable}>
                <thead>
                    <tr>
                        <th>Subject</th>
                        <th>Grade</th>
                        <th>Attendance</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {subjects.map((s, i) => (
                        <tr key={i}>
                            <td>{s.name || s.code}</td>
                            <td>{s.grade ?? '—'}</td>
                            <td>{s.attendance != null ? `${s.attendance}%` : '—'}</td>
                            <td>
                                <span className={`${styles.badge} ${styles[`badge_${s.status}`]}`}>
                                    {s.status || 'unknown'}
                                </span>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

// ── Main Renderer ─────────────────────────────────────────────────────────────
export default function ChatWidgets({ uiCard, onQuizAnswer }) {
    if (!uiCard?.type) return null;

    switch (uiCard.type) {
        case 'schedule_card':     return <ScheduleCard data={uiCard.data} />;
        case 'prediction_card':   return <PredictionCard data={uiCard.data} />;
        case 'quiz_widget':       return <QuizWidget data={uiCard.data} onAnswer={onQuizAnswer} />;
        case 'subject_status':    return <SubjectStatusCard data={uiCard.data} />;
        default:                  return null;
    }
}
