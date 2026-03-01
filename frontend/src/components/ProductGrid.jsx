import React, { useEffect, useMemo, useRef, useState } from 'react';
import ProductCard from './ProductCard';
import './ProductGrid.css';

const SKELETON_COUNT = 8;
const PAGE_SIZE = 24;
const LOAD_MORE_SKELETON_COUNT = 4;
const HOMEPAGE_CACHE_KEY = 'homepage';
const SORT_TYPE_DEFAULT = 'default';
const SORT_TYPE_PRICE = 'price';
const SORT_TYPE_RATING = 'rating';
const SORT_TYPE_REVIEWS = 'reviews';
const SORT_DIRECTION_ASC = 'asc';
const SORT_DIRECTION_DESC = 'desc';
const SORT_TYPE_OPTIONS = [
  { value: SORT_TYPE_DEFAULT, label: 'По релевантности' },
  { value: SORT_TYPE_PRICE, label: 'Цена' },
  { value: SORT_TYPE_RATING, label: 'Рейтинг' },
  { value: SORT_TYPE_REVIEWS, label: 'Отзывы' },
];
const SORT_DIRECTION_OPTIONS = [
  { value: SORT_DIRECTION_ASC, label: 'По возрастанию' },
  { value: SORT_DIRECTION_DESC, label: 'По убыванию' },
];

function getProductsCacheKey(query) {
  return query ? `search:${query.toLowerCase()}` : HOMEPAGE_CACHE_KEY;
}

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

function parsePrice(value) {
  const normalized = String(value ?? '').replace(/\D/g, '');
  if (!normalized) return Number.POSITIVE_INFINITY;
  const parsed = Number.parseInt(normalized, 10);
  return Number.isFinite(parsed) ? parsed : Number.POSITIVE_INFINITY;
}

function parseRating(value) {
  const normalized = String(value ?? '').replace(',', '.').trim();
  if (!normalized) return Number.NEGATIVE_INFINITY;
  const parsed = Number.parseFloat(normalized);
  return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
}

function parseReviews(value) {
  const normalized = String(value ?? '').replace(/\D/g, '');
  if (!normalized) return Number.NEGATIVE_INFINITY;
  const parsed = Number.parseInt(normalized, 10);
  return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
}

function ProductGrid({ searchQuery, onAuthOpen }) {
  const [products, setProducts] = useState([]);
  const [sortType, setSortType] = useState(SORT_TYPE_DEFAULT);
  const [sortDirection, setSortDirection] = useState(SORT_DIRECTION_DESC);
  const [isSortMenuOpen, setIsSortMenuOpen] = useState(false);
  const [isLoadingInitial, setIsLoadingInitial] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);

  const sortMenuRef = useRef(null);
  const requestSeqRef = useRef(0);
  const productsCacheRef = useRef(new Map());
  const loadMoreInFlightRef = useRef(false);
  const query = (searchQuery || '').trim();
  const isSearchMode = query !== '';
  const activeSortType = useMemo(
    () => SORT_TYPE_OPTIONS.find((option) => option.value === sortType) || SORT_TYPE_OPTIONS[0],
    [sortType]
  );
  const activeSortDirection = useMemo(
    () =>
      SORT_DIRECTION_OPTIONS.find((option) => option.value === sortDirection) ||
      SORT_DIRECTION_OPTIONS[1],
    [sortDirection]
  );
  const sortTriggerLabel = sortType === SORT_TYPE_DEFAULT
    ? activeSortType.label
    : `${activeSortType.label}: ${activeSortDirection.label}`;

  useEffect(() => {
    if (!isSearchMode && sortType !== SORT_TYPE_DEFAULT) {
      setSortType(SORT_TYPE_DEFAULT);
    }
    if (!isSearchMode && sortDirection !== SORT_DIRECTION_DESC) {
      setSortDirection(SORT_DIRECTION_DESC);
    }
    if (!isSearchMode && isSortMenuOpen) {
      setIsSortMenuOpen(false);
    }
  }, [isSearchMode, sortType, sortDirection, isSortMenuOpen]);

  useEffect(() => {
    if (!isSortMenuOpen) return undefined;

    const handlePointerDown = (event) => {
      if (!sortMenuRef.current?.contains(event.target)) {
        setIsSortMenuOpen(false);
      }
    };

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setIsSortMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isSortMenuOpen]);

  useEffect(() => {
    const controller = new AbortController();
    const seq = requestSeqRef.current + 1;
    requestSeqRef.current = seq;
    const cacheKey = getProductsCacheKey(query);
    const cachedState = productsCacheRef.current.get(cacheKey);

    if (cachedState) {
      loadMoreInFlightRef.current = false;
      setProducts(cachedState.products);
      setOffset(cachedState.offset);
      setHasMore(cachedState.hasMore);
      setIsLoadingMore(false);
      setIsLoadingInitial(false);
      return () => controller.abort();
    }

    if (!query) {
      const fetchHomepage = async () => {
        loadMoreInFlightRef.current = false;
        setProducts([]);
        setOffset(0);
        setHasMore(false);
        setIsLoadingMore(false);
        setIsLoadingInitial(true);

        try {
          const response = await fetch(`/api/homepage-products?limit=${PAGE_SIZE}&offset=0`, {
            signal: controller.signal,
          });
          if (!response.ok) {
            throw new Error(`Ошибка сети: ${response.status}`);
          }

          const data = await response.json();
          if (requestSeqRef.current !== seq) return;

          const productsList = extractProductsList(data);
          const loadedCount = productsList.length;
          const hasMoreFlag = Boolean(data?.has_more);
          setProducts(productsList);
          setOffset(loadedCount);
          setHasMore(hasMoreFlag);
          productsCacheRef.current.set(cacheKey, {
            products: productsList,
            offset: loadedCount,
            hasMore: hasMoreFlag,
          });
        } catch (error) {
          if (error.name === 'AbortError') return;
          console.error('Ошибка загрузки главной страницы:', error);
          if (requestSeqRef.current !== seq) return;
          setProducts([]);
          setOffset(0);
          setHasMore(false);
        } finally {
          if (!controller.signal.aborted && requestSeqRef.current === seq) {
            setIsLoadingInitial(false);
          }
        }
      };

      fetchHomepage();
      return () => controller.abort();
    }

    const fetchInitial = async () => {
      loadMoreInFlightRef.current = false;
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
        const hasMoreFlag = typeof data?.has_more === 'boolean'
          ? data.has_more
          : loadedCount === PAGE_SIZE;
        setOffset(loadedCount);
        setHasMore(hasMoreFlag);
        productsCacheRef.current.set(cacheKey, {
          products: productsList,
          offset: loadedCount,
          hasMore: hasMoreFlag,
        });
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
    if (!hasMore || isLoadingInitial || loadMoreInFlightRef.current) return undefined;

    const controller = new AbortController();
    let cancelled = false;
    const seq = requestSeqRef.current;
    const requestOffset = offset;

    const fetchNextPage = async () => {
      loadMoreInFlightRef.current = true;
      setIsLoadingMore(true);

      try {
        const url = query
          ? `/api/products?q=${encodeURIComponent(query)}&limit=${PAGE_SIZE}&offset=${requestOffset}`
          : `/api/homepage-products?limit=${PAGE_SIZE}&offset=${requestOffset}`;
        const response = await fetch(url, { signal: controller.signal });

        if (!response.ok) {
          throw new Error(`Ошибка сети: ${response.status}`);
        }

        const data = await response.json();
        if (cancelled || requestSeqRef.current !== seq) return;

        const productsList = extractProductsList(data);
        const hasMoreFlag = typeof data?.has_more === 'boolean'
          ? data.has_more
          : productsList.length === PAGE_SIZE;
        const nextOffset = requestOffset + productsList.length;
        const cacheKey = getProductsCacheKey(query);

        setProducts((prev) => {
          const mergedProducts = mergeUniqueProducts(prev, productsList);
          productsCacheRef.current.set(cacheKey, {
            products: mergedProducts,
            offset: nextOffset,
            hasMore: hasMoreFlag,
          });
          return mergedProducts;
        });
        setHasMore(hasMoreFlag);
        setOffset(nextOffset);
      } catch (error) {
        if (error.name === 'AbortError') return;
        console.error('Ошибка загрузки:', error);
        if (!cancelled && requestSeqRef.current === seq) {
          setHasMore(false);
        }
      } finally {
        if (!cancelled) {
          loadMoreInFlightRef.current = false;
        }
        if (!cancelled && requestSeqRef.current === seq) {
          setIsLoadingMore(false);
        }
      }
    };

    fetchNextPage();

    return () => {
      cancelled = true;
      loadMoreInFlightRef.current = false;
      controller.abort();
    };
  }, [query, hasMore, isLoadingInitial, offset]);

  const displayedProducts = useMemo(() => {
    if (!isSearchMode || sortType === SORT_TYPE_DEFAULT) {
      return products;
    }

    const sorted = [...products];
    const sortSign = sortDirection === SORT_DIRECTION_ASC ? 1 : -1;
    if (sortType === SORT_TYPE_PRICE) {
      sorted.sort((a, b) => sortSign * (parsePrice(a?.price) - parsePrice(b?.price)));
      return sorted;
    }
    if (sortType === SORT_TYPE_RATING) {
      sorted.sort((a, b) => sortSign * (parseRating(a?.rating) - parseRating(b?.rating)));
      return sorted;
    }
    if (sortType === SORT_TYPE_REVIEWS) {
      sorted.sort((a, b) => sortSign * (parseReviews(a?.reviews) - parseReviews(b?.reviews)));
      return sorted;
    }

    return products;
  }, [isSearchMode, products, sortType, sortDirection]);

  const shouldShowNotFound = !isLoadingInitial && products.length === 0 && query !== '';
  const shouldShowHomepageEmpty = !isLoadingInitial && products.length === 0 && query === '';
  const showLoadMoreSkeletons = !isLoadingInitial && isLoadingMore;

  return (
    <div className="product-grid-container" aria-busy={isLoadingInitial || isLoadingMore}>
      {isSearchMode && (
        <div className="search-sort-shell">
          <div className="search-sort-dropdown-wrap" ref={sortMenuRef}>
            <button
              type="button"
              className={`search-sort-trigger ${isSortMenuOpen ? 'is-open' : ''}`}
              aria-haspopup="radiogroup"
              aria-expanded={isSortMenuOpen}
              aria-label="Открыть меню сортировки"
              onClick={() => setIsSortMenuOpen((prev) => !prev)}
            >
              <span className="search-sort-trigger-icon" aria-hidden="true">
                <svg viewBox="0 0 20 20" fill="none">
                  <path d="M4 6h12M6.5 10h7M8.5 14h3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <span className="search-sort-trigger-label">{sortTriggerLabel}</span>
              <span className="search-sort-trigger-caret" aria-hidden="true" />
            </button>

            {isSortMenuOpen && (
              <div className="search-sort-dropdown" aria-label="Варианты сортировки">
                <div className="search-sort-group" role="radiogroup" aria-label="Тип сортировки">
                  {SORT_TYPE_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      role="radio"
                      aria-checked={sortType === option.value}
                      className={`search-sort-option ${sortType === option.value ? 'is-active' : ''}`}
                      onClick={() => setSortType(option.value)}
                    >
                      <span>{option.label}</span>
                      {sortType === option.value && <span className="search-sort-option-check">✓</span>}
                    </button>
                  ))}
                </div>

                <div className="search-sort-separator" aria-hidden="true" />
                <div className="search-sort-group" role="radiogroup" aria-label="Направление сортировки">
                  {SORT_DIRECTION_OPTIONS.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      role="radio"
                      aria-checked={sortDirection === option.value}
                      className={`search-sort-option ${sortDirection === option.value ? 'is-active' : ''}`}
                      onClick={() => setSortDirection(option.value)}
                      disabled={sortType === SORT_TYPE_DEFAULT}
                    >
                      <span>{option.label}</span>
                      {sortDirection === option.value && (
                        <span className="search-sort-option-check">✓</span>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
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

      {!isLoadingInitial && displayedProducts.length > 0 &&
        displayedProducts.map((item, index) => (
          <ProductCard
            key={item.url || item.id || `${item.name}-${index}`}
            product={item}
            onAuthOpen={onAuthOpen}
          />
        ))}

      {shouldShowNotFound && (
        <p className="grid-status" role="status" aria-live="polite">
          Ничего не найдено
        </p>
      )}
      {shouldShowHomepageEmpty && (
        <p className="empty-hint" role="status" aria-live="polite">
          Не удалось получить товары. Попробуйте обновить страницу.
        </p>
      )}

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
