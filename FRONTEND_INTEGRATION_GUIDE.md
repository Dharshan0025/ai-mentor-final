# Frontend Integration Guide - AI Mentor Enhancements

**For React developers integrating the 5 new features**

---

## 🎯 Overview

Backend has **13 new endpoints** and **4 new modules**. Frontend needs to:
1. Display SSE streaming updates in real-time
2. Show learning metrics dashboard
3. Create/manage commitment contracts
4. Display peer comparison insights
5. Cache data client-side where applicable

---

## 📱 UI Components to Build/Update

### 1. Streaming Chat Component (SSE)

**Endpoint**: `POST /chat/stream`

**Implementation**:
```javascript
// frontend/src/pages/Chat/ChatStreaming.jsx

import { useState, useEffect } from 'react';

export function ChatStreaming({ message, sessionId, studentId }) {
  const [stages, setStages] = useState({});
  const [response, setResponse] = useState('');
  const [metadata, setMetadata] = useState(null);

  useEffect(() => {
    const eventSource = new EventSource(
      `/chat/stream?student_id=${studentId}&message=${encodeURIComponent(message)}&session_id=${sessionId}`
    );

    eventSource.addEventListener('stage', (e) => {
      const stage = JSON.parse(e.data);
      setStages(prev => ({
        ...prev,
        [stage.stage]: stage.data
      }));
    });

    eventSource.addEventListener('response', (e) => {
      const data = JSON.parse(e.data);
      setResponse(data.content);
    });

    eventSource.addEventListener('metadata', (e) => {
      setMetadata(JSON.parse(e.data));
    });

    eventSource.addEventListener('done', () => {
      eventSource.close();
    });

    eventSource.addEventListener('error', () => {
      eventSource.close();
    });

    return () => eventSource.close();
  }, [message, sessionId, studentId]);

  return (
    <div className="streaming-chat">
      {/* Show stages as they arrive */}
      {Object.entries(stages).map(([stage, data]) => (
        <StageDisplay key={stage} stage={stage} data={data} />
      ))}

      {/* Final response */}
      {response && <p className="response">{response}</p>}

      {/* Metadata */}
      {metadata && (
        <div className="metadata">
          Tokens: {metadata.tokens} | Model: {metadata.model} | Confidence: {(metadata.confidence * 100).toFixed(0)}%
        </div>
      )}
    </div>
  );
}
```

**Or use HTTP with fallback**:
```javascript
// If SSE not supported, use regular endpoint with streaming response
const response = await fetch('/chat', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    student_id: studentId,
    message,
    show_pipeline: true
  })
});

const data = await response.json();
setPipelineData(data.pipeline);  // Already have all stages
setResponse(data.content);
```

---

### 2. Learning Analytics Dashboard

**Endpoints**:
- `GET /student/{id}/learning/metrics` - Aggregated
- `GET /session/{id}/learning/summary` - Per-session

**Component**:
```javascript
// frontend/src/components/LearningDashboard/LearningDashboard.jsx

export function LearningDashboard({ studentId, sessionId }) {
  const [metrics, setMetrics] = useState(null);
  const [sessionSummary, setSessionSummary] = useState(null);

  useEffect(() => {
    // Aggregate metrics
    fetch(`/student/${studentId}/learning/metrics`)
      .then(r => r.json())
      .then(setMetrics);

    // Session summary
    if (sessionId) {
      fetch(`/session/${sessionId}/learning/summary`)
        .then(r => r.json())
        .then(setSessionSummary);
    }
  }, [studentId, sessionId]);

  return (
    <div className="learning-dashboard">
      {/* Current Session */}
      {sessionSummary && (
        <Card title="This Session" className="session-card">
          <Metric label="Duration" value={sessionSummary.duration} />
          <Metric label="Engagement" value={sessionSummary.engagement} />
          <Metric label="Quality" value={sessionSummary.quality} />
          <TopicList topics={sessionSummary.topics_covered} />
          <ConceptList concepts={sessionSummary.concepts_learned} />
        </Card>
      )}

      {/* Overall Progress */}
      {metrics && (
        <Card title="Your Learning Journey" className="metrics-card">
          <ProgressBar
            label="Sessions"
            value={metrics.total_sessions}
            max={50}
          />
          <ProgressBar
            label="Concepts Learned"
            value={metrics.total_concepts_learned}
            max={200}
          />
          <Metric label="Avg Engagement" value={`${metrics.avg_engagement_score}/100`} />
          <Metric label="Trend" value={metrics.improvement_trend} />
        </Card>
      )}
    </div>
  );
}
```

**Styling Tips**:
- Use gradient progress bars (green = improving, yellow = stable, orange = declining)
- Show trend arrows (📈📉➡️)
- Animate counter updates

---

### 3. Commitment Contracts UI

**Endpoints**:
- `POST /student/{id}/commitment/create` - New
- `GET /student/{id}/commitment/active` - List
- `POST /student/{id}/commitment/check-in` - Progress
- `GET /student/{id}/commitment/summary` - Stats

**Components**:

```javascript
// frontend/src/components/Commitments/CommitmentList.jsx

export function CommitmentList({ studentId }) {
  const [commitments, setCommitments] = useState([]);

  useEffect(() => {
    fetch(`/student/${studentId}/commitment/active`)
      .then(r => r.json())
      .then(d => setCommitments(d.active_commitments));
  }, [studentId]);

  return (
    <div className="commitment-list">
      <h2>Your Study Commitments</h2>
      {commitments.map(c => (
        <CommitmentCard
          key={c.commitment}
          commitment={c}
          onCheckIn={() => handleCheckIn(c)}
        />
      ))}
    </div>
  );
}

// Individual commitment card
function CommitmentCard({ commitment, onCheckIn }) {
  const daysLeft = commitment.days_remaining;
  const isOverdue = commitment.is_overdue;

  return (
    <div className={`commitment-card ${isOverdue ? 'overdue' : ''}`}>
      <h3>{commitment.commitment}</h3>

      <ProgressBar
        value={commitment.progress}
        max={100}
        color={isOverdue ? 'red' : 'blue'}
      />

      <div className="meta">
        <span>📅 {daysLeft > 0 ? `${daysLeft} days left` : 'OVERDUE'}</span>
        <span className={`status ${commitment.status}`}>
          {commitment.status}
        </span>
      </div>

      <div className="actions">
        <CheckInForm commitment={commitment} onSubmit={onCheckIn} />
        {commitment.progress < 100 && (
          <button onClick={onCheckIn}>+ Add Progress</button>
        )}
      </div>
    </div>
  );
}

// Create new commitment modal
function CreateCommitmentModal({ studentId, onClose }) {
  const [form, setForm] = useState({
    commitment: '',
    target_date: '',
    frequency: 'daily',
    goal_metric: '',
  });

  const handleSubmit = async () => {
    const response = await fetch(
      `/student/${studentId}/commitment/create`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form)
      }
    );

    if (response.ok) {
      onClose();
      window.location.reload(); // Refresh list
    }
  };

  return (
    <Modal title="New Study Commitment" onClose={onClose}>
      <input
        placeholder="What do you want to commit to?"
        value={form.commitment}
        onChange={(e) => setForm({...form, commitment: e.target.value})}
      />
      <input
        type="date"
        value={form.target_date}
        onChange={(e) => setForm({...form, target_date: e.target.value})}
      />
      <select
        value={form.frequency}
        onChange={(e) => setForm({...form, frequency: e.target.value})}
      >
        <option>daily</option>
        <option>weekly</option>
        <option>once</option>
      </select>
      <input
        placeholder="Goal metric (e.g., 5 problems)"
        value={form.goal_metric}
        onChange={(e) => setForm({...form, goal_metric: e.target.value})}
      />
      <button onClick={handleSubmit}>Create Commitment</button>
    </Modal>
  );
}
```

**UX Tips**:
- Show commitment progress as circular dial (0-100%)
- Color code: Green (on track), Yellow (at risk), Red (overdue)
- Allow quick check-in with progress slider
- Show celebration animation at 100% completion 🎉

---

### 4. Peer Comparison Card

**Endpoints**:
- `GET /student/{id}/peer/comparison` - Full data
- `GET /student/{id}/peer/suggestions` - Next steps

**Component**:
```javascript
// frontend/src/components/PeerComparison/PeerComparison.jsx

export function PeerComparison({ studentId }) {
  const [comparison, setComparison] = useState(null);
  const [suggestions, setSuggestions] = useState([]);

  useEffect(() => {
    fetch(`/student/${studentId}/peer/comparison`)
      .then(r => r.json())
      .then(setComparison);

    fetch(`/student/${studentId}/peer/suggestions`)
      .then(r => r.json())
      .then(d => setSuggestions(d.suggestions));
  }, [studentId]);

  if (!comparison) return <div>Loading...</div>;

  const summary = comparison.summary;

  return (
    <div className="peer-comparison">
      <h2>How You're Doing</h2>

      {/* Overall Percentile */}
      <PercentileCard
        percentile={summary.overall_percentile}
        message={summary.peer_comparison_message}
      />

      {/* Individual Metrics */}
      <div className="metrics-grid">
        <MetricBox
          label="CGPA"
          percentile={comparison.metrics.cgpa.percentile}
          value={comparison.metrics.cgpa.value}
          status={comparison.metrics.cgpa.status}
        />
        <MetricBox
          label="Engagement"
          percentile={comparison.metrics.engagement.percentile}
          value={comparison.metrics.engagement.value}
          status={comparison.metrics.engagement.status}
        />
        <MetricBox
          label="Learning Speed"
          percentile={comparison.metrics.learning_speed.percentile}
          value={comparison.metrics.learning_speed.value}
          status={comparison.metrics.learning_speed.status}
        />
        <MetricBox
          label="Consistency"
          percentile={comparison.metrics.study_consistency.percentile}
          value={comparison.metrics.study_consistency.value}
          status={comparison.metrics.study_consistency.status}
        />
      </div>

      {/* Strengths & Improvements */}
      <div className="insights">
        <div className="strengths">
          <h3>💪 Your Strengths</h3>
          {summary.strengths.map(s => <p key={s}>{s}</p>)}
        </div>
        <div className="improvements">
          <h3>🎯 Areas to Focus</h3>
          {summary.areas_for_improvement.map(i => <p key={i}>{i}</p>)}
        </div>
      </div>

      {/* Suggestions */}
      <div className="suggestions">
        <h3>💡 Next Steps</h3>
        {suggestions.map((s, i) => (
          <SuggestionCard key={i} text={s} index={i} />
        ))}
      </div>
    </div>
  );
}

// Percentile visualization
function PercentileCard({ percentile, message }) {
  return (
    <div className="percentile-card">
      <div className="percentile-circle">
        <svg viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="45" fill="none" stroke="#e0e0e0" strokeWidth="8" />
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke="#4CAF50"
            strokeWidth="8"
            strokeDasharray={`${percentile * 2.827} 282.7`}
            transform="rotate(-90 50 50)"
          />
          <text x="50" y="50" textAnchor="middle" dy="0.3em" fontSize="24" fontWeight="bold">
            {percentile}th
          </text>
        </svg>
      </div>
      <p className="message">{message}</p>
    </div>
  );
}
```

**Styling Tips**:
- Use circular progress chart for percentile (0-100)
- Color gradient: Red (0%) → Yellow (50%) → Green (100%)
- Show emojis for each metric (📚🔥📈⏰)
- Add micro-interactions (hover = tooltip with explanation)

---

### 5. Cache Management (Admin Panel)

**Endpoints**:
- `GET /cache/stats` - Statistics
- `POST /cache/clear` - Clear all
- `POST /cache/invalidate/{id}` - Clear for student

**Component**:
```javascript
// frontend/src/admin/CacheManagement/CacheManagement.jsx

export function CacheManagement() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    const interval = setInterval(() => {
      fetch('/cache/stats')
        .then(r => r.json())
        .then(setStats);
    }, 5000); // Refresh every 5s

    return () => clearInterval(interval);
  }, []);

  if (!stats) return <div>Connecting to cache...</div>;

  return (
    <div className="cache-management">
      <h2>Cache Statistics</h2>

      {stats.status === 'connected' ? (
        <>
          <Stat label="Total Keys" value={stats.total_cache_keys} />
          <Stat label="Memory Used" value={stats.memory_used} />
          <Stat label="Hit Rate" value={`${(stats.hit_rate * 100).toFixed(1)}%`} />

          <div className="actions">
            <button onClick={() => fetch('/cache/clear', { method: 'POST' })}>
              🧹 Clear All Cache
            </button>
            <input
              placeholder="Student ID to invalidate"
              onKeyPress={(e) => {
                if (e.key === 'Enter') {
                  fetch(`/cache/invalidate/${e.target.value}`, { method: 'POST' });
                }
              }}
            />
          </div>
        </>
      ) : (
        <p className="error">Cache disconnected: {stats.error}</p>
      )}
    </div>
  );
}
```

---

## 🔗 API Service Updates

**Update frontend/src/services/api.js**:

```javascript
// Add these functions

// 1. Streaming chat
export async function* streamChatMessage(message, sessionId, studentId) {
  const params = new URLSearchParams({
    student_id: studentId,
    message,
    session_id: sessionId,
    show_pipeline: true
  });

  const eventSource = new EventSource(`/chat/stream?${params}`);

  yield new Promise((resolve, reject) => {
    eventSource.addEventListener('stage', (e) => {
      resolve({
        type: 'stage',
        data: JSON.parse(e.data)
      });
    });

    eventSource.addEventListener('error', () => {
      reject(new Error('SSE connection error'));
      eventSource.close();
    });
  });
}

// 2. Learning metrics
export async function getLearningMetrics(studentId) {
  return api.get(`/student/${studentId}/learning/metrics`);
}

export async function getSessionLearning(sessionId) {
  return api.get(`/session/${sessionId}/learning/summary`);
}

// 3. Commitments
export async function createCommitment(studentId, commitment) {
  return api.post(`/student/${studentId}/commitment/create`, commitment);
}

export async function checkInCommitment(studentId, checkIn) {
  return api.post(`/student/${studentId}/commitment/check-in`, checkIn);
}

export async function getActiveCommitments(studentId) {
  return api.get(`/student/${studentId}/commitment/active`);
}

export async function getCommitmentSummary(studentId) {
  return api.get(`/student/${studentId}/commitment/summary`);
}

// 4. Peer insights
export async function getPeerComparison(studentId) {
  return api.get(`/student/${studentId}/peer/comparison`);
}

export async function getPeerSuggestions(studentId) {
  return api.get(`/student/${studentId}/peer/suggestions`);
}

// 5. Cache management
export async function getCacheStats() {
  return api.get('/cache/stats');
}

export async function clearCache() {
  return api.post('/cache/clear');
}

export async function invalidateStudentCache(studentId) {
  return api.post(`/cache/invalidate/${studentId}`);
}
```

---

## 🧪 Testing Checklist

- [ ] SSE streaming displays stages in real-time
- [ ] Learning dashboard shows correct metrics
- [ ] Can create/check-in commitments
- [ ] Peer comparison displays percentiles
- [ ] Cache stats update every 5 seconds
- [ ] No console errors on any feature
- [ ] Mobile responsive for all components
- [ ] Touch interactions work on mobile

---

## 📊 Expected User Flow

```
1. Student sends message
   ↓
2. Choose: Regular response or SSE streaming
   ↓
3. If streaming: See pipeline stages appear live
   ↓
4. After response: View learning metrics update
   ↓
5. In sidebar: See active commitments + peer comparison
   ↓
6. Can create new commitment or check in on existing ones
   ↓
7. Dashboard shows overall learning journey + suggestions
```

---

## ⚡ Performance Tips

1. **Streaming**: Use EventSource instead of polling
2. **Analytics**: Cache metrics for 1 minute on client
3. **Commitments**: Load only active ones, paginate history
4. **Peer**: Cache for 1 hour (doesn't change frequently)
5. **Images**: Lazy load percentile charts only when visible

---

## 🚀 Deployment Notes

1. Update API service **before** deploying UI changes
2. Test SSE on both desktop and mobile
3. Check cache stats endpoint is responding
4. Verify commitment dates are in correct timezone
5. Monitor console for any CORS issues with streaming

---

## 📞 Questions?

See `ALL_FEATURES_IMPLEMENTED.md` for complete API reference and troubleshooting.

