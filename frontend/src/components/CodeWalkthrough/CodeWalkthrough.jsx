/**
 * CodeWalkthrough — syntax-highlighted code block with line highlighting
 * Receives { language, code, highlight_lines, explanation }
 * Highlights specific lines with an amber glow border.
 * No external syntax-highlighter dependency — uses CSS-based approach.
 */
import styles from './CodeWalkthrough.module.css';

export default function CodeWalkthrough({ language = 'python', code, highlight_lines = [], explanation, step }) {
    if (!code) return null;

    const lines = code.split('\n');

    return (
        <div className={styles.wrapper}>
            {/* Header */}
            <div className={styles.header}>
                <div className={styles.dots}>
                    <span className={styles.dot} />
                    <span className={styles.dot} />
                    <span className={styles.dot} />
                </div>
                <span className={styles.lang}>{language}</span>
                {step && <span className={styles.stepTag}>Step {step}</span>}
            </div>

            {/* Code body */}
            <div className={styles.body}>
                <pre className={styles.pre}>
                    {lines.map((line, i) => {
                        const lineNum = i + 1;
                        const isHighlighted = highlight_lines.includes(lineNum);
                        return (
                            <div
                                key={i}
                                className={`${styles.line} ${isHighlighted ? styles.lineHighlighted : ''}`}
                            >
                                <span className={styles.lineNum}>{lineNum}</span>
                                <span className={styles.lineContent}>{line || ' '}</span>
                            </div>
                        );
                    })}
                </pre>
            </div>

            {/* Explanation */}
            {explanation && (
                <div className={styles.explanation}>
                    <span className={styles.explainIcon}>💡</span>
                    <span>{explanation}</span>
                </div>
            )}
        </div>
    );
}
