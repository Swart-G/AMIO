import React, { useEffect, useRef, useState } from 'react';
import ProductCard from './ProductCard';
import './ProductGrid.css';

const SKELETON_COUNT = 8;
const PAGE_SIZE = 24;
const LOAD_MORE_SKELETON_COUNT = 4;

function extractProductsList(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.items)) return data.items;
  if (Array.isArray(data?.data)) return data.data;
  if (Array.isArray(data?.products)) return data.products;
  return [];
}

function mergeUniqueProducts(prev, next) {
  const merged = [...prev];
  const seen = new Set(
    prev
      .map((item) => item?.url || item?.id || item?.product_url)
      .filter(Boolean)
  );

  next.forEach((item) => {
    const key = item?.url || item?.id || item?.product_url;
    if (!key || seen.has(key)) return;
    seen.add(key);
    merged.push(item);
  });

  return merged;
}

function ProductGrid({ searchQuery }) {
  const [products, setProducts] = useState([]);
  const [isLoadingInitial, setIsLoadingInitial] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);

  const loadMoreRef = useRef(null);
  const requestSeqRef = useRef(0);
  const query = (searchQuery || '').trim();

  useEffect(() => {
    const controller = new AbortController();
    const seq = requestSeqRef.current + 1;
    requestSeqRef.current = seq;

    if (!query) {
      setProducts([]);
      setIsLoadingInitial(false);
      setIsLoadingMore(false);
      setHasMore(false);
      setOffset(0);
      return () => controller.abort();
    }

    const fetchInitial = async () => {
      setProducts([]);
      setOffset(0);
      setHasMore(false);
      setIsLoadingMore(false);
      setIsLoadingInitial(true);

      try {
        const url = `/api/products?q=${encodeURIComponent(query)}&limit=${PAGE_SIZE}&offset=0`;
        const response = await fetch(url, { signal: controller.signal });

        if (!response.ok) {
          throw new Error(`Ошибка сети: ${response.status}`);
        }

        const data = await response.json();
        if (requestSeqRef.current !== seq) return;

        const productsList = extractProductsList(data);
        setProducts(productsList);

        const loadedCount = productsList.length;
        setOffset(loadedCount);

        const hasMoreFlag = typeof data?.has_more === 'boolean'
          ? data.has_more
          : loadedCount === PAGE_SIZE;
        setHasMore(hasMoreFlag);
      } catch (error) {
        if (error.name === 'AbortError') return;
        console.error('Ошибка загрузки:', error);
        if (requestSeqRef.current !== seq) return;
        setProducts([]);
        setHasMore(false);
        setOffset(0);
      } finally {
        if (!controller.signal.aborted && requestSeqRef.current === seq) {
          setIsLoadingInitial(false);
        }
      }
    };

    fetchInitial();
    return () => controller.abort();
  }, [query]);

  useEffect(() => {
    if (!query || !hasMore || isLoadingInitial || isLoadingMore) return;
    if (typeof IntersectionObserver === 'undefined') return;

    const target = loadMoreRef.current;
    if (!target) return;

    const observer = new IntersectionObserver(
      async (entries) => {
        const entry = entries[0];
        if (!entry?.isIntersecting) return;
        if (isLoadingInitial || isLoadingMore || !hasMore) return;

        setIsLoadingMore(true);
        const seq = requestSeqRef.current;

        try {
          const nextOffset = offset;
          const url = `/api/products?q=${encodeURIComponent(query)}&limit=${PAGE_SIZE}&offset=${nextOffset}`;
          const response = await fetch(url);

          if (!response.ok) {
            throw new Error(`Ошибка сети: ${response.status}`);
          }

          const data = await response.json();
          if (requestSeqRef.current !== seq) return;

          const productsList = extractProductsList(data);
          setProducts((prev) => mergeUniqueProducts(prev, productsList));

          const hasMoreFlag = typeof data?.has_more === 'boolean'
            ? data.has_more
            : productsList.length === PAGE_SIZE;
          setHasMore(hasMoreFlag);
          setOffset((prev) => prev + productsList.length);
        } catch (error) {
          console.error('Ошибка загрузки:', error);
        } finally {
          if (requestSeqRef.current === seq) {
            setIsLoadingMore(false);
          }
        }
      },
      { rootMargin: '220px' }
    );

    observer.observe(target);
    return () => observer.disconnect();
  }, [query, hasMore, isLoadingInitial, isLoadingMore, offset]);

  const shouldShowNotFound = !isLoadingInitial && products.length === 0 && query !== '';
  const showLoadMoreSkeletons = !isLoadingInitial && isLoadingMore;

  return (
    <div className="product-grid-container" aria-busy={isLoadingInitial || isLoadingMore}>
      {!query && (
        <p className="empty-hint">
          Начните с запроса — например, «наушники», «кофеварка» или «кроссовки».
        </p>
      )}

      {(isLoadingInitial || isLoadingMore) && (
        <span className="sr-only" role="status" aria-live="polite">
          Загрузка товаров...
        </span>
      )}

      {isLoadingInitial && Array.from({ length: SKELETON_COUNT }).map((_, index) => (
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

      {!isLoadingInitial && products.length > 0 &&
        products.map((item, index) => (
          <ProductCard key={item.url || item.id || `${item.name}-${index}`} product={item} />
        ))}

      {shouldShowNotFound && (
        <p className="grid-status" role="status" aria-live="polite">
          Ничего не найдено
        </p>
      )}

      {hasMore && <div ref={loadMoreRef} className="grid-load-more" aria-hidden="true" />}
      {showLoadMoreSkeletons && Array.from({ length: LOAD_MORE_SKELETON_COUNT }).map((_, index) => (
        <div className="product-card-skeleton" key={`load-more-skeleton-${index}`} aria-hidden="true">
          <div className="skeleton-image" />
          <div className="skeleton-content">
            <div className="skeleton-line skeleton-line-price" />
            <div className="skeleton-line" />
            <div className="skeleton-line skeleton-line-short" />
            <div className="skeleton-line skeleton-line-market" />
          </div>
        </div>
      ))}
      {showLoadMoreSkeletons && <p className="grid-loading-more">Догружаем товары...</p>}
    </div>
  );
}

export default ProductGrid;
