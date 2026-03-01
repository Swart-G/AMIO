import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import './App.css';
import Header from './components/Header';
import ProductGrid from './components/ProductGrid';
import AuthModal from './components/AuthModal';
import FavoritesPage from './pages/FavoritesPage';
import { AuthProvider, useAuth } from './context/AuthContext';
import { FavoritesProvider } from './context/FavoritesContext';

function getSearchQueryFromLocation(location) {
  const params = new URLSearchParams(location.search || '');
  return (params.get('q') || '').trim();
}

function AuthActionPage({ action }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { confirmRegistrationByToken, confirmEmailChange } = useAuth();
  const [state, setState] = useState({ status: 'loading', message: 'Проверяем ссылку...' });
  const handledRef = useRef('');
  const confirmRegistrationRef = useRef(confirmRegistrationByToken);
  const confirmEmailChangeRef = useRef(confirmEmailChange);

  useEffect(() => {
    confirmRegistrationRef.current = confirmRegistrationByToken;
    confirmEmailChangeRef.current = confirmEmailChange;
  }, [confirmRegistrationByToken, confirmEmailChange]);

  const redirectToHome = () => {
    try {
      navigate('/', { replace: true });
    } catch {
    }
    window.location.replace('/');
  };

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams(location.search || '');
    const token = (params.get('token') || '').trim();

    if (!token) {
      setState({ status: 'error', message: 'Ссылка недействительна: отсутствует токен.' });
      return undefined;
    }

    const actionKey = `${action}:${token}`;
    if (handledRef.current === actionKey) {
      return undefined;
    }
    handledRef.current = actionKey;

    const run = async () => {
      setState({ status: 'loading', message: 'Проверяем ссылку...' });
      try {
        if (action === 'verify-email') {
          await confirmRegistrationRef.current(token);
          if (cancelled) return;
          redirectToHome();
          return;
        } else {
          await confirmEmailChangeRef.current(token);
          if (cancelled) return;
          redirectToHome();
          return;
        }
      } catch (err) {
        if (cancelled) return;
        setState({ status: 'error', message: err?.message || 'Не удалось обработать ссылку.' });
      }
    };

    run();
    return () => {
      cancelled = true;
    };
  }, [action, location.search, navigate]);

  return (
    <section className="auth-action-card" aria-live="polite">
      <h1>{action === 'verify-email' ? 'Подтверждение регистрации' : 'Подтверждение смены email'}</h1>
      <p className={`auth-action-message is-${state.status}`}>{state.message}</p>
      {state.status !== 'loading' && (
        <button type="button" className="auth-action-button" onClick={() => navigate('/')}>
          На главную
        </button>
      )}
    </section>
  );
}

function AppShell() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, status: authStatus } = useAuth();
  const [searchQuery, setSearchQuery] = useState(() => getSearchQueryFromLocation(window.location));
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState('login');

  const normalizedSearchQuery = useMemo(() => searchQuery.trim(), [searchQuery]);
  const isFavoritesRoute = location.pathname === '/favorites';

  useEffect(() => {
    if (location.pathname !== '/') return;
    setSearchQuery(getSearchQueryFromLocation(location));
  }, [location.pathname, location.search]);

  useEffect(() => {
    if (location.pathname !== '/') return;

    const params = new URLSearchParams(window.location.search);
    if (normalizedSearchQuery) {
      params.set('q', normalizedSearchQuery);
    } else {
      params.delete('q');
    }
    const nextSearch = params.toString();
    const nextUrl = `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ''}${window.location.hash}`;
    window.history.replaceState(null, '', nextUrl);
  }, [normalizedSearchQuery, location.pathname]);

  useEffect(() => {
    if (location.pathname !== '/favorites') return;
    if (authStatus !== 'ready') return;
    if (user) return;
    setAuthMode('login');
    setAuthOpen(true);
  }, [location.pathname, authStatus, user]);

  const openAuth = (mode = 'login') => {
    setAuthMode(mode);
    setAuthOpen(true);
  };

  const handleSearch = (nextQuery) => {
    const normalized = (nextQuery || '').trim();
    setSearchQuery(normalized);
    if (location.pathname !== '/') {
      navigate(normalized ? `/?q=${encodeURIComponent(normalized)}` : '/');
    }
  };

  const handleHomeClick = () => {
    setSearchQuery('');
    navigate('/');
  };

  const handleFavoritesClick = () => {
    navigate('/favorites');
  };

  return (
    <FavoritesProvider onRequireAuth={openAuth}>
      <div className="main-container">
        <Header
          searchQuery={normalizedSearchQuery}
          onSearch={handleSearch}
          onHomeClick={handleHomeClick}
          onFavoritesClick={handleFavoritesClick}
          activeNavKey={isFavoritesRoute ? 'favorites' : null}
          onAuthOpen={openAuth}
        />

        <main className="content-max-width">
          <Routes>
            <Route
              path="/"
              element={<ProductGrid searchQuery={normalizedSearchQuery} onAuthOpen={openAuth} />}
            />
            <Route path="/favorites" element={<FavoritesPage onAuthOpen={openAuth} />} />
            <Route path="/auth/verify-email" element={<AuthActionPage action="verify-email" />} />
            <Route path="/auth/change-email" element={<AuthActionPage action="change-email" />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>

        <footer className="site-footer">
          По всем вопросам и предложениям, пожалуйста, обращайтесь в Telegram: @swarthing.
        </footer>

        <AuthModal
          isOpen={authOpen}
          mode={authMode}
          onModeChange={setAuthMode}
          onClose={() => setAuthOpen(false)}
        />
      </div>
    </FavoritesProvider>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}

export default App;
