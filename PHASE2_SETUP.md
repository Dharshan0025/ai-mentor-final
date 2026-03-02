# AI-Mentor — Phase 2 Startup Guide

## System Architecture

```
Frontend  → localhost:5173  (Vite React)
Backend   → localhost:3001  (Node.js Express — API Gateway)
Agents    → localhost:8000  (Python FastAPI — LangGraph agents)
```

## 1. Setup Python Agent Service

```bash
cd agents

# Copy and fill in your API keys
cp .env.example .env

# Create virtual environment
python -m venv venv
venv\Scripts\activate   # Windows

# Install deps
pip install -r requirements.txt

# Start the agent service
python main.py
# or: uvicorn main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

## 2. Setup Node.js Backend

```bash
cd backend

# Copy and fill in JWT secret
cp .env.example .env

# Install deps
npm install

# Start backend
npm run dev
```

## 3. Start Frontend

```bash
cd frontend
npm run dev
```

## 4. Required API Keys

Get free keys here:
- **Groq** (primary LLM): https://console.groq.com
- **Google AI** (Gemini): https://aistudio.google.com/apikey

Set them in `agents/.env`:
```
GROQ_API_KEY=gsk_xxx
GOOGLE_API_KEY=xxx
```

## Quick Test

```bash
# Test agent service health
curl http://localhost:8000/health

# Test chat (with agent service running)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"How am I doing in OS?","session_id":"test-123","student_id":"22CSBS001","lang":"en","history":[]}'
```
