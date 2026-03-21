import { useState } from 'react';
import styles from './ChatHistory.module.css';
import { Clock, ChevronRight, Plus, X, History } from 'lucide-react';

/**
 * ChatHistory – sidebar showing past conversation threads
 * Props:
 *   threads: array of conversation threads with metadata
 *   onSelect: (threadId) => void
 *   onNewChat: () => void
 *   className: string
 */
export default function ChatHistory({ threads = [], onSelect, onNewChat, className }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className={`${styles.historyPanel} ${className || ''}`}>
      <div className={styles.header}>
        <div className={styles.titleSection}>
          <History size={14} />
          <span>Session History</span>
        </div>
        <button className={styles.expandBtn} onClick={() => setExpanded(!expanded)}>
          {expanded ? <X size={14} /> : <Plus size={14} />}
        </button>
      </div>

      {expanded && (
        <div className={styles.content}>
          <button className={styles.newChatBtn} onClick={onNewChat}>
            <Plus size={14} />
            <span>New Chat</span>
          </button>

          {threads.length === 0 ? (
            <div className={styles.empty}>
              <Clock size={24} />
              <p>No previous conversations</p>
              <span>Start a new chat to begin</span>
            </div>
          ) : (
            <div className={styles.threadList}>
              {threads.map((thread) => (
                <button
                  key={thread.id}
                  className={styles.threadItem}
                  onClick={() => onSelect(thread.id)}
                >
                  <div className={styles.threadMeta}>
                    <span className={styles.threadTitle}>{thread.title}</span>
                    <span className={styles.threadTime}>{thread.timeAgo}</span>
                  </div>
                  <div className={styles.threadPreview}>{thread.preview}</div>
                  <div className={styles.threadStats}>
                    <span>{thread.messageCount} messages</span>
                    <span>{thread.agent}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
