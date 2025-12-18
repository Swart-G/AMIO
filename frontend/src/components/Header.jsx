import React, { useState } from 'react';
import './Header.css';
import { FiSearch } from 'react-icons/fi';
import {
  BsHeart,
  BsBell,
  BsPersonCircle,
  BsGear,
  BsGlobe,
  BsBoxArrowRight,
  BsShieldLock,
} from 'react-icons/bs';
import { useAuth } from '../context/AuthContext';

function Header({ onSearch, onAuthOpen }) {
  const { user, logout } = useAuth();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [inputValue, setInputValue] = useState('');

  const toggleMenu = () => setIsMenuOpen((prev) => !prev);
  const closeMenu = () => setIsMenuOpen(false);

  const handleSearchClick = () => {
    const value = inputValue.trim();
    if (onSearch) onSearch(value);
  };

  const handleKeyDown = (event) => {
    if (event.key === 'Enter') {
      handleSearchClick();
    }
  };

  const displayName = user?.name || user?.email?.split('@')[0] || 'Гость';

  const handleLogout = async () => {
    await logout();
    closeMenu();
  };

  return (
    <header className="header-full-width">
      <div className="header-container content-max-width">
        <div className="header-logo">
          <span className="logo-text">AMIO</span>
        </div>

        <div className="header-search">
          <input
            type="text"
            placeholder="Поиск товара..."
            className="search-input"
            value={inputValue}
            onChange={(event) => setInputValue(event.target.value)}
            onKeyDown={handleKeyDown}
          />
          <button className="search-button" onClick={handleSearchClick} type="button">
            <FiSearch />
          </button>
        </div>

        <div className="header-user-actions">
          <button className="icon-button" type="button">
            <BsHeart />
          </button>
          <button className="icon-button" type="button">
            <BsBell />
          </button>

          {!user && (
            <div className="auth-actions">
              <button className="auth-link" type="button" onClick={() => onAuthOpen?.('login')}>
                Войти
              </button>
              <button className="auth-button" type="button" onClick={() => onAuthOpen?.('register')}>
                Регистрация
              </button>
            </div>
          )}

          {user && (
            <div className="user-profile-wrapper">
              <div className="user-profile" onClick={toggleMenu}>
                <span>{displayName}</span>
                <div className="user-avatar">
                  <BsPersonCircle />
                </div>
              </div>

              {isMenuOpen && (
                <div className="profile-dropdown">
                  <div className="dropdown-header">
                    <span>{displayName}</span>
                    <BsPersonCircle className="dropdown-avatar-icon" />
                  </div>
                  <ul className="dropdown-list">
                    <li>
                      <BsGear /> <span>Настройки</span>
                    </li>
                    <li>
                      <BsGlobe /> <span>Язык</span>
                    </li>
                    <li onClick={() => onAuthOpen?.('change')}>
                      <BsShieldLock /> <span>Сменить пароль</span>
                    </li>
                    <li className="logout-item" onClick={handleLogout}>
                      <BsBoxArrowRight /> <span>Выйти</span>
                    </li>
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {isMenuOpen && <div className="overlay" onClick={closeMenu}></div>}
    </header>
  );
}

export default Header;
