/**
 * XPConfetti — fires a celebratory confetti burst + XP toast when the AI
 * awards XP points for a high-quality student question.
 * Uses a pure CSS particle approach — no external dependencies.
 */
import { useEffect, useState } from 'react';
import styles from './XPConfetti.module.css';

const COLORS = ['#3b82f6', '#22c55e', '#f59e0b', '#ec4899', '#a78bfa', '#06b6d4'];
const PARTICLE_COUNT = 28;

function generateParticles() {
    return Array.from({ length: PARTICLE_COUNT }, (_, i) => ({
        id: i,
        color: COLORS[i % COLORS.length],
        left: `${Math.random() * 100}%`,
        delay: `${Math.random() * 0.5}s`,
        size: `${Math.random() * 6 + 5}px`,
        shape: Math.random() > 0.5 ? 'circle' : 'square',
        duration: `${Math.random() * 0.6 + 0.8}s`,
    }));
}

export default function XPConfetti({ xp = 0, onDone }) {
    const [visible, setVisible] = useState(false);
    const [particles] = useState(generateParticles);

    useEffect(() => {
        if (xp <= 0) return;
        setVisible(true);
        const timer = setTimeout(() => {
            setVisible(false);
            onDone?.();
        }, 2500);
        return () => clearTimeout(timer);
    }, [xp, onDone]);

    if (!visible || xp <= 0) return null;

    return (
        <div className={styles.overlay} aria-live="polite">
            {particles.map(p => (
                <div
                    key={p.id}
                    className={`${styles.particle} ${p.shape === 'circle' ? styles.circle : styles.square}`}
                    style={{
                        left: p.left,
                        width: p.size,
                        height: p.size,
                        background: p.color,
                        animationDelay: p.delay,
                        animationDuration: p.duration,
                    }}
                />
            ))}
            <div className={styles.toast}>
                <span className={styles.star}>⚡</span>
                <span className={styles.label}>+{xp} XP</span>
                <span className={styles.sub}>Great question!</span>
            </div>
        </div>
    );
}
