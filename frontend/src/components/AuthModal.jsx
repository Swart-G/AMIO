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
  profile: 'profile',
};

function AuthModal({ isOpen, mode, onClose, onModeChange }) {
  const {
    user,
    login,
    register,
    verify,
    resendVerificationLink,
    forgotPassword,
    resetPassword,
    changePassword,
    requestEmailChange,
    deleteProfile,
  } = useAuth();

  const [form, setForm] = useState({});
  const [status, setStatus] = useState('idle');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [lastRegisteredEmail, setLastRegisteredEmail] = useState('');

  const [profileForm, setProfileForm] = useState({
    new_email: '',
    email_current_password: '',
    current_password: '',
    new_password: '',
    delete_current_password: '',
    delete_confirmation_text: '',
  });
  const [profileBusyAction, setProfileBusyAction] = useState('');
  const [profileMessages, setProfileMessages] = useState({ email: '', password: '', delete: '' });
  const [profileErrors, setProfileErrors] = useState({ email: '', password: '', delete: '' });

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
      case MODES.profile:
        return 'Управление профилем';
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

  const resetProfileState = () => {
    setProfileBusyAction('');
    setProfileMessages({ email: '', password: '', delete: '' });
    setProfileErrors({ email: '', password: '', delete: '' });
    setProfileForm({
      new_email: '',
      email_current_password: '',
      current_password: '',
      new_password: '',
      delete_current_password: '',
      delete_confirmation_text: '',
    });
  };

  const handleClose = () => {
    resetState();
    resetProfileState();
    setLastRegisteredEmail('');
    onClose?.();
  };

  const setValue = (key) => (event) => {
    setForm((prev) => ({ ...prev, [key]: event.target.value }));
  };

  const setProfileValue = (key) => (event) => {
    setProfileForm((prev) => ({ ...prev, [key]: event.target.value }));
  };

  const switchMode = (next) => {
    resetState();
    resetProfileState();
    onModeChange?.(next);
  };

  const setProfileFeedback = (section, nextMessage = '', nextError = '') => {
    setProfileMessages((prev) => ({ ...prev, [section]: nextMessage }));
    setProfileErrors((prev) => ({ ...prev, [section]: nextError }));
  };

  const withProfileAction = async (section, callback) => {
    setProfileBusyAction(section);
    setProfileFeedback(section, '', '');
    try {
      await callback();
    } catch (err) {
      setProfileFeedback(section, '', err?.message || 'Что-то пошло не так');
    } finally {
      setProfileBusyAction('');
    }
  };

  const handleProfileEmailSubmit = async (event) => {
    event.preventDefault();
    await withProfileAction('email', async () => {
      const data = await requestEmailChange({
        new_email: profileForm.new_email,
        current_password: profileForm.email_current_password,
      });
      setProfileFeedback('email', data?.message || 'Письмо отправлено на новый адрес.');
      setProfileForm((prev) => ({ ...prev, email_current_password: '' }));
    });
  };

  const handleProfilePasswordSubmit = async (event) => {
    event.preventDefault();
    await withProfileAction('password', async () => {
      const data = await changePassword({
        current_password: profileForm.current_password,
        new_password: profileForm.new_password,
      });
      setProfileFeedback('password', data?.message || 'Пароль успешно изменён.');
      setProfileForm((prev) => ({
        ...prev,
        current_password: '',
        new_password: '',
      }));
    });
  };

  const handleProfileDeleteSubmit = async (event) => {
    event.preventDefault();
    await withProfileAction('delete', async () => {
      await deleteProfile({
        current_password: profileForm.delete_current_password,
        confirmation_text: profileForm.delete_confirmation_text,
      });
      handleClose();
    });
  };

  const handleResendRegistrationLink = async () => {
    const email = (lastRegisteredEmail || form.email || '').trim();
    if (!email) {
      setError('Укажите email для повторной отправки ссылки.');
      return;
    }
    setStatus('loading');
    setError('');
    try {
      const data = await resendVerificationLink(email);
      setMessage(data?.message || 'Письмо отправлено повторно.');
    } catch (err) {
      setError(err?.message || 'Не удалось отправить письмо повторно');
    } finally {
      setStatus('idle');
    }
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
        const emailValue = (data.email || form.email || '').trim();
        setLastRegisteredEmail(emailValue);
        setForm((prev) => ({ ...prev, password: '' }));
        setMessage('Ссылка для подтверждения регистрации отправлена на почту.');
        return;
      }

      if (activeMode === MODES.verify) {
        await verify({ email: form.email, code: form.code });
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
      setError(err?.message || 'Что-то пошло не так');
    } finally {
      setStatus('idle');
    }
  };

  if (!isOpen) return null;

  const renderStandardForm = () => (
    <>
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
            <input type="email" value={form.email || ''} onChange={setValue('email')} required />
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
          <>
            <button type="button" onClick={() => switchMode(MODES.login)}>
              Уже есть аккаунт? Войти
            </button>
            {lastRegisteredEmail && (
              <button type="button" onClick={handleResendRegistrationLink} disabled={isBusy}>
                Отправить ссылку повторно
              </button>
            )}
          </>
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
    </>
  );

  const renderProfileMode = () => {
    if (!user) {
      return (
        <div className="auth-profile-empty">
          <p className="auth-helper">Сначала войдите в аккаунт.</p>
          <button className="auth-submit" type="button" onClick={() => switchMode(MODES.login)}>
            Перейти ко входу
          </button>
        </div>
      );
    }

    return (
      <div className="auth-profile-layout">
        <section className="auth-profile-section">
          <h3>Данные аккаунта</h3>
          <p className="auth-profile-row">
            <span>Имя</span>
            <strong>{user.name || 'Не указано'}</strong>
          </p>
          <p className="auth-profile-row">
            <span>Email</span>
            <strong>{user.email}</strong>
          </p>
        </section>

        <section className="auth-profile-section">
          <h3>Смена email</h3>
          <form className="auth-modal-form" onSubmit={handleProfileEmailSubmit}>
            <label>
              Новый email
              <input
                type="email"
                value={profileForm.new_email}
                onChange={setProfileValue('new_email')}
                required
              />
            </label>
            <label>
              Текущий пароль
              <input
                type="password"
                value={profileForm.email_current_password}
                onChange={setProfileValue('email_current_password')}
                required
              />
            </label>
            {profileErrors.email && <p className="auth-error">{profileErrors.email}</p>}
            {profileMessages.email && <p className="auth-message">{profileMessages.email}</p>}
            <button className="auth-submit" type="submit" disabled={profileBusyAction === 'email'}>
              {profileBusyAction === 'email' ? 'Отправка...' : 'Отправить ссылку подтверждения'}
            </button>
          </form>
        </section>

        <section className="auth-profile-section">
          <h3>Смена пароля</h3>
          <form className="auth-modal-form" onSubmit={handleProfilePasswordSubmit}>
            <label>
              Текущий пароль
              <input
                type="password"
                value={profileForm.current_password}
                onChange={setProfileValue('current_password')}
                required
              />
            </label>
            <label>
              Новый пароль
              <input
                type="password"
                value={profileForm.new_password}
                onChange={setProfileValue('new_password')}
                required
              />
            </label>
            {profileErrors.password && <p className="auth-error">{profileErrors.password}</p>}
            {profileMessages.password && <p className="auth-message">{profileMessages.password}</p>}
            <button className="auth-submit" type="submit" disabled={profileBusyAction === 'password'}>
              {profileBusyAction === 'password' ? 'Сохраняем...' : 'Сменить пароль'}
            </button>
          </form>
        </section>

        <section className="auth-profile-section auth-profile-danger">
          <h3>Удаление профиля</h3>
          <p className="auth-helper">
            Это действие удалит ваш аккаунт и связанные данные. Для подтверждения введите `DELETE`.
          </p>
          <form className="auth-modal-form" onSubmit={handleProfileDeleteSubmit}>
            <label>
              Текущий пароль
              <input
                type="password"
                value={profileForm.delete_current_password}
                onChange={setProfileValue('delete_current_password')}
                required
              />
            </label>
            <label>
              Подтверждение
              <input
                type="text"
                value={profileForm.delete_confirmation_text}
                onChange={setProfileValue('delete_confirmation_text')}
                placeholder="DELETE"
                required
              />
            </label>
            {profileErrors.delete && <p className="auth-error">{profileErrors.delete}</p>}
            {profileMessages.delete && <p className="auth-message">{profileMessages.delete}</p>}
            <button
              className="auth-submit auth-submit-danger"
              type="submit"
              disabled={profileBusyAction === 'delete'}
            >
              {profileBusyAction === 'delete' ? 'Удаляем...' : 'Удалить профиль'}
            </button>
          </form>
        </section>
      </div>
    );
  };

  return (
    <div className="auth-modal-overlay" onClick={handleClose}>
      <div
        className={`auth-modal ${activeMode === MODES.profile ? 'auth-modal-profile' : ''}`}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="auth-modal-header">
          <h2>{title}</h2>
          <button className="auth-close" onClick={handleClose} type="button">
            ×
          </button>
        </div>

        {activeMode === MODES.profile ? renderProfileMode() : renderStandardForm()}
      </div>
    </div>
  );
}

export default AuthModal;
