// Mock ERP student data — realistic synthetic dataset
export const mockStudents = [
    {
        id: "STU001",
        name: "Dharshan B",
        department: "CSBS",
        year: 4,
        semester: 7,
        college: "Anand Institute of Higher Technology",
        avatar: null,
        cgpaHistory: [7.1, 7.4, 7.0, 7.6, 7.3, 7.8, 7.4],
        currentCGPA: 7.4,
        attendanceOverall: 82,
        subjects: [
            { code: "CS701", name: "Machine Learning", grade: 8.2, attendance: 88, creditWeight: 4, bloomLevel: 4, status: "safe", predicted: 8.0 },
            { code: "CS702", name: "Operating Systems", grade: 5.4, attendance: 65, creditWeight: 4, bloomLevel: 2, status: "risk", predicted: 5.1 },
            { code: "CS703", name: "Database Systems", grade: 7.1, attendance: 78, creditWeight: 3, bloomLevel: 3, status: "watch", predicted: 6.8 },
            { code: "CS704", name: "Computer Networks", grade: 6.3, attendance: 71, creditWeight: 3, bloomLevel: 3, status: "watch", predicted: 6.0 },
            { code: "CS705", name: "Software Engineering", grade: 8.5, attendance: 91, creditWeight: 3, bloomLevel: 5, status: "safe", predicted: 8.6 },
            { code: "CS706", name: "Cloud Computing", grade: 7.8, attendance: 85, creditWeight: 2, bloomLevel: 4, status: "safe", predicted: 7.9 },
        ],
        arrears: [],
        standingarrears: [],
        arrearsHistory: ["CS302 - Data Structures (cleared Sem 4)"],
        sentimentHistory: [0.6, 0.4, 0.3, -0.1, 0.2, 0.5, 0.4, 0.3, -0.2, -0.3, 0.1, 0.4, 0.6, 0.5, 0.7],
        studyStreak: 5,
        examDays: 18,
        predictedCGPA: 7.6,
        predictedCGPARange: [7.2, 8.0],
    }
];

export const mockCurrentStudent = mockStudents[0];

export const AGENTS = [
    { id: "academic", name: "Academic Agent", color: "var(--agent-academic)", icon: "📘" },
    { id: "prediction", name: "Prediction Agent", color: "var(--agent-prediction)", icon: "🔮" },
    { id: "emotional", name: "Emotional Agent", color: "var(--agent-emotional)", icon: "💬" },
    { id: "learning", name: "Learning Agent", color: "var(--agent-learning)", icon: "🎓" },
    { id: "schedule", name: "Schedule Agent", color: "var(--agent-schedule)", icon: "📅" },
    { id: "career", name: "Career Agent", color: "var(--agent-career)", icon: "🚀" },
    { id: "rag", name: "RAG Agent", color: "var(--agent-rag)", icon: "🔍" },
    { id: "multimodal", name: "Multimodal Agent", color: "var(--agent-multimodal)", icon: "🎙️" },
];

export const BLOOM_LEVELS = [
    { level: 1, name: "Remember", color: "#6B7280" },
    { level: 2, name: "Understand", color: "#3B82F6" },
    { level: 3, name: "Apply", color: "#10B981" },
    { level: 4, name: "Analyze", color: "#F59E0B" },
    { level: 5, name: "Evaluate", color: "#EF4444" },
    { level: 6, name: "Create", color: "#8B5CF6" },
];

// Mock chat responses from agents
export const getMockAgentResponse = (query) => {
    const q = query.toLowerCase();
    if (q.includes("operating systems") || q.includes("os")) {
        return {
            agent: "academic",
            text: "Based on your ERP records, your current Operating Systems grade is **5.4 GPA** with only **65% attendance** — this is your highest-risk subject right now.\n\nYour Bloom level for OS topics is at **Level 2 (Understand)**, which means you're still building conceptual ground. I'd recommend starting with Process Scheduling before moving to Memory Management.\n\n**Key focus areas from past exam patterns:**\n1. Process Scheduling Algorithms (appeared in 4/5 past papers)\n2. Deadlock Detection & Prevention\n3. Virtual Memory & Page Replacement\n\nWant me to create a 3-week rescue plan for OS?",
            citations: ["OS Grade: 5.4 — Semester 7", "Attendance: 65% (below 75% threshold)"]
        };
    }
    if (q.includes("cgpa") || q.includes("performance") || q.includes("doing")) {
        return {
            agent: "prediction",
            text: "Your current CGPA is **7.4** and based on your semester trajectory, I'm projecting **7.6** for this semester — but that depends heavily on two subjects.\n\n**Subjects at risk:**\n- Operating Systems → Predicted 51% (arrear risk if below 50%)\n- Computer Networks → Predicted 60% (watch zone)\n\nIf you improve your OS attendance by 15% and complete all assignments, the projection shifts to **7.8**. Want to run a scenario simulation?",
            citations: ["CGPA Trajectory: Semesters 1–6", "Prediction model: v1.0"]
        };
    }
    if (q.includes("schedule") || q.includes("study plan") || q.includes("exam")) {
        return {
            agent: "schedule",
            text: "Your exam is in **18 days**. Based on your risk profile, here's your priority order:\n\n1. 🔴 **Operating Systems** — 4 credit subject, arrear risk → 2 hrs/day\n2. 🟡 **Computer Networks** — 3 credits, watch zone → 1.5 hrs/day\n3. 🟡 **Database Systems** — needs revision → 1 hr/day\n4. 🟢 **ML & SE** — maintain → 30 min/day each\n\nTotal: ~5.5 hrs/day with 2 Pomodoro breaks. Should I generate a day-by-day calendar?",
            citations: ["Exam schedule: Semester 7", "Subject credit weights: ERP"]
        };
    }
    return {
        agent: "academic",
        text: "I've analysed your academic profile across **6 subjects** this semester. Your strongest subject is **Software Engineering (8.5 GPA)** and your primary concern is **Operating Systems (5.4 GPA)**.\n\nWhat would you like to work on today? I can help with:\n- 📊 Detailed subject breakdown\n- 🔮 Performance predictions\n- 📅 Study schedule\n- 📝 Topic explanations",
        citations: []
    };
};

export const SCHEDULE_DATA = [
    {
        day: "Mon", slots: [
            { time: "09:00", subject: "OS", topic: "Process Scheduling", type: "risk", duration: 90 },
            { time: "11:00", subject: "CN", topic: "TCP/IP Layers", type: "watch", duration: 60 },
            { time: "14:00", subject: "ML", topic: "Revision", type: "safe", duration: 45 },
        ]
    },
    {
        day: "Tue", slots: [
            { time: "09:00", subject: "OS", topic: "Deadlocks", type: "risk", duration: 90 },
            { time: "11:00", subject: "DBMS", topic: "Normalization", type: "watch", duration: 60 },
        ]
    },
    {
        day: "Wed", slots: [
            { time: "09:00", subject: "OS", topic: "Memory Management", type: "risk", duration: 90 },
            { time: "11:00", subject: "CN", topic: "Routing Protocols", type: "watch", duration: 60 },
            { time: "14:00", subject: "SE", topic: "SDLC Models", type: "safe", duration: 30 },
        ]
    },
    {
        day: "Thu", slots: [
            { time: "09:00", subject: "OS", topic: "File Systems", type: "risk", duration: 90 },
            { time: "11:00", subject: "DBMS", topic: "Transactions", type: "watch", duration: 60 },
        ]
    },
    {
        day: "Fri", slots: [
            { time: "09:00", subject: "CN", topic: "Network Security", type: "watch", duration: 60 },
            { time: "11:00", subject: "ML", topic: "Neural Networks", type: "safe", duration: 45 },
            { time: "14:00", subject: "OS", topic: "Mock Test", type: "risk", duration: 60 },
        ]
    },
    {
        day: "Sat", slots: [
            { time: "10:00", subject: "OS", topic: "Full Revision", type: "risk", duration: 120 },
            { time: "14:00", subject: "CN", topic: "Past Papers", type: "watch", duration: 90 },
        ]
    },
    {
        day: "Sun", slots: [
            { time: "10:00", subject: "Rest", topic: "Light reading", type: "safe", duration: 60 },
        ]
    },
];
