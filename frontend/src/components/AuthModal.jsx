import React, { useMemo, useState } from 'react';
import './AuthModal.css';
import { useAuth } from '../context/AuthContext';

const MODES = {
  login: 'login',
  register: 'register',
  verify: 'verify',
  forgot: 'forgot',
  reset: 'reset',
  change: 'change',
};

function AuthModal({ isOpen, mode, onClose, onModeChange }) {
  const { login, register, verify, forgotPassword, resetPassword, changePassword } = useAuth();
  const [form, setForm] = useState({});
  const [status, setStatus] = useState('idle');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [pendingEmail, setPendingEmail] = useState('');

  const isBusy = status === 'loading';
  const activeMode = mode || MODES.login;

  const title = useMemo(() => {
    switch (activeMode) {
      case MODES.register:
        return 'Регистрация';
      case MODES.verify:
        return 'Подтверждение';
      case MODES.forgot:
        return 'Восстановление';
      case MODES.reset:
        return 'Новый пароль';
      case MODES.change:
        return 'Смена пароля';
      default:
        return 'Вход';
    }
  }, [activeMode]);

  const resetState = () => {
    setForm({});
    setStatus('idle');
    setMessage('');
    setError('');
  };

  const handleClose = () => {
    resetState();
    setPendingEmail('');
    onClose?.();
  };

  const setValue = (key) => (event) => {
    setForm((prev) => ({ ...prev, [key]: event.target.value }));
  };

  const switchMode = (next) => {
    resetState();
    setPendingEmail('');
    onModeChange?.(next);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setStatus('loading');
    setError('');
    setMessage('');

    try {
      if (activeMode === MODES.login) {
        await login({ email: form.email, password: form.password });
        setMessage('Вы вошли в аккаунт.');
        setTimeout(handleClose, 300);
        return;
      }

      if (activeMode === MODES.register) {
        const data = await register({ name: form.name, email: form.email, password: form.password });
        const emailValue = data.email || form.email;
        setPendingEmail(emailValue);
        setForm({ email: emailValue, code: '' });
        setMessage('Код подтверждения отправлен на почту.');
        onModeChange?.(MODES.verify);
        return;
      }

      if (activeMode === MODES.verify) {
        const email = form.email || pendingEmail;
        await verify({ email, code: form.code });
        setMessage('Аккаунт подтвержден.');
        setTimeout(handleClose, 300);
        return;
      }

      if (activeMode === MODES.forgot) {
        await forgotPassword(form.email);
        setForm({ token: '', new_password: '' });
        setMessage('Проверьте почту, код для сброса уже отправлен.');
        onModeChange?.(MODES.reset);
        return;
      }

      if (activeMode === MODES.reset) {
        await resetPassword({ token: form.token, new_password: form.new_password });
        setMessage('Пароль обновлен. Войдите снова.');
        onModeChange?.(MODES.login);
        return;
      }

      if (activeMode === MODES.change) {
        await changePassword({
          current_password: form.current_password,
          new_password: form.new_password,
        });
        setMessage('Пароль успешно изменен.');
        setTimeout(handleClose, 300);
        return;
      }
    } catch (err) {
      setError(err.message || 'Что-то пошло не так');
    } finally {
      setStatus('idle');
    }
  };

  if (!isOpen) return null;

  return (
    <div className="auth-modal-overlay" onClick={handleClose}>
      <div className="auth-modal" onClick={(event) => event.stopPropagation()}>
        <div className="auth-modal-header">
          <h2>{title}</h2>
          <button className="auth-close" onClick={handleClose} type="button">
            ×
          </button>
        </div>

        <form className="auth-modal-form" onSubmit={handleSubmit}>
          {activeMode === MODES.register && (
            <label>
              Имя
              <input type="text" value={form.name || ''} onChange={setValue('name')} required />
            </label>
          )}

          {(activeMode === MODES.login ||
            activeMode === MODES.register ||
            activeMode === MODES.verify ||
            activeMode === MODES.forgot) && (
            <label>
              Email
              <input
                type="email"
                value={form.email || pendingEmail || ''}
                onChange={setValue('email')}
                required
                disabled={activeMode === MODES.verify && Boolean(pendingEmail)}
              />
            </label>
          )}

          {activeMode === MODES.login && (
            <label>
              Пароль
              <input
                type="password"
                value={form.password || ''}
                onChange={setValue('password')}
                required
              />
            </label>
          )}

          {activeMode === MODES.register && (
            <label>
              Пароль
              <input
                type="password"
                value={form.password || ''}
                onChange={setValue('password')}
                required
              />
            </label>
          )}

          {activeMode === MODES.verify && (
            <label>
              Код подтверждения
              <input type="text" value={form.code || ''} onChange={setValue('code')} required />
            </label>
          )}

          {activeMode === MODES.forgot && (
            <p className="auth-helper">Мы отправим ссылку/код для сброса на вашу почту.</p>
          )}

          {activeMode === MODES.reset && (
            <>
              <label>
                Токен из письма
                <input type="text" value={form.token || ''} onChange={setValue('token')} required />
              </label>
              <label>
                Новый пароль
                <input
                  type="password"
                  value={form.new_password || ''}
                  onChange={setValue('new_password')}
                  required
                />
              </label>
            </>
          )}

          {activeMode === MODES.change && (
            <>
              <label>
                Текущий пароль
                <input
                  type="password"
                  value={form.current_password || ''}
                  onChange={setValue('current_password')}
                  required
                />
              </label>
              <label>
                Новый пароль
                <input
                  type="password"
                  value={form.new_password || ''}
                  onChange={setValue('new_password')}
                  required
                />
              </label>
            </>
          )}

          {error && <p className="auth-error">{error}</p>}
          {message && <p className="auth-message">{message}</p>}

          <button className="auth-submit" type="submit" disabled={isBusy}>
            {isBusy ? 'Подождите...' : title}
          </button>
        </form>

        <div className="auth-modal-footer">
          {activeMode === MODES.login && (
            <>
              <button type="button" onClick={() => switchMode(MODES.register)}>
                Нет аккаунта? Зарегистрироваться
              </button>
              <button type="button" onClick={() => switchMode(MODES.forgot)}>
                Забыли пароль?
              </button>
            </>
          )}

          {activeMode === MODES.register && (
            <button type="button" onClick={() => switchMode(MODES.login)}>
              Уже есть аккаунт? Войти
            </button>
          )}

          {activeMode === MODES.verify && (
            <button type="button" onClick={() => switchMode(MODES.login)}>
              Вернуться к входу
            </button>
          )}

          {activeMode === MODES.reset && (
            <button type="button" onClick={() => switchMode(MODES.login)}>
              Вернуться к входу
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default AuthModal;
