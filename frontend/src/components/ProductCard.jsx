import React from 'react';
import './ProductCard.css';

const DEFAULT_IMAGE = 'https://placehold.co/240x240/f0f0f0/333333?text=%D0%9D%D0%B5%D1%82+%D1%84%D0%BE%D1%82%D0%BE';

function ProductCard({ product }) {
  let imageUrl = DEFAULT_IMAGE;

  if (product.img_url) imageUrl = product.img_url;
  else if (Array.isArray(product.images) && product.images.length > 0) {
    imageUrl = product.images[0];
  }

  const priceValue = Number(product.price) || 0;
  const formattedPrice = new Intl.NumberFormat('ru-RU', {
    style: 'currency',
    currency: 'RUB',
    minimumFractionDigits: 0,
  }).format(priceValue);

  const marketplaceName = product.marketplace || 'Неизвестно';
  const productLink = product.url || product.product_url;
  const rating = product.rating ? Number(product.rating) : null;
  const reviews = product.reviews ? Number(product.reviews) : null;

  const handleFavoriteClick = (event) => {
    event.stopPropagation();
    console.log(`Лайк: ${product.name || product.title}`);
  };

  const handleOpen = () => {
    if (productLink) {
      window.open(productLink, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <div className="product-card" onClick={handleOpen}>
      <div className="product-card-image-wrapper">
        <img
          className="product-card-image"
          src={imageUrl}
          alt={product.name || product.title || 'Товар'}
          onError={(event) => {
            event.target.src = DEFAULT_IMAGE;
          }}
          loading="lazy"
        />
      </div>

      <div className="product-card-details">
        <button className="favorite-button" onClick={handleFavoriteClick} type="button">
          <svg
            className="heart-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path>
          </svg>
        </button>

        <p className="product-card-price">{formattedPrice}</p>
        <p className="product-card-name">{product.name || product.title || 'Название товара'}</p>

        {(rating || reviews) && (
          <div className="product-card-meta">
            {rating && <span className="meta-item">★ {rating.toFixed(1)}</span>}
            {reviews && <span className="meta-item">{reviews} отзывов</span>}
          </div>
        )}

        {productLink ? (
          <a
            className="product-card-marketplace"
            href={productLink}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(event) => event.stopPropagation()}
          >
            {marketplaceName}
          </a>
        ) : (
          <p className="product-card-marketplace">{marketplaceName}</p>
        )}
      </div>
    </div>
  );
}

export default ProductCard;
