import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import './styles/global.css';
import './styles/components.css';
import { AuthProvider, useAuth } from './context/AuthContext';
import Landing from './pages/Landing/Landing';
import Login from './pages/Login/Login';
import Dashboard from './pages/Dashboard/Dashboard';
import Chat from './pages/Chat/Chat';
import Prediction from './pages/Prediction/Prediction';
import Learning from './pages/Learning/Learning';
import Schedule from './pages/Schedule/Schedule';
import Career from './pages/Career/Career';
import Profile from './pages/Profile/Profile';
import Tutor from './pages/Tutor/Tutor';
import Progress from './pages/Progress/Progress';
import ExamMode from './pages/ExamMode/ExamMode';
import KnowledgeHub from './pages/KnowledgeHub/KnowledgeHub';
import Roadmap from './pages/Roadmap/Roadmap';
import Problems from './pages/Problems/Problems';
import AppLayout from './components/Layout/AppLayout';

/** Redirects unauthenticated users to /login */
function ProtectedRoute({ children }) {
  const { isAuthed } = useAuth();
  return isAuthed ? children : <Navigate to="/login" replace />;
}

/** Redirects already-authenticated users away from /login */
function GuestRoute({ children }) {
  const { isAuthed } = useAuth();
  return isAuthed ? <Navigate to="/dashboard" replace /> : children;
}

function AppRoutes() {
  const { logout } = useAuth();

  return (
    <Routes>
      {/* Public — marketing page */}
      <Route path="/" element={<Landing />} />

      {/* Guest-only — login */}
      <Route
        path="/login"
        element={
          <GuestRoute>
            <Login />
          </GuestRoute>
        }
      />

      {/* Protected — authenticated app */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <AppLayout onLogout={logout} />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<Dashboard />} />
        <Route path="chat" element={<Chat />} />
        <Route path="prediction" element={<Prediction />} />
        <Route path="learning" element={<Learning />} />
        <Route path="schedule" element={<Schedule />} />
        <Route path="career" element={<Career />} />
        <Route path="tutor" element={<Tutor />} />
        <Route path="learn/progress" element={<Progress />} />
        <Route path="learn/exam" element={<ExamMode />} />
        <Route path="knowledge" element={<KnowledgeHub />} />
        <Route path="roadmap" element={<Roadmap />} />
        <Route path="problems" element={<Problems />} />
        <Route path="profile" element={<Profile />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
