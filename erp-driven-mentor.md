# OMNISCIENT — ERP-Driven AI Mentor

## Goal
Transform the current chatbot-with-mock-data into a real ERP-grounded AI mentor
by fixing the data foundation first, then building the 2050-vision features on top of it.

## Agents Assigned
- `database-architect` → Schema & Supabase migrations
- `backend-specialist` → FastAPI endpoints, ERP ingestion pipeline
- `frontend-specialist` → Proactive dashboard, chat UI overhaul, visual tutor
- `orchestrator` → Coordinates sequencing and cross-domain synthesis

---

## Phase 1: DATA FOUNDATION (Everything depends on this)

- [x] Task 1.1: Design full 13-section ERP Supabase schema
  → Files: Supabase migrations via MCP
  → Verify: All 13 tables exist with correct FK relationships

- [x] Task 1.2: Seed 1 real student (full ERP profile — all 13 sections)
  → File: `agents/seed_student.py`
  → Verify: `SELECT * FROM students JOIN subjects JOIN attendance...` returns real rows

- [ ] Task 1.3: Ingest `syllabus.md` into RAG vector store
  → File: `agents/db.py` → `add_document()` pipeline
  → Verify: `db.search_documents("OS process scheduling")` returns relevant chunks

- [ ] Task 1.4: Wire `cgpaHistory` write-back — save each semester's CGPA on login
  → File: `agents/db.py`, `backend/src/routes/auth.js`
  → Verify: After login, `cgpa_history` table has a new row

- [x] Task 1.5: Fix `prediction.py` NameError for students with 1-semester history
  → File: `agents/agents/prediction.py` line 154
  → Verify: `compute_predicted_cgpa({cgpaHistory: [7.2]})` returns without exception

---

## Phase 2: PROACTIVE INTELLIGENCE

- [ ] Task 2.1: Minimum Score Calculator endpoint
  → File: `agents/main.py` → `GET /student/{id}/min-scores`
  → Formula: `min_score = (target_cgpa * total_credits - earned_gpa_sum) / remaining_credits`
  → Verify: Returns `{subject: "OS", min_internal_score: 71}` for real student

- [ ] Task 2.2: Proactive Intelligence Briefing API
  → File: `agents/main.py` → `GET /student/{id}/briefing`
  → Returns: top 3 urgent actions derived from real ERP data (attendance alerts, score targets, deadlines)
  → Verify: Returns different briefing based on profile, not hardcoded

- [ ] Task 2.3: Attendance threshold alert detection
  → File: `agents/main.py` inside briefing endpoint
  → Logic: find subjects where `attendance < 80` with days-remaining calculation
  → Verify: Student with OS=71% gets "3 classes left before detention" alert

- [ ] Task 2.4: Replace static Dashboard with Proactive Intelligence Panel
  → File: `frontend/src/pages/Dashboard/Dashboard.jsx`
  → Calls `/api/student/me/briefing` on mount
  → Verify: Dashboard shows real alerts, not hardcoded cards

---

## Phase 3: CHAT UI OVERHAUL

- [ ] Task 3.1: Structured Agent Response Cards (replace raw markdown bubbles)
  → File: `frontend/src/pages/Chat/Chat.jsx`, `Chat.module.css`
  → Each agent type (academic/career/emotional) gets a distinct card component
  → Verify: Career response shows domain badge + salary badge, not plain text

- [ ] Task 3.2: Live Agent Orchestration Visualizer
  → File: `frontend/src/pages/Chat/Chat.jsx`
  → SSE stream from backend shows which agents are running in real time
  → Verify: Typing a message shows agent pipeline animating before response arrives

- [ ] Task 3.3: Action Chips after responses
  → File: `frontend/src/pages/Chat/Chat.jsx`
  → E.g., after Career response: [📊 View Career Page] [🧪 Take Quiz] [📅 Show Schedule]
  → Verify: Chips route to correct pages

---

## Phase 4: VISUAL TUTOR MODE

- [ ] Task 4.1: Concept whiteboard component
  → File: `frontend/src/components/ConceptBoard/ConceptBoard.jsx`
  → D3.js auto-renders Mermaid diagrams when academic agent detects diagram keywords
  → Verify: "explain OS process scheduling" renders a Gantt-style animation

- [ ] Task 4.2: Bloom-adaptive quiz UI on Learning page
  → File: `frontend/src/pages/Learning/Learning.jsx`
  → Shows student's real Bloom level per subject, auto-fills quiz form
  → Verify: Quiz bloom_level defaults to profile value, not "1"

---

## Done When
- [ ] All 13 ERP sections have Supabase tables
- [ ] One real student has complete data seeded across all tables
- [ ] Dashboard shows proactive briefing from real data (no mocks)
- [ ] Chat responses are structured cards, not raw markdown
- [ ] Minimum score calculator returns correct math for real profile
