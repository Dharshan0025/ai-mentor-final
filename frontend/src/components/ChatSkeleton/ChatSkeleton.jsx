import styles from './ChatSkeleton.module.css';

/**
 * ChatSkeleton – beautiful loading skeleton for chat messages
 * Different variants for different message types
 */
export function MessageSkeleton({ variant = 'agent', lines = 3 }) {
  const lineWidths = ['85%', '95%', '70%', '80%', '60%'];
  
  return (
    <div className={`${styles.skeleton} ${styles[variant]}`}>
      <div className={styles.avatar} />
      <div className={styles.content}>
        <div className={styles.header} />
        {Array.from({ length: lines }).map((_, i) => (
          <div 
            key={i} 
            className={styles.line}
            style={{ width: lineWidths[i % lineWidths.length] }}
          />
        ))}
        <div className={styles.actions}>
          <div className={styles.chip} />
          <div className={styles.chip} />
        </div>
      </div>
    </div>
  );
}

export function PipelineSkeleton() {
  return (
    <div className={styles.pipelineSkeleton}>
      <div className={styles.stage}>
        <div className={styles.dot} />
        <div className={styles.stageLine} />
      </div>
      <div className={styles.stage}>
        <div className={styles.dot} />
        <div className={styles.stageLine} />
      </div>
      <div className={styles.stage}>
        <div className={styles.dot} />
        <div className={styles.stageLine} />
      </div>
    </div>
  );
}

export function ThinkingSkeleton({ steps = [] }) {
  return (
    <div className={styles.thinkingSkeleton}>
      <div className={styles.pulseIndicator}>
        <div className={styles.pulse} />
        <span>AI is thinking</span>
      </div>
      <div className={styles.steps}>
        {steps.map((step, i) => (
          <div key={i} className={styles.step}>
            <div className={styles.stepIcon} />
            <div className={styles.stepText} style={{ width: `${70 + (i * 10)}%` }} />
          </div>
        ))}
      </div>
    </div>
  );
}

export function ContextSkeleton() {
  return (
    <div className={styles.contextSkeleton}>
      <div className={styles.contextHeader}>
        <div className={styles.contextAvatar} />
        <div className={styles.contextInfo}>
          <div className={styles.contextLine} style={{ width: '60%' }} />
          <div className={styles.contextLine} style={{ width: '40%' }} />
        </div>
      </div>
      <div className={styles.contextStats}>
        <div className={styles.stat} />
        <div className={styles.stat} />
        <div className={styles.stat} />
      </div>
    </div>
  );
}
