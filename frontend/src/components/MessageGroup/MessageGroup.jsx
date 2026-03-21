import { useState } from 'react';
import styles from './MessageGroup.module.css';
import { ChevronDown, ChevronUp, Clock, CheckCircle2 } from 'lucide-react';

/**
 * MessageGroup – groups related messages into collapsible threads
 * Props:
 *   title: string - group title (e.g., "CGPA Discussion")
 *   messages: array - messages in this group
 *   timestamp: string - when the group was created
 *   isExpanded: boolean - default expansion state
 *   status: 'active' | 'resolved' | 'pending'
 */
export default function MessageGroup({ 
  title, 
  messages = [], 
  timestamp,
  isExpanded = true,
  status = 'active'
}) {
  const [expanded, setExpanded] = useState(isExpanded);
  const messageCount = messages.length;

  const statusConfig = {
    active: { icon: Clock, color: 'var(--accent)', label: 'Active' },
    resolved: { icon: CheckCircle2, color: 'var(--safe)', label: 'Resolved' },
    pending: { icon: Clock, color: 'var(--watch)', label: 'Pending' }
  };

  const StatusIcon = statusConfig[status].icon;

  return (
    <div className={`${styles.group} ${expanded ? styles.expanded : ''}`}>
      <button 
        className={styles.header}
        onClick={() => setExpanded(!expanded)}
      >
        <div className={styles.headerLeft}>
          <div className={styles.iconWrapper} style={{ color: statusConfig[status].color }}>
            <StatusIcon size={16} />
          </div>
          <div className={styles.titleSection}>
            <span className={styles.title}>{title}</span>
            <span className={styles.meta}>
              {messageCount} message{messageCount !== 1 ? 's' : ''} · {timestamp}
            </span>
          </div>
        </div>
        <div className={styles.headerRight}>
          <span 
            className={styles.statusBadge}
            style={{ 
              backgroundColor: `${statusConfig[status].color}15`,
              color: statusConfig[status].color 
            }}
          >
            {statusConfig[status].label}
          </span>
          {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </div>
      </button>
      
      {expanded && (
        <div className={styles.content}>
          {messages.map((msg, idx) => (
            <div key={idx} className={styles.message}>
              {msg}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
