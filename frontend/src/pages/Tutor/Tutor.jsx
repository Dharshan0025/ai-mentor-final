/**
 * AI Visual Tutor — Warm Cream / Orange Theme — V2+
 * Features: Lesson Plan Preview, Checkpoint Quiz, LaTeX equations,
 * Code Walkthrough, inline Q&A diagrams, Spaced Repetition banner,
 * Teaching Style selector, Whiteboard PNG download, Voice I/O.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import {
    Volume2, VolumeX, Mic, MicOff, Send, Brain, Zap, ChevronRight,
    RotateCcw, Loader2, Maximize2, Minimize2, AlertTriangle,
    MessageCircle, Play, BookOpen, CheckCircle2, Circle, Clock,
    CalendarClock, FlaskConical, Download, GraduationCap, Sparkles,
    BarChart3, Code2, Users, History, BookMarked, Globe,
} from 'lucide-react';
import mermaid from 'mermaid';
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import styles from './Tutor.module.css';
import {
    getTutorOptions, startTutorLesson, askTutorQuestion, clearTutorSession,
    getLessonPlan, getDueTopics, recordCheckpointMemory, doubtResolve, awardXp,
    saveDiagram, sendAttentionHeartbeat, reportSilenceAlert, getStoredStudent,
} from '../../services/api';
import CheckpointQuiz from '../../components/CheckpointQuiz/CheckpointQuiz';
import EquationBlock from '../../components/EquationBlock/EquationBlock';
import CodeWalkthrough from '../../components/CodeWalkthrough/CodeWalkthrough';
import VoiceTeacher from '../../components/VoiceTeacher/VoiceTeacher';
import TeacherAvatar from '../../components/TeacherAvatar/TeacherAvatar';
import XpToast from '../../components/XpToast/XpToast';
import CodeRunner from '../../components/CodeRunner/CodeRunner';
import DiagramHistory from '../../components/DiagramHistory/DiagramHistory';
import StudyModeSelector from '../../components/StudyModeSelector/StudyModeSelector';
import { PeerLearning } from '../../components/PeerLearning/PeerLearning';


// ── Mermaid init — light neutral theme ─────────────────────────────────────
mermaid.initialize({
    startOnLoad: false,
    theme: 'neutral',
    themeVariables: {
        background: '#FFFFFF',
        primaryColor: '#FF7A00',
        primaryTextColor: '#1A1A1A',
        primaryBorderColor: '#E8E4DE',
        lineColor: '#9A9A9A',
        secondaryColor: '#FAF8F4',
        tertiaryColor: '#F4F1EC',
        edgeLabelBackground: '#FFFFFF',
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: '14px',
        nodeBorder: '#E8E4DE',
        clusterBkg: '#FAF8F4',
        titleColor: '#1A1A1A',
    },
    flowchart: { curve: 'basis', padding: 24, htmlLabels: true },
    sequence: { fontSize: 13, actorMargin: 50 },
});

function sanitizeMermaid(raw) {
    if (!raw) return '';
    return raw
        .split('\n')
        .filter(l => !/^\s*(style\s+\w|classDef\s|linkStyle\s)/i.test(l))
        .map(l => l.replace(/:::\w+/g, ''))
        .map(l => l.replace(/,?\s*fill\s*:\s*#[0-9a-fA-F]{3,6}/g, ''))
        .map(l => l.replace(/,?\s*stroke\s*:\s*#[0-9a-fA-F]{3,6}/g, ''))
        .map(l => l.replace(/,?\s*color\s*:\s*#[0-9a-fA-F]{3,6}/g, ''))
        .join('\n')
        .trim();
}

const CHIPS = [
    'Explain in simpler terms',
    'Give a real-world example',
    'Quiz me on this',
    "What's the key takeaway?",
    'How does this relate to the exam?',
];

const TEACHING_STYLES = [
    { id: 'visual + example-based', label: 'Visual', icon: '🎨', desc: 'Diagrams & examples' },
    { id: 'analytical + logical', label: 'Logical', icon: '🧮', desc: 'Step-by-step reasoning' },
    { id: 'exam-oriented + concise', label: 'Exam-ready', icon: '📝', desc: 'Key points & tips' },
];

// ── Voice hook ─────────────────────────────────────────────────────────────
function useSpeech() {
    const [voiceEnabled, setVoiceEnabled] = useState(true);
    const [speaking, setSpeaking] = useState(false);
    const [listening, setListening] = useState(false);
    const [transcript, setTranscript] = useState('');
    const queueRef = useRef([]);
    const busyRef = useRef(false);
    const recogRef = useRef(null);

    const getVoice = () => {
        const vs = window.speechSynthesis?.getVoices() || [];
        return vs.find(v => v.name.includes('Google') && v.lang.startsWith('en'))
            || vs.find(v => v.lang.startsWith('en') && v.localService)
            || vs[0];
    };

    const processQueue = useCallback(() => {
        if (!queueRef.current.length) { busyRef.current = false; setSpeaking(false); return; }
        busyRef.current = true; setSpeaking(true);
        const text = queueRef.current.shift();
        const u = new SpeechSynthesisUtterance(text);
        u.voice = getVoice(); u.rate = 0.95; u.pitch = 1.0;
        u.onend = processQueue; u.onerror = processQueue;
        window.speechSynthesis?.speak(u);
    }, []);

    const speak = useCallback((text) => {
        if (!voiceEnabled || !window.speechSynthesis) return;
        queueRef.current.push(text);
        if (!busyRef.current) processQueue();
    }, [voiceEnabled, processQueue]);

    const stop = useCallback(() => {
        window.speechSynthesis?.cancel();
        queueRef.current = []; busyRef.current = false; setSpeaking(false);
    }, []);

    const toggleVoice = useCallback(() => {
        if (voiceEnabled) stop();
        setVoiceEnabled(v => !v);
    }, [voiceEnabled, stop]);

    const startListening = useCallback(() => {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) return;
        const r = new SR();
        r.continuous = false; r.interimResults = false; r.lang = 'en-US';
        r.onresult = e => setTranscript(e.results[0][0].transcript);
        r.onend = () => setListening(false);
        r.onerror = () => setListening(false);
        recogRef.current = r; r.start(); setListening(true);
    }, []);

    const stopListening = useCallback(() => { recogRef.current?.stop(); setListening(false); }, []);

    return { voiceEnabled, speaking, listening, transcript, setTranscript, speak, stop, toggleVoice, startListening, stopListening };
}

// ── Whiteboard Canvas ──────────────────────────────────────────────────────
function Canvas({ code, title, stepNum, totalSteps }) {
    const [svg, setSvg] = useState('');
    const [err, setErr] = useState(null);
    const [rendering, setRendering] = useState(false);
    const [fullscreen, setFullscreen] = useState(false);
    const svgRef = useRef(null);

    useEffect(() => {
        if (!code) { setSvg(''); setErr(null); return; }
        setSvg(''); setErr(null); setRendering(true);
        const clean = sanitizeMermaid(code);
        if (!clean) { setErr('Empty diagram'); setRendering(false); return; }
        const id = `mmd_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
        mermaid.render(id, clean)
            .then(({ svg: s }) => { setSvg(s); setRendering(false); })
            .catch(e => {
                console.warn('[Mermaid]', e, '\n---\n', clean);
                setErr('Could not render diagram');
                setRendering(false);
            });
    }, [code]);

    const downloadPNG = useCallback(() => {
        if (!svgRef.current) return;
        const svgEl = svgRef.current.querySelector('svg');
        if (!svgEl) return;
        const data = new XMLSerializer().serializeToString(svgEl);
        const blob = new Blob([data], { type: 'image/svg+xml' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `${title || 'diagram'}.svg`;
        a.click(); URL.revokeObjectURL(url);
    }, [title]);

    return (
        <div className={`${styles.canvas} ${fullscreen ? styles.canvasFull : ''}`}>
            <div className={styles.canvasGrid} />
            <div className={styles.canvasHeader}>
                <div className={styles.canvasHeaderLeft}>
                    <div className={styles.canvasDot} />
                    <span className={styles.canvasTitle}>{title || 'Visual Whiteboard'}</span>
                    {totalSteps > 0 && (
                        <span className={styles.canvasStepBadge}>
                            Step {stepNum} / {totalSteps}
                        </span>
                    )}
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                    {svg && (
                        <button className={styles.canvasDownloadBtn} onClick={downloadPNG} title="Download diagram as SVG">
                            <Download size={12} /> Export
                        </button>
                    )}
                    <button className={styles.canvasBtn} onClick={() => setFullscreen(f => !f)} title="Toggle fullscreen">
                        {fullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
                    </button>
                </div>
            </div>
            <div className={styles.canvasBody}>
                {!code && !rendering && (
                    <div className={styles.canvasEmpty}>
                        <Brain size={40} className={styles.canvasEmptyIcon} />
                        <p>Start a lesson — diagrams appear here</p>
                        <p className={styles.canvasEmptyHint}>Each teaching step lights up the whiteboard</p>
                    </div>
                )}
                {rendering && (
                    <div className={styles.canvasLoader}>
                        <Loader2 size={20} className={styles.spin} />
                        <span>Rendering diagram…</span>
                    </div>
                )}
                {err && !rendering && (
                    <div className={styles.canvasFallback}>
                        <AlertTriangle size={16} />
                        <span>{err} — diagram unavailable for this step</span>
                    </div>
                )}
                {svg && !rendering && (
                    <TransformWrapper minScale={0.5} maxScale={4} initialScale={1} centerOnInit smooth>
                        <TransformComponent wrapperStyle={{ width: '100%', height: '100%' }}>
                            <div className={styles.canvasDiagramCard}>
                                <div ref={svgRef} className={styles.canvasSvg} dangerouslySetInnerHTML={{ __html: svg }} />
                            </div>
                        </TransformComponent>
                    </TransformWrapper>
                )}
            </div>
            {totalSteps > 0 && (
                <div className={styles.canvasProgress}>
                    <div
                        className={styles.canvasProgressFill}
                        style={{ width: `${(stepNum / totalSteps) * 100}%` }}
                    />
                </div>
            )}
        </div>
    );
}

// ── (V6: Legacy inline TeacherAvatar removed — now imported from /components/TeacherAvatar) ──

// ── Step Rail ──────────────────────────────────────────────────────────────
function StepRail({ steps, currentStep, teaching, planSteps = [] }) {
    const allSteps = planSteps.length > 0 ? planSteps : steps;
    return (
        <div className={styles.rail}>
            <div className={styles.railTitle}>
                <Zap size={12} />
                <span>LESSON FLOW</span>
            </div>
            <div className={styles.railItems}>
                {allSteps.map((s, i) => {
                    const stepNum = s.step_num !== undefined ? s.step_num : (s.step !== undefined ? s.step : i + 1);
                    const done = stepNum < currentStep;
                    const active = stepNum === currentStep;
                    return (
                        <div key={i} className={`${styles.railItem} ${done ? styles.railDone : ''} ${active ? styles.railActive : ''}`}>
                            <div className={styles.railIcon}>
                                {done ? <CheckCircle2 size={14} />
                                    : active ? <Play size={10} />
                                        : <Circle size={14} />}
                            </div>
                            <span className={styles.railLabel}>{s.title}</span>
                            {s.checkpoint_after && <FlaskConical size={10} className={styles.railCheckpointIcon} title="Checkpoint after this step" />}
                            {s.estimated_minutes && (
                                <span className={styles.railMins}>
                                    <Clock size={9} />{s.estimated_minutes}m
                                </span>
                            )}
                            {active && <div className={styles.railPulse} />}
                        </div>
                    );
                })}
                {teaching && (
                    <div className={styles.railItem}>
                        <Loader2 size={14} className={styles.spin} />
                        <span className={styles.railLabel} style={{ color: 'var(--accent)' }}>Loading…</span>
                    </div>
                )}
            </div>
        </div>
    );
}

// ── Lesson Plan Preview ────────────────────────────────────────────────────
function LessonPlanPreview({ plan, onStart, loading }) {
    if (!plan) return null;
    const { steps = [], topic, estimated_total_minutes, checkpoints, bloom_level } = plan;
    return (
        <div className={styles.planPreview}>
            <div className={styles.planHeader}>
                <GraduationCap size={20} className={styles.planIcon} />
                <div>
                    <p className={styles.planTitle}>Lesson Plan</p>
                    <p className={styles.planSubtitle}>{topic}</p>
                </div>
                <div className={styles.planMeta}>
                    <span><Clock size={11} /> ~{estimated_total_minutes}min</span>
                    <span><FlaskConical size={11} /> {checkpoints} checkpoints</span>
                    {bloom_level && <span><BarChart3 size={11} /> Bloom L{bloom_level}</span>}
                </div>
            </div>
            <div className={styles.planSteps}>
                {steps.map((s, i) => (
                    <div key={i} className={styles.planStep}>
                        <span className={styles.planStepNum}>{String(s.step_num).padStart(2, '0')}</span>
                        <div className={styles.planStepInfo}>
                            <span className={styles.planStepTitle}>{s.title}</span>
                            <span className={styles.planStepMeta}>
                                ~{s.estimated_minutes}min · Bloom {s.bloom_target}
                                {s.checkpoint_after && <span className={styles.planCpTag}>✓ Quiz</span>}
                            </span>
                        </div>
                    </div>
                ))}
            </div>
            <button className={styles.planStartBtn} onClick={onStart} disabled={loading}>
                {loading ? <><Loader2 size={14} className={styles.spin} /> Preparing…</> : <>Start Lesson <ChevronRight size={16} /></>}
            </button>
        </div>
    );
}

// ── Due Topics Banner ──────────────────────────────────────────────────────
function DueTopicsBanner({ dueTopics, onSelectTopic }) {
    if (!dueTopics || dueTopics.length === 0) return null;
    return (
        <div className={styles.dueBanner}>
            <CalendarClock size={14} className={styles.dueIcon} />
            <span className={styles.dueText}>Review due:</span>
            {dueTopics.slice(0, 2).map((t, i) => (
                <button
                    key={i}
                    className={styles.dueChip}
                    onClick={() => onSelectTopic(t)}
                    title={`${t.subject_code} — ${t.topic}`}
                >
                    {t.topic.length > 20 ? t.topic.slice(0, 20) + '…' : t.topic}
                    {t.priority === 'high' && <span className={styles.dueHighPriority}>!</span>}
                </button>
            ))}
        </div>
    );
}

// ── Narration line with inline LaTeX ──────────────────────────────────────
function NarrationLine({ text }) {
    const parts = text.split(/(\$\$[^$]+\$\$)/g);
    return (
        <p className={styles.narrationLine}>
            {parts.map((part, i) => {
                if (part.startsWith('$$') && part.endsWith('$$')) {
                    const latex = part.slice(2, -2).trim();
                    return <EquationBlock key={i} latex={latex} display="inline" />;
                }
                return <span key={i}>{part}</span>;
            })}
        </p>
    );
}

// ── Mini Canvas for Q&A inline diagrams ───────────────────────────────────
function MiniCanvas({ code }) {
    const [svg, setSvg] = useState('');
    const [err, setErr] = useState(null);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (!code) { setSvg(''); setErr(null); return; }
        setSvg(''); setErr(null); setBusy(true);
        const clean = sanitizeMermaid(code);
        if (!clean) { setErr('empty'); setBusy(false); return; }
        const id = `mini_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
        mermaid.render(id, clean)
            .then(({ svg: s }) => { setSvg(s); setBusy(false); })
            .catch(() => { setErr('render error'); setBusy(false); });
    }, [code]);

    if (!code) return null;
    if (busy) return <div className={styles.miniCanvasLoader}><Loader2 size={14} className={styles.spin} /></div>;
    if (err) return null;
    return (
        <div
            className={styles.miniCanvas}
            dangerouslySetInnerHTML={{ __html: svg }}
        />
    );
}

// ── Main Page ──────────────────────────────────────────────────────────────
export default function Tutor() {
    const [options, setOptions] = useState({ subjects: [], topics_by_subject: {} });
    const [loadingOptions, setLoadingOptions] = useState(true);
    const [optErr, setOptErr] = useState(null);
    const [selSubject, setSelSubject] = useState(null);
    const [selTopic, setSelTopic] = useState(null);

    // Teaching style
    const [teachingStyle, setTeachingStyle] = useState('visual + example-based');

    // Lesson plan
    const [lessonPlan, setLessonPlan] = useState(null);
    const [planLoading, setPlanLoading] = useState(false);
    const [lessonStarted, setLessonStarted] = useState(false);

    // Lesson streaming
    const [teaching, setTeaching] = useState(false);
    const [steps, setSteps] = useState([]);
    const [currentStep, setCurrentStep] = useState(0);
    const [currentDiagram, setCurrentDiagram] = useState('');
    const [diagramTitle, setDiagramTitle] = useState('');
    const [currentSubtitle, setCurrentSubtitle] = useState('');
    const [lessonDone, setLessonDone] = useState(false);
    const [lessonErr, setLessonErr] = useState(null);
    const narrationEndRef = useRef(null);

    // Checkpoint
    const [checkpoint, setCheckpoint] = useState(null);
    const [paused, setPaused] = useState(false);

    // V2 extras
    const [equations, setEquations] = useState([]);
    const [codeBlocks, setCodeBlocks] = useState([]);

    // Q&A
    const [questionInput, setQuestionInput] = useState('');
    const [qaThread, setQaThread] = useState([]);
    const [asking, setAsking] = useState(false);
    const [askErr, setAskErr] = useState(null);

    // Voice panel (Nova Sonic)
    const [showVoicePanel, setShowVoicePanel] = useState(false);
    const [voiceSpeakQueue, setVoiceSpeakQueue] = useState([]);

    // Session
    const [sessionId, setSessionId] = useState(() =>
        typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('tutor_session_id') : null
    );

    // Talk mode
    const [talkMode, setTalkMode] = useState(false);
    const lastSentTranscriptRef = useRef('');

    // Spaced repetition — SM-2 due topics
    const [dueTopics, setDueTopics] = useState([]);

    // V4 Confusion detection — tracks wrong answers per topic this session
    const confusionMapRef = useRef({});   // { [topicKey]: count }
    const [confusedTopics, setConfusedTopics] = useState([]); // topics with ≥2 wrong

    // V5 Doubt resolution — DoubtResolverAgent response
    const [doubtResolution, setDoubtResolution] = useState(null); // { mode, explanation, mini_question, key_insight, diagram? }
    const [doubtLoading, setDoubtLoading] = useState(false);

    // V6 Teacher Avatar — reacts to lesson events
    const [avatarState, setAvatarState] = useState('idle');
    const avatarTimerRef = useRef(null);
    const setAvatarTimed = useCallback((state, resetMs = 3000) => {
        setAvatarState(state);
        clearTimeout(avatarTimerRef.current);
        if (resetMs > 0) avatarTimerRef.current = setTimeout(() => setAvatarState('idle'), resetMs);
    }, []);

    // V6 XP Toast — shown after XP is awarded
    const [xpToast, setXpToast] = useState(null);

    // ── Phase 8: New state ────────────────────────────────────────────────────
    const [showDiagramHistory, setShowDiagramHistory] = useState(false);
    const [showPeerRoom, setShowPeerRoom]             = useState(false);
    const [showStudyMode, setShowStudyMode]           = useState(false);
    const [studyMode, setStudyMode]                   = useState('concept');
    const [tutorLang, setTutorLang]                   = useState('en');
    const [silenceAlert, setSilenceAlert]             = useState(null);  // { severity, suggestion }
    const silenceTRef = useRef(null);
    const lastInteractRef = useRef(Date.now());


    const speech = useSpeech();

    const subjects = options.subjects || [];
    const topics = selSubject ? (options.topics_by_subject || {})[selSubject.code] || [] : [];

    // Load curriculum
    useEffect(() => {
        getTutorOptions()
            .then(d => {
                setOptions({ subjects: d.subjects || [], topics_by_subject: d.topics_by_subject || {} });
                const subs = d.subjects || [];
                if (subs.length) setSelSubject(subs[0]);
            })
            .catch(() => setOptErr('Could not load curriculum'))
            .finally(() => setLoadingOptions(false));
    }, []);

    // Load SM-2 due topics (smart endpoint)
    useEffect(() => {
        getDueTopics(24)
            .then(d => {
                // Smart endpoint returns d.due_topics; old endpoint returns d.topics
                const topics = d.due_topics || d.topics || [];
                setDueTopics(topics);

            })
            .catch(() => { });
    }, []);

    // ── V8: Attention heartbeat (visibility change) ───────────────────────────
    useEffect(() => {
        let hbInterval = null;
        const handleVisibility = () => sendAttentionHeartbeat(!document.hidden, sessionId || '');

        document.addEventListener('visibilitychange', handleVisibility);
        // Also heartbeat every 30s while visible
        hbInterval = setInterval(() => {
            if (!document.hidden) sendAttentionHeartbeat(true, sessionId || '');
        }, 30_000);

        return () => {
            document.removeEventListener('visibilitychange', handleVisibility);
            clearInterval(hbInterval);
        };
    }, [sessionId]);

    // ── V8: Silence detection (no interaction > 45s during lesson) ────────────
    useEffect(() => {
        if (!teaching || !lessonStarted) {
            clearTimeout(silenceTRef.current);
            return;
        }

        const checkSilence = () => {
            const elapsed = Date.now() - lastInteractRef.current;
            if (elapsed < 45_000) return;
            reportSilenceAlert({
                silence_ms: elapsed,
                topic: selTopic || '',
                step_num: currentStep,
            }).then(r => {
                if (r?.confusion_suspected) setSilenceAlert(r);
            }).catch(() => {});
        };

        silenceTRef.current = setInterval(checkSilence, 10_000);
        return () => clearInterval(silenceTRef.current);
    }, [teaching, lessonStarted, selTopic, currentStep]);

    // Reset silence timer on any interaction
    const handleUserInteract = useCallback(() => {
        lastInteractRef.current = Date.now();
        if (silenceAlert) setSilenceAlert(null);
    }, [silenceAlert]);

    // ── V2: Auto-save diagram to visual memory ────────────────────────────────
    useEffect(() => {
        if (!currentDiagram || !sessionId) return;
        saveDiagram({
            session_id: sessionId,
            subject_code: selSubject?.code || '',
            topic: selTopic || '',
            step_num: currentStep,
            diagram_title: diagramTitle || 'Diagram',
            mermaid_code: currentDiagram,
        });
    }, [currentDiagram]);   // eslint-disable-line react-hooks/exhaustive-deps



    // Talk mode → question auto-send
    useEffect(() => {
        if (!talkMode && speech.transcript) setQuestionInput(speech.transcript);
    }, [talkMode, speech.transcript]);

    useEffect(() => {
        if (!talkMode || speech.listening || asking || !selSubject || !selTopic) return;
        const q = (speech.transcript || '').trim();
        if (!q || q === lastSentTranscriptRef.current) return;
        lastSentTranscriptRef.current = q;
        speech.setTranscript('');
        setQuestionInput('');
        setAskErr(null);
        setAsking(true);
        const history = qaThread.slice(-6).map(({ role, content }) => ({ role, content }));
        askTutorQuestion({ subjectCode: selSubject.code, topic: selTopic, question: q, history, sessionId })
            .then(({ answer }) => {
                setQaThread(p => [...p, { role: 'user', content: q }, { role: 'assistant', content: answer }]);
                if (answer && speech.voiceEnabled) speech.speak(answer.replace(/\n+/g, ' ').slice(0, 400));
            })
            .catch(e => setAskErr(e.response?.data?.detail || e.message || 'Failed to get answer'))
            .finally(() => { setAsking(false); lastSentTranscriptRef.current = ''; });
    }, [talkMode, speech.listening, speech.transcript, selSubject, selTopic, qaThread, sessionId, speech.voiceEnabled, speech.setTranscript, speech.speak]);

    // Voice Interruption (Spacebar)
    useEffect(() => {
        const handleKeyDown = (e) => {
            if (e.code === 'Space') {
                const tg = e.target.tagName;
                if (tg !== 'INPUT' && tg !== 'TEXTAREA' && tg !== 'BUTTON') {
                    e.preventDefault();
                    speech.stop();
                    window.dispatchEvent(new CustomEvent('stop-tutor-audio'));
                }
            }
        };
        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [speech]);

    const resetLesson = () => {
        speech.stop();
        setSelTopic(null); setTeaching(false); setSteps([]); setCurrentStep(0);
        setCurrentDiagram(''); setDiagramTitle(''); setCurrentSubtitle('');
        setLessonDone(false); setLessonErr(null); setQaThread([]);
        setQuestionInput(''); setAskErr(null); setSessionId(null);
        setLessonPlan(null); setLessonStarted(false); setPaused(false); setCheckpoint(null);
        setEquations([]); setCodeBlocks([]);
        if (typeof sessionStorage !== 'undefined') sessionStorage.removeItem('tutor_session_id');
    };

    const resetLessonData = () => {
        setTeaching(false); setSteps([]); setCurrentStep(0);
        setCurrentDiagram(''); setDiagramTitle(''); setCurrentSubtitle('');
        setLessonDone(false); setLessonErr(null); setQaThread([]);
        setQuestionInput(''); setAskErr(null); setPaused(false); setCheckpoint(null);
        setEquations([]); setCodeBlocks([]);
    };

    const startNewConversation = useCallback(async () => {
        if (sessionId) {
            try { await clearTutorSession(sessionId); } catch { /* ignore */ }
        }
        setSessionId(null);
        if (typeof sessionStorage !== 'undefined') sessionStorage.removeItem('tutor_session_id');
        setQaThread([]); setAskErr(null); setQuestionInput('');
    }, [sessionId]);

    const selectTopic = useCallback(async (topic) => {
        setSelTopic(topic);
        setLessonStarted(false);
        setLessonPlan(null);
        setPlanLoading(true);
        speech.stop();
        resetLessonData();
        try {
            const plan = await getLessonPlan({ subjectCode: selSubject.code, topic });
            setLessonPlan(plan);
        } catch {
            setLessonPlan({ steps: [], topic, estimated_total_minutes: 0, checkpoints: 0 });
        } finally {
            setPlanLoading(false);
        }
    }, [selSubject, speech]);

    const startLesson = useCallback(async () => {
        if (!selTopic || !selSubject) return;
        setLessonStarted(true);
        setTeaching(true); setSteps([]); setCurrentStep(0);
        setCurrentDiagram(''); setDiagramTitle(''); setCurrentSubtitle('');
        setLessonDone(false); setLessonErr(null);
        setPaused(false); setCheckpoint(null);
        setEquations([]); setCodeBlocks([]);
        speech.stop();

        try {
            const res = await startTutorLesson({ subjectCode: selSubject.code, topic: selTopic, mode: 'visual', sessionId });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buf = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += decoder.decode(value, { stream: true });
                const lines = buf.split('\n');
                buf = lines.pop() || '';

                let evt = '';
                for (const line of lines) {
                    if (line.startsWith('event: ')) { evt = line.slice(7).trim(); }
                    else if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (evt === 'session_id' && data.session_id) {
                                setSessionId(data.session_id);
                                if (typeof sessionStorage !== 'undefined')
                                    sessionStorage.setItem('tutor_session_id', data.session_id);
                            } else if (evt === 'step') {
                                setSteps(p => [...p, { step: data.step, title: data.title }]);
                                setCurrentStep(data.step);
                                setDiagramTitle(data.title);
                            } else if (evt === 'narration') {
                                setCurrentSubtitle(data.text);
                                speech.speak(data.text);
                                // Also queue for Nova Sonic if panel is open
                                if (showVoicePanel) {
                                    setVoiceSpeakQueue(q => [...q, { text: data.text }]);
                                }
                            } else if (evt === 'diagram') {
                                setCurrentDiagram(data.mermaid);
                                if (data.title) setDiagramTitle(data.title);
                            } else if (evt === 'equation') {
                                setEquations(p => [...p, data]);
                            } else if (evt === 'code_block') {
                                setCodeBlocks(p => [...p, data]);
                            } else if (evt === 'checkpoint') {
                                setCheckpoint({ ...data, subjectCode: selSubject.code });
                                setPaused(true);
                            } else if (evt === 'done') {
                                setLessonDone(true);
                            } else if (evt === 'error') {
                                setLessonErr(data.error);
                            }
                        } catch { /* ignore bad JSON */ }
                        evt = '';
                    }
                }
            }
            setLessonDone(true);
        } catch (e) {
            setLessonErr(e.message || 'Connection failed');
        } finally {
            setTeaching(false);
        }
    }, [selSubject, selTopic, sessionId, speech]);

    const handleCheckpointPass = useCallback(() => {
        setCheckpoint(null); setPaused(false);
    }, []);

    const handleCheckpointSkip = useCallback(() => {
        setCheckpoint(null); setPaused(false);
    }, []);

    // ── Confusion detection — called by CheckpointQuiz via onWrong prop ─────
    // Tracks per-topic wrong answers this session and flags confused topics.
    // Silently records confusion bump to SM-2 memory when ≥ 2 wrong answers.
    const handleCheckpointWrong = useCallback((topic) => {
        if (!topic || !selSubject) return;
        const key = `${selSubject.code}::${topic}`;
        confusionMapRef.current[key] = (confusionMapRef.current[key] || 0) + 1;
        const count = confusionMapRef.current[key];

        // Mark confused after 2 wrong answers on same topic
        if (count >= 2) {
            setConfusedTopics(prev =>
                prev.includes(topic) ? prev : [...prev, topic]
            );
            // Record confusion bump to SM-2 (non-blocking)
            recordCheckpointMemory({
                subject_code: selSubject.code,
                topic,
                question: `Confusion detected (${count} wrong answers)`,
                question_type: 'mcq',
                student_answer: '',
                correct_answer: '',
                is_correct: false,
                score: 0,
                feedback: `Student confused — ${count} wrong answers this session`,
                session_id: sessionId,
            }).catch(console.warn);
        }
    }, [selSubject, sessionId]);

    // ── V5 Doubt Resolver — called when student clicks 'Get Alternative Explanation' ──
    const handleDoubtResolve = useCallback(async (topic) => {
        if (!selSubject || doubtLoading) return;
        setDoubtLoading(true);
        setDoubtResolution(null);
        try {
            const res = await doubtResolve({
                subject_code: selSubject.code,
                topic: selTopic || topic,
                concept: topic,
                wrong_count: confusionMapRef.current[`${selSubject.code}::${topic}`] || 2,
                confusion_context: `Student is confused about ${topic} in ${selSubject.name}`,
            });
            setDoubtResolution(res);
        } catch (e) {
            console.warn('Doubt resolver failed:', e);
        } finally {
            setDoubtLoading(false);
        }
    }, [selSubject, selTopic, doubtLoading]);

    const sendQuestion = useCallback(async (text) => {
        const q = (text || questionInput || '').trim();
        if (!q || !selSubject || !selTopic) return;
        setQuestionInput(''); speech.setTranscript(''); setAskErr(null);
        setQaThread(p => [...p, { role: 'user', content: q }]);
        setAsking(true);
        try {
            const history = qaThread.slice(-6).map(({ role, content }) => ({ role, content }));
            const { answer, mermaid } = await askTutorQuestion({
                subjectCode: selSubject.code, topic: selTopic, question: q, history, sessionId
            });
            setQaThread(p => [...p, { role: 'assistant', content: answer, mermaid }]);
            if (answer && speech.voiceEnabled) speech.speak(answer.replace(/\n+/g, ' ').slice(0, 400));
        } catch (e) {
            setAskErr(e.response?.data?.detail || e.message || 'Failed to get answer');
            setQaThread(p => p.slice(0, -1));
        } finally {
            setAsking(false);
        }
    }, [selSubject, selTopic, questionInput, qaThread, sessionId, speech]);

    const handleDueTopicSelect = useCallback((dueTopic) => {
        const matchSubj = subjects.find(s => s.code === dueTopic.subject_code);
        if (matchSubj) setSelSubject(matchSubj);
        selectTopic(dueTopic.topic);
    }, [subjects, selectTopic]);

    const totalPlanSteps = lessonPlan?.steps?.length || steps.length;

    if (loadingOptions) return (
        <div className={styles.loadingWrap}>
            <Loader2 size={28} className={styles.spin} />
            <span>Loading curriculum…</span>
        </div>
    );

    return (
        <>
        <div className={styles.root}>

            {/* V6 XP Toast overlay */}
            {xpToast && (
                <XpToast
                    xp={xpToast.xp}
                    action={xpToast.action}
                    badges={xpToast.badges || []}
                    onDone={() => setXpToast(null)}
                />
            )}

            {/* Checkpoint overlay */}
            {checkpoint && (
                <CheckpointQuiz
                    checkpoint={checkpoint}
                    subjectCode={selSubject?.code || ''}
                    sessionId={sessionId}
                    onPass={handleCheckpointPass}
                    onSkip={handleCheckpointSkip}
                    onWrong={handleCheckpointWrong}
                />
            )}

            {/* ── Left panel ─────────────────────────────────────────── */}
            <aside className={styles.panel}>
                <div className={styles.panelHeader}>
                    <TeacherAvatar state={avatarState} size={46} />
                    <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--text-1)' }}>AI Tutor</div>
                        <div style={{ fontSize: '0.67rem', color: 'var(--text-3)', textTransform: 'capitalize' }}>{avatarState}</div>
                    </div>
                </div>

                {/* Confused Topics Alert — V5: includes DoubtResolver panel */}
                {confusedTopics.length > 0 && (
                    <div>
                        <div className={styles.confusedAlert}>
                            <AlertTriangle size={12} />
                            <span>
                                Struggling with: {confusedTopics.slice(0, 2).join(', ')}
                                {confusedTopics.length > 2 ? ` +${confusedTopics.length - 2} more` : ''}
                            </span>
                            <button
                                className={styles.doubtHelpBtn}
                                onClick={() => handleDoubtResolve(confusedTopics[0])}
                                disabled={doubtLoading}
                                title="Get alternative explanation from V5 DoubtResolver"
                            >
                                {doubtLoading ? <Loader2 size={10} className={styles.spin} /> : <Sparkles size={10} />}
                                {doubtLoading ? 'Thinking…' : 'Get help'}
                            </button>
                        </div>

                        {/* DoubtResolver Panel — shows after resolution */}
                        {doubtResolution && (
                            <div className={styles.doubtPanel}>
                                <div className={styles.doubtPanelMode}>
                                    {doubtResolution.mode === 'analogy' && '🎭 Analogy'}
                                    {doubtResolution.mode === 'example' && '📌 Concrete Example'}
                                    {doubtResolution.mode === 'breakdown' && '🔧 Step-by-Step'}
                                    {doubtResolution.mode === 'socratic' && '❓ Socratic Method'}
                                </div>
                                <p className={styles.doubtExplanation}>{doubtResolution.explanation}</p>
                                {doubtResolution.key_insight && (
                                    <div className={styles.doubtKeyInsight}>
                                        💡 <strong>Key:</strong> {doubtResolution.key_insight}
                                    </div>
                                )}
                                {doubtResolution.mini_question && (
                                    <p className={styles.doubtQuestion}>❓ {doubtResolution.mini_question}</p>
                                )}
                                <button
                                    className={styles.doubtDismiss}
                                    onClick={() => setDoubtResolution(null)}
                                >✕ Dismiss</button>
                            </div>
                        )}
                    </div>
                )}

                {/* SM-2 Due Topics Banner */}
                <DueTopicsBanner dueTopics={dueTopics} onSelectTopic={handleDueTopicSelect} />

                {optErr && (
                    <div className={styles.panelErr}>
                        <AlertTriangle size={12} /> {optErr}
                    </div>
                )}

                {/* Teaching Style */}
                <div className={styles.styleSelector}>
                    <span className={styles.styleSelectorLabel}>Teaching Style</span>
                    {TEACHING_STYLES.map(s => (
                        <button
                            key={s.id}
                            className={`${styles.styleBtn} ${teachingStyle === s.id ? styles.styleBtnActive : ''}`}
                            onClick={() => setTeachingStyle(s.id)}
                        >
                            <span>{s.icon}</span>
                            <span>{s.label}</span>
                            <span style={{ fontSize: '0.65rem', color: 'var(--text-3)', marginLeft: 'auto' }}>{s.desc}</span>
                        </button>
                    ))}
                </div>

                {/* Subjects */}
                <div className={styles.panelSection}>
                    <span className={styles.panelSectionLabel}>Subjects</span>
                    {subjects.length === 0 && !optErr && (
                        <p className={styles.panelEmpty}>No subjects found in database.</p>
                    )}
                    {subjects.map((s, i) => (
                        <button
                            key={i}
                            className={`${styles.subjectBtn} ${selSubject?.code === s.code ? styles.subjectActive : ''}`}
                            onClick={() => { setSelSubject(s); resetLesson(); }}
                        >
                            <BookOpen size={13} />
                            <span>{s.name}</span>
                            <span className={styles.bloomBadge} style={{
                                color: (s.bloomLevel ?? 2) >= 4 ? 'var(--safe)' : (s.bloomLevel ?? 2) >= 2 ? 'var(--watch)' : 'var(--risk)'
                            }}>L{s.bloomLevel ?? 2}</span>
                        </button>
                    ))}
                </div>

                {/* Topics */}
                {selSubject && (
                    <div className={styles.panelSection}>
                        <span className={styles.panelSectionLabel}>Topics — {selSubject.name}</span>
                        {topics.length === 0 && (
                            <p className={styles.panelEmpty}>No topics in syllabus for this subject.</p>
                        )}
                        {topics.map((t, i) => (
                            <button
                                key={i}
                                className={`${styles.topicBtn} ${selTopic === t ? styles.topicActive : ''}`}
                                onClick={() => selectTopic(t)}
                                disabled={teaching}
                            >
                                <span className={styles.topicIdx}>{String(i + 1).padStart(2, '0')}</span>
                                <span>{t}</span>
                                <ChevronRight size={11} className={styles.topicArrow} />
                            </button>
                        ))}
                    </div>
                )}
            </aside>

            {/* ── Main workspace ─────────────────────────────────────── */}
            <div className={styles.workspace}>
                {!selTopic ? (
                    <div className={styles.welcome}>
                        <div className={styles.welcomeGrid} />
                        <div className={styles.welcomeContent}>
                            <div className={styles.welcomeOrb}>
                                <Brain size={32} className={styles.welcomeIcon} />
                            </div>
                            <h2>AI Visual Tutor</h2>
                            <p>Select a topic from the left panel. Your tutor will show a lesson plan, then teach step-by-step with live diagrams, equations, and code walkthroughs.</p>
                            <div className={styles.welcomeFeatures}>
                                {['Lesson Planner', 'Live Diagrams', 'Checkpoint Quizzes', 'LaTeX Equations', 'Voice Narration'].map(f => (
                                    <span key={f} className={styles.welcomeTag}><Sparkles size={10} /> {f}</span>
                                ))}
                            </div>
                        </div>
                    </div>
                ) : (
                    <>
                        {/* Lesson plan preview */}
                        {!lessonStarted && (
                            <div className={styles.planPreviewWrap}>
                                {planLoading ? (
                                    <div className={styles.planLoading}>
                                        <Loader2 size={22} className={styles.spin} />
                                        <span>Building your lesson plan…</span>
                                    </div>
                                ) : (
                                    <LessonPlanPreview
                                        plan={lessonPlan}
                                        onStart={startLesson}
                                        loading={teaching}
                                    />
                                )}
                            </div>
                        )}

                        {/* Main lesson workspace */}
                        {lessonStarted && (
                            <>
                                {/* Overall progress bar */}
                                {totalPlanSteps > 0 && (
                                    <div className={styles.lessonProgressBar}>
                                        <div
                                            className={styles.lessonProgressFill}
                                            style={{ width: `${Math.min(100, (currentStep / totalPlanSteps) * 100)}%` }}
                                        />
                                    </div>
                                )}

                                {/* Lesson complete banner */}
                                {lessonDone && !teaching && (
                                    <div className={styles.lessonDoneBanner}>
                                        <CheckCircle2 size={18} />
                                        <div>
                                            <div className={styles.lessonDoneTitle}>Lesson Complete!</div>
                                            <span className={styles.lessonDoneSub}>{steps.length} steps covered · Ask follow-up questions below</span>
                                        </div>
                                    </div>
                                )}

                                {/* Status bar */}
                                <div className={styles.statusBar}>
                                    <div className={styles.statusLeft}>
                                        {teaching && <>
                                            <span className={styles.liveDot} />
                                            <span className={styles.statusText}>Teaching step {currentStep}{paused ? ' — Checkpoint ⏸' : '…'}</span>
                                        </>}
                                        {lessonErr && <span className={styles.errText}><AlertTriangle size={13} /> {lessonErr}</span>}
                                        {!teaching && !lessonDone && !lessonErr && selTopic && (
                                            <span className={styles.statusText}>{selTopic}</span>
                                        )}
                                    </div>
                                    {(sessionId || qaThread.length > 0) && (
                                        <button type="button" className={styles.newConvBtn} onClick={startNewConversation} title="Start a new conversation">
                                            <RotateCcw size={12} /> New conversation
                                        </button>
                                    )}
                                    <div className={styles.statusRight}>
                                        {(speech.listening || asking || speech.speaking) && (
                                            <span className={styles.voiceStatus}>
                                                {speech.listening && 'Listening…'}
                                                {asking && !speech.listening && 'Thinking…'}
                                                {speech.speaking && !asking && 'Speaking…'}
                                            </span>
                                        )}
                                        <button
                                            className={`${styles.iconBtn} ${speech.voiceEnabled ? styles.iconBtnAct : ''}`}
                                            onClick={speech.toggleVoice}
                                            title={speech.voiceEnabled ? 'Mute voice' : 'Enable voice'}
                                        >
                                            {speech.voiceEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
                                        </button>
                                        <button
                                            className={`${styles.iconBtn} ${speech.listening ? styles.iconBtnRed : ''} ${talkMode ? styles.iconBtnAct : ''}`}
                                            onClick={speech.listening ? speech.stopListening : speech.startListening}
                                            title={talkMode ? 'Talk mode: speak to send' : 'Voice input'}
                                        >
                                            {speech.listening ? <MicOff size={14} /> : <Mic size={14} />}
                                        </button>
                                        <button
                                            type="button"
                                            className={`${styles.talkModeBtn} ${talkMode ? styles.talkModeBtnOn : ''}`}
                                            onClick={() => setTalkMode(m => !m)}
                                        >
                                            <MessageCircle size={12} />
                                            <span>{talkMode ? ' Talk on' : ' Talk'}</span>
                                        </button>
                                        {(lessonDone || lessonErr) && (
                                            <button className={styles.resetBtn} onClick={resetLesson}>
                                                <RotateCcw size={13} /> New Topic
                                            </button>
                                        )}
                                        <button
                                            type="button"
                                            className={`${styles.iconBtn} ${showVoicePanel ? styles.iconBtnAct : ''}`}
                                            onClick={() => setShowVoicePanel(v => !v)}
                                            title="Toggle Nova Sonic voice panel"
                                        >
                                            <Volume2 size={14} />
                                        </button>
                                        {/* V2: Diagram History */}
                                        <button
                                            type="button"
                                            className={`${styles.iconBtn} ${showDiagramHistory ? styles.iconBtnAct : ''}`}
                                            onClick={() => setShowDiagramHistory(v => !v)}
                                            title="Diagram History — view saved diagrams"
                                        >
                                            <History size={14} />
                                        </button>
                                        {/* V6: Peer Learning */}
                                        <button
                                            type="button"
                                            className={`${styles.iconBtn} ${showPeerRoom ? styles.iconBtnAct : ''}`}
                                            onClick={() => setShowPeerRoom(v => !v)}
                                            title="Peer Study Room"
                                        >
                                            <Users size={14} />
                                        </button>
                                        {/* V9: Study Mode */}
                                        <button
                                            type="button"
                                            className={`${styles.iconBtn} ${showStudyMode ? styles.iconBtnAct : ''}`}
                                            onClick={() => setShowStudyMode(v => !v)}
                                            title="Study Mode Selector"
                                        >
                                            <BookMarked size={14} />
                                        </button>
                                    </div>

                                </div>

                                {/* Nova Sonic Voice Panel */}
                                {showVoicePanel && (
                                    <VoiceTeacher
                                        enabled={showVoicePanel}
                                        onToggle={() => setShowVoicePanel(false)}
                                        onTranscript={t => setQuestionInput(t)}
                                        speakQueue={voiceSpeakQueue}
                                        onSpeakQueueItem={() => setVoiceSpeakQueue(q => q.slice(1))}
                                    />
                                )}
                                {/* Canvas + Rail */}
                                <div className={styles.canvasRow}>
                                    <Canvas
                                        code={currentDiagram}
                                        title={diagramTitle}
                                        stepNum={currentStep}
                                        totalSteps={totalPlanSteps}
                                    />
                                    {(steps.length > 0 || (lessonPlan?.steps?.length > 0)) && (
                                        <StepRail
                                            steps={steps}
                                            currentStep={currentStep}
                                            teaching={teaching}
                                            planSteps={lessonPlan?.steps || []}
                                        />
                                    )}

                                    {/* Cinematic Subtitles Overlay */}
                                    {(currentSubtitle || (teaching && !currentSubtitle)) && (
                                        <div className={styles.subtitleContainer}>
                                            <div className={styles.subtitleOverlay}>
                                                {currentSubtitle || "Tutor is preparing your lesson…"}
                                            </div>
                                            <div className={styles.subtitleControls}>
                                                <button 
                                                    onClick={speech.toggleVoice} 
                                                    className={styles.subCtrlBtn} 
                                                    title={speech.voiceEnabled ? "Mute Voice" : "Unmute Voice"}
                                                >
                                                    {speech.voiceEnabled ? <Volume2 size={18} /> : <VolumeX size={18} />}
                                                </button>
                                                <button 
                                                    onClick={speech.listening ? speech.stopListening : speech.startListening} 
                                                    className={`${styles.subCtrlBtn} ${speech.listening ? styles.subCtrlMicActive : ''}`}
                                                    title={speech.listening ? "Stop Mic" : "Start Mic"}
                                                >
                                                    {speech.listening ? <Mic size={18} /> : <MicOff size={18} />}
                                                </button>
                                            </div>
                                        </div>
                                    )}
                                </div>

                                {/* Q&A Panel */}
                                <div className={styles.qaPanel}>
                                    {/* Quick chips */}
                                    <div className={styles.chipsRow}>
                                        {CHIPS.map((c, i) => (
                                            <button key={i} className={styles.chip} onClick={() => sendQuestion(c)} disabled={asking || !selTopic}>
                                                {c}
                                            </button>
                                        ))}
                                    </div>

                                    {/* Q&A thread */}
                                    <div className={styles.qaThread}>
                                        {qaThread.length === 0 && (
                                            <div className={styles.qaEmptyHint}>
                                                <MessageCircle size={20} style={{ color: 'var(--border)' }} />
                                                <span>Ask any question about this topic</span>
                                            </div>
                                        )}
                                        {qaThread.map((entry, i) => (
                                            <div
                                                key={i}
                                                className={`${styles.qaMessage} ${entry.role === 'user' ? styles.qaMessageUser : ''}`}
                                            >
                                                <div className={`${styles.qaAvatar} ${entry.role === 'user' ? styles.qaAvatarUser : styles.qaAvatarTutor}`}>
                                                    {entry.role === 'user' ? 'You' : <Brain size={12} />}
                                                </div>
                                                <div className={`${styles.qaBubble} ${entry.role === 'user' ? styles.qaBubbleUser : styles.qaBubbleTutor}`}>
                                                    {entry.content}
                                                    {entry.role === 'assistant' && entry.mermaid && (
                                                        <MiniCanvas code={entry.mermaid} />
                                                    )}
                                                </div>
                                            </div>
                                        ))}
                                        {asking && (
                                            <div className={styles.qaMessage}>
                                                <div className={`${styles.qaAvatar} ${styles.qaAvatarTutor}`}>
                                                    <Brain size={12} />
                                                </div>
                                                <div className={`${styles.qaThinking}`}>
                                                    <Loader2 size={13} className={styles.spin} /> Thinking…
                                                </div>
                                            </div>
                                        )}
                                    </div>

                                    {askErr && <p className={styles.qaErr}>{askErr}</p>}

                                    {/* Input row */}
                                    <div className={styles.qaInputRow}>
                                        <textarea
                                            className={styles.qaInput}
                                            rows={1}
                                            placeholder={speech.listening ? 'Listening…' : 'Type or speak your question…'}
                                            value={questionInput}
                                            onChange={e => setQuestionInput(e.target.value)}
                                            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuestion(); } }}
                                            disabled={asking}
                                        />
                                        <button
                                            className={styles.sendBtn}
                                            onClick={() => sendQuestion()}
                                            disabled={asking || !questionInput.trim()}
                                        >
                                            {asking ? <Loader2 size={15} className={styles.spin} /> : <Send size={15} />}
                                        </button>
                                    </div>
                                </div>
                            </>
                        )}
                    </>
                )}
            </div>

            {/* ── Silence Alert Banner (V8) ──────────────────────────────── */}
            {silenceAlert && (
                <div style={{
                    position: 'fixed', bottom: 80, left: '50%', transform: 'translateX(-50%)',
                    background: 'var(--watch)', color: '#1a1a1a', borderRadius: 12,
                    padding: '12px 20px', fontSize: '0.82rem', fontWeight: 500,
                    maxWidth: 480, zIndex: 900, display: 'flex', alignItems: 'center', gap: 12,
                    boxShadow: '0 4px 20px rgba(0,0,0,.2)',
                }}>
                    <span style={{ fontSize: '1.1rem' }}>
                        {silenceAlert.severity === 'high' ? '😵' : silenceAlert.severity === 'moderate' ? '🤔' : '💡'}
                    </span>
                    <span>{silenceAlert.suggestion}</span>
                    <button
                        onClick={() => { setSilenceAlert(null); lastInteractRef.current = Date.now(); }}
                        style={{ background: 'transparent', border: 'none', cursor: 'pointer', fontWeight: 700, fontSize: '1rem' }}
                    >✕</button>
                </div>
            )}
        </div>

        {/* ── Modal: Diagram History (V2) ──────────────────────────────── */}
        {showDiagramHistory && (
            <DiagramHistory
                sessionId={sessionId}
                onClose={() => setShowDiagramHistory(false)}
            />
        )}

        {/* ── Modal: Peer Learning (V6) ────────────────────────────────── */}
        {showPeerRoom && (
            <PeerLearning
                topic={selTopic || ''}
                subjectCode={selSubject?.code || ''}
                onClose={() => setShowPeerRoom(false)}
            />
        )}

        {/* ── Modal: Study Mode Selector (V9) ─────────────────────────── */}
        {showStudyMode && (
            <div style={{
                position: 'fixed', inset: 0, background: 'rgba(0,0,0,.65)', zIndex: 990,
                display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
            }} onClick={() => setShowStudyMode(false)}>
                <div style={{
                    background: 'var(--surface)', borderRadius: 16, border: '1px solid var(--border)',
                    padding: 24, maxWidth: 400, width: '100%', maxHeight: '80vh', overflowY: 'auto',
                }} onClick={e => e.stopPropagation()}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                        <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 600, color: 'var(--text-1)' }}>📚 Study Mode</h3>
                        <button onClick={() => setShowStudyMode(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-3)', fontSize: '1rem' }}>✕</button>
                    </div>
                    <StudyModeSelector
                        currentMode={studyMode}
                        onSelect={mode => { setStudyMode(mode); setShowStudyMode(false); }}
                    />
                </div>
            </div>
        )}
        </>
    );
}
