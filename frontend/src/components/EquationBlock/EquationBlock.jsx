/**
 * EquationBlock — renders LaTeX equations using KaTeX
 * Receives { latex, display } and renders inline or block-level equations.
 * Falls back to plain text if KaTeX is not available.
 */
import { useEffect, useRef } from 'react';
import styles from './EquationBlock.module.css';

// Dynamic KaTeX import — optional dependency, graceful fallback
let katexLoaded = false;
let katexMod = null;

async function loadKatex() {
    if (katexLoaded) return katexMod;
    try {
        katexMod = await import(/* webpackChunkName: "katex" */ 'katex');
        katexLoaded = true;
        return katexMod;
    } catch {
        katexLoaded = true; // don't retry
        return null;
    }
}

export default function EquationBlock({ latex, display = 'inline' }) {
    const ref = useRef(null);

    useEffect(() => {
        if (!latex || !ref.current) return;
        let active = true;
        loadKatex().then(mod => {
            if (!active || !ref.current || !mod) return;
            try {
                const katex = mod.default || mod;
                katex.render(latex, ref.current, {
                    throwOnError: false,
                    displayMode: display === 'block',
                    output: 'html',
                    strict: false,
                    trust: false,
                    macros: { '\\R': '\\mathbb{R}' },
                });
            } catch {
                if (ref.current) ref.current.textContent = `$$${latex}$$`;
            }
        });
        return () => { active = false; };
    }, [latex, display]);

    if (!latex) return null;

    return (
        <span
            ref={ref}
            className={`${styles.equation} ${display === 'block' ? styles.block : styles.inline}`}
            title={latex}
        />
    );
}
