/**
 * TeacherAvatar — Animated SVG professor that reacts to lesson state.
 * Props:
 *   state: 'idle' | 'teaching' | 'thinking' | 'celebrating' | 'encouraging'
 *   size:  number (default 80)
 */
import styles from './TeacherAvatar.module.css';

const STATE_CONFIGS = {
    idle: { bodyColor: '#2F4858', hatColor: '#1A2D3F', eyeAnim: 'blink', mouthType: 'neutral', desc: '😐' },
    teaching: { bodyColor: '#1E3A8A', hatColor: '#0F2055', eyeAnim: 'wide', mouthType: 'talk', desc: '👨‍🏫' },
    thinking: { bodyColor: '#374151', hatColor: '#1F2937', eyeAnim: 'squint', mouthType: 'hmm', desc: '🤔' },
    celebrating: { bodyColor: '#065F46', hatColor: '#034732', eyeAnim: 'star', mouthType: 'smile', desc: '🎉' },
    encouraging: { bodyColor: '#7C3AED', hatColor: '#5B21B6', eyeAnim: 'wide', mouthType: 'cheer', desc: '💪' },
};

export default function TeacherAvatar({ state = 'idle', size = 80 }) {
    const cfg = STATE_CONFIGS[state] || STATE_CONFIGS.idle;

    return (
        <div
            className={`${styles.wrap} ${styles[state]}`}
            style={{ width: size, height: size }}
            title={`Teacher: ${state}`}
            aria-label={`Teacher avatar — ${state}`}
        >
            <svg
                viewBox="0 0 100 100"
                xmlns="http://www.w3.org/2000/svg"
                style={{ width: '100%', height: '100%' }}
            >
                {/* Graduation cap */}
                <rect x="22" y="24" width="56" height="6" rx="2" fill={cfg.hatColor} />
                <polygon points="50,14 22,28 78,28" fill={cfg.hatColor} />
                <line x1="72" y1="26" x2="78" y2="38" stroke={cfg.hatColor} strokeWidth="2.5" strokeLinecap="round" />
                <circle cx="78" cy="40" r="3.5" fill="#FF7A00" />

                {/* Head */}
                <ellipse cx="50" cy="50" rx="24" ry="22" fill="#FDDBA8" />

                {/* Eyes — vary by state */}
                {cfg.eyeAnim === 'blink' && (
                    <>
                        <ellipse cx="40" cy="47" rx="4" ry="4.5" fill="#1E293B" className={styles.eyeBlink} />
                        <ellipse cx="60" cy="47" rx="4" ry="4.5" fill="#1E293B" className={styles.eyeBlink} />
                    </>
                )}
                {cfg.eyeAnim === 'wide' && (
                    <>
                        <ellipse cx="40" cy="47" rx="5" ry="5.5" fill="#1E293B" />
                        <ellipse cx="60" cy="47" rx="5" ry="5.5" fill="#1E293B" />
                        <circle cx="41.5" cy="45.5" r="1.8" fill="white" />
                        <circle cx="61.5" cy="45.5" r="1.8" fill="white" />
                    </>
                )}
                {cfg.eyeAnim === 'squint' && (
                    <>
                        <ellipse cx="40" cy="47" rx="4.5" ry="2.5" fill="#1E293B" />
                        <ellipse cx="60" cy="47" rx="4.5" ry="2.5" fill="#1E293B" />
                    </>
                )}
                {cfg.eyeAnim === 'star' && (
                    <>
                        <text x="34" y="51" fontSize="10" fill="#FF7A00">★</text>
                        <text x="54" y="51" fontSize="10" fill="#FF7A00">★</text>
                    </>
                )}

                {/* Glasses */}
                <circle cx="40" cy="47" r="8" fill="none" stroke="#6B7280" strokeWidth="1.5" opacity="0.7" />
                <circle cx="60" cy="47" r="8" fill="none" stroke="#6B7280" strokeWidth="1.5" opacity="0.7" />
                <line x1="48" y1="47" x2="52" y2="47" stroke="#6B7280" strokeWidth="1.5" />
                <line x1="32" y1="47" x2="28" y2="45" stroke="#6B7280" strokeWidth="1.5" />
                <line x1="68" y1="47" x2="72" y2="45" stroke="#6B7280" strokeWidth="1.5" />

                {/* Nose */}
                <ellipse cx="50" cy="53" rx="2" ry="2.5" fill="#F0B97B" opacity="0.8" />

                {/* Mouth — vary by state */}
                {(cfg.mouthType === 'neutral') && (
                    <line x1="43" y1="62" x2="57" y2="62" stroke="#C97B3A" strokeWidth="2" strokeLinecap="round" />
                )}
                {(cfg.mouthType === 'talk') && (
                    <ellipse cx="50" cy="62" rx="6" ry="3.5" fill="#C97B3A" className={styles.mouth} />
                )}
                {(cfg.mouthType === 'hmm') && (
                    <path d="M 43 63 Q 50 60 57 63" stroke="#C97B3A" strokeWidth="2" fill="none" strokeLinecap="round" />
                )}
                {(cfg.mouthType === 'smile' || cfg.mouthType === 'cheer') && (
                    <path d="M 42 60 Q 50 68 58 60" stroke="#C97B3A" strokeWidth="2" fill="none" strokeLinecap="round" />
                )}

                {/* Body / suit */}
                <path d="M 26 72 Q 26 100 74 100 Q 74 72 74 72 L 63 65 L 50 70 L 37 65 Z" fill={cfg.bodyColor} />

                {/* Tie */}
                <polygon points="47,66 53,66 51,80 50,83 49,80" fill="#FF7A00" />
                <rect x="46" y="64" width="8" height="4" rx="1" fill="#FF9E3D" />

                {/* Teaching state: chalk sparkle */}
                {state === 'teaching' && (
                    <>
                        <text x="76" y="62" fontSize="12" className={styles.sparkle1}>✦</text>
                        <text x="80" y="50" fontSize="8" className={styles.sparkle2}>✦</text>
                    </>
                )}
                {/* Celebrating: confetti */}
                {state === 'celebrating' && (
                    <>
                        <circle cx="18" cy="30" r="3" fill="#FF7A00" className={styles.confetti1} />
                        <circle cx="82" cy="28" r="2.5" fill="#FCD34D" className={styles.confetti2} />
                        <circle cx="15" cy="55" r="2" fill="#34D399" className={styles.confetti3} />
                    </>
                )}
            </svg>
        </div>
    );
}
