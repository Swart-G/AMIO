import React, { useEffect, useMemo, useState } from 'react';
import './ProductCard.css';
import { useFavorites } from '../context/FavoritesContext';

const DEFAULT_IMAGE = 'https://placehold.co/240x240/f0f0f0/333333?text=%D0%9D%D0%B5%D1%82+%D1%84%D0%BE%D1%82%D0%BE';
const MARKETPLACE_META = {
  wildberries: { label: 'Wildberries', className: 'marketplace-wb' },
  wb: { label: 'Wildberries', className: 'marketplace-wb' },
  ozon: { label: 'Ozon', className: 'marketplace-ozon' },
  yandex_market: { label: 'Яндекс Маркет', className: 'marketplace-ym' },
  yandexmarket: { label: 'Яндекс Маркет', className: 'marketplace-ym' },
  ymarket: { label: 'Яндекс Маркет', className: 'marketplace-ym' },
  ym: { label: 'Яндекс Маркет', className: 'marketplace-ym' },
  yandex: { label: 'Яндекс Маркет', className: 'marketplace-ym' },
};

const parsePrice = (value) => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  if (typeof value === 'string') {
    const normalized = value.replace(/\s+/g, '').replace(',', '.');
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};

function ProductCard({ product, onAuthOpen }) {
  const [imageIndex, setImageIndex] = useState(0);
  const { isFavoritedProduct, isFavoritePending, toggleFavoriteProduct } = useFavorites();
  const [favoriteError, setFavoriteError] = useState('');

  const imageCandidates = useMemo(() => {
    const candidates = [];
    const seen = new Set();

    const add = (value) => {
      if (typeof value !== 'string') return;
      const url = value.trim();
      if (!url || seen.has(url)) return;
      seen.add(url);
      candidates.push(url);
    };

    add(product?.img_url);
    if (Array.isArray(product?.image_urls)) product.image_urls.forEach(add);
    if (Array.isArray(product?.images)) product.images.forEach(add);

    return candidates;
  }, [product?.img_url, product?.image_urls, product?.images]);

  useEffect(() => {
    setImageIndex(0);
  }, [product?.url, product?.img_url, product?.image_urls, product?.images]);

  const imageUrl = imageCandidates[imageIndex] || DEFAULT_IMAGE;

  const priceValue = parsePrice(product.price);
  const formattedPrice = new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    minimumFractionDigits: 0,
  }).format(priceValue);

  const marketplaceKey = (product?.marketplace || '').toString().trim().toLowerCase();
  const marketplaceMeta = MARKETPLACE_META[marketplaceKey] || {};
  const marketplaceName = marketplaceMeta.label || product.marketplace || 'Неизвестно';
  const marketplaceClassName = marketplaceMeta.className || '';

  const productLink = product.url || product.product_url;
  const isInteractive = Boolean(productLink);
  const rating = product.rating ? Number(product.rating) : null;
  const reviews = product.reviews ? Number(product.reviews) : null;
  const isFavorited = isFavoritedProduct(product);
  const favoritePending = isFavoritePending(product);

  const handleFavoriteClick = async (event) => {
    event.preventDefault();
    event.stopPropagation();
    setFavoriteError('');
    try {
      const result = await toggleFavoriteProduct(product);
      if (result?.requiresAuth) {
        onAuthOpen?.('login');
      }
    } catch (error) {
      setFavoriteError(error.message || 'Не удалось обновить избранное');
      console.error('Ошибка работы с избранным:', error);
    }
  };

  const handleOpen = () => {
    if (!productLink) return;
    if (document.body.classList.contains('mobile-nav-open')) return;
    window.open(productLink, '_blank', 'noopener,noreferrer');
  };

  const handleKeyDown = (event) => {
    if (!isInteractive) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      handleOpen();
    }
  };

  const handleImageError = () => {
    if (imageUrl === DEFAULT_IMAGE) return;
    const nextIndex = imageIndex + 1;
    if (nextIndex < imageCandidates.length) {
      setImageIndex(nextIndex);
      return;
    }
    setImageIndex(imageCandidates.length);
  };

  return (
    <div
      className={`product-card ${isInteractive ? 'product-card--interactive' : ''}`}
      onClick={handleOpen}
      onKeyDown={handleKeyDown}
      role={isInteractive ? 'link' : undefined}
      tabIndex={isInteractive ? 0 : undefined}
    >
      <div className="product-card-image-wrapper">
        <button
          className={`favorite-button ${isFavorited ? 'is-active' : ''} ${favoritePending ? 'is-loading' : ''}`.trim()}
          onClick={handleFavoriteClick}
          type="button"
          aria-label={isFavorited ? 'Убрать из избранного' : 'Добавить в избранное'}
          aria-pressed={isFavorited}
          disabled={favoritePending}
          title={favoriteError || undefined}
        >
          <svg
            className="heart-icon"
            viewBox="0 0 24 24"
            fill={isFavorited ? 'currentColor' : 'none'}
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>
          </svg>
        </button>
        <img
          className="product-card-image"
          src={imageUrl}
          alt={product.name || product.title || 'Товар'}
          onError={handleImageError}
          loading="lazy"
        />
      </div>

      <div className="product-card-details">
        <p className="product-card-price">{formattedPrice}</p>
        <p className="product-card-name">{product.name || product.title || 'Название товара'}</p>

        <div className={`product-card-meta ${!(rating || reviews) ? 'is-empty' : ''}`.trim()}>
          {rating && (
            <span className="meta-item meta-item-rating">
              <span className={`rating-star ${rating > 4 ? 'rating-star--high' : ''}`}>★</span>
              <span>{rating.toFixed(1)}</span>
            </span>
          )}
          {reviews && <span className="meta-item">{reviews} отзывов</span>}
        </div>

        {favoriteError && <p className="product-card-favorite-error" role="status">{favoriteError}</p>}

        {productLink ? (
          <a
            className={`product-card-marketplace ${marketplaceClassName}`.trim()}
            href={productLink}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(event) => event.stopPropagation()}
          >
            {marketplaceName}
          </a>
        ) : (
          <p className={`product-card-marketplace ${marketplaceClassName}`.trim()}>{marketplaceName}</p>
        )}
      </div>
    </div>
  );
}

export default ProductCard;
