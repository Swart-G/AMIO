import React, { useEffect, useState } from 'react';
import './Header.css';
import { FiSearch, FiMenu, FiX } from 'react-icons/fi';
import { BsHeart, BsBell, BsPersonCircle } from 'react-icons/bs';
import { useAuth } from '../context/AuthContext';

function Header({ onSearch, onAuthOpen }) {
  const { user } = useAuth();
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileView, setIsMobileView] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };

    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    const handleEscape = (event) => {
      if (event.key === 'Escape') {
        setIsMobileNavOpen(false);
      }
    };

    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, []);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(max-width: 768px)');
    const handleChange = () => setIsMobileView(mediaQuery.matches);

    handleChange();
    if (mediaQuery.addEventListener) {
      mediaQuery.addEventListener('change', handleChange);
      return () => mediaQuery.removeEventListener('change', handleChange);
    }

    mediaQuery.addListener(handleChange);
    return () => mediaQuery.removeListener(handleChange);
  }, []);

  useEffect(() => {
    if (!isMobileView) {
      setIsMobileNavOpen(false);
    }
  }, [isMobileView]);

  useEffect(() => {
    if (isMobileView) {
      document.body.style.overflow = isMobileNavOpen ? 'hidden' : '';
      document.body.classList.toggle('mobile-nav-open', isMobileNavOpen);
    } else {
      document.body.style.overflow = '';
      document.body.classList.remove('mobile-nav-open');
    }

    return () => {
      document.body.style.overflow = '';
      document.body.classList.remove('mobile-nav-open');
    };
  }, [isMobileNavOpen, isMobileView]);

  const handleSearch = () => {
    if (onSearch) onSearch(inputValue.trim());
    setIsMobileNavOpen(false);
  };

  const handleOverlayDismiss = (event) => {
    event.preventDefault();
    event.stopPropagation();
    setIsMobileNavOpen(false);
  };

  return (
    <header className={`header-full-width ${isScrolled ? 'header-scrolled' : ''}`}>
      <div className="header-container content-max-width">
        <button
          className="burger-btn"
          type="button"
          aria-label={isMobileNavOpen ? 'Закрыть меню' : 'Открыть меню'}
          onClick={() => setIsMobileNavOpen(!isMobileNavOpen)}
        >
          {isMobileNavOpen ? <FiX /> : <FiMenu />}
        </button>

        <div className="header-logo">AMIO</div>

        <div className="search-wrapper">
          <div className="header-search">
            <input
              type="text"
              aria-label="Поиск товара"
              placeholder="Поиск товара..."
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            />
            <button type="button" aria-label="Искать" onClick={handleSearch}><FiSearch /></button>
          </div>
        </div>

        <nav
          className={`header-nav ${isMobileNavOpen ? 'nav-open' : ''}`}
          aria-hidden={isMobileView && !isMobileNavOpen}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <div className="nav-items">
            <button className="nav-icon-btn" type="button" aria-label="Избранное"><BsHeart /> <span>Избранное</span></button>
            <button className="nav-icon-btn" type="button" aria-label="Уведомления"><BsBell /> <span>Уведомления</span></button>
            
            <div className="nav-auth">
              {!user ? (
                <>
                  <button className="btn-login" type="button" onClick={() => onAuthOpen?.('login')}>Войти</button>
                  <button className="btn-reg" type="button" onClick={() => onAuthOpen?.('register')}>Регистрация</button>
                </>
              ) : (
                <div className="user-info">
                  <BsPersonCircle /> <span>{user.name || 'Профиль'}</span>
                </div>
              )}
            </div>
          </div>
        </nav>
      </div>
      {isMobileNavOpen && (
        <div
          className="nav-overlay"
          aria-hidden="true"
          onPointerDown={handleOverlayDismiss}
          onClick={handleOverlayDismiss}
        />
      )}
    </header>
  );
}

export default Header;
