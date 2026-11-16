// 확률 전개(fan) 음영을 그리는 lightweight-charts v5 시리즈 프리미티브.
// points: [{time, p2_5, p10, p25, p50, p75, p90, p97_5}, ...]  (time = UNIX 초, 차트에 존재하는 시각)
const BANDS = [
  ['p2_5', 'p97_5', 0.14],
  ['p10', 'p90', 0.26],
  ['p25', 'p75', 0.42],
];

class FanRenderer {
  constructor(view) { this._v = view; }
  draw(target) {
    const { xs, ys, rgb, median } = this._v;
    if (!xs.length) return;
    target.useBitmapCoordinateSpace(({ context: ctx, horizontalPixelRatio: hr, verticalPixelRatio: vr }) => {
      for (const [lo, hi, a] of BANDS) {
        ctx.beginPath();
        xs.forEach((x, i) => (i ? ctx.lineTo(x * hr, ys[hi][i] * vr) : ctx.moveTo(x * hr, ys[hi][i] * vr)));
        for (let i = xs.length - 1; i >= 0; i--) ctx.lineTo(xs[i] * hr, ys[lo][i] * vr);
        ctx.closePath();
        ctx.fillStyle = `rgba(${rgb}, ${a})`;
        ctx.fill();
      }
      ctx.beginPath();
      xs.forEach((x, i) => (i ? ctx.lineTo(x * hr, ys.p50[i] * vr) : ctx.moveTo(x * hr, ys.p50[i] * vr)));
      ctx.strokeStyle = median;
      ctx.lineWidth = 2 * hr;
      ctx.setLineDash([6 * hr, 4 * hr]);
      ctx.stroke();
      ctx.setLineDash([]);
    });
  }
}

class FanPaneView {
  constructor(src) { this._src = src; this.xs = []; this.ys = {}; this.rgb = '124,92,255'; this.median = '#7c5cff'; }
  update() {
    const s = this._src;
    this.xs = []; this.ys = {};
    if (!s._chart || !s._points.length) return;
    const ts = s._chart.timeScale();
    const keys = ['p2_5', 'p10', 'p25', 'p50', 'p75', 'p90', 'p97_5'];
    keys.forEach((k) => (this.ys[k] = []));
    for (const p of s._points) {
      const x = ts.timeToCoordinate(p.time);
      if (x === null) continue;
      const row = keys.map((k) => s._series.priceToCoordinate(p[k]));
      if (row.some((y) => y === null)) continue;
      this.xs.push(x);
      keys.forEach((k, i) => this.ys[k].push(row[i]));
    }
    this.rgb = s._rgb; this.median = s._median;
  }
  zOrder() { return 'bottom'; }
  renderer() { return new FanRenderer(this); }
}

export class FanPrimitive {
  constructor() { this._points = []; this._rgb = '124,92,255'; this._median = '#7c5cff'; this._view = new FanPaneView(this); }
  attached({ chart, series, requestUpdate }) { this._chart = chart; this._series = series; this._req = requestUpdate; }
  detached() { this._chart = null; this._series = null; }
  setData(points, rgb, median) { this._points = points || []; if (rgb) this._rgb = rgb; if (median) this._median = median; this._req?.(); }
  updateAllViews() { this._view.update(); }
  paneViews() { return [this._view]; }
  // 자동 축척에 예측 범위를 포함
  // 자동 축척: 화면에 보이는 예측 구간만 포함(과거만 볼 땐 캔들 기준 축척 유지)
  autoscaleInfo() {
    if (!this._points.length || !this._chart) return null;
    const vr = this._chart.timeScale().getVisibleRange();
    if (!vr || vr.to < this._points[0].time) return null;
    let lo = Infinity, hi = -Infinity;
    for (const p of this._points) {
      if (p.time < vr.from || p.time > vr.to) continue;
      lo = Math.min(lo, p.p2_5); hi = Math.max(hi, p.p97_5);
    }
    return lo < hi ? { priceRange: { minValue: lo, maxValue: hi } } : null;
  }
}
