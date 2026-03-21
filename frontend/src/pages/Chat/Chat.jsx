import { useState, useRef, useEffect, useCallback, lazy, Suspense } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { Send, Zap, BookOpen, Brain, Heart, Calendar, TrendingUp, Briefcase, ChevronRight, AlertTriangle, BarChart2 } from 'lucide-react';
import { v4 as uuidv4 } from 'uuid';
import styles from './Chat.module.css';
import { sendChatMessage, getStoredStudent, getBriefing, getChatSessions, getChatHistory } from '../../services/api';
import VoiceMentor from '../../components/VoiceMentor/VoiceMentor';
import ChatWidgets from '../../components/ChatWidgets/ChatWidgets';
import SuggestedActions from '../../components/SuggestedActions/SuggestedActions';
import XPConfetti from '../../components/XPConfetti/XPConfetti';
const ConceptBoard = lazy(() => import('../../components/ConceptBoard/ConceptBoard'));

// ── Agent metadata ─────────────────────────────────────────────────────────────
const AGENT_META = {
    academic: { label: 'Academic', icon: BookOpen, color: 'var(--agent-academic)', accent: '#3b82f6' },
    prediction: { label: 'Prediction', icon: TrendingUp, color: 'var(--agent-prediction)', accent: '#f59e0b' },
    emotional: { label: 'Emotional', icon: Heart, color: 'var(--agent-emotional)', accent: '#ec4899' },
    learning: { label: 'Learning', icon: Brain, color: 'var(--agent-learning)', accent: '#10b981' },
    schedule: { label: 'Schedule', icon: Calendar, color: 'var(--agent-schedule)', accent: '#8b5cf6' },
    career: { label: 'Career', icon: Briefcase, color: 'var(--agent-career)', accent: '#06b6d4' },
    orchestrator: { label: 'Mentor', icon: Zap, color: 'var(--accent)', accent: '#6366f1' },
};

// ── Pipeline stages shown while loading ──────────────────────────────────────
const PIPELINE_STAGES = [
    { id: 'intent', label: 'Parsing intent', delay: 0 },
    { id: 'route', label: 'Routing to agents', delay: 600 },
    { id: 'fetch', label: 'Loading ERP context', delay: 1200 },
    { id: 'compute', label: 'Computing insights', delay: 2000 },
    { id: 'compose', label: 'Composing response', delay: 2800 },
];

// ── Action chips per agent type ───────────────────────────────────────────────
const AGENT_CHIPS = {
    academic: [{ label: '📊 View Predictions', path: '/prediction' }, { label: '📅 Get Schedule', path: '/schedule' }, { label: '🧪 Take Quiz', path: '/learning' }],
    prediction: [{ label: '📅 Build Study Plan', path: '/schedule' }, { label: '📊 Full Prediction', path: '/prediction' }],
    emotional: [{ label: '📅 Plan Rest Day', path: '/schedule' }, { label: '📖 Study Tips', path: '/learning' }],
    learning: [{ label: '🧪 Start Quiz', path: '/learning' }, { label: '📅 Schedule Practice', path: '/schedule' }],
    schedule: [{ label: '📅 View Full Schedule', path: '/schedule' }, { label: '🧪 Start Session', path: '/learning' }],
    career: [{ label: '💼 Career Dashboard', path: '/career' }, { label: '🧪 Skill Quiz', path: '/learning' }],
};

// ── Quick prompts shown in the empty state ────────────────────────────────────
const QUICK_PROMPTS = [
    { icon: '📊', text: 'How is my CGPA trending?' },
    { icon: '⚠️', text: 'Which subjects am I at risk in?' },
    { icon: '📅', text: 'Build me a study plan for this week' },
    { icon: '💼', text: 'What career paths suit my profile?' },
    { icon: '🧪', text: 'Quiz me on Operating Systems' },
    { icon: '😟', text: 'I\'m stressed about exams' },
];

// ── Structured markdown renderer ─────────────────────────────────────────────
function renderInline(text, keyPrefix = 'inline') {
    const source = String(text || '');
    const tokenRegex = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g;
    const nodes = [];
    let lastIndex = 0;
    let match;
    let part = 0;

    while ((match = tokenRegex.exec(source)) !== null) {
        if (match.index > lastIndex) {
            nodes.push(source.slice(lastIndex, match.index));
        }

        const token = match[0];
        if (token.startsWith('**') && token.endsWith('**')) {
            nodes.push(<strong key={`${keyPrefix}-strong-${part}`}>{token.slice(2, -2)}</strong>);
        } else if (token.startsWith('`') && token.endsWith('`')) {
            nodes.push(<code key={`${keyPrefix}-code-${part}`}>{token.slice(1, -1)}</code>);
        } else if (token.startsWith('*') && token.endsWith('*')) {
            nodes.push(<em key={`${keyPrefix}-em-${part}`}>{token.slice(1, -1)}</em>);
        } else {
            nodes.push(token);
        }

        lastIndex = tokenRegex.lastIndex;
        part += 1;
    }

    if (lastIndex < source.length) {
        nodes.push(source.slice(lastIndex));
    }

    return nodes.length ? nodes : source;
}

function isTableDivider(line) {
    return /^\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?$/.test(line);
}

function parseTableRow(line) {
    return line
        .trim()
        .replace(/^\|/, '')
        .replace(/\|$/, '')
        .split('|')
        .map(cell => cell.trim());
}

function isSpecialBlockStart(line, nextLine = '') {
    return (
        line.startsWith('```') ||
        /^##\s+/.test(line) ||
        /^###\s+/.test(line) ||
        /^\d+\.\s+/.test(line) ||
        /^[-*•]\s+/.test(line) ||
        (line.startsWith('|') && isTableDivider(nextLine))
    );
}

function renderStructuredContent(text) {
    const raw = String(text || '').replace(/\r\n?/g, '\n');
    const lines = raw.split('\n');
    const blocks = [];
    let i = 0;

    while (i < lines.length) {
        const line = lines[i];
        const trimmed = line.trim();
        const nextTrimmed = lines[i + 1]?.trim() || '';

        if (!trimmed) {
            i += 1;
            continue;
        }

        if (trimmed.startsWith('```')) {
            const codeLines = [];
            i += 1;
            while (i < lines.length && !lines[i].trim().startsWith('```')) {
                codeLines.push(lines[i]);
                i += 1;
            }
            if (i < lines.length) i += 1;
            blocks.push(
                <pre key={`code-${blocks.length}`} className={styles.codeBlock}>
                    <code>{codeLines.join('\n')}</code>
                </pre>
            );
            continue;
        }

        if (trimmed.startsWith('|') && isTableDivider(nextTrimmed)) {
            const headers = parseTableRow(trimmed);
            const rows = [];
            i += 2;
            while (i < lines.length && lines[i].trim().startsWith('|')) {
                const row = parseTableRow(lines[i]);
                if (row.some(cell => cell.length > 0)) rows.push(row);
                i += 1;
            }

            blocks.push(
                <div key={`table-${blocks.length}`} className={styles.tableWrap}>
                    <table className={styles.table}>
                        <thead>
                            <tr>
                                {headers.map((header, idx) => (
                                    <th key={`th-${idx}`}>{renderInline(header, `th-${idx}`)}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((row, rowIdx) => (
                                <tr key={`row-${rowIdx}`}>
                                    {headers.map((_, colIdx) => (
                                        <td key={`cell-${rowIdx}-${colIdx}`}>
                                            {renderInline(row[colIdx] || '', `cell-${rowIdx}-${colIdx}`)}
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            );
            continue;
        }

        if (/^###\s+/.test(trimmed)) {
            blocks.push(
                <h3 key={`h3-${blocks.length}`}>
                    {renderInline(trimmed.replace(/^###\s+/, ''), `h3-${blocks.length}`)}
                </h3>
            );
            i += 1;
            continue;
        }

        if (/^##\s+/.test(trimmed)) {
            blocks.push(
                <h2 key={`h2-${blocks.length}`}>
                    {renderInline(trimmed.replace(/^##\s+/, ''), `h2-${blocks.length}`)}
                </h2>
            );
            i += 1;
            continue;
        }

        if (/^\d+\.\s+/.test(trimmed)) {
            const items = [];
            while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
                items.push(lines[i].trim().replace(/^\d+\.\s+/, ''));
                i += 1;
            }
            blocks.push(
                <ol key={`ol-${blocks.length}`}>
                    {items.map((item, idx) => (
                        <li key={`oli-${idx}`}>{renderInline(item, `oli-${idx}`)}</li>
                    ))}
                </ol>
            );
            continue;
        }

        if (/^[-*•]\s+/.test(trimmed)) {
            const items = [];
            while (i < lines.length && /^[-*•]\s+/.test(lines[i].trim())) {
                items.push(lines[i].trim().replace(/^[-*•]\s+/, ''));
                i += 1;
            }
            blocks.push(
                <ul key={`ul-${blocks.length}`}>
                    {items.map((item, idx) => (
                        <li key={`uli-${idx}`}>{renderInline(item, `uli-${idx}`)}</li>
                    ))}
                </ul>
            );
            continue;
        }

        const paragraphLines = [];
        while (i < lines.length) {
            const paragraphLine = lines[i].trim();
            const paragraphNext = lines[i + 1]?.trim() || '';
            if (!paragraphLine || isSpecialBlockStart(paragraphLine, paragraphNext)) break;
            paragraphLines.push(paragraphLine);
            i += 1;
        }

        if (paragraphLines.length) {
            blocks.push(
                <p key={`p-${blocks.length}`}>
                    {renderInline(paragraphLines.join(' '), `p-${blocks.length}`)}
                </p>
            );
            continue;
        }

        i += 1;
    }

    return blocks.length ? blocks : <p>{raw}</p>;
}

// ── Orchestration Pipeline Visualizer ────────────────────────────────────────
function OrchestrationPipeline({ agent }) {
    const [activeStage, setActiveStage] = useState(0);

    useEffect(() => {
        PIPELINE_STAGES.forEach((stage, i) => {
            const t = setTimeout(() => setActiveStage(i + 1), stage.delay);
            return () => clearTimeout(t);
        });
    }, []);

    const meta = AGENT_META[agent] || AGENT_META.orchestrator;
    const AgentIcon = meta.icon;

    return (
        <div className={styles.pipeline}>
            <div className={styles.pipelineHeader}>
                <span className={styles.pipelinePulse} style={{ background: meta.accent }} />
                <AgentIcon size={13} style={{ color: meta.accent }} />
                <span className={styles.pipelineLabel}>{meta.label} agent processing</span>
            </div>
            <div className={styles.pipelineStages}>
                {PIPELINE_STAGES.map((stage, i) => (
                    <div key={stage.id} className={`${styles.pipelineStage} ${i < activeStage ? styles.pipelineDone : ''} ${i === activeStage - 1 ? styles.pipelineActive : ''}`}>
                        <div className={styles.pipelineDot} />
                        <span className={styles.pipelineStageName}>{stage.label}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ── Agent Response Card ───────────────────────────────────────────────────────
function AgentCard({ msg, onChipClick }) {
    const meta = AGENT_META[msg.agent] || AGENT_META.orchestrator;
    const AgentIcon = meta.icon;
    const chips = AGENT_CHIPS[msg.agent] || [];
    const [diagramClosed, setDiagramClosed] = useState(false);
    const diagramKey = msg.uiCard?.type === 'concept_board' ? msg.uiCard.data?.keyword : null;
    const showDiagram = !!diagramKey && !diagramClosed;

    return (
        <div className={styles.msgRowAgent}>
            {/* Agent badge */}
            <div className={styles.agentBadge} style={{ '--agent-c': meta.accent }}>
                <div className={styles.agentBadgeIcon}>
                    <AgentIcon size={12} />
                </div>
                <span className={styles.agentBadgeLabel}>{meta.label} Agent</span>
                <span className={styles.agentBadgeDot} />
                <span className={styles.agentBadgeStatus}>ERP-grounded</span>
            </div>

            {/* Card body */}
            <div className={styles.agentCard} style={{ '--agent-c': meta.accent }}>
                <div className={styles.cardContent}>
                    {renderStructuredContent(msg.text)}
                </div>

                {/* Citations */}
                {msg.citations?.length > 0 && (
                    <div className={styles.citations}>
                        {msg.citations.map((c, i) => (
                            <span key={i} className={styles.citation}>
                                🗂 {typeof c === 'object' ? c.label || String(c) : c}
                            </span>
                        ))}
                    </div>
                )}

                {/* Action chips */}
                {chips.length > 0 && (
                    <div className={styles.chips}>
                        {chips.map((chip, i) => (
                            <button
                                key={i}
                                className={styles.chip}
                                onClick={() => onChipClick(chip.path)}
                            >
                                {chip.label}
                                <ChevronRight size={11} />
                            </button>
                        ))}
                    </div>
                )}

                {/* Show Your Work / Reasoning */}
                <details className={styles.reasoningDrawer}>
                    <summary><Brain size={12} /> AI Reasoning Log</summary>
                    <div className={styles.reasoningContent}>
                        <p><strong>Primary Agent:</strong> {meta.label}</p>
                        <p><strong>Context Status:</strong> ERP-Grounded</p>
                        {msg.citations?.length > 0 && <p><strong>Sources Cited:</strong> {msg.citations.length}</p>}
                    </div>
                </details>
            </div>

            {/* Visual concept board — auto-rendered when topic matches */}
            {showDiagram && (
                <Suspense fallback={null}>
                    <ConceptBoard
                        keyword={diagramKey}
                        customCode={msg.uiCard.data?.code}
                        onClose={() => setDiagramClosed(true)}
                    />
                </Suspense>
            )}
        </div>
    );
}

// ── Briefing Alert Strip ──────────────────────────────────────────────────────
function BriefingStrip({ alerts }) {
    const [dismissed, setDismissed] = useState(false);
    if (dismissed || !alerts?.length) return null;

    const critical = alerts.find(a => a.type === 'critical');
    const top = critical || alerts[0];

    return (
        <div className={`${styles.briefingStrip} ${top.type === 'critical' ? styles.briefingCritical : top.type === 'warning' ? styles.briefingWarning : styles.briefingInfo}`}>
            <span className={styles.briefingIcon}>{top.icon}</span>
            <span className={styles.briefingText}>{top.message}</span>
            <button className={styles.briefingDismiss} onClick={() => setDismissed(true)}>✕</button>
        </div>
    );
}

// ── User bubble ───────────────────────────────────────────────────────────────
function UserBubble({ text }) {
    return (
        <div className={styles.msgRowUser}>
            <div className={styles.userBubble}>{text}</div>
        </div>
    );
}

// ── Empty state with quick prompts ────────────────────────────────────────────
function EmptyState({ student, onPrompt }) {
    return (
        <div className={styles.emptyState}>
            <div className={styles.emptyAvatar}>
                {student?.name?.charAt(0) || 'A'}
            </div>
            <h2 className={styles.emptyTitle}>
                Good evening, {student?.name?.split(' ')[0] || 'Student'}
            </h2>
            <p className={styles.emptySub}>
                Your ERP profile is loaded · Sem {student?.current_semester || '—'} · CGPA {student?.cgpa || '—'}
            </p>
            <div className={styles.quickGrid}>
                {QUICK_PROMPTS.map((p, i) => (
                    <button key={i} className={styles.quickCard} onClick={() => onPrompt(p.text)}>
                        <span className={styles.quickIcon}>{p.icon}</span>
                        <span className={styles.quickText}>{p.text}</span>
                    </button>
                ))}
            </div>
        </div>
    );
}

// ── Context sidebar ───────────────────────────────────────────────────────────
function ContextPanel({ student, briefing }) {
    if (!student) return null;
    const subjects = student.subjects || [];
    const riskCount = subjects.filter(s => s.status !== 'safe').length;
    // Support both camelCase (from ERP profile) and snake_case (legacy)
    const cgpa = student.currentCGPA ?? student.cgpa;
    const examDays = student.examDays ?? student.exam_days;
    const sem = student.semester ?? student.current_semester;
    const dept = student.department ?? student.dept;

    return (
        <aside className={styles.contextPanel}>
            <div className={styles.contextHeader}>
                <div className={styles.contextAvatar}>{student.name?.charAt(0)}</div>
                <div>
                    <div className={styles.contextName}>{student.name}</div>
                    <div className={styles.contextSub}>Sem {sem} · {dept?.slice(0, 18)}</div>
                </div>
            </div>

            <div className={styles.contextStats}>
                {[
                    { label: 'CGPA', val: cgpa ?? '—', highlight: true },
                    { label: 'At Risk', val: riskCount, danger: riskCount > 0 },
                    { label: 'Exam', val: examDays ? `${examDays}d` : '—' },
                ].map((s, i) => (
                    <div key={i} className={`${styles.contextStat} ${s.highlight ? styles.statHighlight : ''} ${s.danger ? styles.statDanger : ''}`}>
                        <span className={styles.statVal}>{s.val}</span>
                        <span className={styles.statLabel}>{s.label}</span>
                    </div>
                ))}
            </div>

            {/* Subject risk bars */}
            <div className={styles.sideSection}>
                <span className={styles.sideSectionTitle}>Subject Status</span>
                {subjects.slice(0, 6).map((s, i) => {
                    const att = s.live_attendance ?? s.attendance ?? 0;
                    const pct = Math.min(100, att);
                    return (
                        <div key={i} className={styles.subjectRow}>
                            <div className={styles.subjectMeta}>
                                <span className={styles.subjectName}>{s.name?.slice(0, 16)}</span>
                                <span className={`${styles.subjectStatus} ${styles[s.status]}`}>
                                    {s.status}
                                </span>
                            </div>
                            <div className={styles.attBar}>
                                <div
                                    className={`${styles.attFill} ${styles[s.status]}`}
                                    style={{ width: `${pct}%` }}
                                />
                            </div>
                            <span className={styles.attPct}>{att}%</span>
                        </div>
                    );
                })}
            </div>

            {/* Briefing summary */}
            {briefing?.summary && (
                <div className={styles.sideSection}>
                    <span className={styles.sideSectionTitle}>Intelligence Brief</span>
                    <div className={styles.briefSummary}>
                        {briefing.summary.critical > 0 && (
                            <div className={styles.briefItem + ' ' + styles.briefCritical}>
                                <AlertTriangle size={11} /> {briefing.summary.critical} critical
                            </div>
                        )}
                        {briefing.summary.warning > 0 && (
                            <div className={styles.briefItem + ' ' + styles.briefWarning}>
                                <BarChart2 size={11} /> {briefing.summary.warning} warnings
                            </div>
                        )}
                        {briefing.summary.info > 0 && (
                            <div className={styles.briefItem + ' ' + styles.briefInfoItem}>
                                <Zap size={11} /> {briefing.summary.info} insights
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Active agents */}
            <div className={styles.sideSection}>
                <span className={styles.sideSectionTitle}>Active Agents</span>
                <div className={styles.agentPills}>
                    {Object.entries(AGENT_META).slice(0, 6).map(([id, meta]) => (
                        <div key={id} className={styles.agentPill}>
                            <span className={styles.agentPillDot} style={{ background: meta.accent }} />
                            <span className={styles.agentPillName}>{meta.label}</span>
                        </div>
                    ))}
                </div>
            </div>
        </aside>
    );
}

// ── Main Chat component ───────────────────────────────────────────────────────
export default function Chat() {
    const location = useLocation();
    const navigate = useNavigate();
    const [searchParams, setSearchParams] = useSearchParams();
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [loadingAgent, setLoadingAgent] = useState('orchestrator');
    const [sessionId, setSessionId] = useState(() => uuidv4());
    const [briefing, setBriefing] = useState(null);
    const [student, setStudent] = useState(null);
    const [lastResponse, setLastResponse] = useState('');
    const [pendingXP, setPendingXP] = useState(0);
    const bottomRef = useRef(null);
    const prefillHandledRef = useRef(false);

    // Load student from localStorage + briefing from API
    useEffect(() => {
        const stored = getStoredStudent();
        if (stored) setStudent(stored);

        getBriefing()
            .then(data => setBriefing(data))
            .catch(() => { }); // briefing is non-critical

        // Load chat history
        getChatSessions()
            .then(sessions => {
                if (sessions?.length > 0) {
                    const latestSession = sessions[0];
                    setSessionId(latestSession.id);
                    return getChatHistory(latestSession.id);
                }
                return null;
            })
            .then(hist => {
                if (hist?.length > 0) {
                    const loadedMessages = hist.map(m => ({
                        role: m.role === 'user' ? 'user' : 'agent',
                        agent: m.agent || 'academic',
                        text: m.content || '',
                        citations: m.citations ? (typeof m.citations === 'string' ? JSON.parse(m.citations) : m.citations) : []
                    }));
                    setMessages(loadedMessages);
                }
            })
            .catch(() => {});
    }, []);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, loading]);

    const sendMessage = useCallback(async (text) => {
        const msg = (text || input).trim();
        if (!msg || loading) return;

        setInput('');
        setMessages(m => [...m, { role: 'user', text: msg }]);
        setLoading(true);
        setLoadingAgent('orchestrator');

        const history = messages.slice(-10).map(m => ({
            role: m.role === 'user' ? 'user' : 'assistant',
            content: m.text,
        }));

        try {
            const response = await sendChatMessage({ message: msg, sessionId, lang: 'en', history });
            setLoadingAgent(response.agent || 'academic');
            setMessages(m => [...m, {
                role: 'agent',
                agent: response.agent || 'academic',
                text: response.content || 'I had trouble processing that.',
                citations: response.citations || [],
                uiCard: response.ui_card || null,
                suggestedActions: response.suggested_actions || [],
            }]);
            setLastResponse(response.content || '');
            if (response.xp_awarded > 0) setPendingXP(response.xp_awarded);
        } catch (err) {
            const errText = err.response?.status === 503
                ? '⚠️ The AI service is temporarily offline. Please try again in a moment.'
                : '⚠️ Something went wrong. Please try again.';
            setMessages(m => [...m, { role: 'agent', agent: 'academic', text: errText, citations: [] }]);
        } finally {
            setLoading(false);
        }
    }, [input, loading, messages, sessionId]);

    useEffect(() => {
        const stateMessage = location.state?.initialMessage?.trim();
        const queryMessage = searchParams.get('q')?.trim();
        const initialMessage = stateMessage || queryMessage;

        if (!initialMessage || prefillHandledRef.current || loading) return;

        prefillHandledRef.current = true;
        setInput(initialMessage);
        sendMessage(initialMessage);

        if (stateMessage) {
            navigate(location.pathname, { replace: true, state: null });
        }

        if (queryMessage) {
            const nextParams = new URLSearchParams(searchParams);
            nextParams.delete('q');
            setSearchParams(nextParams, { replace: true });
        }
    }, [location.pathname, location.state, navigate, loading, searchParams, sendMessage, setSearchParams]);

    const handleChipClick = (path) => {
        navigate(path);
    };

    const showEmpty = messages.length === 0 && !loading;

    return (
        <div className={styles.layout}>
            <ContextPanel student={student} briefing={briefing} />

            <div className={styles.chatArea}>
                {/* Briefing strip at top */}
                <BriefingStrip alerts={briefing?.briefing} />

                {/* Messages */}
                <div className={styles.messages}>
                    {showEmpty && (
                        <EmptyState student={student} onPrompt={(t) => sendMessage(t)} />
                    )}

                    {messages.map((msg, i) =>
                        msg.role === 'user'
                            ? <UserBubble key={i} text={msg.text} />
                            : (
                                <div key={i}>
                                    <AgentCard msg={msg} onChipClick={handleChipClick} />
                                    {msg.uiCard && <ChatWidgets uiCard={msg.uiCard} onQuizAnswer={(ans) => sendMessage(`My answer to the quiz is: ${ans}`)} />}
                                    {msg.suggestedActions?.length > 0 && (
                                        <SuggestedActions
                                            actions={msg.suggestedActions}
                                            onSelect={(prompt) => sendMessage(prompt)}
                                        />
                                    )}
                                </div>
                            )
                    )}

                    {/* XP confetti overlay */}
                    <XPConfetti xp={pendingXP} onDone={() => setPendingXP(0)} />

                    {/* Live orchestration visualizer */}
                    {loading && (
                        <div className={styles.msgRowAgent}>
                            <OrchestrationPipeline agent={loadingAgent} />
                        </div>
                    )}

                    <div ref={bottomRef} />
                </div>

                {/* Input area */}
                <div className={styles.inputArea}>
                    {/* Predictive Smart Prompts */}
                    {!showEmpty && !loading && (
                        <div className={styles.smartPrompts}>
                            <button className={styles.smartPromptBtn} onClick={() => sendMessage("🎯 What should be my focus today?")}>🎯 Focus for today</button>
                            <button className={styles.smartPromptBtn} onClick={() => sendMessage("🧪 Quiz me on my weakest subject")}>🧪 Quick Quiz</button>
                            <button className={styles.smartPromptBtn} onClick={() => sendMessage("📅 Build a study plan for this week")}>📅 Weekly Plan</button>
                            <button className={styles.smartPromptBtn} onClick={() => sendMessage("🧠 Explain a complex concept using a diagram")}>🧠 Whiteboard a concept</button>
                        </div>
                    )}
                    <div className={`${styles.inputBar} ${loading ? styles.inputBarBusy : ''}`}>
                        <input
                            id="chat-input"
                            className={styles.input}
                            value={input}
                            onChange={e => setInput(e.target.value)}
                            placeholder="Ask anything — your ERP data is loaded..."
                            onKeyDown={e => e.key === 'Enter' && sendMessage()}
                            disabled={loading}
                            autoComplete="off"
                        />
                        <VoiceMentor variant="inline" onTranscript={(t) => { setInput(t); sendMessage(t); }} autoPlayText={lastResponse} />
                        <button
                            id="chat-send-btn"
                            className={`${styles.sendBtn} ${loading ? styles.sendBtnBusy : ''}`}
                            onClick={() => sendMessage()}
                            disabled={loading}
                            aria-label="Send message"
                        >
                            {loading
                                ? <div className={styles.sendSpinner} />
                                : <Send size={16} />
                            }
                        </button>
                    </div>
                    <p className={styles.inputHint}>
                        Responses grounded in your ERP academic record · All 13 data sections loaded
                    </p>
                </div>
            </div>
        </div>
    );
}
