/**
 * CodeRunner — Phase 6/7 Live Code Execution + AI Debugger
 * Uses Piston API for execution. AI debug uses Groq via backend.
 */
import { useState, useRef, useCallback } from 'react';
import { Play, Loader2, Copy, Check, X, Code2, ChevronDown, Bug, ChevronRight } from 'lucide-react';
import styles from './CodeRunner.module.css';
import { analyzeDebug } from '../../services/api';

const PISTON_API = 'https://emkc.org/api/v2/piston/execute';
const LANGUAGES = [
    { id: 'python',     label: 'Python',     version: '3.10.0',  ext: '.py'   },
    { id: 'cpp',        label: 'C++',        version: '10.2.0',  ext: '.cpp'  },
    { id: 'java',       label: 'Java',       version: '15.0.2',  ext: '.java' },
    { id: 'javascript', label: 'JavaScript', version: '18.15.0', ext: '.js'   },
];
const STARTER = {
    python:     'print("Hello, World!")',
    cpp:        '#include <iostream>\nusing namespace std;\nint main() {\n    cout << "Hello, World!" << endl;\n    return 0;\n}',
    java:       'public class Main {\n    public static void main(String[] args) {\n        System.out.println("Hello, World!");\n    }\n}',
    javascript: 'console.log("Hello, World!");',
};

export default function CodeRunner({ initialCode = '', initialLang = 'python', onClose }) {
    const [lang, setLang]           = useState(initialLang);
    const [code, setCode]           = useState(initialCode || STARTER[initialLang] || '');
    const [stdin, setStdin]         = useState('');
    const [running, setRunning]     = useState(false);
    const [output, setOutput]       = useState(null);
    const [copied, setCopied]       = useState(false);
    const [showLangMenu, setShowLangMenu] = useState(false);
    const [debugging, setDebugging] = useState(false);
    const [debugResult, setDebugResult] = useState(null);
    const [showFixed, setShowFixed] = useState(false);
    const textareaRef = useRef(null);

    const handleRun = useCallback(async () => {
        if (!code.trim()) return;
        setRunning(true); setOutput(null); setDebugResult(null); setShowFixed(false);
        const langMeta = LANGUAGES.find(l => l.id === lang);
        const filename = lang === 'java' ? 'Main.java' : `main${langMeta?.ext || '.py'}`;
        try {
            const res = await fetch(PISTON_API, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    language: lang === 'cpp' ? 'c++' : lang,
                    version:  langMeta?.version || '*',
                    files: [{ name: filename, content: code }],
                    stdin: stdin || '',
                }),
            });
            if (!res.ok) throw new Error(`API error ${res.status}`);
            const data = await res.json();
            const run  = data.run || {};
            setOutput({ stdout: run.stdout || '', stderr: run.stderr || '', exitCode: run.code ?? 0, time_ms: run.cpu_time ? Math.round(run.cpu_time * 1000) : null });
        } catch (err) {
            setOutput({ stdout: '', stderr: `Connection error: ${err.message}`, exitCode: -1, time_ms: null });
        } finally { setRunning(false); }
    }, [code, lang, stdin]);

    const handleDebug = useCallback(async () => {
        if (!output?.stderr) return;
        setDebugging(true); setDebugResult(null); setShowFixed(false);
        try {
            const result = await analyzeDebug({ code, stderr: output.stderr, language: lang });
            setDebugResult(result);
        } catch {
            setDebugResult({ error_type: 'Error', root_cause: 'AI debugger unavailable.', fix_suggestion: '', learning_tip: '', fixed_code: '' });
        }
        setDebugging(false);
    }, [code, output, lang]);

    const handleCopy = async () => {
        await navigator.clipboard.writeText(code);
        setCopied(true); setTimeout(() => setCopied(false), 2000);
    };

    const handleTabKey = (e) => {
        if (e.key === 'Tab') {
            e.preventDefault();
            const ta = textareaRef.current, s = ta.selectionStart;
            setCode(code.substring(0, s) + '    ' + code.substring(ta.selectionEnd));
            setTimeout(() => { ta.selectionStart = ta.selectionEnd = s + 4; }, 0);
        }
    };

    const changeLang = (l) => { setLang(l); setCode(STARTER[l] || ''); setOutput(null); setDebugResult(null); setShowLangMenu(false); };
    const hasError  = output?.exitCode !== 0 && output?.exitCode !== null;
    const hasOutput = output?.stdout || output?.stderr;
    const langMeta  = LANGUAGES.find(l => l.id === lang);

    return (
        <div className={styles.runner}>
            {/* Toolbar */}
            <div className={styles.toolbar}>
                <div className={styles.toolbarLeft}>
                    <Code2 size={15} />
                    <span className={styles.toolbarTitle}>Code Runner</span>
                    <div className={styles.langDropdown}>
                        <button className={styles.langBtn} onClick={() => setShowLangMenu(v => !v)}>
                            {langMeta?.label} <ChevronDown size={12} />
                        </button>
                        {showLangMenu && (
                            <div className={styles.langMenu}>
                                {LANGUAGES.map(l => (
                                    <button key={l.id} className={`${styles.langOption} ${lang === l.id ? styles.langActive : ''}`} onClick={() => changeLang(l.id)}>{l.label}</button>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
                <div className={styles.toolbarRight}>
                    <button className={styles.copyBtn} onClick={handleCopy} title="Copy code">
                        {copied ? <Check size={13} /> : <Copy size={13} />}
                    </button>
                    <button className={styles.runBtn} onClick={handleRun} disabled={running || !code.trim()}>
                        {running ? <><Loader2 size={13} className={styles.spin} /> Running…</> : <><Play size={13} /> Run</>}
                    </button>
                    {onClose && <button className={styles.closeBtn} onClick={onClose} title="Close"><X size={15} /></button>}
                </div>
            </div>

            {/* Editor */}
            <textarea ref={textareaRef} className={styles.editor} value={code}
                onChange={e => setCode(e.target.value)} onKeyDown={handleTabKey}
                spellCheck={false} placeholder={`Write your ${langMeta?.label} code here…`} />

            {/* Stdin */}
            <div className={styles.stdinRow}>
                <label className={styles.stdinLabel}>stdin (optional):</label>
                <input className={styles.stdinInput} placeholder="Input for your program…" value={stdin} onChange={e => setStdin(e.target.value)} />
            </div>

            {/* Output */}
            {hasOutput && (
                <div className={`${styles.output} ${hasError ? styles.outputErr : styles.outputOk}`}>
                    <div className={styles.outputHeader}>
                        <span className={hasError ? styles.errLabel : styles.okLabel}>{hasError ? '✗ Error' : '✓ Output'}</span>
                        {output.time_ms !== null && <span className={styles.timeLabel}>{output.time_ms}ms</span>}
                        <span className={styles.exitLabel}>exit {output.exitCode}</span>
                        {hasError && (
                            <button className={styles.debugBtn} onClick={handleDebug} disabled={debugging}>
                                {debugging ? <><Loader2 size={11} className={styles.spin} /> Analyzing…</> : <><Bug size={11} /> Debug with AI</>}
                            </button>
                        )}
                    </div>
                    <pre className={styles.outputText}>{output.stdout || ''}{output.stderr ? `\n[stderr]\n${output.stderr}` : ''}</pre>
                </div>
            )}

            {/* AI Debug Panel */}
            {debugResult && (
                <div className={styles.debugPanel}>
                    <div className={styles.debugHeader}>
                        <Bug size={13} />
                        <span>AI Debug Report</span>
                        <span className={styles.errType}>{debugResult.error_type}</span>
                    </div>
                    <div className={styles.debugRow}>
                        <span className={styles.debugLabel}>Root Cause</span>
                        <p className={styles.debugText}>{debugResult.root_cause}</p>
                    </div>
                    {debugResult.line_hint && (
                        <div className={styles.debugRow}>
                            <span className={styles.debugLabel}>Line</span>
                            <p className={styles.debugText}>{debugResult.line_hint}</p>
                        </div>
                    )}
                    <div className={styles.debugRow}>
                        <span className={styles.debugLabel}>Fix</span>
                        <p className={styles.debugText}>{debugResult.fix_suggestion}</p>
                    </div>
                    {debugResult.learning_tip && (
                        <div className={styles.debugRow}>
                            <span className={styles.debugLabel}>💡 Tip</span>
                            <p className={`${styles.debugText} ${styles.tip}`}>{debugResult.learning_tip}</p>
                        </div>
                    )}
                    {debugResult.fixed_code && (
                        <>
                            <button className={styles.fixedToggle} onClick={() => setShowFixed(v => !v)}>
                                <ChevronRight size={12} style={{ transform: showFixed ? 'rotate(90deg)' : undefined, transition: 'transform 0.2s' }} />
                                {showFixed ? 'Hide' : 'Show'} Fixed Code
                            </button>
                            {showFixed && (
                                <div className={styles.fixedCode}>
                                    <button className={styles.useFixBtn} onClick={() => { setCode(debugResult.fixed_code); setDebugResult(null); }}>
                                        ↑ Use this code
                                    </button>
                                    <pre>{debugResult.fixed_code}</pre>
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}
        </div>
    );
}
