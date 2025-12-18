import React, { useEffect, useState } from 'react';
import ProductCard from './ProductCard';
import './ProductGrid.css';

function ProductGrid({ searchQuery }) {
  const [products, setProducts] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const query = (searchQuery || '').trim();

  useEffect(() => {
    if (!query) {
      setProducts([]);
      setIsLoading(false);
      return;
    }

    const fetchProducts = async () => {
      setIsLoading(true);

      try {
        const url = `/api/products?q=${encodeURIComponent(query)}`;
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

        setProducts(productsList);
      } catch (error) {
        console.error('Ошибка загрузки:', error);
        setProducts([]);
      } finally {
        setIsLoading(false);
      }
    };

    fetchProducts();
  }, [query]);

  const shouldShowNotFound = !isLoading && products.length === 0 && query !== '';

  return (
    <div className="product-grid-container">
      {!query && (
        <p className="empty-hint">
          Начните с запроса — например, «наушники», «кофеварка» или «кроссовки».
        </p>
      )}

      {isLoading && <p className="grid-status">Загрузка товаров...</p>}

      {!isLoading && products.length > 0 &&
        products.map((item, index) => (
          <ProductCard key={item.id || index} product={item} />
        ))}

      {shouldShowNotFound && <p className="grid-status">Ничего не найдено</p>}
    </div>
  );
}

export default ProductGrid;
