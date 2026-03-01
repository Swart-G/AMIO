import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { authFetch } from '../api';
import { useAuth } from './AuthContext';

const FavoritesContext = createContext(null);

const MARKETPLACE_ALIASES = {
  wildberries: 'wb',
  wb: 'wb',
  ozon: 'ozon',
  yandex_market: 'ym',
  yandexmarket: 'ym',
  ymarket: 'ym',
  ym: 'ym',
  yandex: 'ym',
};

function normalizeMarketplace(value) {
  return MARKETPLACE_ALIASES[String(value || '').trim().toLowerCase()] || null;
}

function canonicalizeUrl(rawUrl, marketplace) {
  const input = String(rawUrl || '').trim();
  if (!input) return '';

  try {
    const parsed = new URL(input);
    const host = parsed.host.toLowerCase();
    const path = (parsed.pathname || '/').replace(/\/+$/, '') || '/';

    if (marketplace === 'wb') {
      const match = path.match(/\/catalog\/(\d+)(?:\/|$)/i);
      if (match) return `https://www.wildberries.ru/catalog/${match[1]}/detail.aspx`;
      return `https://${host}${path}`;
    }

    if (marketplace === 'ozon') {
      const next = new URL(`https://${host}${path}`);
      ['asb', 'at'].forEach((key) => {
        const value = parsed.searchParams.get(key);
        if (value) next.searchParams.set(key, value);
      });
      return next.toString();
    }

    if (marketplace === 'ym') {
      const next = new URL(`https://${host}${path}`);
      ['sku', 'nid', 'hid'].forEach((key) => {
        const value = parsed.searchParams.get(key);
        if (value) next.searchParams.set(key, value);
      });
      return next.toString();
    }

    return parsed.toString();
  } catch {
    return input;
  }
}

function productToFavoritePayload(product) {
  const marketplace = normalizeMarketplace(product?.marketplace);
  const url = product?.url || product?.product_url || '';
  return {
    marketplace,
    url,
    name: product?.name || product?.title || '',
    img_url: product?.img_url || (Array.isArray(product?.image_urls) ? product.image_urls[0] : '') || '',
    price: product?.price || '',
  };
}

function buildFavoriteKey({ marketplace, canonicalUrl, originalUrl }) {
  const market = normalizeMarketplace(marketplace);
  if (!market) return '';
  const url = canonicalUrl || canonicalizeUrl(originalUrl, market);
  return url ? `${market}|${url}` : '';
}

export function FavoritesProvider({ children, onRequireAuth }) {
  const { user } = useAuth();
  const [keysMap, setKeysMap] = useState(new Map());
  const [keysStatus, setKeysStatus] = useState('idle');
  const [pendingKeys, setPendingKeys] = useState(new Set());
  const [version, setVersion] = useState(0);

  const clearState = () => {
    setKeysMap(new Map());
    setKeysStatus('idle');
    setPendingKeys(new Set());
  };

  const refreshKeys = async () => {
    if (!user) {
      clearState();
      return new Map();
    }
    setKeysStatus('loading');
    const response = await authFetch('/api/auth/favorites/keys');
    if (!response.ok) {
      setKeysStatus('error');
      throw new Error((await response.json().catch(() => ({}))).detail || 'Не удалось загрузить избранное');
    }
    const data = await response.json();
    const nextMap = new Map();
    (data?.items || []).forEach((item) => {
      const key = buildFavoriteKey({
        marketplace: item.marketplace,
        canonicalUrl: item.product_url_canonical,
        originalUrl: item.product_url_original,
      });
      if (key) nextMap.set(key, item);
      const originalKey = buildFavoriteKey({
        marketplace: item.marketplace,
        canonicalUrl: '',
        originalUrl: item.product_url_original,
      });
      if (originalKey) nextMap.set(originalKey, item);
    });
    setKeysMap(nextMap);
    setKeysStatus('ready');
    return nextMap;
  };

  useEffect(() => {
    if (!user) {
      clearState();
      return;
    }
    refreshKeys().catch((error) => {
      console.error('Ошибка загрузки ключей избранного:', error);
    });
  }, [user?.id]);

  const getProductKey = (product) => {
    const payload = productToFavoritePayload(product);
    if (!payload.marketplace || !payload.url) return '';
    return buildFavoriteKey({
      marketplace: payload.marketplace,
      canonicalUrl: canonicalizeUrl(payload.url, payload.marketplace),
      originalUrl: payload.url,
    });
  };

  const isFavoritedProduct = (product) => {
    const key = getProductKey(product);
    return Boolean(key && keysMap.has(key));
  };

  const isFavoritePending = (product) => {
    const key = getProductKey(product);
    return Boolean(key && pendingKeys.has(key));
  };

  const fetchFavoritesPage = async ({ limit = 50, offset = 0 } = {}) => {
    if (!user) {
      return {
        count: 0,
        items: [],
        total: 0,
        offset,
        limit,
        has_more: false,
      };
    }

    const response = await authFetch(`/api/auth/favorites?limit=${limit}&offset=${offset}`);
    if (!response.ok) {
      throw new Error((await response.json().catch(() => ({}))).detail || 'Не удалось загрузить избранное');
    }
    return response.json();
  };

  const markPending = (key, isPending) => {
    setPendingKeys((prev) => {
      const next = new Set(prev);
      if (isPending) next.add(key);
      else next.delete(key);
      return next;
    });
  };

  const toggleFavoriteProduct = async (product) => {
    const payload = productToFavoritePayload(product);
    if (!payload.marketplace || !payload.url) {
      throw new Error('У товара нет корректной ссылки или маркетплейса');
    }

    if (!user) {
      onRequireAuth?.('login');
      return { requiresAuth: true };
    }

    const key = buildFavoriteKey({
      marketplace: payload.marketplace,
      canonicalUrl: canonicalizeUrl(payload.url, payload.marketplace),
      originalUrl: payload.url,
    });
    if (!key) return { changed: false };
    if (pendingKeys.has(key)) return { changed: false };

    markPending(key, true);
    try {
      const existing = keysMap.get(key);
      if (existing?.id) {
        const delResponse = await authFetch(`/api/auth/favorites/${existing.id}`, { method: 'DELETE' });
        if (!delResponse.ok) {
          throw new Error((await delResponse.json().catch(() => ({}))).detail || 'Не удалось удалить из избранного');
        }
      } else {
        const addResponse = await authFetch('/api/auth/favorites', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!addResponse.ok) {
          throw new Error((await addResponse.json().catch(() => ({}))).detail || 'Не удалось добавить в избранное');
        }
      }

      await refreshKeys();
      setVersion((prev) => prev + 1);
      return { changed: true };
    } finally {
      markPending(key, false);
    }
  };

  const removeFavoriteById = async (favoriteId) => {
    if (!user) return;
    const response = await authFetch(`/api/auth/favorites/${favoriteId}`, { method: 'DELETE' });
    if (!response.ok) {
      throw new Error((await response.json().catch(() => ({}))).detail || 'Не удалось удалить из избранного');
    }
    await refreshKeys();
    setVersion((prev) => prev + 1);
  };

  const value = useMemo(
    () => ({
      keysStatus,
      favoritesVersion: version,
      refreshKeys,
      fetchFavoritesPage,
      toggleFavoriteProduct,
      removeFavoriteById,
      isFavoritedProduct,
      isFavoritePending,
      getProductKey,
    }),
    [keysStatus, version, keysMap, pendingKeys, user]
  );

  return <FavoritesContext.Provider value={value}>{children}</FavoritesContext.Provider>;
}

export function useFavorites() {
  const ctx = useContext(FavoritesContext);
  if (!ctx) {
    throw new Error('useFavorites must be used inside FavoritesProvider');
  }
  return ctx;
}
