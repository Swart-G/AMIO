import React, { useEffect, useMemo, useState } from 'react';
import { useFavorites } from '../context/FavoritesContext';
import { useAuth } from '../context/AuthContext';
import PriceSparkline from '../components/PriceSparkline';
import './FavoritesPage.css';

const MARKETPLACE_META = {
  wb: 'Wildberries',
  ozon: 'Ozon',
  ym: 'Яндекс Маркет',
};

function formatCurrency(value) {
  if (!Number.isFinite(value)) return '—';
  return new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    minimumFractionDigits: 0,
  }).format(value);
}

function formatDisplayPrice(amountValue, textValue) {
  if (Number.isFinite(amountValue)) {
    return formatCurrency(amountValue);
  }
  const text = String(textValue || '').trim();
  return text || '—';
}

function formatPercent(value) {
  if (!Number.isFinite(value)) return '—';
  const formatter = new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
    signDisplay: 'always',
  });
  return `${formatter.format(value)}%`;
}

function trendClassName(value) {
  if (!Number.isFinite(value)) return 'is-neutral';
  if (value > 0) return 'is-up';
  if (value < 0) return 'is-down';
  return 'is-neutral';
}

function parseBackendDate(value) {
  if (!value) return null;
  const raw = String(value).trim();
  if (!raw) return null;
  const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(raw);
  const normalized = hasTimezone ? raw : `${raw}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatUpdatedAgo(value) {
  if (!value) return '—';
  const date = parseBackendDate(value);
  if (!date) return '—';
  const diffMs = Date.now() - date.getTime();
  if (diffMs <= 0) return 'только что';
  const hours = Math.floor(diffMs / (1000 * 60 * 60));
  if (hours <= 0) return 'менее часа назад';
  return `${hours} ч назад`;
}

function FavoritesPage({ onAuthOpen }) {
  const { user, status: authStatus } = useAuth();
  const { fetchFavoritesPage, removeFavoriteById, favoritesVersion } = useFavorites();
  const [items, setItems] = useState([]);
  const [loadState, setLoadState] = useState('idle');
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const [removingId, setRemovingId] = useState(null);
  const [reloadSeq, setReloadSeq] = useState(0);

  useEffect(() => {
    if (authStatus !== 'ready') return;
    if (!user) {
      onAuthOpen?.('login');
      setItems([]);
      setLoadState('idle');
      setActionError('');
      return;
    }

    let cancelled = false;
    const load = async () => {
      setLoadState('loading');
      setError('');
      setActionError('');
      try {
        const data = await fetchFavoritesPage({ limit: 100, offset: 0 });
        if (cancelled) return;
        setItems(Array.isArray(data?.items) ? data.items : []);
        setLoadState('ready');
      } catch (err) {
        if (cancelled) return;
        setError(err.message || 'Не удалось загрузить избранное');
        setLoadState('error');
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [user?.id, authStatus, favoritesVersion, reloadSeq]);

  const content = useMemo(() => {
    if (authStatus === 'loading') {
      return <div className="favorites-state">Проверяем авторизацию...</div>;
    }

    if (!user) {
      return <div className="favorites-state">Войдите в аккаунт, чтобы увидеть избранное.</div>;
    }

    if (loadState === 'loading') {
      return <div className="favorites-state">Загружаем избранные товары...</div>;
    }

    if (loadState === 'error') {
      return (
        <div className="favorites-state favorites-state-error">
          <p>{error || 'Не удалось загрузить избранное'}</p>
          <button type="button" onClick={() => setReloadSeq((prev) => prev + 1)}>Повторить</button>
        </div>
      );
    }

    if (!items.length) {
      return (
        <div className="favorites-empty">
          <h2>Избранное пока пусто</h2>
          <p>Нажмите на сердечко в карточке товара, чтобы добавить его сюда.</p>
        </div>
      );
    }

    return (
      <div className="favorites-list-wrap">
        {actionError && (
          <div className="favorites-inline-error" role="status">
            {actionError}
          </div>
        )}
        <div className="favorites-list" role="list">
          {items.map((item) => (
            <article key={item.id} className="favorite-row" role="listitem">
              <div className="favorite-row-main">
                <img
                  className="favorite-row-image"
                  src={item.img_url || 'https://placehold.co/88x88/f0f0f0/333333?text=Фото'}
                  alt={item.product_name || 'Товар'}
                  loading="lazy"
                />

                <div className="favorite-row-info">
                  <div className="favorite-row-title-line">
                    {item.product_url_original ? (
                      <a
                        className="favorite-row-title"
                        href={item.product_url_original}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {item.product_name || 'Без названия'}
                      </a>
                    ) : (
                      <p className="favorite-row-title">{item.product_name || 'Без названия'}</p>
                    )}
                    <span className={`favorite-row-market is-${item.marketplace || 'unknown'}`}>
                      {MARKETPLACE_META[item.marketplace] || item.marketplace}
                    </span>
                  </div>

                  <div className="favorite-row-price-line">
                    <span className="favorite-row-price">
                      {formatDisplayPrice(item.last_price_amount_rub, item.last_price_text)}
                    </span>
                    <span className={`favorite-row-trend ${trendClassName(item.change_30d_percent)}`}>
                      {formatPercent(item.change_30d_percent)}
                    </span>
                    <span className={`favorite-row-status is-${item.last_refresh_status || 'unknown'}`}>
                      {item.last_refresh_status === 'ok' ? 'обновлено' : (item.last_refresh_status || '—')}
                    </span>
                  </div>

                  <div className="favorite-row-chart-line">
                    <PriceSparkline values={item.sparkline_30d || []} trendPercent={item.change_30d_percent} />
                    <span className="favorite-row-updated">
                      Обновлено: {formatUpdatedAgo(item.last_success_price_at || item.last_refresh_attempt_at)}
                    </span>
                  </div>
                </div>
              </div>
              <button
                type="button"
                className={`favorite-row-favorite-button ${removingId !== item.id ? 'is-active' : ''} ${removingId === item.id ? 'is-loading' : ''}`.trim()}
                aria-label={removingId === item.id ? 'Удаляем из избранного' : 'Убрать из избранного'}
                aria-pressed={removingId !== item.id}
                disabled={removingId === item.id}
                onClick={async () => {
                  try {
                    setActionError('');
                    setRemovingId(item.id);
                    await removeFavoriteById(item.id);
                  } catch (err) {
                    setActionError(err.message || 'Не удалось удалить из избранного');
                  } finally {
                    setRemovingId((prev) => (prev === item.id ? null : prev));
                  }
                }}
              >
                <svg
                  className="favorite-row-heart-icon"
                  viewBox="0 0 24 24"
                  fill={removingId === item.id ? 'none' : 'currentColor'}
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
                </svg>
              </button>
            </article>
          ))}
        </div>
      </div>
    );
  }, [authStatus, user, loadState, error, items, removingId, removeFavoriteById, actionError]);

  return (
    <section className="favorites-page" aria-live="polite">
      <header className="favorites-page-header">
        <h1>Избранные товары</h1>
      </header>
      {content}
    </section>
  );
}

export default FavoritesPage;
