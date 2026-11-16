// 가격 차트: 캔들 + 이동평균 + 거래량 + 지지/저항선 + 확률 fan.
import { FanPrimitive } from './fan-primitive.js';

const LWC = window.LightweightCharts;
const STEP = { '1h': 3600, '4h': 14400, '1d': 86400 };
const QK = ['p2_5', 'p10', 'p25', 'p50', 'p75', 'p90', 'p97_5'];

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const alpha = (hex, a) => {
  const m = hex.replace('#', '');
  const n = parseInt(m.length === 3 ? m.split('').map((c) => c + c).join('') : m, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
};
const pad = (n) => String(n).padStart(2, '0');

export class PriceChart {
  constructor(el, legendEl) {
    this.el = el;
    this.legend = legendEl;
    this.chart = LWC.createChart(el, {
      autoSize: true,
      layout: { fontSize: 11, attributionLogo: true },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.08, bottom: 0.2 } },
      timeScale: {
        borderVisible: false, rightOffset: 4, timeVisible: true, secondsVisible: false,
        tickMarkFormatter: (t, type) => {
          const d = new Date(t * 1000);
          if (type === 0) return String(d.getFullYear());
          if (type === 1) return `${d.getMonth() + 1}월`;
          if (type === 2) return `${d.getMonth() + 1}/${d.getDate()}`;
          return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
        },
      },
      localization: {
        locale: 'ko-KR',
        timeFormatter: (t) => {
          const d = new Date(t * 1000);
          return `${d.getFullYear()}.${d.getMonth() + 1}.${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
        },
      },
      crosshair: { mode: LWC.CrosshairMode.Normal },
      // 세로로 미는 동작은 페이지 스크롤에 양보
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: false },
      handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
      kineticScroll: { touch: true, mouse: false },
    });
    this.candles = this.chart.addSeries(LWC.CandlestickSeries, { priceLineVisible: false });
    this.vol = this.chart.addSeries(LWC.HistogramSeries, {
      priceScaleId: 'vol', priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false,
    });
    this.chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
    const line = (w) => ({ lineWidth: w, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false });
    this.ma = { sma20: this.chart.addSeries(LWC.LineSeries, line(1)), sma50: this.chart.addSeries(LWC.LineSeries, line(1)),
      sma200: this.chart.addSeries(LWC.LineSeries, line(2)) };
    this.fan = new FanPrimitive();
    this.candles.attachPrimitive(this.fan);
    this.priceLines = [];
    this.fanPoints = [];
    this.data = null;
    this.chart.subscribeCrosshairMove((p) => this._onCrosshair(p));
    this.applyTheme();
  }

  applyTheme() {
    const c = { bg: css('--surface'), text: css('--text-2'), line: css('--line'), up: css('--up'), down: css('--down'),
      ma20: css('--ma20'), ma50: css('--ma50'), ma200: css('--ma200'), accent: css('--accent'), fan: css('--fan') };
    this.colors = c;
    this.chart.applyOptions({
      layout: { background: { type: 'solid', color: c.bg }, textColor: c.text },
      grid: { vertLines: { color: alpha(c.line, 0.5) }, horzLines: { color: alpha(c.line, 0.5) } },
      crosshair: { vertLine: { labelBackgroundColor: c.accent }, horzLine: { labelBackgroundColor: c.accent } },
    });
    this.candles.applyOptions({ upColor: c.up, downColor: c.down, borderUpColor: c.up, borderDownColor: c.down, wickUpColor: c.up, wickDownColor: c.down });
    this.ma.sma20.applyOptions({ color: c.ma20 });
    this.ma.sma50.applyOptions({ color: c.ma50 });
    this.ma.sma200.applyOptions({ color: c.ma200 });
    if (this.data) this._setVolume();
    this.fan.setData(this.fanPoints, c.fan.replace(/\s/g, ''), c.accent);
    this._drawLevels();
  }

  /**
   * @param {object} o {candles, tf, horizon, pathDaily, originPrice, levels, precision}
   */
  setData(o) {
    const first = !this.data || this.data.key !== `${o.asset}-${o.tf}`;
    const prevHorizon = this.data?.lastHorizon;
    this.data = { ...o, key: `${o.asset}-${o.tf}` };
    const k = o.candles;
    const step = STEP[o.tf];
    const n = k.t.length;
    const lastT = k.t[n - 1];
    const bars = [];
    for (let i = 0; i < n; i++) bars.push({ time: k.t[i], open: k.o[i], high: k.h[i], low: k.l[i], close: k.c[i] });
    // 미래 구간 빈칸(whitespace): 예측 기간 + 여유 10%
    const futureBars = Math.ceil((o.horizon * 86400 * 1.1) / step);
    for (let j = 1; j <= futureBars; j++) bars.push({ time: lastT + j * step });
    const prec = o.precision;
    this.candles.applyOptions({ priceFormat: { type: 'price', precision: prec, minMove: prec ? 0.01 : 1 } });
    this.candles.setData(bars);
    for (const key of ['sma20', 'sma50', 'sma200']) {
      const arr = [];
      for (let i = 0; i < n; i++) if (k[key][i] !== null) arr.push({ time: k.t[i], value: k[key][i] });
      this.ma[key].setData(arr);
    }
    this._setVolume();

    // fan: 출발점(마지막 봉) + d일 뒤 분위수
    const pts = [{ time: lastT, ...Object.fromEntries(QK.map((q) => [q, o.originPrice])) }];
    for (const row of o.pathDaily) {
      if (row.day > o.horizon) break;
      const t = lastT + row.day * 86400;
      pts.push({ time: t - (t - lastT) % step, ...Object.fromEntries(QK.map((q) => [q, row[q]])) });
    }
    this.fanPoints = pts;
    this.fan.setData(pts, this.colors.fan.replace(/\s/g, ''), this.colors.accent);
    this._drawLevels();

    // 처음 보거나 봉/자산이 바뀌면 보기 범위 재설정: 과거 일부 + 예측 전체
    if (first || prevHorizon !== o.horizon) {
      const fut = Math.ceil((o.horizon * 86400) / step);
      const hist = Math.min(n - 1, Math.max(Math.round(fut * 1.4), 60));
      this.chart.timeScale().setVisibleLogicalRange({ from: n - 1 - hist, to: n - 1 + fut + 3 });
    }
    this.data.lastHorizon = o.horizon;
    this._showLegendDefault();
  }

  _setVolume() {
    const k = this.data.candles;
    const up = alpha(this.colors.up, 0.35), dn = alpha(this.colors.down, 0.35);
    const arr = [];
    for (let i = 0; i < k.t.length; i++) arr.push({ time: k.t[i], value: k.v[i], color: k.c[i] >= k.o[i] ? up : dn });
    this.vol.setData(arr);
  }

  _drawLevels() {
    for (const pl of this.priceLines) this.candles.removePriceLine(pl);
    this.priceLines = [];
    if (!this.data) return;
    for (const lv of this.data.levels || []) {
      const sup = lv.type === 'support';
      this.priceLines.push(this.candles.createPriceLine({
        price: lv.price, color: alpha(sup ? this.colors.down : this.colors.up, 0.75), lineWidth: 1,
        lineStyle: LWC.LineStyle.Dashed, axisLabelVisible: true, title: sup ? '지지' : '저항',
      }));
    }
  }

  _fmt(v) { return v == null ? '—' : v.toLocaleString('en-US', { maximumFractionDigits: this.data.precision, minimumFractionDigits: this.data.precision }); }

  _showLegendDefault() {
    this.legend.innerHTML = '';
  }

  _onCrosshair(p) {
    if (!this.data || !p || p.time === undefined || !p.point) return this._showLegendDefault();
    const t = p.time;
    const pts = this.fanPoints;
    if (pts.length > 1 && t > pts[0].time) {
      // 예측 구간: 앞뒤 지점 선형 보간
      let i = pts.findIndex((q) => q.time >= t);
      if (i === -1) return this._showLegendDefault();
      const b = pts[i], a = pts[Math.max(0, i - 1)];
      const w = b.time === a.time ? 1 : (t - a.time) / (b.time - a.time);
      const v = (k) => a[k] + (b[k] - a[k]) * w;
      const days = (t - pts[0].time) / 86400;
      const d = new Date(t * 1000);
      this.legend.innerHTML =
        `<b>${days < 1 ? `${Math.round(days * 24)}시간` : `${days.toFixed(days < 3 ? 1 : 0)}일`} 뒤</b> · ${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}시<br>` +
        `중앙값 <b>${this._fmt(v('p50'))}</b><br>50% ${this._fmt(v('p25'))} ~ ${this._fmt(v('p75'))}<br>` +
        `80% ${this._fmt(v('p10'))} ~ ${this._fmt(v('p90'))}<br>95% ${this._fmt(v('p2_5'))} ~ ${this._fmt(v('p97_5'))}`;
      return;
    }
    const bar = p.seriesData.get(this.candles);
    if (!bar || bar.open === undefined) return this._showLegendDefault();
    const chg = (bar.close / bar.open - 1) * 100;
    const cls = chg >= 0 ? 'up' : 'down';
    this.legend.innerHTML = `시 ${this._fmt(bar.open)} 고 ${this._fmt(bar.high)}<br>저 ${this._fmt(bar.low)} 종 <span class="${cls}">${this._fmt(bar.close)} (${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%)</span>`;
  }
}
