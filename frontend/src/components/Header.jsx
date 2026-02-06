import React, { useEffect, useRef, useState } from 'react';
import './Header.css';
import {
  FiSearch,
  FiMenu,
  FiX,
  FiHeart,
  FiBell,
  FiUser,
  FiChevronDown,
  FiChevronRight,
  FiLogOut,
} from 'react-icons/fi';
import { useAuth } from '../context/AuthContext';

function Header({ searchQuery = '', onSearch, onHomeClick, onAuthOpen }) {
  const { user, logout } = useAuth();
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [inputValue, setInputValue] = useState('');
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileView, setIsMobileView] = useState(false);
  const [isDesktopProfileMenuOpen, setIsDesktopProfileMenuOpen] = useState(false);
  const openButtonRef = useRef(null);
  const lastFocusRef = useRef(null);
  const desktopProfileMenuRef = useRef(null);

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
        setIsDesktopProfileMenuOpen(false);
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
      return;
    }
    setIsDesktopProfileMenuOpen(false);
  }, [isMobileView]);

  useEffect(() => {
    if (!isDesktopProfileMenuOpen || isMobileView) return undefined;

    const handleClickOutside = (event) => {
      if (!desktopProfileMenuRef.current?.contains(event.target)) {
        setIsDesktopProfileMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isDesktopProfileMenuOpen, isMobileView]);

  useEffect(() => {
    setInputValue(searchQuery);
  }, [searchQuery]);

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

  const openDrawer = () => {
    lastFocusRef.current = document.activeElement;
    setIsMobileNavOpen(true);
  };

  const closeDrawer = () => {
    setIsMobileNavOpen(false);
    const restoreTarget = lastFocusRef.current || openButtonRef.current;
    setTimeout(() => restoreTarget?.focus?.(), 0);
  };

  const handleProfileClick = () => {
    if (user) return;
    closeDrawer();
    onAuthOpen?.('login');
  };

  const handleManageProfile = () => {
    setIsDesktopProfileMenuOpen(false);
    onAuthOpen?.('change');
  };

  const navItems = [
    { key: 'favorites', label: 'Избранное', icon: FiHeart },
    { key: 'notifications', label: 'Уведомления', icon: FiBell },
  ];

  return (
    <>
      <header className={`header-full-width ${isScrolled ? 'header-scrolled' : ''}`}>
        <div className="header-container content-max-width">
          <button
            ref={openButtonRef}
            className="burger-btn"
            id="openMenu"
            type="button"
            aria-controls="drawer"
            aria-expanded={isMobileNavOpen}
            aria-label="Открыть меню"
            onClick={openDrawer}
          >
            <FiMenu />
          </button>

          <button
            className="header-logo"
            type="button"
            onClick={onHomeClick}
            aria-label="Перейти на главную"
          >
            AMIO
          </button>

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

          <nav className="header-nav" aria-hidden={isMobileView}>
            <div className="nav-items">
              <button className="nav-icon-btn" type="button" aria-label="Избранное"><FiHeart /> <span>Избранное</span></button>
              <button className="nav-icon-btn" type="button" aria-label="Уведомления"><FiBell /> <span>Уведомления</span></button>

              <div className="nav-auth">
                {!user ? (
                  <>
                    <button className="btn-login" type="button" onClick={() => onAuthOpen?.('login')}>Войти</button>
                    <button className="btn-reg" type="button" onClick={() => onAuthOpen?.('register')}>Регистрация</button>
                  </>
                ) : (
                  <div className="desktop-profile-menu-wrap" ref={desktopProfileMenuRef}>
                    <button
                      className={`user-info desktop-profile-trigger ${isDesktopProfileMenuOpen ? 'is-open' : ''}`}
                      type="button"
                      aria-haspopup="menu"
                      aria-expanded={isDesktopProfileMenuOpen}
                      aria-label="Открыть меню профиля"
                      onClick={() => setIsDesktopProfileMenuOpen((prev) => !prev)}
                    >
                      <FiUser />
                      <span>{user.name || 'Профиль'}</span>
                      <FiChevronDown className="desktop-profile-chevron" />
                    </button>

                    {isDesktopProfileMenuOpen && (
                      <div className="desktop-profile-menu" role="menu" aria-label="Меню профиля">
                        <button className="desktop-profile-item" type="button" role="menuitem" onClick={handleManageProfile}>
                          <FiUser className="desktop-profile-item-icon" />
                          <span>Управление профилем</span>
                        </button>
                        <button
                          className="desktop-profile-item desktop-profile-item-danger"
                          type="button"
                          role="menuitem"
                          onClick={async () => {
                            await logout();
                            setIsDesktopProfileMenuOpen(false);
                          }}
                        >
                          <FiLogOut className="desktop-profile-item-icon" />
                          <span>Выйти</span>
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          </nav>
        </div>
      </header>

      <div className={`mobile-drawer-root ${isMobileNavOpen ? 'is-open' : ''}`}>
        <div id="scrim" className="nav-overlay" hidden={!isMobileNavOpen} onClick={closeDrawer} />

        <aside
          id="drawer"
          className={`mobile-drawer ${isMobileNavOpen ? 'is-open' : ''}`}
          role="dialog"
          aria-modal="true"
          aria-label="Меню"
          aria-hidden={!isMobileNavOpen}
        >
          <div className="drawer-header">
            <div className="drawer-title">Меню</div>
            <button
              id="closeMenu"
              className="drawer-icon-btn"
              type="button"
              aria-label="Закрыть меню"
              onClick={closeDrawer}
            >
              <FiX />
            </button>
          </div>

          <div className="drawer-section">
            <button className="drawer-profile" type="button" onClick={handleProfileClick}>
              <span className="drawer-avatar"><FiUser /></span>
              <span className="drawer-profile-text">
                <span className="drawer-profile-name">{user?.name || 'Профиль'}</span>
                <span className="drawer-profile-meta">{user ? 'Управление аккаунтом' : 'Войти в аккаунт'}</span>
              </span>
              <FiChevronRight className="drawer-chevron" />
            </button>
          </div>

          <nav className="drawer-nav" aria-label="Навигация">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <button key={item.key} className="drawer-item" type="button">
                  <Icon className="nav-ic" />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>

          <div className="drawer-footer">
            {user ? (
              <button
                className="danger-btn"
                type="button"
                onClick={async () => {
                  await logout();
                  closeDrawer();
                }}
              >
                <FiLogOut /> <span>Выйти</span>
              </button>
            ) : (
              <>
                <button
                  className="btn-login drawer-auth-btn"
                  type="button"
                  onClick={() => {
                    closeDrawer();
                    onAuthOpen?.('login');
                  }}
                >
                  Войти
                </button>
                <button
                  className="btn-reg drawer-auth-btn"
                  type="button"
                  onClick={() => {
                    closeDrawer();
                    onAuthOpen?.('register');
                  }}
                >
                  Регистрация
                </button>
              </>
            )}
          </div>
        </aside>
      </div>
    </>
  );
}

export default Header;
