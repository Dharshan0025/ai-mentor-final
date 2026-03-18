/**
 * DrawToolbar — V2 Whiteboard draw/annotate mode (Phase 7)
 * Floating toolbar: pencil, highlight, eraser, text, color picker, clear
 * Props: canvasRef — ref to the HTML canvas element in the whiteboard
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { Pencil, Highlighter, Eraser, Type, Trash2, Palette, ChevronDown, ChevronUp, Minus } from 'lucide-react';
import styles from './DrawToolbar.module.css';

const COLORS = ['#FF7A00','#2563EB','#16A34A','#DC2626','#7C3AED','#000000','#FFFFFF'];
const TOOLS  = [
    { id: 'pencil',    icon: Pencil,      label: 'Draw',      size: 2,  alpha: 1   },
    { id: 'highlight', icon: Highlighter, label: 'Highlight', size: 14, alpha: 0.3 },
    { id: 'eraser',    icon: Eraser,      label: 'Eraser',    size: 20, alpha: 1   },
];

export default function DrawToolbar({ canvasRef }) {
    const [tool, setTool]     = useState('pencil');
    const [color, setColor]   = useState('#FF7A00');
    const [size, setSize]     = useState(2);
    const [open, setOpen]     = useState(true);
    const [textMode, setTextMode] = useState(false);
    const drawing = useRef(false);
    const lastPos = useRef({ x: 0, y: 0 });

    // ── Canvas 2D helpers ────────────────────────────────────────────────────
    const getCtx = useCallback(() => {
        const canvas = canvasRef?.current;
        if (!canvas) return null;
        return canvas.getContext('2d');
    }, [canvasRef]);

    const getPos = (e, canvas) => {
        const rect = canvas.getBoundingClientRect();
        const src  = e.touches ? e.touches[0] : e;
        return {
            x: (src.clientX - rect.left) * (canvas.width  / rect.width),
            y: (src.clientY - rect.top)  * (canvas.height / rect.height),
        };
    };

    // ── Pointer handlers ─────────────────────────────────────────────────────
    const onDown = useCallback((e) => {
        if (textMode) return;
        const canvas = canvasRef?.current;
        if (!canvas) return;
        drawing.current = true;
        const pos = getPos(e, canvas);
        lastPos.current = pos;
        e.preventDefault();
    }, [canvasRef, textMode]);

    const onMove = useCallback((e) => {
        if (!drawing.current || textMode) return;
        const canvas = canvasRef?.current;
        const ctx    = getCtx();
        if (!canvas || !ctx) return;

        const pos = getPos(e, canvas);
        ctx.save();
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';

        if (tool === 'eraser') {
            ctx.globalCompositeOperation = 'destination-out';
            ctx.lineWidth = size;
            ctx.strokeStyle = 'rgba(0,0,0,1)';
        } else if (tool === 'highlight') {
            ctx.globalCompositeOperation = 'source-over';
            ctx.globalAlpha = 0.3;
            ctx.lineWidth   = size;
            ctx.strokeStyle = color;
        } else {
            ctx.globalCompositeOperation = 'source-over';
            ctx.globalAlpha = 1;
            ctx.lineWidth   = size;
            ctx.strokeStyle = color;
        }

        ctx.beginPath();
        ctx.moveTo(lastPos.current.x, lastPos.current.y);
        ctx.lineTo(pos.x, pos.y);
        ctx.stroke();
        ctx.restore();

        lastPos.current = pos;
        e.preventDefault();
    }, [canvasRef, getCtx, tool, color, size, textMode]);

    const onUp = useCallback(() => { drawing.current = false; }, []);

    // ── Text placement ───────────────────────────────────────────────────────
    const onCanvasClick = useCallback((e) => {
        if (!textMode) return;
        const canvas = canvasRef?.current;
        const ctx    = getCtx();
        if (!canvas || !ctx) return;

        const pos  = getPos(e, canvas);
        const text = window.prompt('Enter text to add:');
        if (!text) return;

        ctx.save();
        ctx.font      = `bold ${size + 12}px Inter, sans-serif`;
        ctx.fillStyle = color;
        ctx.fillText(text, pos.x, pos.y);
        ctx.restore();
        setTextMode(false);
    }, [canvasRef, getCtx, textMode, color, size]);

    const clearCanvas = useCallback(() => {
        const canvas = canvasRef?.current;
        const ctx    = getCtx();
        if (!canvas || !ctx) return;
        if (window.confirm('Clear all annotations?')) {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }
    }, [canvasRef, getCtx]);

    // ── Attach / detach listeners ────────────────────────────────────────────
    useEffect(() => {
        const canvas = canvasRef?.current;
        if (!canvas) return;

        canvas.addEventListener('mousedown',  onDown,        { passive: false });
        canvas.addEventListener('mousemove',  onMove,        { passive: false });
        canvas.addEventListener('mouseup',    onUp);
        canvas.addEventListener('mouseleave', onUp);
        canvas.addEventListener('touchstart', onDown,        { passive: false });
        canvas.addEventListener('touchmove',  onMove,        { passive: false });
        canvas.addEventListener('touchend',   onUp);
        canvas.addEventListener('click',      onCanvasClick);

        return () => {
            canvas.removeEventListener('mousedown',  onDown);
            canvas.removeEventListener('mousemove',  onMove);
            canvas.removeEventListener('mouseup',    onUp);
            canvas.removeEventListener('mouseleave', onUp);
            canvas.removeEventListener('touchstart', onDown);
            canvas.removeEventListener('touchmove',  onMove);
            canvas.removeEventListener('touchend',   onUp);
            canvas.removeEventListener('click',      onCanvasClick);
        };
    }, [canvasRef, onDown, onMove, onUp, onCanvasClick]);

    return (
        <div className={styles.toolbar}>
            {/* Collapse toggle */}
            <button className={styles.collapseBtn} onClick={() => setOpen(v => !v)}>
                {open ? <ChevronDown size={13} /> : <ChevronUp size={13} />}
                <span>{open ? 'Hide tools' : 'Annotate'}</span>
            </button>

            {open && (
                <div className={styles.toolRow}>
                    {/* Draw tools */}
                    {TOOLS.map(t => {
                        const Icon = t.icon;
                        return (
                            <button
                                key={t.id}
                                title={t.label}
                                className={`${styles.toolBtn} ${tool === t.id && !textMode ? styles.toolActive : ''}`}
                                onClick={() => { setTool(t.id); setSize(t.size); setTextMode(false); }}
                            >
                                <Icon size={15} />
                            </button>
                        );
                    })}

                    {/* Text tool */}
                    <button
                        title="Add Text"
                        className={`${styles.toolBtn} ${textMode ? styles.toolActive : ''}`}
                        onClick={() => setTextMode(v => !v)}
                    >
                        <Type size={15} />
                    </button>

                    <span className={styles.divider} />

                    {/* Color swatches */}
                    {COLORS.map(c => (
                        <button
                            key={c}
                            title={c}
                            className={`${styles.swatch} ${color === c ? styles.swatchActive : ''}`}
                            style={{ background: c, border: c === '#FFFFFF' ? '1.5px solid #ccc' : undefined }}
                            onClick={() => setColor(c)}
                        />
                    ))}

                    <span className={styles.divider} />

                    {/* Brush size */}
                    <input
                        type="range" min={1} max={30} value={size}
                        className={styles.sizeSlider}
                        title="Brush size"
                        onChange={e => setSize(+e.target.value)}
                    />

                    {/* Clear */}
                    <button title="Clear annotations" className={styles.clearBtn} onClick={clearCanvas}>
                        <Trash2 size={14} />
                    </button>
                </div>
            )}
        </div>
    );
}
