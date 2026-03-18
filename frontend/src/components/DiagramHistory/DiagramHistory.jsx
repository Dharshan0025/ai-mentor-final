import { useState, useEffect } from 'react';
import { getSessionDiagrams } from '../../services/api';
import mermaid from 'mermaid';
import styles from './DiagramHistory.module.css';

/**
 * DiagramHistory — shows all diagrams generated in past sessions.
 * Lets student browse, zoom, and download any saved diagram (V2).
 */
export function DiagramHistory({ sessionId = null, onClose }) {
    const [diagrams, setDiagrams]   = useState([]);
    const [loading, setLoading]     = useState(true);
    const [active, setActive]       = useState(null);   // index of zoomed diagram
    const [rendered, setRendered]   = useState({});      // id -> svg string

    useEffect(() => {
        getSessionDiagrams(sessionId, 40)
            .then(r => { setDiagrams(r.diagrams || []); })
            .finally(() => setLoading(false));
    }, [sessionId]);

    // Render mermaid SVG for each diagram lazily
    useEffect(() => {
        if (!diagrams.length) return;
        diagrams.forEach(async (d) => {
            if (rendered[d.id]) return;
            try {
                const { svg } = await mermaid.render(
                    `hist-${d.id}`, d.mermaid_code.replace(/^```mermaid\s*/i, '').replace(/```\s*$/, '').trim()
                );
                setRendered(prev => ({ ...prev, [d.id]: svg }));
            } catch {
                setRendered(prev => ({ ...prev, [d.id]: null }));
            }
        });
    }, [diagrams]);

    function downloadSvg(d) {
        const svg = rendered[d.id];
        if (!svg) return;
        const blob = new Blob([svg], { type: 'image/svg+xml' });
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href     = url;
        a.download = `${d.diagram_title || 'diagram'}-step${d.step_num}.svg`;
        a.click();
        URL.revokeObjectURL(url);
    }

    return (
        <div className={styles.overlay}>
            <div className={styles.panel}>
                <div className={styles.header}>
                    <h3>📽️ Diagram History</h3>
                    <button className={styles.close} onClick={onClose}>✕</button>
                </div>

                {loading && <div className={styles.loading}>Loading diagrams…</div>}
                {!loading && diagrams.length === 0 && (
                    <div className={styles.empty}>No diagrams saved yet. Start a lesson to see them here!</div>
                )}

                {active !== null && (
                    <div className={styles.zoom} onClick={() => setActive(null)}>
                        <div className={styles.zoomInner} onClick={e => e.stopPropagation()}>
                            <div className={styles.zoomHeader}>
                                <span>{diagrams[active]?.diagram_title}</span>
                                <div className={styles.zoomActions}>
                                    <button onClick={() => downloadSvg(diagrams[active])}>⬇ Download SVG</button>
                                    <button onClick={() => setActive(null)}>✕ Close</button>
                                </div>
                            </div>
                            {rendered[diagrams[active]?.id] ? (
                                <div
                                    className={styles.zoomSvg}
                                    dangerouslySetInnerHTML={{ __html: rendered[diagrams[active]?.id] }}
                                />
                            ) : <div className={styles.loading}>Rendering…</div>}
                        </div>
                    </div>
                )}

                <div className={styles.grid}>
                    {diagrams.map((d, i) => (
                        <div key={d.id} className={styles.card} onClick={() => setActive(i)}>
                            <div className={styles.cardTop}>
                                {rendered[d.id] ? (
                                    <div
                                        className={styles.preview}
                                        dangerouslySetInnerHTML={{ __html: rendered[d.id] }}
                                    />
                                ) : (
                                    <div className={styles.previewPlaceholder}>
                                        {rendered[d.id] === null ? '⚠ Render error' : 'Loading…'}
                                    </div>
                                )}
                            </div>
                            <div className={styles.cardBottom}>
                                <span className={styles.cardTitle}>{d.diagram_title || 'Diagram'}</span>
                                <span className={styles.cardMeta}>Step {d.step_num} · {d.topic}</span>
                                <button
                                    className={styles.dlBtn}
                                    onClick={e => { e.stopPropagation(); downloadSvg(d); }}
                                    disabled={!rendered[d.id]}
                                >
                                    ⬇
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

export default DiagramHistory;
