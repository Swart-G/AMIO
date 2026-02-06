import React, { useEffect, useMemo, useState } from 'react';
import './App.css';
import Header from './components/Header';
import ProductGrid from './components/ProductGrid';
import AuthModal from './components/AuthModal';
import { AuthProvider } from './context/AuthContext';

function getInitialSearchQuery() {
  const params = new URLSearchParams(window.location.search);
  return (params.get('q') || '').trim();
}

function App() {
  const [searchQuery, setSearchQuery] = useState(getInitialSearchQuery);
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState('login');
  const normalizedSearchQuery = useMemo(() => searchQuery.trim(), [searchQuery]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (normalizedSearchQuery) {
      params.set('q', normalizedSearchQuery);
    } else {
      params.delete('q');
    }

    const nextSearch = params.toString();
    const nextUrl = `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ''}${window.location.hash}`;
    window.history.replaceState(null, '', nextUrl);
  }, [normalizedSearchQuery]);

  const handleSearch = (nextQuery) => {
    setSearchQuery((nextQuery || '').trim());
  };

  const handleHomeClick = () => {
    setSearchQuery('');
  };

  return (
    <AuthProvider>
      <div className="main-container">
        <Header
          searchQuery={normalizedSearchQuery}
          onSearch={handleSearch}
          onHomeClick={handleHomeClick}
          onAuthOpen={(mode = 'login') => {
            setAuthMode(mode);
            setAuthOpen(true);
          }}
        />

        <main className="content-max-width">
          <ProductGrid searchQuery={normalizedSearchQuery} />
        </main>

        <AuthModal
          isOpen={authOpen}
          mode={authMode}
          onModeChange={setAuthMode}
          onClose={() => setAuthOpen(false)}
        />
      </div>
    </AuthProvider>
  );
}

export default App;
