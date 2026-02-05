import React, { useEffect, useRef, useState } from 'react';
import ProductCard from './ProductCard';
import './ProductGrid.css';

function ProductGrid({ searchQuery }) {
  const [products, setProducts] = useState([]);
  const [isLoadingInitial, setIsLoadingInitial] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const loadMoreRef = useRef(null);
  const query = (searchQuery || '').trim();
  const pageSize = 24;

  useEffect(() => {
    let cancelled = false;
    if (!query) {
      setProducts([]);
      setIsLoadingInitial(false);
      setIsLoadingMore(false);
      setHasMore(false);
      setOffset(0);
      return () => {
        cancelled = true;
      };
    }

    setProducts([]);
    setIsLoadingInitial(true);
    setIsLoadingMore(false);
    setHasMore(false);
    setOffset(0);

    const fetchProducts = async (nextOffset, reset = false) => {
      setIsLoadingInitial(true);
      setIsLoadingMore(false);

      try {
        const url = `/api/products?q=${encodeURIComponent(query)}&limit=${pageSize}&offset=${nextOffset}`;
        const response = await fetch(url);

        if (!response.ok) {
          throw new Error(`Ошибка сети: ${response.status}`);
        }

        const data = await response.json();
        if (cancelled) {
          return;
        }
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

        setProducts((prev) => {
          const next = reset ? [] : prev;
          const seen = new Set(next.map((item) => item?.url).filter(Boolean));
          const merged = [...next];
          productsList.forEach((item) => {
            const key = item?.url || item?.id;
            if (!key || seen.has(key)) return;
            seen.add(key);
            merged.push(item);
          });
          return merged;
        });
        const hasMoreFlag = typeof data.has_more === 'boolean'
          ? data.has_more
          : productsList.length === pageSize;
        setHasMore(hasMoreFlag);
        setOffset(nextOffset + productsList.length);
      } catch (error) {
        if (cancelled) {
          return;
        }
        console.error('Ошибка загрузки:', error);
        if (reset) {
          setProducts([]);
          setHasMore(false);
          setOffset(0);
        }
      } finally {
        if (!cancelled) {
          setIsLoadingInitial(false);
        }
      }
    };

    fetchProducts(0, true);
    return () => {
      cancelled = true;
    };
  }, [query]);

  useEffect(() => {
    if (!query || !hasMore) return;
    if (typeof IntersectionObserver === 'undefined') return;
    const target = loadMoreRef.current;
    if (!target) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry.isIntersecting && !isLoadingMore && !isLoadingInitial && hasMore) {
          const nextOffset = offset;
          if (nextOffset >= 0) {
            const fetchMore = async () => {
              setIsLoadingMore(true);
              try {
                const url = `/api/products?q=${encodeURIComponent(query)}&limit=${pageSize}&offset=${nextOffset}`;
                const response = await fetch(url);
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
                setProducts((prev) => {
                  const seen = new Set(prev.map((item) => item?.url).filter(Boolean));
                  const merged = [...prev];
                  productsList.forEach((item) => {
                    const key = item?.url || item?.id;
                    if (!key || seen.has(key)) return;
                    seen.add(key);
                    merged.push(item);
                  });
                  return merged;
                });
                const hasMoreFlag = typeof data.has_more === 'boolean'
                  ? data.has_more
                  : productsList.length === pageSize;
                setHasMore(hasMoreFlag);
                setOffset(nextOffset + productsList.length);
              } catch (error) {
                console.error('Ошибка загрузки:', error);
              } finally {
                setIsLoadingMore(false);
              }
            };
            fetchMore();
          }
        }
      },
      { rootMargin: '200px' }
    );

    observer.observe(target);
    return () => {
      observer.disconnect();
    };
  }, [query, hasMore, isLoadingInitial, isLoadingMore, offset]);

  const shouldShowNotFound = !isLoadingInitial && products.length === 0 && query !== '';

  return (
    <div className="product-grid-container">
      {!query && (
        <p className="empty-hint">
          Начните с запроса — например, «наушники», «кофеварка» или «кроссовки».
        </p>
      )}

      {isLoadingInitial && products.length === 0 && (
        <div className="grid-loading-initial" aria-live="polite">
          <span className="grid-spinner" aria-hidden="true" />
          <span className="grid-loading-text">Загрузка товаров...</span>
        </div>
      )}

      {products.length > 0 &&
        products.map((item, index) => (
          <ProductCard key={item.id || index} product={item} />
        ))}

      {shouldShowNotFound && <p className="grid-status">Ничего не найдено</p>}
      {hasMore && <div ref={loadMoreRef} className="grid-load-more" />}
      {isLoadingMore && (
        <div className="grid-loading-more" aria-live="polite">
          <span className="grid-spinner" aria-hidden="true" />
          <span className="grid-loading-text">Догружаем товары...</span>
        </div>
      )}
    </div>
  );
}

export default ProductGrid;
