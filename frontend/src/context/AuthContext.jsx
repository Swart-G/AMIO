import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { authFetch, clearTokens, getStoredTokens, storeTokens } from '../api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState('idle');

  const fetchMe = async () => {
    const response = await authFetch('/api/auth/me');
    if (!response.ok) {
      return null;
    }
    return response.json();
  };

  useEffect(() => {
    const init = async () => {
      const tokens = getStoredTokens();
      if (!tokens.access && !tokens.refresh) {
        setStatus('ready');
        return;
      }
      setStatus('loading');
      const me = await fetchMe();
      if (me) {
        setUser(me);
      } else {
        clearTokens();
        setUser(null);
      }
      setStatus('ready');
    };
    init();
  }, []);

  const login = async ({ email, password }) => {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) {
      throw new Error((await response.json()).detail || 'Ошибка входа');
    }
    const data = await response.json();
    storeTokens(data.tokens.access_token, data.tokens.refresh_token);
    setUser(data.user);
    return data.user;
  };

  const register = async ({ name, email, password }) => {
    const response = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password }),
    });
    if (!response.ok) {
      throw new Error((await response.json()).detail || 'Ошибка регистрации');
    }
    return response.json();
  };

  const verify = async ({ email, code }) => {
    const response = await fetch('/api/auth/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, code }),
    });
    if (!response.ok) {
      throw new Error((await response.json()).detail || 'Ошибка подтверждения');
    }
    const data = await response.json();
    storeTokens(data.tokens.access_token, data.tokens.refresh_token);
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    const { refresh } = getStoredTokens();
    if (refresh) {
      await fetch('/api/auth/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      });
    }
    clearTokens();
    setUser(null);
  };

  const forgotPassword = async (email) => {
    const response = await fetch('/api/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    if (!response.ok) {
      throw new Error((await response.json()).detail || 'Ошибка запроса');
    }
    return response.json();
  };

  const resetPassword = async ({ token, new_password }) => {
    const response = await fetch('/api/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, new_password }),
    });
    if (!response.ok) {
      throw new Error((await response.json()).detail || 'Ошибка сброса пароля');
    }
    return response.json();
  };

  const changePassword = async ({ current_password, new_password }) => {
    const response = await authFetch('/api/auth/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password, new_password }),
    });
    if (!response.ok) {
      throw new Error((await response.json()).detail || 'Ошибка смены пароля');
    }
    return response.json();
  };

  const value = useMemo(
    () => ({
      user,
      status,
      login,
      register,
      verify,
      logout,
      forgotPassword,
      resetPassword,
      changePassword,
      refreshMe: fetchMe,
      setUser,
    }),
    [user, status]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside AuthProvider');
  }
  return ctx;
}
