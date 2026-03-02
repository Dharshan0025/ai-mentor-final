/**
 * ConceptBoard — Visual Tutor Whiteboard
 * Renders Mermaid diagrams auto-triggered by Chat agent responses.
 * Supports: flowchart, sequenceDiagram, gantt, classDiagram, stateDiagram
 */
import { useEffect, useRef, useState, useId } from 'react';
import { X, Maximize2, Copy, Check, LayoutTemplate } from 'lucide-react';
import mermaid from 'mermaid';
import styles from './ConceptBoard.module.css';

// ── Mermaid global config ─────────────────────────────────────────────────────
mermaid.initialize({
    startOnLoad: false,
    theme: 'dark',
    themeVariables: {
        background: '#0f1117',
        primaryColor: '#6366f1',
        primaryTextColor: '#f1f5f9',
        primaryBorderColor: '#4f46e5',
        lineColor: '#64748b',
        secondaryColor: '#1e293b',
        tertiaryColor: '#1e293b',
        edgeLabelBackground: '#1e293b',
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: '14px',
    },
    flowchart: { curve: 'basis', padding: 20 },
    gantt: { barHeight: 26, fontSize: 13, fontFamily: 'Inter' },
    sequence: { fontSize: 13, fontFamily: 'Inter' },
});

// ── Preset concept diagrams keyed by keyword ──────────────────────────────────
export const CONCEPT_DIAGRAMS = {
    'process scheduling': {
        title: 'Process Scheduling — Round Robin',
        type: 'gantt',
        code: `gantt
    title Round Robin Scheduling (Quantum=2)
    dateFormat X
    axisFormat %s
    section P1 (BT=4)
        Running   :a1, 0, 2
        Waiting   :crit, 2, 4
        Running   :a2, 4, 6
    section P2 (BT=3)
        Waiting   :2, 4
        Running   :b1, 4, 6
        Waiting   :6, 7
    section P3 (BT=2)
        Waiting   :4, 7
        Running   :c1, 7, 9`,
    },
    'deadlock': {
        title: 'Deadlock — Resource Allocation Graph',
        type: 'flowchart',
        code: `flowchart LR
    P1((Process P1)) -->|requests| R1[Resource R1]
    P2((Process P2)) -->|requests| R2[Resource R2]
    R1 -->|held by| P2
    R2 -->|held by| P1
    style P1 fill:#6366f1,color:#fff
    style P2 fill:#6366f1,color:#fff
    style R1 fill:#1e293b,stroke:#f59e0b,color:#f59e0b
    style R2 fill:#1e293b,stroke:#f59e0b,color:#f59e0b`,
    },
    'memory management': {
        title: 'Memory Management — Paging',
        type: 'flowchart',
        code: `flowchart TD
    CPU["CPU generates\nlogical address"] --> PT["Page Table\nlookup"]
    PT -->|page hit| Frame["Physical Frame\nin RAM"]
    PT -->|page fault| Swap["Load from\nSwap Space"]
    Swap --> Frame
    Frame --> MA["Physical Memory\nAccess ✓"]
    style CPU fill:#6366f1,color:#fff
    style PT fill:#1e293b,stroke:#6366f1
    style Frame fill:#10b981,color:#fff
    style Swap fill:#f59e0b,color:#000
    style MA fill:#10b981,color:#fff`,
    },
    'tcp': {
        title: 'TCP 3-Way Handshake',
        type: 'sequenceDiagram',
        code: `sequenceDiagram
    participant C as Client
    participant S as Server
    C->>S: SYN (seq=x)
    Note over C,S: Connection request
    S->>C: SYN-ACK (seq=y, ack=x+1)
    Note over C,S: Server acknowledges
    C->>S: ACK (ack=y+1)
    Note over C,S: Connection established ✓`,
    },
    'osi model': {
        title: 'OSI Model — 7 Layers',
        type: 'flowchart',
        code: `flowchart TB
    A7["7 — Application\n(HTTP, FTP, SMTP)"] --> A6
    A6["6 — Presentation\n(SSL, Encryption)"] --> A5
    A5["5 — Session\n(NetBIOS, RPC)"] --> A4
    A4["4 — Transport\n(TCP, UDP)"] --> A3
    A3["3 — Network\n(IP, ICMP)"] --> A2
    A2["2 — Data Link\n(Ethernet, MAC)"] --> A1
    A1["1 — Physical\n(Cables, Signals)"]
    style A7 fill:#6366f1,color:#fff
    style A4 fill:#f59e0b,color:#000
    style A1 fill:#10b981,color:#fff`,
    },
    'normalization': {
        title: 'Database Normalization — 1NF → BCNF',
        type: 'flowchart',
        code: `flowchart LR
    UN["Unnormalized\nTable"] -->|"Remove repeating\ngroups"| NF1["1NF\n(Atomic values)"]
    NF1 -->|"Remove partial\ndependencies"| NF2["2NF\n(Full dependency)"]
    NF2 -->|"Remove transitive\ndependencies"| NF3["3NF\n(No transitive dep)"]
    NF3 -->|"Every determinant\nis a candidate key"| BCNF["BCNF\n(Boyce-Codd)"]
    style UN fill:#ef4444,color:#fff
    style NF1 fill:#f59e0b,color:#000
    style NF2 fill:#f59e0b,color:#000
    style NF3 fill:#10b981,color:#fff
    style BCNF fill:#6366f1,color:#fff`,
    },
    'neural network': {
        title: 'Neural Network — Forward Pass',
        type: 'flowchart',
        code: `flowchart LR
    I1((x1)) & I2((x2)) & I3((x3)) --> H1((h1))
    I1 & I2 & I3 --> H2((h2))
    I1 & I2 & I3 --> H3((h3))
    H1 & H2 & H3 --> O1((ŷ))
    subgraph Input[ Input Layer]
        I1; I2; I3
    end
    subgraph Hidden[Hidden Layer]
        H1; H2; H3
    end
    subgraph Output[Output Layer]
        O1
    end
    style I1 fill:#6366f1,color:#fff
    style I2 fill:#6366f1,color:#fff
    style I3 fill:#6366f1,color:#fff
    style H1 fill:#f59e0b,color:#000
    style H2 fill:#f59e0b,color:#000
    style H3 fill:#f59e0b,color:#000
    style O1 fill:#10b981,color:#fff`,
    },
    'sdlc': {
        title: 'SDLC — Agile Sprint Cycle',
        type: 'flowchart',
        code: `flowchart LR
    PB["Product Backlog"] --> SP["Sprint Planning\n(2 weeks)"]
    SP --> SD["Sprint Development\n(Daily Standups)"]
    SD --> SR["Sprint Review\n+ Retrospective"]
    SR -->|next sprint| SP
    SR -->|done| RL["Release to\nProduction ✓"]
    style PB fill:#1e293b,stroke:#6366f1
    style SP fill:#6366f1,color:#fff
    style SD fill:#f59e0b,color:#000
    style SR fill:#10b981,color:#fff
    style RL fill:#10b981,color:#fff`,
    },
    'cloud': {
        title: 'Cloud Architecture — IaaS / PaaS / SaaS',
        type: 'flowchart',
        code: `flowchart TB
    U[("User / Browser")] --> CDN["CDN\n(Edge Caching)"]
    CDN --> LB["Load Balancer"]
    LB --> A1["App Server 1\n(Docker)"] & A2["App Server 2\n(Docker)"]
    A1 & A2 --> DB[("Managed DB\n(RDS)")]
    A1 & A2 --> Cache["Redis Cache"]
    A1 & A2 --> S3["Object Storage\n(S3)"]
    style U fill:#6366f1,color:#fff
    style LB fill:#f59e0b,color:#000
    style DB fill:#10b981,color:#fff`,
    },
};

// ── Keyword detection ─────────────────────────────────────────────────────────
export function detectDiagramKeyword(text) {
    const lower = text.toLowerCase();
    for (const key of Object.keys(CONCEPT_DIAGRAMS)) {
        if (lower.includes(key)) return key;
    }
    return null;
}

// ── Main component ────────────────────────────────────────────────────────────
export default function ConceptBoard({ keyword, customCode, customTitle, onClose }) {
    const id = useId().replace(/:/g, '');
    const containerRef = useRef(null);
    const [fullscreen, setFullscreen] = useState(false);
    const [copied, setCopied] = useState(false);
    const [svgHtml, setSvgHtml] = useState('');
    const [error, setError] = useState(null);

    const diagram = keyword ? CONCEPT_DIAGRAMS[keyword] : null;
    const code = customCode || diagram?.code || '';
    const title = customTitle || diagram?.title || 'Concept Diagram';

    useEffect(() => {
        if (!code) return;
        setSvgHtml('');
        setError(null);

        mermaid.render(`cb_${id}`, code)
            .then(({ svg }) => setSvgHtml(svg))
            .catch(err => {
                console.error('[ConceptBoard] render error:', err);
                setError('Diagram could not be rendered. Check syntax.');
            });
    }, [code, id]);

    function copyCode() {
        navigator.clipboard.writeText(code).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1800);
        });
    }

    return (
        <div className={`${styles.board} ${fullscreen ? styles.fullscreen : ''}`}>
            {/* Header */}
            <div className={styles.header}>
                <div className={styles.headerLeft}>
                    <LayoutTemplate size={14} className={styles.headerIcon} />
                    <span className={styles.title}>{title}</span>
                </div>
                <div className={styles.controls}>
                    <button className={styles.ctrl} onClick={copyCode} title="Copy diagram code">
                        {copied ? <Check size={13} /> : <Copy size={13} />}
                    </button>
                    <button className={styles.ctrl} onClick={() => setFullscreen(f => !f)} title="Toggle fullscreen">
                        <Maximize2 size={13} />
                    </button>
                    {onClose && (
                        <button className={styles.ctrl} onClick={onClose} title="Close">
                            <X size={13} />
                        </button>
                    )}
                </div>
            </div>

            {/* Canvas */}
            <div className={styles.canvas} ref={containerRef}>
                {!svgHtml && !error && (
                    <div className={styles.loadingState}>
                        <div className={styles.loadingRing} />
                        <span>Rendering diagram...</span>
                    </div>
                )}
                {error && (
                    <div className={styles.errorState}>
                        <span>⚠️</span>
                        <p>{error}</p>
                    </div>
                )}
                {svgHtml && (
                    <div
                        className={styles.svgWrapper}
                        dangerouslySetInnerHTML={{ __html: svgHtml }}
                    />
                )}
            </div>

            {/* Footer legend */}
            <div className={styles.footer}>
                <span className={styles.footerTag}>📐 AI Concept Visualization · Auto-rendered from ERP query</span>
            </div>
        </div>
    );
}
