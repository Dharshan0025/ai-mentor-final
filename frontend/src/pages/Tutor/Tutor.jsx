/**
 * AI Visual Tutor — n8n-style immersive teaching canvas
 * Fully redesigned to work inside AppLayout (no duplicate sidebar).
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import {
    Volume2, VolumeX, Mic, MicOff, Send, Brain, Zap, ChevronRight,
    RotateCcw, Loader2, Maximize2, Minimize2, AlertTriangle,
    MessageCircle, Play, BookOpen, CheckCircle2, Circle
} from 'lucide-react';
import mermaid from 'mermaid';
import styles from './Tutor.module.css';
import { getTutorOptions, startTutorLesson, askTutorQuestion, clearTutorSession } from '../../services/api';

// ── Mermaid init ───────────────────────────────────────────────────────────
mermaid.initialize({
    startOnLoad: false,
    theme: 'dark',
    themeVariables: {
        background: '#0d1117',
        primaryColor: '#6366f1',
        primaryTextColor: '#e2e8f0',
        primaryBorderColor: '#4f46e5',
        lineColor: '#475569',
        secondaryColor: '#1e293b',
        tertiaryColor: '#1e293b',
        edgeLabelBackground: '#1e293b',
        fontFamily: 'Inter, system-ui, sans-serif',
        fontSize: '14px',
        nodeBorder: '#334155',
        clusterBkg: '#1e293b',
        titleColor: '#e2e8f0',
        actorBkg: '#1e293b',
        actorBorder: '#6366f1',
        actorTextColor: '#e2e8f0',
        signalColor: '#94a3b8',
        labelBoxBkgColor: '#1e293b',
        labelTextColor: '#e2e8f0',
    },
    flowchart: { curve: 'basis', padding: 24, htmlLabels: true },
    sequence: { fontSize: 13, actorMargin: 50 },
});

// ── Sanitize mermaid output from LLM ─────────────────────────────────────
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

// ── Suggested question chips ───────────────────────────────────────────────
const CHIPS = [
    'Explain in simpler terms',
    'Give a real-world example',
    'Quiz me on this',
    "What's the key takeaway?",
    'How does this relate to the exam?',
];

// ── Voice hook ────────────────────────────────────────────────────────────
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

// ── Canvas Whiteboard ─────────────────────────────────────────────────────
function Canvas({ code, title, stepNum, totalSteps }) {
    const [svg, setSvg] = useState('');
    const [err, setErr] = useState(null);
    const [rendering, setRendering] = useState(false);
    const [fullscreen, setFullscreen] = useState(false);

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

    return (
        <div className={`${styles.canvas} ${fullscreen ? styles.canvasFull : ''}`}>
            {/* Grid background */}
            <div className={styles.canvasGrid} />

            {/* Header bar */}
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
                <button className={styles.canvasBtn} onClick={() => setFullscreen(f => !f)} title="Toggle fullscreen">
                    {fullscreen ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
                </button>
            </div>

            {/* Content */}
            <div className={styles.canvasBody}>
                {!code && !rendering && (
                    <div className={styles.canvasEmpty}>
                        <Brain size={44} className={styles.canvasEmptyIcon} />
                        <p>Start a lesson — diagrams will appear here</p>
                        <p className={styles.canvasEmptyHint}>Like n8n, each step lights up on the board</p>
                    </div>
                )}
                {rendering && (
                    <div className={styles.canvasLoader}>
                        <Loader2 size={22} className={styles.spin} />
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
                    <div className={styles.canvasDiagramCard}>
                        <div
                            className={styles.canvasSvg}
                            dangerouslySetInnerHTML={{ __html: svg }}
                        />
                    </div>
                )}
            </div>

            {/* Step progress bar */}
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

// ── Teacher Avatar (speaking state from TTS) ──────────────────────────────
function TeacherAvatar({ speaking }) {
    return (
        <div className={`${styles.teacherAvatar} ${speaking ? styles.teacherAvatarSpeaking : ''}`} title="Tutor">
            <div className={styles.teacherAvatarIcon}>
                <Brain size={22} strokeWidth={2} />
            </div>
            <span className={styles.teacherAvatarLabel}>Tutor</span>
        </div>
    );
}

// ── Step Rail ─────────────────────────────────────────────────────────────
function StepRail({ steps, currentStep, teaching }) {
    return (
        <div className={styles.rail}>
            <div className={styles.railTitle}>
                <Zap size={12} />
                <span>LESSON FLOW</span>
            </div>
            <div className={styles.railItems}>
                {steps.map((s, i) => {
                    const done = i + 1 < currentStep;
                    const active = i + 1 === currentStep;
                    return (
                        <div key={i} className={`${styles.railItem} ${done ? styles.railDone : ''} ${active ? styles.railActive : ''}`}>
                            <div className={styles.railIcon}>
                                {done ? <CheckCircle2 size={14} /> : active ? <Play size={10} /> : <Circle size={14} />}
                            </div>
                            <span className={styles.railLabel}>{s.title}</span>
                            {active && <div className={styles.railPulse} />}
                        </div>
                    );
                })}
                {teaching && (
                    <div className={styles.railItem}>
                        <Loader2 size={14} className={styles.spin} style={{ color: '#6366f1' }} />
                        <span className={styles.railLabel} style={{ color: '#6366f1' }}>Loading…</span>
                    </div>
                )}
            </div>
        </div>
    );
}

// ── Main Page ─────────────────────────────────────────────────────────────
export default function Tutor() {
    const [options, setOptions] = useState({ subjects: [], topics_by_subject: {} });
    const [loadingOptions, setLoadingOptions] = useState(true);
    const [optErr, setOptErr] = useState(null);
    const [selSubject, setSelSubject] = useState(null);
    const [selTopic, setSelTopic] = useState(null);

    // Lesson
    const [teaching, setTeaching] = useState(false);
    const [steps, setSteps] = useState([]);
    const [currentStep, setCurrentStep] = useState(0);
    const [currentDiagram, setCurrentDiagram] = useState('');
    const [diagramTitle, setDiagramTitle] = useState('');
    const [narrationLog, setNarrationLog] = useState([]);
    const [lessonDone, setLessonDone] = useState(false);
    const [lessonErr, setLessonErr] = useState(null);
    const narrationEndRef = useRef(null);

    // Q&A
    const [questionInput, setQuestionInput] = useState('');
    const [qaThread, setQaThread] = useState([]);
    const [asking, setAsking] = useState(false);
    const [askErr, setAskErr] = useState(null);

    // Tutor session (server-side continuity)
    const [sessionId, setSessionId] = useState(() => typeof sessionStorage !== 'undefined' ? sessionStorage.getItem('tutor_session_id') : null);

    // Talk mode: when on, STT result is auto-sent and tutor reply is spoken
    const [talkMode, setTalkMode] = useState(false);
    const lastSentTranscriptRef = useRef('');

    const speech = useSpeech();

    const subjects = options.subjects || [];
    const topics = selSubject ? (options.topics_by_subject || {})[selSubject.code] || [] : [];

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

    useEffect(() => {
        if (!talkMode && speech.transcript) setQuestionInput(speech.transcript);
    }, [talkMode, speech.transcript]);

    // Talk mode: on STT result, auto-send and get TTS reply
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
            .catch(e => {
                setAskErr(e.response?.data?.detail || e.message || 'Failed to get answer');
            })
            .finally(() => {
                setAsking(false);
                lastSentTranscriptRef.current = '';
            });
    }, [talkMode, speech.listening, speech.transcript, selSubject, selTopic, qaThread, sessionId, speech.voiceEnabled, speech.setTranscript, speech.speak]);

    // Auto-scroll narration
    useEffect(() => {
        narrationEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [narrationLog]);

    const resetLesson = () => {
        speech.stop();
        setSelTopic(null); setTeaching(false); setSteps([]); setCurrentStep(0);
        setCurrentDiagram(''); setDiagramTitle(''); setNarrationLog([]);
        setLessonDone(false); setLessonErr(null); setQaThread([]);
        setQuestionInput(''); setAskErr(null); setSessionId(null);
        if (typeof sessionStorage !== 'undefined') sessionStorage.removeItem('tutor_session_id');
    };

    const startNewConversation = useCallback(async () => {
        if (sessionId) {
            try { await clearTutorSession(sessionId); } catch { /* ignore */ }
        }
        setSessionId(null);
        if (typeof sessionStorage !== 'undefined') sessionStorage.removeItem('tutor_session_id');
        setQaThread([]); setAskErr(null); setQuestionInput('');
    }, [sessionId]);

    const startLesson = useCallback(async (topic) => {
        setSelTopic(topic); setTeaching(true); setSteps([]); setCurrentStep(0);
        setCurrentDiagram(''); setDiagramTitle(''); setNarrationLog([]);
        setLessonDone(false); setLessonErr(null);
        speech.stop();

        try {
            const res = await startTutorLesson({ subjectCode: selSubject.code, topic, mode: 'visual', sessionId });
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
                                if (typeof sessionStorage !== 'undefined') sessionStorage.setItem('tutor_session_id', data.session_id);
                            } else if (evt === 'step') {
                                setSteps(p => [...p, { step: data.step, title: data.title }]);
                                setCurrentStep(data.step);
                                setDiagramTitle(data.title);
                            } else if (evt === 'narration') {
                                setNarrationLog(p => [...p, data.text]);
                                speech.speak(data.text);
                            } else if (evt === 'diagram') {
                                setCurrentDiagram(data.mermaid);
                                if (data.title) setDiagramTitle(data.title);
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
    }, [selSubject, sessionId, speech]);

    const sendQuestion = useCallback(async (text) => {
        const q = (text || questionInput || '').trim();
        if (!q || !selSubject || !selTopic) return;
        setQuestionInput(''); speech.setTranscript(''); setAskErr(null);
        setQaThread(p => [...p, { role: 'user', content: q }]);
        setAsking(true);
        try {
            const history = qaThread.slice(-6).map(({ role, content }) => ({ role, content }));
            const { answer } = await askTutorQuestion({ subjectCode: selSubject.code, topic: selTopic, question: q, history, sessionId });
            setQaThread(p => [...p, { role: 'assistant', content: answer }]);
            if (answer && speech.voiceEnabled) speech.speak(answer.replace(/\n+/g, ' ').slice(0, 400));
        } catch (e) {
            setAskErr(e.response?.data?.detail || e.message || 'Failed to get answer');
            setQaThread(p => p.slice(0, -1));
        } finally {
            setAsking(false);
        }
    }, [selSubject, selTopic, questionInput, qaThread, sessionId, speech]);

    if (loadingOptions) return (
        <div className={styles.loadingWrap}>
            <Loader2 size={28} className={styles.spin} />
            <span>Loading curriculum…</span>
        </div>
    );

    return (
        <div className={styles.root}>

            {/* ── Left panel: Subject + Topic picker ───────────────── */}
            <aside className={styles.panel}>
                <div className={styles.panelHeader}>
                    <GraduationCapIcon />
                    <span>AI Tutor</span>
                </div>

                {optErr && (
                    <div className={styles.panelErr}>
                        <AlertTriangle size={12} /> {optErr}
                    </div>
                )}

                {/* Subjects */}
                <div className={styles.panelSection}>
                    <span className={styles.panelSectionLabel}>SUBJECTS</span>
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
                                color: (s.bloomLevel ?? 2) >= 4 ? '#10b981' : (s.bloomLevel ?? 2) >= 2 ? '#f59e0b' : '#ef4444'
                            }}>L{s.bloomLevel ?? 2}</span>
                        </button>
                    ))}
                </div>

                {/* Topics */}
                {selSubject && (
                    <div className={styles.panelSection}>
                        <span className={styles.panelSectionLabel}>TOPICS — {selSubject.name}</span>
                        {topics.length === 0 && (
                            <p className={styles.panelEmpty}>No topics in syllabus for this subject.</p>
                        )}
                        {topics.map((t, i) => (
                            <button
                                key={i}
                                className={`${styles.topicBtn} ${selTopic === t ? styles.topicActive : ''}`}
                                onClick={() => startLesson(t)}
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

            {/* ── Main canvas area ──────────────────────────────────── */}
            <div className={styles.workspace}>
                {!selTopic ? (
                    <div className={styles.welcome}>
                        <div className={styles.welcomeGrid} />
                        <div className={styles.welcomeContent}>
                            <div className={styles.welcomeOrb} />
                            <Brain size={48} className={styles.welcomeIcon} />
                            <h2>AI Visual Tutor</h2>
                            <p>Select a topic from the left panel. Your tutor will explain it step-by-step with live diagrams and narration.</p>
                            <div className={styles.welcomeFeatures}>
                                {['n8n-style canvas diagrams', 'Voice narration (TTS)', 'Interactive Q&A'].map(f => (
                                    <span key={f} className={styles.welcomeTag}>✦ {f}</span>
                                ))}
                            </div>
                        </div>
                    </div>
                ) : (
                    <>
                        {/* Top status bar */}
                        <div className={styles.statusBar}>
                            <div className={styles.statusLeft}>
                                {teaching && <>
                                    <span className={styles.liveDot} />
                                    <span className={styles.statusText}>Teaching step {currentStep}…</span>
                                </>}
                                {lessonDone && <span className={styles.doneText}><CheckCircle2 size={13} /> Lesson complete — {steps.length} steps</span>}
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
                                    title={talkMode ? 'Talk mode: speak to send (click to stop)' : 'Voice input'}
                                >
                                    {speech.listening ? <MicOff size={14} /> : <Mic size={14} />}
                                </button>
                                <button
                                    type="button"
                                    className={`${styles.talkModeBtn} ${talkMode ? styles.talkModeBtnOn : ''}`}
                                    onClick={() => setTalkMode(m => !m)}
                                    title={talkMode ? 'Turn off: speak then tap Send' : 'Turn on: speak and get spoken reply'}
                                >
                                    <MessageCircle size={12} />
                                    <span>{talkMode ? ' Talk on' : ' Talk'}</span>
                                </button>
                                {(lessonDone || lessonErr) && (
                                    <button className={styles.resetBtn} onClick={resetLesson}>
                                        <RotateCcw size={13} /> New Topic
                                    </button>
                                )}
                            </div>
                        </div>

                        {/* Canvas + Rail */}
                        <div className={styles.canvasRow}>
                            <Canvas
                                code={currentDiagram}
                                title={diagramTitle}
                                stepNum={currentStep}
                                totalSteps={steps.length}
                            />
                            {steps.length > 0 && (
                                <StepRail steps={steps} currentStep={currentStep} teaching={teaching} />
                            )}
                        </div>

                        {/* Teacher avatar + Narration */}
                        <div className={styles.narrationRow}>
                            <TeacherAvatar speaking={speech.speaking} />
                            <div className={styles.narrationBox}>
                                <div className={styles.narrationHeader}>
                                    <span className={styles.narrationDot} />
                                    <span>Narration</span>
                                    {speech.speaking && <span className={styles.speakingTag}>Speaking…</span>}
                                </div>
                                <div className={styles.narrationScroll}>
                                    {narrationLog.length === 0 && teaching && (
                                        <p className={styles.narrationHint}>Tutor is preparing your lesson…</p>
                                    )}
                                    {narrationLog.map((t, i) => (
                                        <p key={i} className={styles.narrationLine}>{t}</p>
                                    ))}
                                    <div ref={narrationEndRef} />
                                </div>
                            </div>
                        </div>

                        {/* Q&A panel */}
                        <div className={styles.qaBox}>
                            <div className={styles.qaHeader}>
                                <MessageCircle size={13} />
                                <span>Ask a Question</span>
                            </div>
                            <div className={styles.chips}>
                                {CHIPS.map((c, i) => (
                                    <button key={i} className={styles.chip} onClick={() => sendQuestion(c)} disabled={asking}>
                                        {c}
                                    </button>
                                ))}
                            </div>
                            <div className={styles.qaInputRow}>
                                <input
                                    className={styles.qaInput}
                                    type="text"
                                    placeholder={speech.listening ? 'Listening…' : 'Type or speak your question…'}
                                    value={questionInput}
                                    onChange={e => setQuestionInput(e.target.value)}
                                    onKeyDown={e => e.key === 'Enter' && sendQuestion()}
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
                            {askErr && <p className={styles.qaErr}>{askErr}</p>}
                            {qaThread.length > 0 && (
                                <div className={styles.qaThread}>
                                    {qaThread.map((e, i) => (
                                        <div key={i} className={e.role === 'user' ? styles.qaUser : styles.qaAssistant}>
                                            <span className={styles.qaRole}>{e.role === 'user' ? 'You' : 'Tutor'}</span>
                                            <p className={styles.qaContent}>{e.content}</p>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}

function GraduationCapIcon() {
    return (
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 10v6M2 10l10-5 10 5-10 5z" />
            <path d="M6 12v5c3 3 9 3 12 0v-5" />
        </svg>
    );
}
