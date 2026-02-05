const ACCESS_KEY = 'amio_access_token';
const REFRESH_KEY = 'amio_refresh_token';

export function getStoredTokens() {
  return {
    access: localStorage.getItem(ACCESS_KEY) || '',
    refresh: localStorage.getItem(REFRESH_KEY) || '',
  };
}

export function storeTokens(access, refresh) {
  if (access) localStorage.setItem(ACCESS_KEY, access);
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

async function refreshTokens(refreshToken) {
  const response = await fetch('/api/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) {
    return null;
  }

  return response.json();
}

export async function authFetch(path, options = {}) {
  const tokens = getStoredTokens();
  const headers = new Headers(options.headers || {});
  if (tokens.access) {
    headers.set('Authorization', `Bearer ${tokens.access}`);
  }

  const response = await fetch(path, { ...options, headers });
  if (response.status !== 401 || !tokens.refresh) {
    return response;
  }

  const refreshed = await refreshTokens(tokens.refresh);
  if (!refreshed?.access_token) {
    return response;
  }

  storeTokens(refreshed.access_token, refreshed.refresh_token);
  const retryHeaders = new Headers(options.headers || {});
  retryHeaders.set('Authorization', `Bearer ${refreshed.access_token}`);
  return fetch(path, { ...options, headers: retryHeaders });
}
