import React, { useState } from 'react';
import styles from './CommitTracker.module.css';
import { CheckCircle } from 'lucide-react';

/**
 * CommitTracker – shows pending actions (suggested actions) and lets the user mark them complete.
 * Props:
 *   commitments: [{ label: string, prompt: string }]
 *   onComplete: (label, prompt) => void
 */
export default function CommitTracker({ commitments = [], onComplete }) {
  const [completed, setCompleted] = useState({});

  const handleCheck = (label, prompt) => {
    const newCompleted = { ...completed, [label]: true };
    setCompleted(newCompleted);
    if (onComplete) onComplete(label, prompt);
  };

  if (commitments.length === 0) return null;

  return (
    <div className={styles.container}>
      <h3 className={styles.title}>🗒️ Pending Commitments</h3>
      <ul className={styles.list}>
        {commitments.map((c, i) => (
          <li key={i} className={styles.item}>
            <label className={styles.label}>
              <input
                type="checkbox"
                checked={!!completed[c.label]}
                onChange={() => handleCheck(c.label, c.prompt)}
                className={styles.checkbox}
              />
              <span className={styles.text}>{c.label}</span>
            </label>
            {completed[c.label] && <CheckCircle size={14} className={styles.doneIcon} />}
          </li>
        ))}
      </ul>
    </div>
  );
}
