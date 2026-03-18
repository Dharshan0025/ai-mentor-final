import { useState, useEffect } from 'react';
import { getStudyModes } from '../../services/api';
import styles from './StudyModeSelector.module.css';

const FALLBACK_MODES = [
    { mode: 'concept',    label: 'Concept Deep-Dive', icon: '🧠', description: 'Thorough explanations with examples.' },
    { mode: 'fast_track', label: 'Fast-Track',         icon: '⚡', description: 'Move quickly, advance Bloom level.' },
    { mode: 'exam',       label: 'Exam Mode',          icon: '📝', description: 'Key points and exam summaries.' },
    { mode: 'slow_deep',  label: 'Slow & Deep',        icon: '🐢', description: 'Mastery-first learning.' },
    { mode: 'olympiad',   label: 'Olympiad',           icon: '🏆', description: 'Challenge-level theory.' },
    { mode: 'hackathon',  label: 'Hackathon Prep',     icon: '🚀', description: 'Project-oriented learning.' },
    { mode: 'interview',  label: 'Interview Prep',     icon: '💼', description: 'Technical Q&A and design.' },
];

/**
 * StudyModeSelector — lets student choose a study mode before starting a lesson (V9).
 * Lists all available modes and returns the selected one via onSelect callback.
 */
export function StudyModeSelector({ currentMode = 'concept', onSelect, compact = false }) {
    const [modes, setModes] = useState(FALLBACK_MODES);

    useEffect(() => {
        getStudyModes()
            .then(r => { if (r?.modes?.length) setModes(r.modes); })
            .catch(() => {});
    }, []);

    if (compact) {
        return (
            <div className={styles.compact}>
                {modes.map(m => (
                    <button
                        key={m.mode}
                        className={`${styles.compactBtn} ${currentMode === m.mode ? styles.activeCompact : ''}`}
                        onClick={() => onSelect(m.mode)}
                        title={m.description}
                    >
                        <span>{m.icon}</span>
                        <span>{m.label}</span>
                    </button>
                ))}
            </div>
        );
    }

    return (
        <div className={styles.grid}>
            {modes.map(m => (
                <button
                    key={m.mode}
                    className={`${styles.card} ${currentMode === m.mode ? styles.active : ''}`}
                    onClick={() => onSelect(m.mode)}
                >
                    <span className={styles.icon}>{m.icon}</span>
                    <div className={styles.info}>
                        <div className={styles.label}>{m.label}</div>
                        <div className={styles.desc}>{m.description}</div>
                    </div>
                    {currentMode === m.mode && <span className={styles.check}>✓</span>}
                </button>
            ))}
        </div>
    );
}

export default StudyModeSelector;
