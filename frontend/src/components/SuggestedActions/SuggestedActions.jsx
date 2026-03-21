/**
 * SuggestedActions — row of tappable CTA chips below the last agent message.
 * Each chip contains an emoji icon, a label, and fires a prompt when clicked.
 */
import styles from './SuggestedActions.module.css';

export default function SuggestedActions({ actions = [], onSelect }) {
    if (!actions.length) return null;

    return (
        <div className={styles.row}>
            {actions.map((action, i) => (
                <button
                    key={i}
                    className={styles.chip}
                    onClick={() => onSelect?.(action.prompt || action.label)}
                    title={action.prompt || action.label}
                >
                    {action.icon && <span className={styles.icon}>{action.icon}</span>}
                    <span className={styles.label}>{action.label}</span>
                </button>
            ))}
        </div>
    );
}
