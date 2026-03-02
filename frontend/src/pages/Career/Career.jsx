import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import {
    Briefcase, TrendingUp, Star, Award, Target,
    ChevronRight, AlertCircle, Zap, Users, DollarSign,
    MapPin, BookOpen, ArrowRight, CheckCircle, Clock
} from 'lucide-react';
import styles from './Career.module.css';
import { CareerSkeleton } from '../../components/Skeleton/Skeleton';
import { mockCurrentStudent } from '../../data/mockData';

// ── Mock career data (used as fallback) ─────────────────────────────────────
const MOCK_CAREER = {
    student_name: "Dharshan B",
    cgpa: 7.4,
    semester: 7,
    readiness_score: 71,
    placement_tier: "Mid-tier Product / Service",
    placement_eligible: true,
    maang_eligible: false,
    has_active_arrears: false,
    primary_domain: "AI/ML Engineer",
    secondary_domain: "Data Scientist",
    career_paths: [
        { domain: "AI/ML Engineer", match_score: 82 },
        { domain: "Data Scientist", match_score: 74 },
        { domain: "Software Developer", match_score: 68 },
        { domain: "Cloud Architect", match_score: 55 },
    ],
    strength_subjects: [
        { name: "Machine Learning", grade: 8.1, code: "CS701" },
        { name: "Software Engineering", grade: 8.6, code: "CS705" },
        { name: "Cloud Computing", grade: 7.5, code: "CS706" },
    ],
    certifications: {
        primary: [
            "Google ML Engineer Professional",
            "AWS Machine Learning Specialty",
            "Deep Learning Specialization (Coursera)",
        ],
        secondary: [
            "IBM Data Science Professional",
            "Google Data Analytics",
        ]
    },
    skills_to_build: ["Python", "PyTorch/TensorFlow", "MLflow", "Hugging Face", "Scikit-learn", "CUDA"],
    urgent_actions: [
        "Build 2-3 GitHub projects showcasing your primary domain",
        "Start LeetCode DSA practice — 2 problems/day minimum",
        "Update LinkedIn profile with projects and skills",
        "Get 1 domain-specific certification (AI/ML Engineer)",
        "Apply for internships on LinkedIn, Internshala, and Unstop",
    ],
    weeks_to_placement: 6,
    market_context: {
        top_hiring_companies: ["Google DeepMind India", "Microsoft AI", "Sarvam AI", "Meesho", "Flipkart AI"],
        salary_range_lpa: { min_lpa: 9.6, max_lpa: 36.0, fresher_average_lpa: 18.2 },
        internship_portals: ["LinkedIn", "Internshala", "Unstop", "LeetCode Jobs", "GFG Jobs"],
    }
};

const DOMAIN_COLORS = {
    "AI/ML Engineer": "#FF7A00",
    "Data Scientist": "#10B981",
    "Software Developer": "#3B82F6",
    "Cloud Architect": "#8B5CF6",
    "DevOps/SRE": "#F59E0B",
    "Full-Stack Developer": "#EC4899",
    "Cybersecurity Analyst": "#EF4444",
    "Data Engineer": "#06B6D4",
};

const getDomainColor = (domain) =>
    DOMAIN_COLORS[domain] || "#6B7280";

// ── Animated Radial Gauge ─────────────────────────────────────────────────
function ReadinessGauge({ score }) {
    const [animated, setAnimated] = useState(0);
    useEffect(() => {
        const timer = setTimeout(() => setAnimated(score), 300);
        return () => clearTimeout(timer);
    }, [score]);

    const r = 54;
    const circ = 2 * Math.PI * r;
    const dash = (animated / 100) * circ;
    const tier = score >= 80 ? "PLACEMENT READY" : score >= 60 ? "ON TRACK" : "NEEDS FOCUS";
    const tierColor = score >= 80 ? "#10B981" : score >= 60 ? "#FF7A00" : "#EF4444";

    return (
        <div className={styles.gauge}>
            <svg viewBox="0 0 120 120" className={styles.gaugeSvg}>
                {/* Background track */}
                <circle cx="60" cy="60" r={r} fill="none"
                    stroke="rgba(255,255,255,0.06)" strokeWidth="10" strokeLinecap="round"
                    strokeDasharray={`${circ * 0.75} ${circ * 0.25}`}
                    strokeDashoffset={circ * 0.125}
                    style={{ transform: 'rotate(135deg)', transformOrigin: '60px 60px' }}
                />
                {/* Animated arc */}
                <circle cx="60" cy="60" r={r} fill="none"
                    stroke={tierColor} strokeWidth="10" strokeLinecap="round"
                    strokeDasharray={`${dash * 0.75} ${circ - dash * 0.75}`}
                    strokeDashoffset={circ * 0.125}
                    style={{
                        transform: 'rotate(135deg)', transformOrigin: '60px 60px',
                        transition: 'stroke-dasharray 1.2s cubic-bezier(0.34, 1.56, 0.64, 1)',
                        filter: `drop-shadow(0 0 8px ${tierColor}80)`
                    }}
                />
                <text x="60" y="56" textAnchor="middle" fill="white"
                    fontSize="22" fontWeight="700" fontFamily="Inter, sans-serif">{animated}</text>
                <text x="60" y="70" textAnchor="middle" fill="rgba(255,255,255,0.5)"
                    fontSize="7.5" fontFamily="Inter, sans-serif" letterSpacing="1">/ 100</text>
            </svg>
            <div className={styles.gaugeLabel} style={{ color: tierColor }}>{tier}</div>
        </div>
    );
}

// ── Domain Match Bar ─────────────────────────────────────────────────────
function DomainBar({ domain, score, isTop }) {
    const [width, setWidth] = useState(0);
    const color = getDomainColor(domain);
    useEffect(() => {
        const t = setTimeout(() => setWidth(score), 500);
        return () => clearTimeout(t);
    }, [score]);

    return (
        <div className={`${styles.domainBar} ${isTop ? styles.domainBarTop : ''}`}>
            <div className={styles.domainBarHeader}>
                <span className={styles.domainBarName}>{domain}</span>
                <span className={styles.domainBarScore} style={{ color }}>{score}%</span>
            </div>
            <div className={styles.domainBarTrack}>
                <div className={styles.domainBarFill}
                    style={{
                        width: `${width}%`, background: color,
                        boxShadow: isTop ? `0 0 12px ${color}60` : 'none',
                        transition: 'width 1s cubic-bezier(0.34, 1.56, 0.64, 1)'
                    }} />
            </div>
        </div>
    );
}

// ── Main Career Page ─────────────────────────────────────────────────────
export default function Career() {
    const [career, setCareer] = useState(null);
    const [loading, setLoading] = useState(true);
    const [activeAction, setActiveAction] = useState(null);

    useEffect(() => {
        import('../../services/api').then(({ getMyCareer }) => {
            getMyCareer()
                .then(data => setCareer(data))
                .catch(() => setCareer(MOCK_CAREER))
                .finally(() => setLoading(false));
        });
    }, []);

    if (loading) return <CareerSkeleton />;

    const c = career;
    const primaryColor = getDomainColor(c.primary_domain);

    return (
        <div className={styles.page}>
            {/* Header */}
            <div className={styles.header}>
                <div className={styles.headerLeft}>
                    <span className={styles.headerBadge}>
                        <Briefcase size={12} /> Career Intelligence
                    </span>
                    <h1 className={styles.headerTitle}>
                        Your Path to <span style={{ color: primaryColor }}>{c.primary_domain}</span>
                    </h1>
                    <p className={styles.headerSub}>
                        Based on your academic profile · Semester {c.semester} · CGPA {c.cgpa}
                    </p>
                </div>
                <div className={styles.headerRight}>
                    <ReadinessGauge score={c.readiness_score} />
                </div>
            </div>

            {/* Eligibility Banner */}
            <div className={`${styles.eligibilityBanner} ${c.has_active_arrears ? styles.bannerRisk : c.maang_eligible ? styles.bannerSuccess : styles.bannerInfo}`}>
                {c.has_active_arrears
                    ? <><AlertCircle size={16} /> <strong>Active arrears detected</strong> — {c.placement_tier_detail || 'clear them immediately to unlock product company opportunities'}</>
                    : c.maang_eligible
                        ? <><CheckCircle size={16} /> <strong>{c.placement_tier || 'MAANG Eligible'}</strong> — {c.placement_tier_detail || `CGPA ${c.cgpa} qualifies you for top product companies`}</>
                        : <><Zap size={16} /> <strong>{c.placement_tier || 'Placement Eligible'}</strong> — {c.placement_tier_detail || 'Push CGPA to 7.5+ to unlock MAANG opportunities'}</>
                }
            </div>

            {/* Main Grid */}
            <div className={styles.grid}>
                {/* Left Column */}
                <div className={styles.colLeft}>

                    {/* Career Domain Matching */}
                    <div className={styles.card}>
                        <div className={styles.cardHeader}>
                            <h2 className={styles.cardTitle}>
                                <Target size={16} style={{ color: primaryColor }} /> Career Domain Match
                            </h2>
                            <span className={styles.cardBadge}>AI-scored from your grades</span>
                        </div>
                        <div className={styles.domainList}>
                            {c.career_paths.map((p, i) => (
                                <DomainBar key={p.domain} domain={p.domain} score={p.match_score} isTop={i === 0} />
                            ))}
                        </div>
                        <div className={styles.strengthSubjects}>
                            <span className={styles.strengthLabel}>Driving subjects</span>
                            <div className={styles.strengthPills}>
                                {c.strength_subjects.map(s => (
                                    <span key={s.code} className={styles.strengthPill}>
                                        <Star size={10} /> {s.name}
                                        <span className={styles.gradeTag}>{s.grade}</span>
                                    </span>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Skill Roadmap */}
                    <div className={styles.card}>
                        <div className={styles.cardHeader}>
                            <h2 className={styles.cardTitle}>
                                <TrendingUp size={16} style={{ color: primaryColor }} /> Skills to Build
                            </h2>
                            <span className={styles.cardBadge}>{c.primary_domain}</span>
                        </div>
                        <div className={styles.skillGrid}>
                            {c.skills_to_build.map((skill, i) => (
                                <div key={skill} className={styles.skillChip}
                                    style={{ animationDelay: `${i * 80}ms` }}>
                                    <span className={styles.skillNum}>{String(i + 1).padStart(2, '0')}</span>
                                    {skill}
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Prioritized Next Actions (Phase 5) */}
                    {c.next_actions && c.next_actions.length > 0 && (
                        <div className={styles.card}>
                            <div className={styles.cardHeader}>
                                <h2 className={styles.cardTitle}>
                                    <Target size={16} style={{ color: "#10B981" }} /> Prioritized Actions
                                </h2>
                                <span className={styles.cardBadge} style={{ color: '#10B981' }}>
                                    Impact-ranked
                                </span>
                            </div>
                            <div className={styles.actionList}>
                                {c.next_actions.map((na, i) => (
                                    <div key={i}
                                        className={`${styles.actionItem} ${activeAction === `na-${i}` ? styles.actionItemActive : ''}`}
                                        onClick={() => setActiveAction(activeAction === `na-${i}` ? null : `na-${i}`)}>
                                        <div className={styles.actionNum}
                                            style={{ background: activeAction === `na-${i}` ? '#10B981' : 'rgba(255,255,255,0.06)' }}>
                                            P{na.priority}
                                        </div>
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <span className={styles.actionText}>{na.action}</span>
                                            {activeAction === `na-${i}` && (
                                                <div style={{ marginTop: 6, fontSize: '0.75rem', color: 'rgba(255,255,255,0.55)', lineHeight: 1.4 }}>
                                                    <strong style={{ color: '#10B981' }}>Impact:</strong> {na.impact}
                                                    <br />
                                                    <strong style={{ color: '#F59E0B' }}>Timeline:</strong> {na.timeline}
                                                </div>
                                            )}
                                        </div>
                                        <ChevronRight size={14} className={styles.actionArrow} />
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Urgent Actions */}
                    <div className={styles.card}>
                        <div className={styles.cardHeader}>
                            <h2 className={styles.cardTitle}>
                                <Zap size={16} style={{ color: "#FF7A00" }} /> Quick Actions
                            </h2>
                            <span className={styles.cardBadge} style={{ color: '#FF7A00' }}>
                                <Clock size={10} /> {c.weeks_to_placement}w to placements
                            </span>
                        </div>
                        <div className={styles.actionList}>
                            {c.urgent_actions.map((action, i) => (
                                <div key={i}
                                    className={`${styles.actionItem} ${activeAction === i ? styles.actionItemActive : ''}`}
                                    onClick={() => setActiveAction(activeAction === i ? null : i)}>
                                    <div className={styles.actionNum}
                                        style={{ background: activeAction === i ? primaryColor : 'rgba(255,255,255,0.06)' }}>
                                        {i + 1}
                                    </div>
                                    <span className={styles.actionText}>{action}</span>
                                    <ChevronRight size={14} className={styles.actionArrow} />
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Right Column */}
                <div className={styles.colRight}>
                    {/* Salary Intelligence */}
                    <div className={styles.card + ' ' + styles.salaryCard}>
                        <div className={styles.salaryGlow} style={{ background: primaryColor }} />
                        <div className={styles.cardHeader}>
                            <h2 className={styles.cardTitle}>
                                <DollarSign size={16} style={{ color: primaryColor }} /> Salary Intelligence
                            </h2>
                        </div>
                        <div className={styles.salaryRange}>
                            <div className={styles.salaryBlock}>
                                <span className={styles.salaryLabel}>Fresher Avg</span>
                                <span className={styles.salaryValue} style={{ color: primaryColor }}>
                                    ₹{c.market_context.salary_range_lpa.fresher_average_lpa}L
                                </span>
                            </div>
                            <div className={styles.salarySep} />
                            <div className={styles.salaryBlock}>
                                <span className={styles.salaryLabel}>Range</span>
                                <span className={styles.salaryValue} style={{ color: 'white', fontSize: '1.1rem' }}>
                                    ₹{c.market_context.salary_range_lpa.min_lpa}L – ₹{c.market_context.salary_range_lpa.max_lpa}L
                                </span>
                            </div>
                        </div>
                        <div className={styles.salaryNote}>
                            <span>2025 Indian market · {c.primary_domain}</span>
                            <span className={styles.salaryTier}>{c.placement_tier}</span>
                        </div>
                    </div>

                    {/* Top Hiring Companies */}
                    <div className={styles.card}>
                        <div className={styles.cardHeader}>
                            <h2 className={styles.cardTitle}>
                                <Users size={16} style={{ color: primaryColor }} /> Top Hiring Companies
                            </h2>
                            <span className={styles.cardBadge}>{c.primary_domain}</span>
                        </div>
                        <div className={styles.companyList}>
                            {c.market_context.top_hiring_companies.map((company, i) => (
                                <div key={company} className={styles.companyRow}
                                    style={{ animationDelay: `${i * 100}ms` }}>
                                    <div className={styles.companyAvatar}
                                        style={{ background: `${primaryColor}18`, color: primaryColor }}>
                                        {company.split(' ')[0][0]}
                                    </div>
                                    <span className={styles.companyName}>{company}</span>
                                    <ArrowRight size={14} className={styles.companyArrow} />
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Certifications */}
                    <div className={styles.card}>
                        <div className={styles.cardHeader}>
                            <h2 className={styles.cardTitle}>
                                <Award size={16} style={{ color: primaryColor }} /> Recommended Certs
                            </h2>
                        </div>
                        <div className={styles.certSection}>
                            <span className={styles.certDomain}>{c.primary_domain}</span>
                            {c.certifications.primary.map((cert, i) => (
                                <div key={cert} className={styles.certRow}>
                                    <div className={styles.certDot} style={{ background: primaryColor }} />
                                    <span>{cert}</span>
                                </div>
                            ))}
                        </div>
                        {c.certifications.secondary.length > 0 && (
                            <div className={styles.certSection}>
                                <span className={styles.certDomain} style={{ color: getDomainColor(c.secondary_domain) }}>
                                    {c.secondary_domain}
                                </span>
                                {c.certifications.secondary.map((cert) => (
                                    <div key={cert} className={styles.certRow} style={{ opacity: 0.7 }}>
                                        <div className={styles.certDot} style={{ background: getDomainColor(c.secondary_domain) }} />
                                        <span>{cert}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* Internship Portals */}
                    <div className={styles.card}>
                        <div className={styles.cardHeader}>
                            <h2 className={styles.cardTitle}>
                                <MapPin size={16} style={{ color: primaryColor }} /> Where to Apply
                            </h2>
                        </div>
                        <div className={styles.portalGrid}>
                            {c.market_context.internship_portals.map((portal) => (
                                <div key={portal} className={styles.portalChip}>{portal}</div>
                            ))}
                        </div>
                        <Link to="/chat" className={styles.chatCta}>
                            <Briefcase size={14} />
                            Ask Career Agent for personalized leads
                            <ArrowRight size={14} />
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    );
}
