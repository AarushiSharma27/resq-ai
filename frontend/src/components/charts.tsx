// Shared recharts styling: recessive grid/axes, dark tooltip, text in ink tokens (never series colour).
export const AXIS_TICK = { fill: '#94a3b8', fontSize: 11 };
export const AXIS_LINE = { stroke: '#26345a' };
export const GRID_STROKE = '#1b2744';
export const TOOLTIP_STYLE = {
  contentStyle: { background: '#0a1020', border: '1px solid #26345a', borderRadius: 8, fontSize: 12, color: '#e2e8f0' },
  labelStyle: { color: '#e2e8f0', fontWeight: 600 },
  itemStyle: { color: '#cbd5e1' },
  cursor: { fill: 'rgba(148,163,184,0.08)' },
};
export const LEGEND_STYLE = { wrapperStyle: { fontSize: 12, color: '#cbd5e1' } };
/** 4px rounded data-end on vertical bars. */
export const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0];
/** 4px rounded data-end on horizontal bars. */
export const HBAR_RADIUS: [number, number, number, number] = [0, 4, 4, 0];
