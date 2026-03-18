/**
 * KnowledgeHub — Phase 5 V7 Knowledge Engine
 * 4-tab page: My Documents, PYQ Analyzer, Concept Graph, My Notes
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import {
    Brain, FileText, Search, Upload, Trash2, BookOpen,
    AlertTriangle, CheckCircle, Download, RefreshCw, ChevronRight,
    FileSearch, Network, StickyNote, Plus, Loader2, X, Zap,
} from 'lucide-react';
import mermaid from 'mermaid';
import styles from './KnowledgeHub.module.css';
import {
    getDocuments, uploadDocument, deleteDocument,
    analyzePYQ, getPYQHistory,
    buildConceptGraph, getConceptGraph,
    generateNotes, getNotes, getNote, deleteNote,
    ragSearch, getTutorOptions,
} from '../../services/api';

// Mermaid config (matches Tutor.jsx theme)
mermaid.initialize({
    startOnLoad: false,
    theme: 'neutral',
    themeVariables: {
        background: '#FFFDF7', primaryColor: '#FF7A00',
        primaryTextColor: '#1C1410', lineColor: '#9A9A9A',
        fontFamily: 'Inter, system-ui, sans-serif', fontSize: '13px',
    },
    flowchart: { curve: 'basis', padding: 20, htmlLabels: true },
});

const TABS = [
    { id: 'docs', label: 'My Documents', icon: FileText },
    { id: 'pyq', label: 'PYQ Analyzer', icon: FileSearch },
    { id: 'graph', label: 'Concept Graph', icon: Network },
    { id: 'notes', label: 'My Notes', icon: StickyNote },
];

const BLOOM_COLORS = ['', '#94a3b8', '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6'];
const BLOOM_LABELS = ['', 'Remember', 'Understand', 'Apply', 'Analyze', 'Evaluate', 'Create'];

export default function KnowledgeHub() {
    const [activeTab, setActiveTab] = useState('docs');
    const [subjects, setSubjects] = useState([]);

    useEffect(() => {
        getTutorOptions().then(d => setSubjects(d.subjects || [])).catch(() => { });
    }, []);

    return (
        <div className={styles.page}>
            <header className={styles.header}>
                <div className={styles.headerIcon}><Brain size={24} /></div>
                <div>
                    <h1 className={styles.title}>Knowledge Hub</h1>
                    <p className={styles.subtitle}>Your AI-powered study intelligence centre</p>
                </div>
            </header>

            {/* Tab Bar */}
            <nav className={styles.tabBar}>
                {TABS.map(t => {
                    const Icon = t.icon;
                    return (
                        <button
                            key={t.id}
                            className={`${styles.tab} ${activeTab === t.id ? styles.tabActive : ''}`}
                            onClick={() => setActiveTab(t.id)}
                        >
                            <Icon size={16} />
                            <span>{t.label}</span>
                        </button>
                    );
                })}
            </nav>

            {/* Tab Panels */}
            <div className={styles.panel}>
                {activeTab === 'docs' && <DocsTab subjects={subjects} />}
                {activeTab === 'pyq' && <PYQTab subjects={subjects} />}
                {activeTab === 'graph' && <GraphTab subjects={subjects} />}
                {activeTab === 'notes' && <NotesTab subjects={subjects} />}
            </div>
        </div>
    );
}

// ── Documents Tab ────────────────────────────────────────────────────────────
function DocsTab({ subjects }) {
    const [docs, setDocs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);
    const [selSubject, setSelSubject] = useState('');
    const [searchQ, setSearchQ] = useState('');
    const [searchResults, setSearchResults] = useState(null);
    const [searching, setSearching] = useState(false);
    const fileRef = useRef(null);

    const loadDocs = useCallback(async () => {
        setLoading(true);
        try { setDocs((await getDocuments()).documents || []); } catch { setDocs([]); }
        setLoading(false);
    }, []);

    useEffect(() => { loadDocs(); }, [loadDocs]);

    const handleUpload = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;
        setUploading(true);
        try {
            await uploadDocument(file, selSubject);
            await loadDocs();
        } catch (err) {
            alert(err.response?.data?.detail || 'Upload failed');
        } finally {
            setUploading(false);
            e.target.value = '';
        }
    };

    const handleDelete = async (id) => {
        if (!confirm('Delete this document and all its indexed chunks?')) return;
        try { await deleteDocument(id); await loadDocs(); } catch { alert('Delete failed'); }
    };

    const handleSearch = async () => {
        if (!searchQ.trim()) return;
        setSearching(true);
        try {
            const r = await ragSearch(searchQ, selSubject || null);
            setSearchResults(r.results || []);
        } catch { setSearchResults([]); }
        setSearching(false);
    };

    const statusBadge = (s) => ({
        processing: <span className={`${styles.badge} ${styles.badgeWarn}`}>⏳ Processing</span>,
        ready: <span className={`${styles.badge} ${styles.badgeOk}`}>✅ Ready</span>,
        error: <span className={`${styles.badge} ${styles.badgeErr}`}>❌ Error</span>,
    }[s] || null);

    return (
        <div className={styles.tabContent}>
            <div className={styles.sectionRow}>
                <h2 className={styles.sectionTitle}><FileText size={16} /> My Study Materials</h2>
                <div className={styles.actions}>
                    <select className={styles.select} value={selSubject} onChange={e => setSelSubject(e.target.value)}>
                        <option value="">All Subjects</option>
                        {subjects.map(s => <option key={s.code} value={s.code}>{s.name}</option>)}
                    </select>
                    <button className={styles.uploadBtn} onClick={() => fileRef.current?.click()} disabled={uploading}>
                        {uploading ? <Loader2 size={15} className={styles.spin} /> : <Upload size={15} />}
                        {uploading ? 'Uploading…' : 'Upload PDF'}
                    </button>
                    <input ref={fileRef} type="file" accept=".pdf" hidden onChange={handleUpload} />
                </div>
            </div>

            {/* RAG Search */}
            <div className={styles.searchRow}>
                <input
                    className={styles.searchInput}
                    placeholder="Search your documents semantically…"
                    value={searchQ}
                    onChange={e => setSearchQ(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleSearch()}
                />
                <button className={styles.searchBtn} onClick={handleSearch} disabled={searching}>
                    {searching ? <Loader2 size={15} className={styles.spin} /> : <Search size={15} />}
                </button>
            </div>

            {searchResults !== null && (
                <div className={styles.searchResults}>
                    {searchResults.length === 0
                        ? <p className={styles.empty}>No relevant results found.</p>
                        : searchResults.map((r, i) => (
                            <div key={i} className={styles.resultChunk}>
                                <div className={styles.chunkMeta}>
                                    <span className={styles.chunkFile}>{r.filename}</span>
                                    <span className={styles.chunkSim}>{(r.similarity * 100).toFixed(0)}% match</span>
                                </div>
                                <p className={styles.chunkText}>{r.content}</p>
                            </div>
                        ))
                    }
                </div>
            )}

            {/* Document List */}
            {loading ? (
                <div className={styles.centerLoader}><Loader2 size={24} className={styles.spin} /></div>
            ) : docs.length === 0 ? (
                <div className={styles.emptyState}>
                    <FileText size={40} className={styles.emptyIcon} />
                    <p>No documents uploaded yet.</p>
                    <p className={styles.emptyHint}>Upload a PDF textbook or notes — the AI will index it for semantic search and RAG-enhanced teaching.</p>
                </div>
            ) : (
                <div className={styles.docList}>
                    {docs.filter(d => !selSubject || d.subject_code === selSubject).map(d => (
                        <div key={d.id} className={styles.docCard}>
                            <div className={styles.docIcon}><FileText size={20} /></div>
                            <div className={styles.docInfo}>
                                <div className={styles.docName}>{d.original_name}</div>
                                <div className={styles.docMeta}>
                                    {d.subject_code && <span className={styles.docSubject}>{d.subject_code}</span>}
                                    <span>{d.chunks_count || 0} chunks indexed</span>
                                    <span>{((d.file_size_bytes || 0) / 1024).toFixed(0)} KB</span>
                                </div>
                            </div>
                            {statusBadge(d.status)}
                            <button className={styles.iconBtn} onClick={() => handleDelete(d.id)} title="Delete">
                                <Trash2 size={15} />
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

// ── PYQ Analyzer Tab ─────────────────────────────────────────────────────────
function PYQTab({ subjects }) {
    const [selSubject, setSelSubject] = useState('');
    const [title, setTitle] = useState('');
    const [text, setText] = useState('');
    const [analyzing, setAnalyzing] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState('');
    const [history, setHistory] = useState([]);

    useEffect(() => {
        getPYQHistory().then(d => setHistory(d.analyses || [])).catch(() => { });
    }, []);

    const handleAnalyze = async () => {
        if (!text.trim()) { setError('Please paste the question paper text.'); return; }
        if (!selSubject) { setError('Please select a subject.'); return; }
        setError(''); setAnalyzing(true);
        try {
            const r = await analyzePYQ({ text, subject_code: selSubject, title: title || undefined });
            setResult(r);
            getPYQHistory().then(d => setHistory(d.analyses || [])).catch(() => { });
        } catch (e) {
            setError(e.response?.data?.detail || 'Analysis failed. Try again.');
        }
        setAnalyzing(false);
    };

    return (
        <div className={styles.tabContent}>
            <h2 className={styles.sectionTitle}><FileSearch size={16} /> Past Year Question Analyzer</h2>
            <p className={styles.sectionHint}>Paste a question paper → AI extracts topic weights, Bloom's levels, and exam predictions.</p>

            <div className={styles.pyqForm}>
                <div className={styles.formRow}>
                    <select className={styles.select} value={selSubject} onChange={e => setSelSubject(e.target.value)}>
                        <option value="">Select Subject *</option>
                        {subjects.map(s => <option key={s.code} value={s.code}>{s.name}</option>)}
                    </select>
                    <input
                        className={styles.input}
                        placeholder="Title (e.g. May 2024 PYQ)"
                        value={title}
                        onChange={e => setTitle(e.target.value)}
                    />
                </div>
                <textarea
                    className={styles.textarea}
                    rows={10}
                    placeholder={"Paste the full question paper here…\n\nExample:\n1. Explain Binary Search Tree with examples. (10 marks)\n2. Write Dijkstra's algorithm. (8 marks)\n..."}
                    value={text}
                    onChange={e => setText(e.target.value)}
                />
                {error && <p className={styles.err}>{error}</p>}
                <button className={styles.analyzeBtn} onClick={handleAnalyze} disabled={analyzing}>
                    {analyzing ? <><Loader2 size={15} className={styles.spin} /> Analyzing…</> : <><Zap size={15} /> Analyze Paper</>}
                </button>
            </div>

            {result && (
                <div className={styles.pyqResult}>
                    <div className={styles.pyqSummaryRow}>
                        <span className={styles.pyqStat}>{result.total_questions} Questions</span>
                        <span className={styles.pyqStat}>{result.topics_count} Topics</span>
                        {result.summary && <p className={styles.pyqSummary}>{result.summary}</p>}
                    </div>
                    <div className={styles.topicTable}>
                        <div className={styles.tableHeader}>
                            <span>Topic</span><span>Bloom's</span><span>Freq.</span><span>Weight</span><span>Exam?</span>
                        </div>
                        {(result.topics || []).map((t, i) => (
                            <div key={i} className={`${styles.tableRow} ${t.likely_exam ? styles.highWeight : ''}`}>
                                <span className={styles.topicName}>{t.name}</span>
                                <span
                                    className={styles.bloomBadge}
                                    style={{ background: BLOOM_COLORS[t.bloom_level] || '#ccc' }}
                                    title={t.bloom_desc}
                                >
                                    L{t.bloom_level} {BLOOM_LABELS[t.bloom_level]}
                                </span>
                                <span className={styles.freq}>{t.frequency}×</span>
                                <div className={styles.weightBar}>
                                    <div className={styles.weightFill} style={{ width: `${Math.min(t.weight_pct, 100)}%` }} />
                                    <span className={styles.weightLabel}>{t.weight_pct}%</span>
                                </div>
                                <span>{t.likely_exam ? '🎯 Yes' : '—'}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {history.length > 0 && !result && (
                <div className={styles.historySection}>
                    <h3 className={styles.historyTitle}>Recent Analyses</h3>
                    {history.map(h => (
                        <div key={h.id} className={styles.historyItem}>
                            <BookOpen size={14} />
                            <span>{h.title || h.subject_code}</span>
                            <span className={styles.histMeta}>{h.total_questions}Q · {h.topics_count} topics</span>
                            <span className={styles.histDate}>{new Date(h.created_at).toLocaleDateString()}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

// ── Concept Graph Tab ────────────────────────────────────────────────────────
function GraphTab({ subjects }) {
    const [selSubject, setSelSubject] = useState('');
    const [building, setBuilding] = useState(false);
    const [graph, setGraph] = useState(null);
    const [error, setError] = useState('');
    const mermaidRef = useRef(null);

    const renderMermaid = useCallback(async (code) => {
        if (!mermaidRef.current || !code) return;
        try {
            mermaidRef.current.innerHTML = '';
            const id = `cg-${Date.now()}`;
            const { svg } = await mermaid.render(id, code);
            mermaidRef.current.innerHTML = svg;
        } catch (e) {
            mermaidRef.current.innerHTML = `<pre style="font-size:0.75rem;overflow:auto">${code}</pre>`;
        }
    }, []);

    useEffect(() => {
        if (graph?.mermaid_code) renderMermaid(graph.mermaid_code);
    }, [graph, renderMermaid]);

    const handleBuild = async (refresh = false) => {
        if (!selSubject) { setError('Please select a subject.'); return; }
        setError(''); setBuilding(true);
        try {
            const r = refresh
                ? await buildConceptGraph({ subject_code: selSubject, refresh: true })
                : await getConceptGraph(selSubject).catch(() =>
                    buildConceptGraph({ subject_code: selSubject })
                );
            setGraph(r);
        } catch (e) {
            setError(e.response?.data?.detail || 'Graph generation failed. Try again.');
        }
        setBuilding(false);
    };

    return (
        <div className={styles.tabContent}>
            <h2 className={styles.sectionTitle}><Network size={16} /> Concept Dependency Graph</h2>
            <p className={styles.sectionHint}>Visual map of topic prerequisites — see which concepts to learn first. Colors: <span style={{ color: '#065F46' }}>■ Mastered</span> <span style={{ color: '#FF7A00' }}>■ Learning</span> <span style={{ color: '#888' }}>■ Not started</span></p>

            <div className={styles.graphControls}>
                <select className={styles.select} value={selSubject} onChange={e => { setSelSubject(e.target.value); setGraph(null); }}>
                    <option value="">Select Subject *</option>
                    {subjects.map(s => <option key={s.code} value={s.code}>{s.name}</option>)}
                </select>
                <button className={styles.buildBtn} onClick={() => handleBuild(false)} disabled={building || !selSubject}>
                    {building ? <Loader2 size={15} className={styles.spin} /> : <Network size={15} />}
                    {building ? 'Building…' : 'Load Graph'}
                </button>
                {graph && (
                    <button className={styles.refreshBtn} onClick={() => handleBuild(true)} disabled={building} title="Regenerate">
                        <RefreshCw size={14} />
                    </button>
                )}
            </div>

            {error && <p className={styles.err}>{error}</p>}

            {!graph && !building && (
                <div className={styles.emptyState}>
                    <Network size={40} className={styles.emptyIcon} />
                    <p>Select a subject and click "Load Graph" to generate a concept map.</p>
                </div>
            )}

            {graph && (
                <>
                    <div className={styles.graphMeta}>
                        <span>{graph.nodes?.length || 0} topics</span>
                        <span>{graph.edges?.length || 0} dependencies</span>
                        {graph.from_cache && <span className={styles.cached}>Cached</span>}
                    </div>
                    <div className={styles.mermaidWrap} ref={mermaidRef} />
                    {graph.study_order?.length > 0 && (
                        <div className={styles.studyOrder}>
                            <h3 className={styles.studyOrderTitle}>Recommended Study Order</h3>
                            <div className={styles.orderList}>
                                {graph.study_order.map((t, i) => (
                                    <span key={i} className={styles.orderItem}>
                                        <span className={styles.orderNum}>{i + 1}</span> {t}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                </>
            )}
        </div>
    );
}

// ── Notes Tab ────────────────────────────────────────────────────────────────
function NotesTab({ subjects }) {
    const [notes, setNotes] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selSubject, setSelSubject] = useState('');
    const [selTopic, setSelTopic] = useState('');
    const [generating, setGenerating] = useState(false);
    const [viewNote, setViewNote] = useState(null);
    const [error, setError] = useState('');

    const loadNotes = useCallback(async () => {
        setLoading(true);
        try { setNotes((await getNotes()).notes || []); } catch { setNotes([]); }
        setLoading(false);
    }, []);

    useEffect(() => { loadNotes(); }, [loadNotes]);

    const handleGenerate = async () => {
        if (!selSubject || !selTopic.trim()) {
            setError('Subject and topic are required to generate notes.');
            return;
        }
        setError(''); setGenerating(true);
        try {
            const n = await generateNotes({ subject_code: selSubject, topic: selTopic });
            await loadNotes();
            setViewNote(n);
        } catch (e) {
            setError(e.response?.data?.detail || 'Generation failed.');
        }
        setGenerating(false);
    };

    const handleDelete = async (id) => {
        if (!confirm('Delete this note?')) return;
        try { await deleteNote(id); await loadNotes(); if (viewNote?.note_id === id) setViewNote(null); }
        catch { alert('Delete failed'); }
    };

    const handleView = async (id) => {
        try {
            const n = await getNote(id);
            setViewNote(n);
        } catch { alert('Could not load note.'); }
    };

    const handleDownload = (note) => {
        const md = note.markdown_content || note.markdown || '';
        const blob = new Blob([md], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${note.topic || 'notes'}.md`;
        a.click();
        URL.revokeObjectURL(url);
    };

    if (viewNote) return (
        <div className={styles.tabContent}>
            <button className={styles.backBtn} onClick={() => setViewNote(null)}>← Back to Notes</button>
            <div className={styles.noteView}>
                <div className={styles.noteViewHeader}>
                    <h2 className={styles.noteViewTitle}>{viewNote.title || viewNote.topic}</h2>
                    <button className={styles.downloadBtn} onClick={() => handleDownload(viewNote)}>
                        <Download size={14} /> Download .md
                    </button>
                </div>
                <div
                    className={styles.noteMarkdown}
                    dangerouslySetInnerHTML={{ __html: viewNote.html_content || viewNote.html || '' }}
                />
            </div>
        </div>
    );

    return (
        <div className={styles.tabContent}>
            <h2 className={styles.sectionTitle}><StickyNote size={16} /> My Notes</h2>
            <p className={styles.sectionHint}>AI generates structured study notes from any topic or lesson session.</p>

            <div className={styles.generateForm}>
                <select className={styles.select} value={selSubject} onChange={e => setSelSubject(e.target.value)}>
                    <option value="">Select Subject *</option>
                    {subjects.map(s => <option key={s.code} value={s.code}>{s.name}</option>)}
                </select>
                <input
                    className={styles.input}
                    placeholder="Topic (e.g. Binary Search Trees) *"
                    value={selTopic}
                    onChange={e => setSelTopic(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleGenerate()}
                />
                <button className={styles.generateBtn} onClick={handleGenerate} disabled={generating}>
                    {generating
                        ? <><Loader2 size={15} className={styles.spin} /> Generating…</>
                        : <><Plus size={15} /> Generate Notes</>}
                </button>
            </div>
            {error && <p className={styles.err}>{error}</p>}

            {loading ? (
                <div className={styles.centerLoader}><Loader2 size={24} className={styles.spin} /></div>
            ) : notes.length === 0 ? (
                <div className={styles.emptyState}>
                    <StickyNote size={40} className={styles.emptyIcon} />
                    <p>No notes yet.</p>
                    <p className={styles.emptyHint}>Generate notes from any topic above, or use "Generate Notes" after a Tutor lesson.</p>
                </div>
            ) : (
                <div className={styles.notesList}>
                    {notes.map(n => (
                        <div key={n.id} className={styles.noteCard}>
                            <div className={styles.noteInfo}>
                                <div className={styles.noteTopic}>{n.topic}</div>
                                <div className={styles.noteMeta}>
                                    {n.subject_code && <span className={styles.noteSubject}>{n.subject_code}</span>}
                                    <span>{n.word_count} words</span>
                                    <span>{new Date(n.created_at).toLocaleDateString()}</span>
                                </div>
                            </div>
                            <div className={styles.noteActions}>
                                <button className={styles.iconBtn} onClick={() => handleView(n.id)} title="View"><BookOpen size={15} /></button>
                                <button className={styles.iconBtn} onClick={() => handleDownload(n)} title="Download"><Download size={15} /></button>
                                <button className={`${styles.iconBtn} ${styles.danger}`} onClick={() => handleDelete(n.id)} title="Delete"><Trash2 size={15} /></button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
