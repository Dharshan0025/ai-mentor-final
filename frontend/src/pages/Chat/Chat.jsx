import { useState, useRef, useEffect, useCallback, lazy, Suspense } from 'react';
import { Send, Zap, BookOpen, Brain, Heart, Calendar, TrendingUp, Briefcase, ChevronRight, AlertTriangle, BarChart2 } from 'lucide-react';
import { v4 as uuidv4 } from 'uuid';
import styles from './Chat.module.css';
import { sendChatMessage, getStoredStudent, getBriefing } from '../../services/api';
import { detectDiagramKeyword } from '../../components/ConceptBoard/ConceptBoard';
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
    academic: [{ label: '📊 View Predictions', path: '/predictions' }, { label: '📅 Get Schedule', path: '/schedule' }, { label: '🧪 Take Quiz', path: '/learning' }],
    prediction: [{ label: '📅 Build Study Plan', path: '/schedule' }, { label: '📊 Full Prediction', path: '/predictions' }],
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

// ── Markdown renderer ─────────────────────────────────────────────────────────
function renderMd(text) {
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code>$1</code>')
        .replace(/^### (.+)$/gm, '<h3>$1</h3>')
        .replace(/^## (.+)$/gm, '<h2>$1</h2>')
        .replace(/^\d+\.\s(.+)/gm, '<li class="ordered">$1</li>')
        .replace(/^[-•]\s(.+)/gm, '<li>$1</li>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br/>');
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
    const diagramKey = detectDiagramKeyword(msg.text);
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
                <div
                    className={styles.cardContent}
                    dangerouslySetInnerHTML={{ __html: renderMd(msg.text) }}
                />

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
            </div>

            {/* Visual concept board — auto-rendered when topic matches */}
            {showDiagram && (
                <Suspense fallback={null}>
                    <ConceptBoard
                        keyword={diagramKey}
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
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [loadingAgent, setLoadingAgent] = useState('orchestrator');
    const [sessionId] = useState(() => uuidv4());
    const [briefing, setBriefing] = useState(null);
    const [student, setStudent] = useState(null);
    const bottomRef = useRef(null);

    // Load student from localStorage + briefing from API
    useEffect(() => {
        const stored = getStoredStudent();
        if (stored) setStudent(stored);

        getBriefing()
            .then(data => setBriefing(data))
            .catch(() => { }); // briefing is non-critical
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
            }]);
        } catch (err) {
            const errText = err.response?.status === 503
                ? '⚠️ The AI service is temporarily offline. Please try again in a moment.'
                : '⚠️ Something went wrong. Please try again.';
            setMessages(m => [...m, { role: 'agent', agent: 'academic', text: errText, citations: [] }]);
        } finally {
            setLoading(false);
        }
    }, [input, loading, messages, sessionId]);

    const handleChipClick = (path) => {
        window.location.href = path;
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
                            : <AgentCard key={i} msg={msg} onChipClick={handleChipClick} />
                    )}

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
