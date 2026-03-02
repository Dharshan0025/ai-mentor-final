import styles from './Schedule.module.css';
import { mockCurrentStudent, SCHEDULE_DATA } from '../../data/mockData';
import { AlertTriangle } from 'lucide-react';

const TYPE_COLORS = {
    risk: { bg: 'rgba(239,68,68,0.12)', border: 'var(--risk)', text: '#B91C1C' },
    watch: { bg: 'rgba(245,158,11,0.12)', border: 'var(--watch)', text: '#92400E' },
    safe: { bg: 'rgba(34,197,94,0.12)', border: 'var(--safe)', text: '#15803D' },
};

export default function Schedule() {
    const student = mockCurrentStudent;

    return (
        <div className={styles.page}>
            {/* Header */}
            <div className={styles.header}>
                <div>
                    <span className="section-label">📅 Study Schedule</span>
                    <h1 className={styles.title}>Your Study Plan</h1>
                    <p className={styles.sub}>Built around your risk priorities and exam dates.</p>
                </div>

                {/* Stat pills */}
                <div className={styles.stats}>
                    {[
                        { label: 'Study hrs today', val: '5.5h' },
                        { label: 'On track', val: '3/5' },
                        { label: 'Exam in', val: `${student.examDays}d` },
                    ].map((s, i) => (
                        <div key={i} className={styles.statPill}>
                            <span className={styles.statVal}>{s.val}</span>
                            <span className={styles.statLabel}>{s.label}</span>
                        </div>
                    ))}
                </div>
            </div>

            {/* Nudge */}
            <div className={styles.nudge}>
                <AlertTriangle size={15} />
                You haven't studied Operating Systems today — exam in {student.examDays} days.
                <span className={styles.nudgeLink}>Start now →</span>
            </div>

            {/* Legend */}
            <div className={styles.legend}>
                {[
                    { label: 'At-risk / Backlog', type: 'risk' },
                    { label: 'Watch zone', type: 'watch' },
                    { label: 'On track', type: 'safe' },
                ].map(l => (
                    <div key={l.type} className={styles.legendItem}>
                        <div className={styles.legendBlock} style={{ background: TYPE_COLORS[l.type].bg, borderLeft: `3px solid ${TYPE_COLORS[l.type].border}` }} />
                        <span>{l.label}</span>
                    </div>
                ))}
            </div>

            {/* Week calendar */}
            <div className={`card ${styles.calendarCard}`}>
                <div className={styles.calendar}>
                    {SCHEDULE_DATA.map((day, di) => (
                        <div key={di} className={styles.dayColumn}>
                            <div className={styles.dayHeader}>{day.day}</div>
                            <div className={styles.daySlots}>
                                {day.slots.map((slot, si) => {
                                    const c = TYPE_COLORS[slot.type];
                                    return (
                                        <div
                                            key={si}
                                            className={styles.slot}
                                            style={{
                                                background: c.bg,
                                                borderLeft: `3px solid ${c.border}`,
                                                minHeight: `${Math.round(slot.duration * 0.6)}px`,
                                            }}
                                        >
                                            <div className={styles.slotTime}>{slot.time}</div>
                                            <div className={styles.slotSubject} style={{ color: c.text }}>{slot.subject}</div>
                                            <div className={styles.slotTopic}>{slot.topic}</div>
                                            <div className={styles.slotDuration}>{slot.duration}min</div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Pomodoro tip */}
            <div className={styles.tip}>
                <span>💡</span>
                <span>Use the <strong>Pomodoro technique</strong> — 25 min focused study, 5 min break. Repeat 4 times, then take a 20 min long break.</span>
            </div>
        </div>
    );
}
