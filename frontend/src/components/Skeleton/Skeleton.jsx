import styles from './Skeleton.module.css';

/**
 * Composable skeleton primitives for loading states.
 * Uses the global shimmer animation from global.css.
 */

export function SkeletonLine({ width = '100%', height = 14, style }) {
    return (
        <div
            className={styles.line}
            style={{ width, height, ...style }}
        />
    );
}

export function SkeletonCircle({ size = 40, style }) {
    return (
        <div
            className={styles.circle}
            style={{ width: size, height: size, ...style }}
        />
    );
}

export function SkeletonCard({ height = 120, style }) {
    return (
        <div className={styles.card} style={{ height, ...style }}>
            <SkeletonLine width="40%" height={12} />
            <SkeletonLine width="80%" height={10} style={{ marginTop: 12 }} />
            <SkeletonLine width="60%" height={10} style={{ marginTop: 8 }} />
            <SkeletonLine width="70%" height={10} style={{ marginTop: 8 }} />
        </div>
    );
}

export function DashboardSkeleton() {
    return (
        <div className={styles.dashboardSkeleton}>
            {/* Header */}
            <div className={styles.headerSkel}>
                <SkeletonCircle size={48} />
                <div style={{ flex: 1 }}>
                    <SkeletonLine width="35%" height={18} />
                    <SkeletonLine width="55%" height={12} style={{ marginTop: 8 }} />
                </div>
            </div>

            {/* Metric strip */}
            <div className={styles.metricStripSkel}>
                {[1, 2, 3, 4, 5].map(i => (
                    <div key={i} className={styles.metricSkel}>
                        <SkeletonLine width="50%" height={10} />
                        <SkeletonLine width="40%" height={22} style={{ marginTop: 8 }} />
                        <SkeletonLine width="65%" height={9} style={{ marginTop: 6 }} />
                    </div>
                ))}
            </div>

            {/* Two-column */}
            <div className={styles.row2Skel}>
                <SkeletonCard height={200} />
                <SkeletonCard height={200} />
            </div>

            {/* Subject grid */}
            <div className={styles.gridSkel}>
                {[1, 2, 3, 4, 5, 6].map(i => (
                    <SkeletonCard key={i} height={110} />
                ))}
            </div>
        </div>
    );
}

export function LearningSkeleton() {
    return (
        <div className={styles.learningSkeleton}>
            <div className={styles.learnSidebar}>
                <SkeletonLine width="50%" height={14} />
                {[1, 2, 3, 4, 5, 6].map(i => (
                    <div key={i} className={styles.learnSubjectSkel}>
                        <SkeletonLine width="70%" height={12} />
                        <SkeletonLine width="100%" height={6} style={{ marginTop: 8 }} />
                    </div>
                ))}
            </div>
            <div className={styles.learnContent}>
                <SkeletonLine width="40%" height={16} />
                <SkeletonLine width="60%" height={22} style={{ marginTop: 10 }} />
                <div className={styles.topicGridSkel}>
                    {[1, 2, 3, 4, 5, 6, 7, 8].map(i => (
                        <SkeletonCard key={i} height={70} />
                    ))}
                </div>
            </div>
        </div>
    );
}

export function CareerSkeleton() {
    return (
        <div className={styles.careerSkeleton}>
            {/* Header */}
            <div className={styles.careerHeaderSkel}>
                <div style={{ flex: 1 }}>
                    <SkeletonLine width="30%" height={12} />
                    <SkeletonLine width="60%" height={22} style={{ marginTop: 8 }} />
                    <SkeletonLine width="45%" height={11} style={{ marginTop: 8 }} />
                </div>
                <SkeletonCircle size={120} />
            </div>
            {/* Banner */}
            <SkeletonLine width="100%" height={44} style={{ borderRadius: 10 }} />
            {/* Grid */}
            <div className={styles.careerGridSkel}>
                <div className={styles.careerColSkel}>
                    <SkeletonCard height={180} />
                    <SkeletonCard height={140} />
                    <SkeletonCard height={160} />
                </div>
                <div className={styles.careerColSkel}>
                    <SkeletonCard height={130} />
                    <SkeletonCard height={150} />
                    <SkeletonCard height={130} />
                </div>
            </div>
        </div>
    );
}
