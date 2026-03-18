import { useState, useEffect } from 'react';
import { Line } from 'react-chartjs-2';
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Tooltip } from 'chart.js';
import styles from './Profile.module.css';
import { getStudentProfile, getMySentiment } from '../../services/api';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip);

const MOCK_SENTIMENT = [0.6, 0.4, 0.3, -0.1, 0.2, 0.5, 0.4, 0.3, -0.2, -0.3, 0.1, 0.4, 0.6, 0.5, 0.7];

export default function Profile() {
    const [student, setStudent] = useState(null);
    const [loading, setLoading] = useState(true);
    const [sentimentData, setSentimentData] = useState({
        scores: MOCK_SENTIMENT,
        mood_label: 'Neutral',
        rolling_avg: 0.0,
        data_points: 0,
        live: false,
    });

    useEffect(() => {
        getStudentProfile()
            .then(data => setStudent(data))
            .catch(() => { })
            .finally(() => setLoading(false));

        getMySentiment(30)
            .then(res => {
                if (res.history && res.history.length > 0) {
                    setSentimentData({
                        scores: res.history.map(p => p.score),
                        mood_label: res.mood_label,
                        rolling_avg: res.rolling_avg,
                        data_points: res.data_points,
                        live: true,
                    });
                }
            })
            .catch(() => { /* keep mock on error */ });
    }, []);

    if (loading) {
        return (
            <div className={styles.page}>
                <div className={styles.loadingWrap}>
                    <div className={styles.spinner} />
                    <p className={styles.loadingText}>Loading your profile…</p>
                </div>
            </div>
        );
    }

    if (!student) {
        return (
            <div className={styles.page}>
                <div className={`card ${styles.errorCard}`}>
                    <p>⚠️ Could not load profile. Please refresh or log in again.</p>
                </div>
            </div>
        );
    }

    const cgpaHistory = student.cgpaHistory || student.cgpa_history || [];
    const subjects = student.subjects || student.subject_profiles || [];
    const attendanceOverall = student.attendanceOverall ?? student.attendance_overall ?? '—';
    const studyStreak = student.studyStreak ?? student.study_streak ?? 0;
    const examDays = student.examDays ?? student.exam_days ?? '—';
    const predictedCGPA = student.predictedCGPA ?? student.predicted_cgpa ?? '—';
    const arrearsHistory = student.arrearsHistory || student.arrears_history || [];
    const arrearCount = student.arrear_count ?? student.activeArrears ?? 0;

    const riskSubjects = subjects.filter(s => s.status !== 'safe');

    const sparkData = {
        labels: cgpaHistory.map((_, i) => `S${i + 1}`),
        datasets: [{
            data: cgpaHistory,
            borderColor: '#FF7A00',
            borderWidth: 2,
            pointBackgroundColor: '#FF7A00',
            pointRadius: 3,
            tension: 0.35,
            fill: false,
        }]
    };

    const sparkOptions = {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { backgroundColor: '#fff', titleColor: '#1A1A1A', bodyColor: '#6B6B6B', borderColor: '#E8E4DE', borderWidth: 1 } },
        scales: {
            x: { grid: { display: false }, ticks: { color: '#9A9A9A', font: { size: 10 } }, border: { display: false } },
            y: { grid: { color: '#F0ECE6' }, ticks: { color: '#9A9A9A', font: { size: 10 } }, border: { display: false }, min: 5, max: 10 }
        }
    };

    const statChips = [
        { icon: '📚', label: 'Subjects', val: subjects.length },
        { icon: '⚠️', label: 'At Risk', val: riskSubjects.length },
        { icon: '📊', label: 'Attendance', val: `${attendanceOverall}%` },
        { icon: '🔥', label: 'Study Streak', val: `${studyStreak} days` },
        { icon: '📅', label: 'Exam in', val: examDays !== '—' ? `${examDays} days` : '—' },
    ];

    return (
        <div className={styles.page}>
            {/* Profile hero card */}
            <div className={`card ${styles.heroCard}`}>
                <div className={styles.heroLeft}>
                    <div className={styles.avatarLarge}>{(student.name || 'S').charAt(0)}</div>
                    <div className={styles.heroInfo}>
                        <h1 className={styles.heroName}>{student.name}</h1>
                        <p className={styles.heroSub}>
                            {student.department} · Year {student.year} · Semester {student.semester}
                        </p>
                        <p className={styles.heroCollege}>{student.college}</p>
                        {student.college_id && (
                            <p className={styles.heroId}>ID: {student.college_id}</p>
                        )}
                    </div>
                </div>
                <div className={styles.heroCGPA}>
                    <div className={styles.heroCGPANum}>{student.currentCGPA ?? student.current_cgpa ?? '—'}</div>
                    <div className={styles.heroCGPALabel}>/ 10.0 CGPA</div>
                    {predictedCGPA !== '—' && (
                        <div className={styles.heroCGPAProjected}>↑ Projected {predictedCGPA}</div>
                    )}
                    {arrearCount > 0 && (
                        <div className={styles.heroCGPAArrear}>⚠️ {arrearCount} active arrear{arrearCount > 1 ? 's' : ''}</div>
                    )}
                </div>
            </div>

            {/* Stat chips row */}
            <div className={styles.statChips}>
                {statChips.map((s, i) => (
                    <div key={i} className={styles.statChip}>
                        <span className={styles.statIcon}>{s.icon}</span>
                        <div className={styles.statText}>
                            <span className={styles.statVal}>{s.val}</span>
                            <span className={styles.statLabel}>{s.label}</span>
                        </div>
                    </div>
                ))}
            </div>

            {/* CGPA journey */}
            {cgpaHistory.length > 0 && (
                <div className={`card ${styles.journeyCard}`}>
                    <h2 className={styles.cardTitle}>Grade Journey</h2>
                    <div className={styles.sparkWrap}>
                        <Line data={sparkData} options={sparkOptions} />
                    </div>
                    <div className={styles.semBadges}>
                        {cgpaHistory.map((g, i) => (
                            <div key={i} className={styles.semBadge}>
                                <span className={styles.semLabel}>Sem {i + 1}</span>
                                <span className={styles.semGrade} style={{ color: g >= 7.5 ? 'var(--safe)' : g >= 6.5 ? 'var(--watch)' : 'var(--risk)' }}>
                                    {g}
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Subject table + right panel */}
            <div className={styles.bottomRow}>
                {/* Subject performance */}
                <div className={`card ${styles.subjectCard}`}>
                    <h2 className={styles.cardTitle}>Subject Performance</h2>
                    {subjects.length === 0 ? (
                        <p className={styles.emptyNote}>No subject data available yet.</p>
                    ) : (
                        <div className={styles.tableWrap}>
                            <table className={styles.table}>
                                <thead>
                                    <tr>
                                        <th>Subject</th>
                                        <th>Grade</th>
                                        <th>Attendance</th>
                                        <th>Bloom</th>
                                        <th>Status</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {subjects.map((s, i) => {
                                        const grade = s.grade ?? s.current_grade ?? '—';
                                        const att = s.attendance ?? s.live_attendance ?? '—';
                                        const bloom = s.bloomLevel ?? s.bloom_level ?? 1;
                                        return (
                                            <tr key={i} className={i % 2 === 0 ? styles.rowEven : ''}>
                                                <td>{s.name ?? s.subject_name}</td>
                                                <td className={styles.grade}>{grade}</td>
                                                <td>
                                                    <span style={{ color: typeof att === 'number' && att < 75 ? 'var(--risk)' : 'var(--text-1)' }}>
                                                        {att !== '—' ? `${att}%` : '—'}
                                                    </span>
                                                </td>
                                                <td>
                                                    <div className={styles.miniBloom}>
                                                        {[1, 2, 3, 4, 5, 6].map(l => (
                                                            <div
                                                                key={l}
                                                                className="bloom-block"
                                                                style={{ background: l <= bloom ? 'var(--accent)' : 'var(--border)', width: 10, height: 10 }}
                                                            />
                                                        ))}
                                                    </div>
                                                </td>
                                                <td>
                                                    <span className={`pill ${s.status === 'safe' ? 'pill-safe' : s.status === 'watch' ? 'pill-watch' : 'pill-risk'}`} style={{ fontSize: '0.6875rem' }}>
                                                        {s.status === 'safe' ? 'Safe' : s.status === 'watch' ? 'Watch' : 'At Risk'}
                                                    </span>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>

                {/* Right panel */}
                <div className={styles.rightPanel}>
                    {/* Academic history */}
                    <div className={`card ${styles.historyCard}`}>
                        <h2 className={styles.cardTitle}>Academic History</h2>
                        {arrearsHistory.length > 0 ? (
                            arrearsHistory.map((item, i) => (
                                <div key={i} className={styles.historyItem}>
                                    <span className={styles.historyIcon}>✓</span>
                                    <span>{item}</span>
                                </div>
                            ))
                        ) : (
                            <div className={styles.historyItem} style={{ color: 'var(--safe)' }}>
                                <span className={styles.historyIcon} style={{ background: 'var(--safe-light)' }}>✓</span>
                                <span>No arrear history on record</span>
                            </div>
                        )}
                        {arrearCount === 0 && (
                            <div className={styles.historyItem} style={{ color: 'var(--safe)' }}>
                                <span className={styles.historyIcon} style={{ background: 'var(--safe-light)' }}>✓</span>
                                <span>No active arrears</span>
                            </div>
                        )}
                    </div>

                    {/* Emotional arc — live sentiment from DB */}
                    <div className={`card ${styles.emotionCard}`}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-2)' }}>
                            <h2 className={styles.cardTitle} style={{ margin: 0 }}>Session Sentiment</h2>
                            <span style={{
                                fontSize: '0.6rem', fontWeight: 700, padding: '2px 8px', borderRadius: 20,
                                background: sentimentData.live ? 'rgba(16,185,129,0.1)' : 'rgba(245,158,11,0.1)',
                                color: sentimentData.live ? '#10B981' : '#F59E0B',
                            }}>{sentimentData.live ? '● Live' : '○ Demo'}</span>
                        </div>
                        <p className={styles.emotionSub}>
                            {sentimentData.live
                                ? `${sentimentData.data_points} interactions · avg ${sentimentData.rolling_avg > 0 ? '+' : ''}${sentimentData.rolling_avg} · ${sentimentData.mood_label}`
                                : 'Chat with Mentor to start tracking real session emotions'}
                        </p>
                        <div className={styles.sentimentBar}>
                            {sentimentData.scores.map((v, i) => (
                                <div
                                    key={i}
                                    className={styles.sentimentBlock}
                                    style={{
                                        height: `${Math.abs(v) * 40 + 8}px`,
                                        background: v > 0 ? 'var(--safe)' : 'var(--risk)',
                                        opacity: 0.5 + Math.abs(v) * 0.5,
                                    }}
                                    title={`${v > 0 ? '+' : ''}${v}`}
                                />
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
