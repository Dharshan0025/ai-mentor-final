# Development Plan: AI-Mentor Engines

## 1. Overview
This plan outlines the specific implementation steps required to build the advanced "brain" modules of the AI-Mentor system, fulfilling the vision outlined in the academic paper and the adjusted project vision. The foundational infrastructure (Frontend React, Node.js Gateway, FastAPI Agents, Supabase) is complete. This phase focuses entirely on the intelligent agents and pedagogical enforcement logic.

## 2. Project Type
**BACKEND** (Primary Agent: `backend-specialist` + `orchestrator`)

## 3. Success Criteria
*   **Prediction Agent:** Can successfully calculate a projected CGPA and subject scores using historical ERP data (mocked or real), identifying at-risk subjects.
*   **Academic Agent (Bloom's + DAG):** Strictly prevents answering questions at a higher Bloom's level until 80% mastery is achieved at the lower level. Blocks access to advanced DAG topics if prerequisite mastery is < 60%.
*   **RAG Pipeline:** Successfully ingests course PDF documents, vectorizes them using Gemini `text-embedding-004`, stores in Supabase `pgvector`, and queries them based on student intent.
*   **Frontend Integration:** The React Dashboard accurately reflects the real data from the Prediction Engine and true Supabase profile (Phase 4 wiring).

## 4. Tech Stack & Tools
*   **Python / FastAPI:** Core backend environment for the agents.
*   **Scikit-learn / Numpy:** Statistical modeling for linear regression and standard deviation anomaly detection (Prediction Engine).
*   **LangGraph:** Agent orchestration and state management.
*   **Supabase (pgvector):** Storing cognitive mapping (Bloom's state) and vector embeddings for RAG.
*   **Gemini Embeddings:** Generating 768-D vectors.
*   **Groq LLM:** Final generation and synthesis.

## 5. Proposed File Structure
We will mostly modify existing files, but will add new specific modules:
```
agents/
├── main.py                 [MODIFY: Add new routes for prediction/learning data]
├── db.py                   [MODIFY: Add RAG vector insertion and DAG schema queries]
├── orchestrator.py         [MODIFY: Update intent classification rules]
├── agents/
│   ├── prediction.py       [MODIFY: Implement scikit-learn regression logic]
│   ├── academic.py         [MODIFY: Integrate Bloom's + DAG logic before generation]
│   ├── learning.py         [MODIFY: Implement Quiz/Mastery evaluation loop]
│   └── rag_engine.py       [NEW: PDF processing, chunking, Gemini embedding tool]
```

## 6. Task Breakdown

| Task ID | Component/Feature | Agent | Skill | INPUT → OUTPUT → VERIFY | Priority | Dependencies |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ENG-01** | Connect Dashboard to Real Profile | `frontend-specialist` | `react-best-practices` | **IN:** `App.jsx` JWT auth. **OUT:** Dashboard reads from `/api/student/me`. **VERIFY:** Dashboard displays Dharshan's actual Supabase data. | High | None |
| **ENG-02** | RAG Pipeline: Vectorization Tool | `backend-specialist` | `python-patterns` | **IN:** PDF course files. **OUT:** `rag_engine.py` that chunks and sends to Supabase `pgvector`. **VERIFY:** Vectors are saved in `documents` table. | High | None |
| **ENG-03** | RAG Pipeline: Retrieval Agent | `backend-specialist` | `api-patterns` | **IN:** User query. **OUT:** Context retrieved via cosine similarity. **VERIFY:** Agent responses include citations from PDF content. | High | ENG-02 |
| **ENG-04** | Prediction Engine (Math logic) | `backend-specialist` | `python-patterns` | **IN:** 3 semesters CGPA data. **OUT:** Scikit-learn linear regression forecast. **VERIFY:** Agent correctly returns projected score and flags arrears > 1.5 SD. | Medium | None |
| **ENG-05** | Wire Prediction UI | `frontend-specialist` | `react-best-practices` | **IN:** Forecast API. **OUT:** Charts render predicted scores vs actual. **VERIFY:** UI properly visualizes the risk heatmap. | Medium | ENG-04 |
| **ENG-06** | Bloom's API Logic | `backend-specialist` | `api-patterns` | **IN:** Topic query. **OUT:** Rejection or Answer based on `bloom_progress` table score (>80%). **VERIFY:** Agent refuses Apply question if Understand score is 50%. | Medium | None |
| **ENG-07** | DAG Prerequisite Mapper | `backend-specialist` | `python-patterns` | **IN:** Topic schema graph. **OUT:** Access allowed/denied based on prerequisite node scores. **VERIFY:** Student cannot access Advanced Networking if basic Protocols failed. | Low | ENG-06 |

## 7. Phase X: Final Verification Plan
*   [ ] `python .agent/scripts/checklist.py .` - Core Security & Linting
*   [ ] Verify the 4 Backend Engines run without stack tracing or timeouts.
*   [ ] Visual inspection of the React Dashboard to ensure real prediction data is completely replacing mock data.
*   [ ] Manual test of the Socratic Gate (asking a complex Apply question and being explicitly blocked by the Bloom's enforcer).
