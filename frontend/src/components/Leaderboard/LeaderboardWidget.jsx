/**
 * LeaderboardWidget — Phase 7 V6 Competitive Leaderboard
 * Displays top 10 students by XP for competitive mode
 */
import { useState, useEffect } from 'react';
import { Trophy, Crown, Flame, Loader2, RefreshCw } from 'lucide-react';
import { getLeaderboard } from '../../services/api';
import styles from './LeaderboardWidget.module.css';

const MEDAL = ['🥇', '🥈', '🥉'];

export default function LeaderboardWidget({ currentStudentId, subjectCode }) {
    const [board, setBoard]     = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError]     = useState('');

    const load = async () => {
        setLoading(true); setError('');
        try {
            const data = await getLeaderboard(subjectCode);
            setBoard(data.leaderboard || []);
        } catch { setError('Could not load leaderboard.'); }
        setLoading(false);
    };

    useEffect(() => { load(); }, [subjectCode]);

    if (loading) return (
        <div className={styles.widget}>
            <div className={styles.header}><Trophy size={14} /> Leaderboard</div>
            <div className={styles.loader}><Loader2 size={18} className={styles.spin} /></div>
        </div>
    );

    return (
        <div className={styles.widget}>
            <div className={styles.header}>
                <Trophy size={14} /> Leaderboard
                <button className={styles.refreshBtn} onClick={load} title="Refresh"><RefreshCw size={12} /></button>
            </div>

            {error && <p className={styles.err}>{error}</p>}

            <div className={styles.rows}>
                {board.slice(0, 10).map((s, i) => {
                    const isSelf = s.student_id === currentStudentId;
                    return (
                        <div key={s.student_id} className={`${styles.row} ${isSelf ? styles.self : ''}`}>
                            <span className={styles.rank}>
                                {i < 3 ? MEDAL[i] : `#${i + 1}`}
                            </span>
                            <div className={styles.nameCol}>
                                <span className={styles.name}>{s.name}{isSelf ? ' (You)' : ''}</span>
                                {s.section && <span className={styles.section}>{s.section}</span>}
                            </div>
                            <div className={styles.right}>
                                <span className={styles.xp}>⚡ {s.total_xp.toLocaleString()}</span>
                                {s.streak_days > 0 && (
                                    <span className={styles.streak}><Flame size={10} /> {s.streak_days}d</span>
                                )}
                                <span className={styles.level}>Lv {s.level}</span>
                            </div>
                        </div>
                    );
                })}
                {board.length === 0 && !error && (
                    <p className={styles.empty}>No data yet. Study to earn XP! ⚡</p>
                )}
            </div>
        </div>
    );
}
