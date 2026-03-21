import { useState, useEffect, useRef } from 'react';
import styles from './ChatStream.module.css';

/**
 * ChatStream – streaming message component that types out response
 * Props:
 *   text: string - full message text
 *   speed: number - ms per character (default: 15)
 *   onComplete: () => void - callback when streaming finishes
 *   renderContent: (text) => ReactNode - custom content renderer
 */
export default function ChatStream({ text, speed = 15, onComplete, renderContent }) {
  const [displayText, setDisplayText] = useState('');
  const [isComplete, setIsComplete] = useState(false);
  const [cursorVisible, setCursorVisible] = useState(true);
  const textRef = useRef(text);
  const indexRef = useRef(0);
  const timeoutRef = useRef(null);

  useEffect(() => {
    textRef.current = text;
    indexRef.current = 0;
    setDisplayText('');
    setIsComplete(false);

    const stream = () => {
      if (indexRef.current < textRef.current.length) {
        const nextIndex = indexRef.current + 1;
        setDisplayText(textRef.current.slice(0, nextIndex));
        indexRef.current = nextIndex;
        
        // Variable speed for natural feel
        const nextSpeed = /[.!?]$/.test(textRef.current.slice(nextIndex - 2, nextIndex)) 
          ? speed * 3  // Pause at sentence endings
          : /[,;]$/.test(textRef.current.slice(nextIndex - 1, nextIndex))
          ? speed * 1.5  // Slight pause at clauses
          : speed;
          
        timeoutRef.current = setTimeout(stream, nextSpeed);
      } else {
        setIsComplete(true);
        if (onComplete) onComplete();
      }
    };

    // Small delay before starting
    timeoutRef.current = setTimeout(stream, 100);

    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [text, speed, onComplete]);

  // Cursor blink effect
  useEffect(() => {
    if (isComplete) {
      setCursorVisible(false);
      return;
    }
    
    const interval = setInterval(() => {
      setCursorVisible(v => !v);
    }, 530);
    return () => clearInterval(interval);
  }, [isComplete]);

  const content = renderContent ? renderContent(displayText) : displayText;

  return (
    <span className={styles.streamContainer}>
      {content}
      {!isComplete && cursorVisible && (
        <span className={styles.cursor}>▋</span>
      )}
    </span>
  );
}
