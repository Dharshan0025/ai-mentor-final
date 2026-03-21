import { useState } from 'react';
import styles from './MessageFeedback.module.css';
import { ThumbsUp, ThumbsDown, MessageSquare, Flag, Check, X } from 'lucide-react';

/**
 * MessageFeedback – feedback collection for AI responses
 * Props:
 *   messageId: string - unique message identifier
 *   onFeedback: (type, comment) => void - feedback callback
 *   showInline: boolean - show inline or in popup
 */
export default function MessageFeedback({ messageId, onFeedback, showInline = true }) {
  const [feedback, setFeedback] = useState(null);
  const [showComment, setShowComment] = useState(false);
  const [comment, setComment] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const handleFeedback = (type) => {
    setFeedback(type);
    if (type === 'negative') {
      setShowComment(true);
    } else {
      // Positive feedback - submit immediately
      submitFeedback(type, '');
    }
  };

  const submitFeedback = (type, text) => {
    if (onFeedback) {
      onFeedback({
        messageId,
        type,
        comment: text,
        timestamp: new Date().toISOString()
      });
    }
    setSubmitted(true);
    setTimeout(() => {
      setShowComment(false);
      setComment('');
    }, 2000);
  };

  const handleCommentSubmit = (e) => {
    e.preventDefault();
    submitFeedback('negative', comment);
  };

  if (submitted && !showComment) {
    return (
      <div className={styles.feedbackSubmitted}>
        <Check size={14} />
        <span>Thanks for your feedback!</span>
      </div>
    );
  }

  return (
    <div className={styles.feedbackContainer}>
      {!feedback ? (
        <div className={styles.feedbackButtons}>
          <button
            className={`${styles.feedbackBtn} ${styles.positive}`}
            onClick={() => handleFeedback('positive')}
            aria-label="Helpful response"
            title="This was helpful"
          >
            <ThumbsUp size={14} />
          </button>
          <button
            className={`${styles.feedbackBtn} ${styles.negative}`}
            onClick={() => handleFeedback('negative')}
            aria-label="Not helpful"
            title="This wasn't helpful"
          >
            <ThumbsDown size={14} />
          </button>
          <button
            className={styles.feedbackBtn}
            aria-label="Flag issue"
            title="Report an issue"
          >
            <Flag size={14} />
          </button>
        </div>
      ) : (
        <div className={styles.feedbackGiven}>
          {feedback === 'positive' ? (
            <><ThumbsUp size={14} /> <span>Thanks!</span></>
          ) : (
            <><ThumbsDown size={14} /> <span>Tell us more...</span></>
          )}
        </div>
      )}

      {showComment && (
        <div className={styles.commentPopup}>
          <form onSubmit={handleCommentSubmit} className={styles.commentForm}>
            <div className={styles.commentHeader}>
              <MessageSquare size={14} />
              <span>What could be better?</span>
              <button
                type="button"
                className={styles.closeBtn}
                onClick={() => setShowComment(false)}
              >
                <X size={14} />
              </button>
            </div>
            <textarea
              className={styles.commentInput}
              placeholder="e.g., The answer was too vague, I needed code examples, etc."
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={3}
              autoFocus
            />
            <div className={styles.commentActions}>
              <button
                type="button"
                className={styles.skipBtn}
                onClick={() => submitFeedback('negative', '')}
              >
                Skip
              </button>
              <button
                type="submit"
                className={styles.submitBtn}
                disabled={!comment.trim()}
              >
                Submit
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
