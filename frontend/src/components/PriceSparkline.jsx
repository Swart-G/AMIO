import React from 'react';

const RANGE_PADDING_RATIO = 0.15;
const MIN_RANGE_RATIO = 0.04;
const MIN_RANGE_ABSOLUTE = 100;

function getDisplayBounds(values) {
  const numericValues = values.filter((value) => Number.isFinite(value));
  if (numericValues.length < 2) return null;

  const min = Math.min(...numericValues);
  const max = Math.max(...numericValues);
  const avg = numericValues.reduce((sum, value) => sum + value, 0) / numericValues.length;
  const naturalRange = Math.max(max - min, 0);
  const minVisualRange = Math.max(Math.round(Math.abs(avg) * MIN_RANGE_RATIO), MIN_RANGE_ABSOLUTE);
  const targetRange = Math.max(naturalRange, minVisualRange);
  const padding = Math.max(targetRange * RANGE_PADDING_RATIO, minVisualRange * 0.25);
  const center = naturalRange === 0 ? avg : (min + max) / 2;
  const halfRange = targetRange / 2 + padding;

  return {
    min: center - halfRange,
    max: center + halfRange,
  };
}

function toPath(values, width, height, padding) {
  const innerW = width - padding * 2;
  const innerH = height - padding * 2;
  const valid = values
    .map((value, index) => ({ value, index }))
    .filter((point) => Number.isFinite(point.value));

  if (valid.length === 0) return '';
  if (valid.length === 1) {
    const y = padding + innerH / 2;
    return `M ${padding} ${y} L ${width - padding} ${y}`;
  }

  const bounds = getDisplayBounds(valid.map((point) => point.value));
  if (!bounds) {
    const y = padding + innerH / 2;
    return `M ${padding} ${y} L ${width - padding} ${y}`;
  }

  const range = Math.max(bounds.max - bounds.min, 1);

  let path = '';
  let started = false;

  values.forEach((value, index) => {
    if (!Number.isFinite(value)) {
      started = false;
      return;
    }
    const x = padding + (index / Math.max(values.length - 1, 1)) * innerW;
    const normalizedValue = Math.min(Math.max(value, bounds.min), bounds.max);
    const y = padding + innerH - ((normalizedValue - bounds.min) / range) * innerH;
    path += `${started ? ' L' : 'M'} ${x} ${y}`;
    started = true;
  });

  return path.trim();
}

function getColor(trendPercent) {
  if (!Number.isFinite(trendPercent)) return '#64748b';
  if (trendPercent > 0) return '#dc2626';
  if (trendPercent < 0) return '#059669';
  return '#475569';
}

function PriceSparkline({ values = [], trendPercent = null, width = 144, height = 36 }) {
  const color = getColor(trendPercent);
  const normalized = Array.isArray(values)
    ? values.map((value) => (Number.isFinite(value) ? Number(value) : null))
    : [];
  const path = toPath(normalized, width, height, 4);
  const hasAnyValue = normalized.some((value) => Number.isFinite(value));

  return (
    <svg
      className="price-sparkline"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
    >
      <rect x="0.5" y="0.5" width={width - 1} height={height - 1} rx="9" className="price-sparkline-bg" />
      {hasAnyValue ? (
        <path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      ) : (
        <line
          x1="10"
          y1={height / 2}
          x2={width - 10}
          y2={height / 2}
          stroke="#cbd5e1"
          strokeWidth="1.75"
          strokeLinecap="round"
        />
      )}
    </svg>
  );
}

export default PriceSparkline;
