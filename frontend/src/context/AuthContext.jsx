import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { authFetch, clearTokens, getStoredTokens, storeTokens } from '../api';

const AuthContext = createContext(null);
const JSON_CONTENT_TYPE_RE = /(^|;|\s)(application\/json|[^;\s]+\/[^;\s]+\+json)(;|$)/i;

async function readResponsePayload(response) {
  const contentType = response.headers.get('content-type') || '';
  const text = await response.text();
  const isJson = JSON_CONTENT_TYPE_RE.test(contentType);

  if (!text) {
    return { data: null, text: '', isJson };
  }

  if (isJson) {
    try {
      return { data: JSON.parse(text), text, isJson: true };
    } catch {
      return { data: null, text, isJson: true };
    }
  }

  return { data: null, text, isJson: false };
}

async function parseJsonOrThrow(response, fallbackMessage) {
  const payload = await readResponsePayload(response);
  const statusLabel = response.status ? ` (HTTP ${response.status})` : '';

  if (!response.ok) {
    if (payload.data?.detail || payload.data?.message) {
      throw new Error(payload.data?.detail || payload.data?.message);
    }
    if (!payload.text) {
      throw new Error(`${fallbackMessage}: пустой ответ сервера${statusLabel}`);
    }
    if (!payload.isJson) {
      throw new Error(`${fallbackMessage}: сервер вернул не JSON${statusLabel}`);
    }
    throw new Error(`${fallbackMessage}: сервер вернул некорректный JSON${statusLabel}`);
  }

  if (payload.data !== null) {
    return payload.data;
  }

  if (!payload.isJson) {
    throw new Error(`${fallbackMessage}: сервер вернул не JSON${statusLabel}`);
  }
  if (!payload.text) {
    throw new Error(`${fallbackMessage}: пустой ответ сервера${statusLabel}`);
  }
  throw new Error(`${fallbackMessage}: сервер вернул некорректный JSON${statusLabel}`);
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [status, setStatus] = useState('idle');

  const applyAuthResponse = (data) => {
    storeTokens(data.tokens.access_token, data.tokens.refresh_token);
    setUser(data.user);
    return data.user;
  };

  const fetchMe = async () => {
    const response = await authFetch('/api/auth/me');
    if (!response.ok) {
      return null;
    }
    try {
      return await parseJsonOrThrow(response, 'Не удалось получить профиль');
    } catch {
      return null;
    }
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
    const data = await parseJsonOrThrow(response, 'Ошибка входа');
    return applyAuthResponse(data);
  };

  const register = async ({ name, email, password }) => {
    const response = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password }),
    });
    return parseJsonOrThrow(response, 'Ошибка регистрации');
  };

  const verify = async ({ email, code }) => {
    const response = await fetch('/api/auth/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, code }),
    });
    const data = await parseJsonOrThrow(response, 'Ошибка подтверждения');
    return applyAuthResponse(data);
  };

  const confirmRegistrationByToken = async (token) => {
    const response = await fetch('/api/auth/verify-email-link', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    const data = await parseJsonOrThrow(response, 'Ошибка подтверждения регистрации');
    return applyAuthResponse(data);
  };

  const resendVerificationLink = async (email) => {
    const response = await fetch('/api/auth/resend-verification-link', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    });
    return parseJsonOrThrow(response, 'Ошибка повторной отправки письма');
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
    return parseJsonOrThrow(response, 'Ошибка запроса');
  };

  const resetPassword = async ({ token, new_password }) => {
    const response = await fetch('/api/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, new_password }),
    });
    return parseJsonOrThrow(response, 'Ошибка сброса пароля');
  };

  const changePassword = async ({ current_password, new_password }) => {
    const response = await authFetch('/api/auth/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password, new_password }),
    });
    return parseJsonOrThrow(response, 'Ошибка смены пароля');
  };

  const requestEmailChange = async ({ new_email, current_password }) => {
    const response = await authFetch('/api/auth/change-email/request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_email, current_password }),
    });
    return parseJsonOrThrow(response, 'Ошибка запроса на смену email');
  };

  const confirmEmailChange = async (token) => {
    const response = await fetch('/api/auth/change-email/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token }),
    });
    const data = await parseJsonOrThrow(response, 'Ошибка подтверждения смены email');
    return applyAuthResponse(data);
  };

  const deleteProfile = async ({ current_password, confirmation_text }) => {
    const response = await authFetch('/api/auth/me', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password, confirmation_text }),
    });
    const data = await parseJsonOrThrow(response, 'Ошибка удаления профиля');
    clearTokens();
    setUser(null);
    return data;
  };

  const value = useMemo(
    () => ({
      user,
      status,
      login,
      register,
      verify,
      confirmRegistrationByToken,
      resendVerificationLink,
      logout,
      forgotPassword,
      resetPassword,
      changePassword,
      requestEmailChange,
      confirmEmailChange,
      deleteProfile,
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
