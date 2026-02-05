import React, { useEffect, useState } from 'react';
import ProductCard from './ProductCard';
import './ProductGrid.css';

const SKELETON_COUNT = 8;

function ProductGrid({ searchQuery }) {
  const [products, setProducts] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const query = (searchQuery || '').trim();

  useEffect(() => {
    const controller = new AbortController();

    if (!query) {
      setProducts([]);
      setIsLoading(false);
      return () => controller.abort();
    }

    const fetchProducts = async () => {
      setIsLoading(true);

      try {
        const url = `/api/products?q=${encodeURIComponent(query)}`;
        const response = await fetch(url, { signal: controller.signal });

        if (!response.ok) {
          throw new Error(`Ошибка сети: ${response.status}`);
        }

        const data = await response.json();
        let productsList = [];
        if (Array.isArray(data)) {
          productsList = data;
        } else if (data.items && Array.isArray(data.items)) {
          productsList = data.items;
        } else if (data.data && Array.isArray(data.data)) {
          productsList = data.data;
        } else if (data.products && Array.isArray(data.products)) {
          productsList = data.products;
        }

        setProducts(productsList);
      } catch (error) {
        if (error.name === 'AbortError') return;
        console.error('Ошибка загрузки:', error);
        setProducts([]);
      } finally {
        if (!controller.signal.aborted) {
          setIsLoading(false);
        }
      }
    };

    fetchProducts();
    return () => controller.abort();
  }, [query]);

  const shouldShowNotFound = !isLoading && products.length === 0 && query !== '';

  return (
    <div className="product-grid-container" aria-busy={isLoading}>
      {!query && (
        <p className="empty-hint">
          Начните с запроса — например, «наушники», «кофеварка» или «кроссовки».
        </p>
      )}

      {isLoading && <span className="sr-only" role="status" aria-live="polite">Загрузка товаров...</span>}

      {isLoading && Array.from({ length: SKELETON_COUNT }).map((_, index) => (
        <div className="product-card-skeleton" key={`skeleton-${index}`} aria-hidden="true">
          <div className="skeleton-image" />
          <div className="skeleton-content">
            <div className="skeleton-line skeleton-line-price" />
            <div className="skeleton-line" />
            <div className="skeleton-line skeleton-line-short" />
            <div className="skeleton-line skeleton-line-market" />
          </div>
        </div>
      ))}

      {!isLoading && products.length > 0 &&
        products.map((item, index) => (
          <ProductCard key={item.id || index} product={item} />
        ))}

      {shouldShowNotFound && <p className="grid-status" role="status" aria-live="polite">Ничего не найдено</p>}
    </div>
  );
}

export default ProductGrid;
