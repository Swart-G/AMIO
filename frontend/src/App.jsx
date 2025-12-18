import React, { useState } from 'react';
import './App.css';
import Header from './components/Header';
import ProductGrid from './components/ProductGrid';
import AuthModal from './components/AuthModal';
import { AuthProvider } from './context/AuthContext';

function App() {
  const [searchQuery, setSearchQuery] = useState('');
  const [authOpen, setAuthOpen] = useState(false);
  const [authMode, setAuthMode] = useState('login');

  return (
    <AuthProvider>
      <div className="main-container">
        <Header
          onSearch={setSearchQuery}
          onAuthOpen={(mode = 'login') => {
            setAuthMode(mode);
            setAuthOpen(true);
          }}
        />

        <main className="content-max-width">
          <ProductGrid searchQuery={searchQuery} />
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
