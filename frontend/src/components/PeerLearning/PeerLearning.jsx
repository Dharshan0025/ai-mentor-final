import { useState, useEffect, useRef } from 'react';
import { createStudyRoom, getStudyRoom, postRoomMessage, getStoredStudent } from '../../services/api';
import styles from './PeerLearning.module.css';

/**
 * PeerLearning — Study room component (V6).
 * Students can create or join a room using a room code, then chat in real-time (polling).
 */
export function PeerLearning({ topic = '', subjectCode = '', onClose }) {
    const [view, setView]         = useState('lobby');   // 'lobby' | 'room'
    const [roomCode, setRoomCode] = useState('');
    const [joinCode, setJoinCode] = useState('');
    const [room, setRoom]         = useState(null);
    const [messages, setMessages] = useState([]);
    const [input, setInput]       = useState('');
    const [creating, setCreating] = useState(false);
    const [joining, setJoining]   = useState(false);
    const [sending, setSending]   = useState(false);
    const [error, setError]       = useState('');
    const bottomRef               = useRef(null);
    const pollRef                 = useRef(null);

    const student     = getStoredStudent();
    const senderId    = student?.college_id || student?.id || 'anon';
    const senderName  = student?.name || 'Student';

    // Auto-scroll on new messages
    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages]);

    // Poll for new messages every 3s when in a room
    useEffect(() => {
        if (view !== 'room' || !roomCode) return;
        pollRef.current = setInterval(() => {
            getStudyRoom(roomCode)
                .then(r => setMessages(r.messages || []))
                .catch(() => {});
        }, 3000);
        return () => clearInterval(pollRef.current);
    }, [view, roomCode]);

    async function handleCreate() {
        setCreating(true);
        setError('');
        try {
            const r = await createStudyRoom({ topic, subject_code: subjectCode });
            setRoomCode(r.room_code);
            await loadRoom(r.room_code);
            setView('room');
        } catch {
            setError('Failed to create room. Try again.');
        } finally {
            setCreating(false);
        }
    }

    async function handleJoin() {
        if (!joinCode.trim()) return;
        setJoining(true);
        setError('');
        try {
            await loadRoom(joinCode.trim().toUpperCase());
            setRoomCode(joinCode.trim().toUpperCase());
            setView('room');
        } catch {
            setError('Room not found. Check the code and try again.');
        } finally {
            setJoining(false);
        }
    }

    async function loadRoom(code) {
        const r = await getStudyRoom(code);
        setRoom(r.room);
        setMessages(r.messages || []);
    }

    async function handleSend() {
        if (!input.trim() || sending) return;
        setSending(true);
        try {
            await postRoomMessage(roomCode, { sender_id: senderId, sender_name: senderName, message: input.trim() });
            setInput('');
            await loadRoom(roomCode);
        } catch {
            setError('Failed to send. Try again.');
        } finally {
            setSending(false);
        }
    }

    function handleKeyDown(e) {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
    }

    return (
        <div className={styles.overlay}>
            <div className={styles.panel}>
                {/* Header */}
                <div className={styles.header}>
                    <div>
                        <h3>👥 Peer Study Room</h3>
                        {view === 'room' && roomCode && (
                            <span className={styles.roomCode}>
                                Room: <strong>{roomCode}</strong>
                                <button className={styles.copyBtn} onClick={() => navigator.clipboard.writeText(roomCode)} title="Copy code">⧉</button>
                            </span>
                        )}
                    </div>
                    <button className={styles.close} onClick={onClose}>✕</button>
                </div>

                {/* Lobby */}
                {view === 'lobby' && (
                    <div className={styles.lobby}>
                        <div className={styles.lobbyCard}>
                            <div className={styles.lobbyTitle}>Create a new room</div>
                            <div className={styles.lobbyDesc}>
                                {topic ? `Topic: ${topic}` : 'Start a room and invite peers with the room code.'}
                            </div>
                            <button className={styles.primaryBtn} onClick={handleCreate} disabled={creating}>
                                {creating ? 'Creating…' : '➕ Create Room'}
                            </button>
                        </div>
                        <div className={styles.divider}>— or join existing —</div>
                        <div className={styles.lobbyCard}>
                            <div className={styles.lobbyTitle}>Join a room</div>
                            <input
                                className={styles.codeInput}
                                placeholder="Enter room code (e.g. AB12CD34)"
                                value={joinCode}
                                onChange={e => setJoinCode(e.target.value.toUpperCase())}
                                maxLength={8}
                            />
                            <button className={styles.primaryBtn} onClick={handleJoin} disabled={joining || !joinCode.trim()}>
                                {joining ? 'Joining…' : '🔗 Join Room'}
                            </button>
                        </div>
                        {error && <p className={styles.error}>{error}</p>}
                    </div>
                )}

                {/* Chat room */}
                {view === 'room' && (
                    <div className={styles.chatWrap}>
                        <div className={styles.topic}>
                            📚 {room?.topic || topic || 'General Study'} {room?.subject_code && `· ${room.subject_code}`}
                        </div>
                        <div className={styles.messages}>
                            {messages.length === 0 && (
                                <div className={styles.empty}>No messages yet. Start the conversation!</div>
                            )}
                            {messages.map(m => (
                                <div key={m.id} className={`${styles.msg} ${m.sender_id === senderId ? styles.me : ''}`}>
                                    <div className={styles.msgName}>{m.sender_id === senderId ? 'You' : m.sender_name}</div>
                                    <div className={styles.msgBubble}>{m.message}</div>
                                    <div className={styles.msgTime}>
                                        {new Date(m.sent_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                                    </div>
                                </div>
                            ))}
                            <div ref={bottomRef} />
                        </div>
                        {error && <p className={styles.error}>{error}</p>}
                        <div className={styles.inputRow}>
                            <textarea
                                className={styles.msgInput}
                                rows={2}
                                placeholder="Type a message… (Enter to send)"
                                value={input}
                                onChange={e => setInput(e.target.value)}
                                onKeyDown={handleKeyDown}
                                disabled={sending}
                            />
                            <button className={styles.sendBtn} onClick={handleSend} disabled={sending || !input.trim()}>
                                {sending ? '…' : '➤'}
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default PeerLearning;
