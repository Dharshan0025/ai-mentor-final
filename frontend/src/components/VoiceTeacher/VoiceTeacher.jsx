/**
 * VoiceTeacher — Nova Sonic voice personality selector and audio playback component
 *
 * Features:
 *  - Voice personality selector (Professor / Coach / Friend)
 *  - Nova Sonic TTS via Bedrock with browser TTS fallback
 *  - Animated waveform bars during playback
 *  - Microphone recording → backend STT or browser STT fallback
 *  - Speed control slider
 *  - Hands-free toggle mode
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import {
    Mic, MicOff, Volume2, VolumeX, GraduationCap, Dumbbell, Users,
    Loader2, AlertCircle,
} from 'lucide-react';
import { tutorVoiceSpeak, tutorVoiceTranscribe, getVoiceSettings } from '../../services/api';
import styles from './VoiceTeacher.module.css';

// ── Voice personalities ────────────────────────────────────────────────────
const PERSONALITIES = [
    {
        id: 'professor',
        label: 'Professor',
        desc: 'Formal & clear',
        icon: GraduationCap,
        iconColor: '#2563EB',
    },
    {
        id: 'coach',
        label: 'Coach',
        desc: 'Energetic & motivating',
        icon: Dumbbell,
        iconColor: '#16A34A',
    },
    {
        id: 'friend',
        label: 'Friend',
        desc: 'Casual & warm',
        icon: Users,
        iconColor: '#FF7A00',
    },
];

// ── Audio playback via Web Audio API ──────────────────────────────────────
async function playWavArrayBuffer(arrayBuffer, audioCtxRef, gainValue = 1.0) {
    if (!audioCtxRef.current) {
        audioCtxRef.current = new (window.AudioContext || window.webkitAudioContext)();
    }
    const ctx = audioCtxRef.current;
    if (ctx.state === 'suspended') await ctx.resume();

    const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
    const source = ctx.createBufferSource();
    const gainNode = ctx.createGain();
    gainNode.gain.value = gainValue;

    source.buffer = audioBuffer;
    source.connect(gainNode);
    gainNode.connect(ctx.destination);
    source.start(0);
    return new Promise(resolve => { source.onended = resolve; });
}

// ── Browser TTS fallback ───────────────────────────────────────────────────
function browserSpeak(text, personality = 'professor', speedRate = 1.0) {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    const voices = window.speechSynthesis.getVoices();
    const englishVoice = voices.find(v => v.lang.startsWith('en') && v.localService) || voices[0];
    u.voice = englishVoice;
    u.rate  = (personality === 'coach' ? 1.1 : personality === 'professor' ? 0.9 : 1.0) * speedRate;
    u.pitch = personality === 'coach' ? 1.1 : personality === 'friend' ? 1.05 : 1.0;
    window.speechSynthesis.speak(u);
}

// ── Waveform bars ─────────────────────────────────────────────────────────
function WaveformBars({ active }) {
    return (
        <div className={`${styles.waveform} ${active ? styles.waveformActive : ''}`}>
            {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className={styles.waveBar} style={{ animationDelay: `${i * 0.07}s` }} />
            ))}
        </div>
    );
}

// ── Main component ─────────────────────────────────────────────────────────
export default function VoiceTeacher({
    enabled,
    onToggle,
    onTranscript,
    speakQueue = [],
    onSpeakQueueItem,
}) {
    const [personality, setPersonality] = useState('professor');
    const [speaking, setSpeaking]       = useState(false);
    const [listening, setListening]     = useState(false);
    const [loading, setLoading]         = useState(false);
    const [error, setError]             = useState(null);
    const [provider, setProvider]       = useState('browser-tts');
    const [handsFreeModeOn, setHandsFreeModeOn] = useState(false);
    const [speedRate, setSpeedRate]     = useState(1.0);  // Voice speed: 0.5× – 2.0×

    const audioCtxRef = useRef(null);
    const mediaRecorderRef = useRef(null);
    const chunksRef = useRef([]);
    const speakQueueRef = useRef(speakQueue);
    const processingRef = useRef(false);

    speakQueueRef.current = speakQueue;

    // Load voice settings to know if Nova Sonic is available
    useEffect(() => {
        if (!enabled) return;
        getVoiceSettings()
            .then(s => setProvider(s.tts_provider || 'browser-tts'))
            .catch(() => setProvider('browser-tts'));
    }, [enabled]);

    // Process speak queue
    useEffect(() => {
        if (!enabled || processingRef.current || speakQueue.length === 0) return;
        const item = speakQueue[0];
        processingRef.current = true;
        speakText(item.text, item.personality || personality)
            .finally(() => {
                processingRef.current = false;
                onSpeakQueueItem?.(item);
            });
    }, [speakQueue, enabled, personality]);

    const speakText = useCallback(async (text, voicePersonality = personality) => {
        if (!text || !enabled) return;
        setSpeaking(true);
        setError(null);

        try {
            const arrayBuffer = await tutorVoiceSpeak({ text, voice: voicePersonality, maxChars: 500 });

            if (arrayBuffer && arrayBuffer.byteLength > 0) {
                await playWavArrayBuffer(arrayBuffer, audioCtxRef);
            } else {
                browserSpeak(text.slice(0, 300), voicePersonality, speedRate);
                const ms = Math.max(2000, Math.min(12000, text.length * 60));
                await new Promise(r => setTimeout(r, ms));
            }
        } catch (e) {
            console.warn('[VoiceTeacher] TTS error:', e);
            browserSpeak(text.slice(0, 300), voicePersonality, speedRate);
        } finally {
            setSpeaking(false);
        }
    }, [enabled, personality, speedRate]);

    const startRecording = useCallback(async () => {
        if (listening) return;
        setError(null);
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            chunksRef.current = [];
            const mr = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
            mr.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data); };
            mr.onstop = async () => {
                stream.getTracks().forEach(t => t.stop());
                if (chunksRef.current.length === 0) return;
                const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
                setLoading(true);
                try {
                    const transcript = await tutorVoiceTranscribe(blob);
                    if (transcript) {
                        onTranscript?.(transcript);
                    } else {
                        // Backend STT failed — try browser STT
                        _browserSTT();
                    }
                } catch {
                    _browserSTT();
                } finally {
                    setLoading(false);
                }
            };
            mr.start();
            mediaRecorderRef.current = mr;
            setListening(true);
        } catch (e) {
            setError('Microphone access denied');
            // Fall back to browser Web Speech API
            _browserSTT();
        }
    }, [listening, onTranscript]);

    const stopRecording = useCallback(() => {
        if (!listening) return;
        mediaRecorderRef.current?.stop();
        mediaRecorderRef.current = null;
        setListening(false);
    }, [listening]);

    const _browserSTT = useCallback(() => {
        const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SR) return;
        const r = new SR();
        r.continuous = false; r.interimResults = false; r.lang = 'en-US';
        r.onresult = e => { onTranscript?.(e.results[0][0].transcript); };
        r.onerror = () => { };
        r.start();
    }, [onTranscript]);

    const handleMicClick = useCallback(() => {
        if (listening) stopRecording();
        else startRecording();
    }, [listening, startRecording, stopRecording]);

    if (!enabled) return null;

    return (
        <div className={styles.voiceTeacher}>
            {/* Header */}
            <div className={styles.header}>
                <Volume2 size={14} className={styles.headerIcon} />
                <span className={styles.headerTitle}>Nova Sonic Voice</span>
                <span className={styles.providerChip}>
                    {provider === 'amazon-nova-sonic' ? '🔵 Nova Sonic' : '🌐 Browser TTS'}
                </span>
                <button className={styles.closeBtn} onClick={onToggle}>✕</button>
            </div>

            {/* Personality selector */}
            <div className={styles.personalities}>
                {PERSONALITIES.map(p => {
                    const Icon = p.icon;
                    return (
                        <button
                            key={p.id}
                            className={`${styles.personalityBtn} ${personality === p.id ? styles.personalityActive : ''}`}
                            onClick={() => setPersonality(p.id)}
                            title={p.desc}
                        >
                            <Icon size={16} style={{ color: personality === p.id ? p.iconColor : undefined }} />
                            <span>{p.label}</span>
                            <span className={styles.personalityDesc}>{p.desc}</span>
                        </button>
                    );
                })}
            </div>

            {/* Waveform + mic row */}
            <div className={styles.waveRow}>
                <WaveformBars active={speaking} />
                <div className={styles.stateLabel}>
                    {speaking && <><span className={styles.dot} /> Speaking…</>}
                    {listening && <><span className={`${styles.dot} ${styles.dotRed}`} /> Listening…</>}
                    {loading && <><Loader2 size={12} className={styles.spin} /> Processing…</>}
                    {!speaking && !listening && !loading && <span className={styles.readyText}>Ready</span>}
                </div>

                {/* Mic button */}
                <button
                    className={`${styles.micBtn} ${listening ? styles.micBtnActive : ''}`}
                    onClick={handleMicClick}
                    disabled={speaking || loading}
                    title={listening ? 'Stop recording' : 'Start recording'}
                >
                    {listening ? <MicOff size={18} /> : <Mic size={18} />}
                </button>
            </div>

            {/* Hands-free mode toggle */}
            <label className={styles.handsFreeRow}>
                <input
                    type="checkbox"
                    checked={handsFreeModeOn}
                    onChange={e => setHandsFreeModeOn(e.target.checked)}
                    className={styles.handsFreeCheckbox}
                />
                <span>Hands-free mode</span>
                <span className={styles.handsFreeHint}>(auto-listen after each step)</span>
            </label>

            {/* Speed control */}
            <div className={styles.speedRow}>
                <span className={styles.speedLabel}>Speed: {speedRate.toFixed(1)}×</span>
                <input
                    type="range" min={0.5} max={2.0} step={0.1}
                    value={speedRate}
                    onChange={e => setSpeedRate(parseFloat(e.target.value))}
                    className={styles.speedSlider}
                    title="Voice speed"
                />
                <span className={styles.speedHint}>🐢 Slow · Fast 🐇</span>
            </div>

            {error && (
                <div className={styles.errorRow}>
                    <AlertCircle size={13} />
                    <span>{error}</span>
                </div>
            )}
        </div>
    );
}
