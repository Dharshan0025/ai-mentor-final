import React, { useState, useRef, useEffect } from 'react';
import { Mic, Square, Volume2, User, Loader2 } from 'lucide-react';
import styles from './VoiceMentor.module.css';
import TeacherAvatar from '../TeacherAvatar/TeacherAvatar';

export default function VoiceMentor({ onTranscript, autoPlayText, variant = 'default' }) {
    const [status, setStatus] = useState('idle'); // idle, listening, processing, speaking
    const [audioUrl, setAudioUrl] = useState(null);
    const mediaRecorder = useRef(null);
    const audioChunks = useRef([]);
    const audioEl = useRef(null);
    const analyzer = useRef(null);
    const [volume, setVolume] = useState(0);
    const animationFrameId = useRef(null);

    // If autoPlayText changes, trigger TTS synthesis
    useEffect(() => {
        if (autoPlayText && autoPlayText.length > 0) {
            handleSpeak(autoPlayText);
        }
    }, [autoPlayText]);

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder.current = new MediaRecorder(stream, { mimeType: 'audio/webm' });
            
            mediaRecorder.current.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunks.current.push(event.data);
                }
            };

            mediaRecorder.current.onstop = async () => {
                const audioBlob = new Blob(audioChunks.current, { type: 'audio/webm' });
                audioChunks.current = [];
                setStatus('processing');
                await handleTranscribe(audioBlob);
            };

            mediaRecorder.current.start();
            setStatus('listening');

            // Set up volume analyzer for pulse animation
            const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const source = audioCtx.createMediaStreamSource(stream);
            const analyserNode = audioCtx.createAnalyser();
            analyserNode.fftSize = 256;
            source.connect(analyserNode);
            analyzer.current = analyserNode;
            
            const dataArray = new Uint8Array(analyserNode.frequencyBinCount);
            const updateVolume = () => {
                analyserNode.getByteTimeDomainData(dataArray);
                let max = 0;
                for (let i = 0; i < dataArray.length; i++) {
                    const diff = Math.abs(dataArray[i] - 128);
                    if (diff > max) max = diff;
                }
                setVolume(max);
                if (status === 'listening') {
                    animationFrameId.current = requestAnimationFrame(updateVolume);
                }
            };
            updateVolume();

        } catch (err) {
            console.error('Failed to start microphone:', err);
            alert('Microphone access denied or unavailable.');
            setStatus('idle');
        }
    };

    const stopRecording = () => {
        if (mediaRecorder.current && mediaRecorder.current.state !== 'inactive') {
            mediaRecorder.current.stop();
            mediaRecorder.current.stream.getTracks().forEach(t => t.stop());
        }
        if (animationFrameId.current) {
            cancelAnimationFrame(animationFrameId.current);
        }
        setVolume(0);
    };

    const handleTranscribe = async (blob) => {
        const formData = new FormData();
        formData.append('audio', blob, 'recording.webm');
        
        try {
            const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8000';
            const res = await fetch(`${apiBase}/voice/transcribe`, {
                method: 'POST',
                body: formData
            });
            const data = await res.json();
            if (data.transcript) {
                // Send transcript up to parent Chat.jsx
                onTranscript(data.transcript);
            }
        } catch (err) {
            console.error('Transcription error:', err);
        } finally {
            setStatus('idle');
        }
    };

    const handleSpeak = async (text) => {
        setStatus('speaking');
        try {
            const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8000';
            const res = await fetch(`${apiBase}/voice/synthesize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, personality: 'professor' })
            });

            if (!res.ok) throw new Error('Network response was not ok');
            
            const audioBlob = await res.blob();
            const url = URL.createObjectURL(audioBlob);
            setAudioUrl(url);

        } catch (err) {
            console.error('TTS error:', err);
            setStatus('idle');
        }
    };

    const handleAudioEnded = () => {
        setStatus('idle');
        if (audioUrl) {
            URL.revokeObjectURL(audioUrl);
            setAudioUrl(null);
        }
    };

    const getAvatarState = () => {
        switch (status) {
            case 'listening': return 'thinking';
            case 'processing': return 'thinking';
            case 'speaking': return 'teaching';
            default: return 'idle';
        }
    };

    if (variant === 'inline') {
        return (
            <div className={styles.inlineContainer}>
                {status === 'idle' || status === 'speaking' ? (
                    <button className={styles.inlineMicButton} onClick={startRecording} title="Hold or Click to Speak">
                        <Mic size={18} />
                    </button>
                ) : status === 'listening' ? (
                    <button className={`${styles.inlineMicButton} ${styles.recording}`} onClick={stopRecording}>
                        <Square size={18} />
                    </button>
                ) : (
                    <button className={styles.inlineMicButton} disabled>
                        <Loader2 size={18} className={styles.spin} />
                    </button>
                )}

                {audioUrl && (
                    <audio 
                        ref={audioEl} 
                        src={audioUrl} 
                        autoPlay 
                        onEnded={handleAudioEnded}
                        onError={handleAudioEnded}
                        className={styles.hiddenAudio} 
                    />
                )}
            </div>
        );
    }

    return (
        <div className={styles.container}>
            <div className={styles.avatarWrapper} style={{ transform: `scale(${1 + volume * 0.001})` }}>
                <TeacherAvatar state={getAvatarState()} size={100} />
                
                {status === 'processing' && (
                    <div className={styles.spinnerBadge}><Loader2 size={16} className={styles.spin} /></div>
                )}
                {status === 'speaking' && (
                    <div className={styles.speakingBadge}><Volume2 size={16} className={styles.pulse} /></div>
                )}
            </div>
            
            <div className={styles.controls}>
                {status === 'idle' || status === 'speaking' ? (
                    <button className={styles.micButton} onClick={startRecording} title="Hold or Click to Speak">
                        <Mic size={20} />
                        <span>Tap to Talk</span>
                    </button>
                ) : status === 'listening' ? (
                    <button className={`${styles.micButton} ${styles.recording}`} onClick={stopRecording}>
                        <Square size={20} />
                        <span>Stop Recording</span>
                    </button>
                ) : (
                    <button className={styles.micButton} disabled>
                        <Loader2 size={20} className={styles.spin} />
                        <span>Processing...</span>
                    </button>
                )}
            </div>

            {audioUrl && (
                <audio 
                    ref={audioEl} 
                    src={audioUrl} 
                    autoPlay 
                    onEnded={handleAudioEnded}
                    onError={handleAudioEnded}
                    className={styles.hiddenAudio} 
                />
            )}
        </div>
    );
}
