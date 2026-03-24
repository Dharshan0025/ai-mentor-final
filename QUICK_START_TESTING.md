# Quick Start: Testing AI Pipeline Visualization

## 🚀 How to Test the Complete Implementation

### Prerequisites
```bash
# Backend running
cd agents
python -m uvicorn main:app --reload --port 8000

# Frontend running (in another terminal)
cd frontend
npm run dev
```

---

## Test 1: See the Pipeline in Action

### Steps
1. Open http://localhost:5173/chat
2. Log in with any seeded college ID (e.g., `22CSBS001`, password: `password`)
3. Send: **"How is my CGPA trending?"**
4. **Expected**:
   - Chat response appears
   - Below response: Collapsed bar showing "🧠 AI Thinking Process [+]"
   - Click `[+]` to expand
   - See all 5 stages with confidence score

---

## Test 2: Verify Parallel Execution

### Backend Check
1. Open terminal running backend
2. Look for logs showing:
   ```
   ✅ Agents selected: prediction + academic + schedule
   ✅ Prediction agent computed (confidence: 0.85)
   ✅ Academic agent computed (confidence: 0.88)
   ✅ Schedule agent computed (confidence: 0.92)
   ```

### Frontend Check
1. Open DevTools: F12 → Network tab
2. Send a chat message
3. Click on `/chat` POST request
4. Check Response → Look for `pipeline` field with structure:
   ```json
   {
     "pipeline": {
       "intent": { "intent": "prediction", "confidence": 0.92 },
       "agent_selection": { "primary": "prediction", "supporting": [...] },
       "context": { "profile": {...}, "sentiment": 0.2 },
       "agent_outputs": {
         "prediction": { "reasoning": "...", "score": 0.85 },
         "academic": { "reasoning": "...", "score": 0.88 },
         "schedule": { "reasoning": "...", "score": 0.92 }
       },
       "synthesis": { "response_mode": "strategic", "tone": "supportive" },
       "overall_confidence": 0.88
     }
   }
   ```

---

## Test 3: Mobile Responsive

### Steps
1. Open DevTools (F12)
2. Click responsive design mode (Ctrl+Shift+M)
3. Select "iPhone 12 Pro" (390x844)
4. Send a chat message
5. **Expected**:
   - Pipeline shows as collapsible drawer
   - [+] button toggles expand/collapse
   - Stages stack vertically
   - No horizontal scrolling

---

## Test 4: Performance Metrics

### Response Time Check
1. DevTools → Performance tab
2. Send chat message
3. **Expected metrics**:
   - Response time: 2-3 seconds (not 4-5s)
   - Pipeline rendering: <500ms
   - Total with animations: <3.5s

### Database Query Check
1. Backend logs should show:
   ```
   ✅ Context loaded (CGPA: 7.4, Bloom: L4/6)
   ```
   (Single log message = batch query, not N+1)

### Memory Check
1. Keep chat open for 10 minutes
2. Send 10+ messages
3. Backend memory should remain stable
4. Logs should show cleanup:
   ```
   ✅ Cleaned up X stale tutor sessions
   ```

---

## Test 5: Error Scenarios

### Test: LLM Timeout
1. Send message while backend LLM is simulated to hang
2. **Expected**: After 30 seconds, clean error message
3. Not: Indefinite "loading..." state

### Test: Bad Agent Output
1. (Admin only) Simulate bad JSON from LLM
2. **Expected**: System continues, returns fallback response
3. Not: 500 error or crash

### Test: SSE Stream
1. Send message to `/alerts/stream`
2. Keep connection open for 2 hours
3. **Expected**: Connection closes gracefully at 1 hour mark
4. Not: Infinite "connected" state

---

## Test 6: Data Accuracy

### Intent Parsing
- Message: "Which subject am I weakest in?"
- Expected: Intent = "analysis", Confidence ≥ 85%

### Agent Selection
- Message: "I'm feeling stressed about exams"
- Expected: Primary = "emotional", Supporting = ["academic", "schedule"]

### Context Loading
- Check profile data is loaded (CGPA, year, subjects)
- Check sentiment calculated (-1 to +1)
- Check bloom level detected (1-6)

### Synthesis
- Response mode should match student readiness
- Tone should match emotional state
- UI widgets should be relevant to query

---

## Test 7: Feature Completeness

### Expandable/Collapsible
- [ ] Start message, pipeline shows collapsed
- [ ] Click [+], expands smoothly
- [ ] Click [−], collapses smoothly
- [ ] Each expansion takes ~200-300ms

### Animations
- [ ] Stages appear one by one with 200ms delay
- [ ] Confidence bar fills gradually
- [ ] Smooth slide-in animations

### Mobile
- [ ] Drawer slides from bottom on mobile
- [ ] Touch-friendly tap targets (44px minimum)
- [ ] No horizontal overflow

### Accessibility
- [ ] Stages labeled with emojis + text
- [ ] Confidence shown as % and bar
- [ ] Color contrast ≥ 4.5:1

---

## Test 8: Compare with Baseline

### Before (Old System)
```
You: "How's my CGPA?"
Mentor: [Response appears immediately]
        [No indication of how answer was generated]
        [User trust: "Why should I believe this?"]
```

### After (New System)
```
You: "How's my CGPA?"
🧠 AI Thinking Process [+]
   [Stages appear one by one]
   Intent: Prediction (92%)
   Agents: Prediction + Academic (reasoning shown)
   Context: CGPA loaded, sentiment detected
   Reasoning: Each agent's key insight shown
   Synthesis: Strategic approach with supportive tone
   Confidence: 88%

Mentor: [Response appears with confidence backing]
        [User sees exactly how answer was generated]
        [User trust: "This AI showed its work!"]
```

---

## Debug Tips

### If Pipeline Doesn't Show
1. Check DevTools Network → /chat response has `pipeline` field
2. Check frontend shows `pipelineData` in console:
   ```js
   // In Chat.jsx
   console.log('Pipeline:', pipelineData);
   ```
3. Check backend logs for tracker calls

### If Stages Don't Animate
1. Check CSS: `animation: slideIn 0.3s ease-out`
2. Check JS: `visible` class being added
3. Check delays: Should be 0ms, 200ms, 400ms, 600ms, 800ms

### If Performance Slow
1. Backend: Check for N+1 queries in logs
2. Frontend: Check React re-renders (React DevTools Profiler)
3. Network: Check if pipeline data is too large (should be <10KB)

---

## Success Checklist

- [ ] Pipeline appears on all messages
- [ ] 5 stages visible when expanded
- [ ] Animations smooth and timed correctly
- [ ] Mobile layout responsive
- [ ] Performance: Response time 2-3s
- [ ] No console errors
- [ ] Data accuracy verified
- [ ] Confidence scores meaningful
- [ ] Parallel execution confirmed in logs
- [ ] User feels trust increase

---

## Production Deployment

Before deploying to production:

1. **Load Test**: 50 concurrent users
2. **Memory Test**: 24-hour stability check
3. **Accuracy Test**: Verify pipeline matches actual decisions
4. **Mobile Test**: iOS Safari, Android Chrome
5. **A/B Test**: Compare with/without pipeline on learning outcomes

---

## Rollback Plan

If issues found:
```bash
# Disable pipeline (keep code, don't show)
# In main.py chat endpoint:
pipeline=None  # Instead of tracker.get_pipeline_data()

# Users won't see thinking process, but system still tracks
# Can re-enable when issues fixed
```

---

Questions? Check logs:
```bash
# Backend logs
tail -f agents/agent_service.log

# Frontend console
F12 → Console tab → filter: "Pipeline"
```

