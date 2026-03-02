/**
 * AuthContext — Global authentication state
 * Provides: { user, isAuthed, login, logout }
 * Hydrates from localStorage on mount so JWT persists across refreshes.
 */
import { createContext, useContext, useState, useCallback } from 'react';
import { login as apiLogin, logout as apiLogout, getStoredStudent } from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [user, setUser] = useState(() => getStoredStudent());
    const [token, setToken] = useState(() => localStorage.getItem('ai_mentor_token'));

    const login = useCallback(async (collegeId, password) => {
        const { student, token: newToken } = await apiLogin(collegeId, password);
        setUser(student);
        setToken(newToken);
        return student;
    }, []);

    const logout = useCallback(() => {
        apiLogout();
        setUser(null);
        setToken(null);
    }, []);

    return (
        <AuthContext.Provider value={{ user, token, isAuthed: Boolean(token), login, logout }}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used within <AuthProvider>');
    return ctx;
}
