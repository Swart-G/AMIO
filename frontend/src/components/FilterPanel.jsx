import React from 'react';
import './FilterPanel.css';

function FilterPanel() {
  return (
    <div className="filter-panel-container">
      <h2>Фильтры</h2>

      <div className="filter-group">
        <h4>Сортировка</h4>
        <select className="filter-select">
          <option value="price_asc">Цена: по возрастанию</option>
          <option value="price_desc">Цена: по убыванию</option>
          <option value="newest">Сначала новинки</option>
        </select>
      </div>

      <div className="filter-group">
        <h4>Категории</h4>
        <label><input type="checkbox" /> Электроника</label>
        <label><input type="checkbox" /> Одежда</label>
        <label><input type="checkbox" /> Обувь</label>
      </div>

      <button className="filter-reset-button" type="button">
        Сбросить фильтры
      </button>
    </div>
  );
}

export default FilterPanel;
