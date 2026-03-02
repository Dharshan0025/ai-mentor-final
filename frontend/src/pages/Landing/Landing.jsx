import { Link } from 'react-router-dom';
import styles from './Landing.module.css';
import { ArrowRight, Zap, TrendingUp, BookOpen, Calendar } from 'lucide-react';

const FEATURES = [
    {
        icon: <TrendingUp size={22} />,
        title: "Future Prediction Engine",
        desc: "Forecast your next semester CGPA and spot at-risk subjects before it's too late.",
        color: "#FF7A00"
    },
    {
        icon: <BookOpen size={22} />,
        title: "Active Learning Loop",
        desc: "Explain → Quiz → Re-explain. Your AI mentor adapts to your Bloom's level for each topic.",
        color: "#10B981"
    },
    {
        icon: <Calendar size={22} />,
        title: "Smart Study Scheduler",
        desc: "Auto-built study plans based on your exam dates, subject credits, and risk priorities.",
        color: "#3B82F6"
    },
    {
        icon: <Zap size={22} />,
        title: "8-Agent Intelligence",
        desc: "Academic, Prediction, Emotional, Learning, Schedule, Career, RAG & Multimodal agents working together.",
        color: "#EC4899"
    }
];

export default function Landing() {
    return (
        <div className={styles.page}>
            {/* Nav */}
            <nav className={styles.nav}>
                <div className={styles.navInner}>
                    <div className={styles.logo}>
                        <div className={styles.logoIcon}>✦</div>
                        <span className={styles.logoText}>AI Mentor</span>
                    </div>
                    <div className={styles.navLinks}>
                        <a href="#features">Features</a>
                        <a href="#how">How it works</a>
                        <a href="#about">About</a>
                    </div>
                    <div className={styles.navActions}>
                        <Link to="/login" className={styles.signInLink}>Sign in →</Link>
                    </div>
                </div>
            </nav>

            {/* Hero */}
            <section className={styles.hero}>
                <div className={styles.heroGlow} />
                <div className={styles.heroContent}>
                    <div className={`${styles.heroPill} animate-fade-up`}>
                        <Zap size={13} />
                        Powered by Institutional ERP Intelligence
                    </div>

                    <h1 className={`${styles.heroTitle} animate-fade-up stagger-1`}>
                        Your smartest academic<br />
                        <span className={styles.heroAccent}>mentor starts here</span>
                    </h1>

                    <p className={`${styles.heroSub} animate-fade-up stagger-2`}>
                        An agentic AI that knows your full academic history, predicts your performance,
                        and builds a personalised path to help you excel — not just pass.
                    </p>

                    <div className="animate-fade-up stagger-3">
                        <Link to="/login" className={`btn btn-primary ${styles.heroBtn}`}>
                            Enter AI Mentor <ArrowRight size={16} />
                        </Link>
                    </div>
                </div>

                {/* Dashboard preview mock */}
                <div className={`${styles.heroPreview} animate-fade-up stagger-4`}>
                    <div className={styles.previewBar}>
                        <div className={styles.previewDot} style={{ background: '#EF4444' }} />
                        <div className={styles.previewDot} style={{ background: '#F59E0B' }} />
                        <div className={styles.previewDot} style={{ background: '#22C55E' }} />
                        <span className={styles.previewURL}>ai-mentor.edu.in/dashboard</span>
                    </div>
                    <div className={styles.previewBody}>
                        <div className={styles.previewCard}>
                            <div className={styles.previewMeta}>Current CGPA</div>
                            <div className={styles.previewBig}>7.4</div>
                            <div className={styles.previewSub}>↑ Projected 7.6 next sem</div>
                        </div>
                        <div className={styles.previewCard} style={{ background: 'var(--risk-light)', border: '1px solid var(--risk)' }}>
                            <div className={styles.previewMeta}>⚠️ At Risk</div>
                            <div className={styles.previewBig} style={{ color: 'var(--risk)', fontSize: '1.5rem' }}>Operating Systems</div>
                            <div className={styles.previewSub} style={{ color: '#DC2626' }}>Predicted 51% · 4 credit subject</div>
                        </div>
                        <div className={styles.previewCard}>
                            <div className={styles.previewMeta}>🎓 Bloom Level</div>
                            <div className={styles.previewBloom}>
                                {[1, 2, 3, 4, 5, 6].map(i => (
                                    <div key={i} className={styles.previewBlock} style={{ background: i <= 4 ? 'var(--accent)' : 'var(--border)' }} />
                                ))}
                            </div>
                            <div className={styles.previewSub}>Analyze level achieved</div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Features */}
            <section className={styles.features} id="features">
                <div className={styles.featuresGlow} />
                <div className={styles.featuresInner}>
                    <div className={styles.sectionHeader}>
                        <span className="section-label">✦ Our Benefits</span>
                        <h2 className={styles.sectionTitle}>
                            How we're <span className={styles.heroAccent}>different</span>
                        </h2>
                        <p className={styles.sectionSub}>
                            Unlike generic tutoring apps, AI Mentor is built on your real academic data — it knows your history
                            before you ask your first question.
                        </p>
                    </div>

                    <div className={styles.featureGrid}>
                        {FEATURES.map((f, i) => (
                            <div key={i} className={`card card--interactive ${styles.featureCard} animate-fade-up`} style={{ animationDelay: `${i * 60}ms` }}>
                                <div className={styles.featureIcon} style={{ background: f.color + '18', color: f.color }}>
                                    {f.icon}
                                </div>
                                <h3 className={styles.featureTitle}>{f.title}</h3>
                                <p className={styles.featureDesc}>{f.desc}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA */}
            <section className={styles.ctaSection}>
                <h2 className={styles.ctaTitle}>
                    Start learning smarter,<br />
                    <span className={styles.heroAccent}>not just harder</span>
                </h2>
                <Link to="/login" className={`btn btn-primary ${styles.ctaBtn}`}>
                    Enter AI Mentor <ArrowRight size={16} />
                </Link>
            </section>

            {/* Footer */}
            <footer className={styles.footer}>
                <span>© 2026 AI Mentor · Built for Indian Higher Education</span>
                <span>DPDP Act 2023 Compliant · Privacy First</span>
            </footer>
        </div>
    );
}
