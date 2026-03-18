import styles from './XpToast.module.css';

/**
 * XpToast — animated "+XP 🎉" notification that slides up then fades out.
 * Props:
 *   xp       {number}  — XP amount awarded
 *   action   {string}  — action label ("Lesson Complete", "Checkpoint Pass", etc.)
 *   badges   {Array}   — optional list of { icon, name } badges earned this event
 *   onDone   {func}    — callback when animation finishes (parent removes from DOM)
 */
export default function XpToast({ xp = 20, action = 'XP Earned', badges = [], onDone }) {
    return (
        <div className={styles.toast} onAnimationEnd={onDone}>
            <div className={styles.xpPill}>
                <span className={styles.xpAmount}>+{xp} XP</span>
                <span className={styles.bolt}>⚡</span>
            </div>
            <span className={styles.action}>{action}</span>
            {badges.length > 0 && (
                <div className={styles.badges}>
                    {badges.map(b => (
                        <span key={b.badge_id} className={styles.badge} title={b.name}>
                            {b.icon}
                        </span>
                    ))}
                    <span className={styles.badgeLabel}>
                        {badges.length === 1 ? `Badge: ${badges[0].name}` : `${badges.length} badges!`}
                    </span>
                </div>
            )}
        </div>
    );
}
