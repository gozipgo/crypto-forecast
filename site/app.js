// 화면: data/*.json 을 읽어서 그리기만 한다(계산 없음).
import { PriceChart } from './chart.js';

const SUPPORTED_MAJOR = 1;
const $ = (id) => document.getElementById(id);
const state = { asset: 'BTC', tf: '4h', horizon: 14, model: 'ensemble', hLong: { '1w': 365, '1M': 1826 }, scen: 'ta0', variant: 'shrunk' };
// 경로 선택: ta0/ta1 = 차트 기술적 시나리오(주/대안), st0/st1 = 통계 묶음 1·2번(주봉·월봉), off = 음영만
const SCENS = ['ta0', 'ta1', 'st0', 'st1', 'off'];
const OLD_SCEN = { 0: 'st0', 1: 'st1', '-1': 'off' };
const cache = new Map();
let manifest = null;
let chart = null;

try { Object.assign(state, JSON.parse(localStorage.getItem('view') || '{}')); } catch (e) { /* 저장소 사용 불가 */ }
state.horizon = Number(state.horizon) || 14;
state.hLong = { '1w': 365, '1M': 1826, ...(state.hLong || {}) };
if (!SCENS.includes(state.scen)) state.scen = 'ta0';
if (!['shrunk', 'zero', 'historical'].includes(state.variant)) state.variant = 'shrunk';
// 주소로 보기 지정(공유·테스트용): ?asset=ETH&tf=1M&h=1826&scen=1
{
  const q = new URLSearchParams(location.search);
  if (['BTC', 'ETH'].includes(q.get('asset'))) state.asset = q.get('asset');
  if (['1h', '4h', '1d', '1w', '1M'].includes(q.get('tf'))) state.tf = q.get('tf');
  if (q.get('h')) { const h = Number(q.get('h')); if (state.tf === '1w' || state.tf === '1M') state.hLong[state.tf] = h; else state.horizon = h; }
  const qs = q.get('scen');
  if (qs !== null) state.scen = SCENS.includes(qs) ? qs : (OLD_SCEN[qs] || state.scen);
  if (['ensemble', 'montecarlo', 'analog'].includes(q.get('model'))) state.model = q.get('model');
  if (['shrunk', 'zero', 'historical'].includes(q.get('trend'))) state.variant = q.get('trend');
}

const MODEL_KO = { ensemble: '혼합', montecarlo: '몬테카를로', analog: '유사 패턴' };
const TF_KO = { '1h': '1시간봉', '4h': '4시간봉', '1d': '일봉', '1w': '주봉', '1M': '월봉' };
const HZ = {
  short: [[7, '7일'], [14, '14일'], [30, '30일']],
  '1w': [[91, '3개월'], [182, '6개월'], [365, '1년']],
  '1M': [[365, '1년'], [1095, '3년'], [1826, '5년']],
};
const dirArrow = (d) => (d === 'up' ? '↗' : d === 'down' ? '↘' : '↔');
const isLong = () => state.tf === '1w' || state.tf === '1M';
const curH = () => (isLong() ? state.hLong[state.tf] : state.horizon);
// 장기 결과: 선택한 추세 가정의 값으로 덮어쓴 보기
const longView = (fc) => ({ ...fc.long_term, ...(fc.long_term.variants?.[state.variant] || {}) });
const VARIANT_SHORT = { shrunk: '줄인', zero: '0', historical: '과거' };
const hzLabel = (h) => [...HZ.short, ...HZ['1w'], ...HZ['1M']].find(([v]) => v === h)?.[1] || `${h}일`;
const IND_KO = { ma: '이동평균', rsi14: 'RSI', macd: 'MACD', bollinger: '볼린저', volume: '거래량' };

const precision = (asset) => (asset === 'BTC' ? 0 : 2);
const fmtUSD = (v, p = precision(state.asset)) => v == null ? '—' : '$' + v.toLocaleString('en-US', { minimumFractionDigits: p, maximumFractionDigits: p });
const fmtPct = (x, d = 1, sign = true) => x == null ? '—' : `${sign && x > 0 ? '+' : ''}${(x * 100).toFixed(d)}%`;
const pct0 = (x) => `${Math.round(x * 100)}%`;
const cls = (x) => (x > 0 ? 'up' : x < 0 ? 'down' : 'flat');
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

async function getJSON(path, bust) {
  const url = `data/${path}${bust ? `?v=${encodeURIComponent(bust)}` : ''}`;
  if (cache.has(url)) return cache.get(url);
  const r = await fetch(url, { cache: bust ? 'default' : 'no-store' });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  const j = await r.json();
  if (bust) cache.set(url, j);
  return j;
}

async function loadManifest() {
  const m = await getJSON('manifest.json');
  const major = Number(String(m.schema_version).split('.')[0]);
  if (major !== SUPPORTED_MAJOR) throw new Error(`데이터 형식 버전(${m.schema_version})이 화면과 맞지 않습니다. 새로고침해 주세요.`);
  if (manifest && manifest.generated_at !== m.generated_at) cache.clear();
  manifest = m;
}

function saveView() {
  try { localStorage.setItem('view', JSON.stringify(state)); } catch (e) { /* 무시 */ }
}

function buildSegs(fc) {
  const hz = HZ[isLong() ? state.tf : 'short'];
  const hs = document.querySelector('[data-ctl="horizon"]');
  const key = hz.map(([v]) => v).join(',');
  if (hs.dataset.key !== key) {
    hs.innerHTML = hz.map(([v, l]) => `<button data-v="${v}">${l}</button>`).join('');
    hs.dataset.key = key;
  }
  $('modelRow').hidden = isLong();
  $('variantRow').hidden = !isLong() || !fc?.long_term?.variants;
  if (isLong() && fc) {
    const vs = fc.long_term.variants;
    if (vs) {
      document.querySelector('[data-ctl="variant"]').innerHTML = ['shrunk', 'zero', 'historical'].map((k) => {
        const d = vs[k].drift_annual;
        return `<button data-v="${k}">${VARIANT_SHORT[k]} ${k === 'zero' ? '' : `${d >= 0 ? '+' : ''}${Math.round(d * 100)}%/년`}</button>`;
      }).join('');
    }
  }
  if (fc) {
    const ta = fc.ta_scenarios?.[state.tf];
    const taBtns = ta ? ta.scenarios.map((sc, i) => `<button data-v="ta${i}" title="${esc(sc.label_ko)}">${i ? '대안' : '주'} ${dirArrow(sc.direction)}</button>`).join('') : '';
    const stBtns = isLong() ? longView(fc).top_scenarios.map((g, i) => `<button data-v="st${i}" title="통계 묶음: ${esc(g.label_ko)}">통계${i + 1}</button>`).join('') : '';
    document.querySelector('[data-ctl="scen"]').innerHTML = taBtns + stBtns + '<button data-v="off">끔</button>';
    $('scenRow').hidden = false;
  }
}

function syncControls() {
  document.querySelectorAll('[data-asset]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.asset === state.asset)));
  document.querySelectorAll('[data-ctl]').forEach((g) => {
    const cur = g.dataset.ctl === 'horizon' ? curH() : state[g.dataset.ctl];
    g.querySelectorAll('button').forEach((b) => b.classList.toggle('on', b.dataset.v === String(cur)));
  });
}

function relTime(iso) {
  const t = new Date(iso);
  const min = Math.round((Date.now() - t) / 60000);
  const abs = `${t.getMonth() + 1}/${t.getDate()} ${String(t.getHours()).padStart(2, '0')}:${String(t.getMinutes()).padStart(2, '0')}`;
  const rel = min < 1 ? '방금' : min < 60 ? `${min}분 전` : min < 1440 ? `${Math.floor(min / 60)}시간 ${min % 60}분 전` : `${Math.floor(min / 1440)}일 전`;
  return { text: `마지막 업데이트 ${rel} (${abs})`, stale: min > 150 };
}

async function render() {
  buildSegs(null);
  syncControls();
  const files = manifest.files[state.asset];
  const bust = manifest.generated_at;
  if (!files.candles[state.tf]) state.tf = '1d';  // 이전 버전 데이터 대비
  const [fc, candles] = await Promise.all([getJSON(files.forecast, bust), getJSON(files.candles[state.tf], bust)]);
  buildSegs(fc);
  syncControls();
  renderHeader(fc);
  if (isLong()) return renderLong(fc, candles);
  for (const id of ['cmpCard', 'analogCard']) $(id).hidden = false;
  $('longCard').hidden = true;
  if (state.scen.startsWith('st')) state.scen = 'ta0';
  const model = fc.forecasts[state.model];
  const H = String(state.horizon);
  const hz = model.horizons[H];

  // 차트
  chart.setData({
    asset: state.asset, tf: state.tf, horizon: state.horizon, candles, pathDaily: model.path_daily,
    originPrice: fc.forecast_origin.price, levels: fc.levels, precision: precision(state.asset), ...pickScenario(fc),
  });
  renderTA(fc);

  // 시나리오
  renderScenarioBars(hz, fc, `${state.horizon}일 뒤 시나리오`, `${MODEL_KO[state.model]}${model.calibrated ? ' · 보정 적용' : ''}`);

  // 모델 비교
  $('cmpH').textContent = `${state.horizon}일 뒤`;
  $('cmpTable').innerHTML = '<tr><th>모델</th><th class="r">중앙값</th><th class="r">80% 구간</th><th class="r">상승</th><th class="r">±' +
    `${Math.round(hz.threshold * 100)}% 밖</th></tr>` +
    ['ensemble', 'montecarlo', 'analog'].map((m) => {
      const h = fc.forecasts[m].horizons[H];
      const big = h.scenarios.filter((s) => s.key !== 'flat').reduce((a, s) => a + s.prob, 0);
      return `<tr class="${m === state.model ? 'sel' : ''}" data-model="${m}"><td>${MODEL_KO[m]}</td><td class="r">${fmtUSD(h.quantiles.p50)}</td>` +
        `<td class="r">${fmtCompact(h.quantiles.p10)}~${fmtCompact(h.quantiles.p90)}</td><td class="r">${pct0(h.prob_up)}</td><td class="r">${pct0(big)}</td></tr>`;
    }).join('');
  const mc = fc.forecasts.montecarlo.horizons[H], an = fc.forecasts.analog.horizons[H];
  const diff = an.prob_up - mc.prob_up;
  $('cmpNote').textContent = Math.abs(diff) < 0.04
    ? '두 모델의 방향 판단이 비슷합니다.'
    : `유사 패턴이 몬테카를로보다 상승 확률을 ${Math.round(Math.abs(diff) * 100)}%p ${diff > 0 ? '높게' : '낮게'} 봅니다(과거 비슷한 국면의 흐름 반영).`;

  // 지지/저항 도달
  renderLevels(fc, hz.level_touch, `${state.horizon}일 안 · ${MODEL_KO[state.model]}`);

  renderIndicators(fc);

  // 유사 패턴
  const nb = fc.forecasts.analog.info.neighbors.slice(0, 5);
  const rk = `ret_${state.horizon}d`;
  $('analogTable').innerHTML = `<tr><th>날짜</th><th class="r">유사도</th><th class="r">이후 ${state.horizon}일</th></tr>` +
    nb.map((n) => `<tr><td>${n.date}</td><td class="r">${pct0(n.similarity)}</td><td class="r ${cls(n[rk])}">${fmtPct(n[rk])}</td></tr>`).join('');
  $('analogNote').textContent = `가격 흐름·이동평균 위치·RSI·MACD·변동성 등 12개 특징이 가장 닮은 날짜(일봉 기준). ` +
    `비슷했던 ${fc.forecasts.analog.info.k}개 국면 중 14일 뒤 올랐던 비율 ${pct0(fc.forecasts.analog.info.neighbor_prob_up_14d)}.`;

  renderCalibration(fc);
  renderMeta(fc);
}

// 차트에 그릴 가상 캔들(선택한 시나리오) + 다른 기술적 시나리오 점선 + 목표/무효화 선
function pickScenario(fc) {
  const ta = fc.ta_scenarios?.[state.tf];
  const s = state.scen;
  let out = { scenario: null, scenarioAlt: null, scenarioTitle: '', scenarioMarks: [] };
  if (s.startsWith('ta') && ta) {
    const i = Number(s[2]);
    const sc = ta.scenarios[i];
    const marks = [];
    if (sc.box) marks.push({ price: sc.box[0], title: '박스 하단', kind: 'tgt' }, { price: sc.box[1], title: '박스 상단', kind: 'tgt' });
    else marks.push({ price: sc.first_target.price, title: '1차 목표', kind: 'tgt' });
    if (sc.invalidation) marks.push({ price: sc.invalidation.price, title: '무효화', kind: 'inv' });
    out = { scenario: sc.candles, scenarioAlt: ta.scenarios[1 - i].candles, scenarioTitle: i ? '대안' : '주 시나리오', scenarioMarks: marks };
  } else if (s.startsWith('st') && isLong()) {
    const g = longView(fc).top_scenarios[Number(s[2])];
    if (g) out = { ...out, scenario: g.candles[state.tf], scenarioTitle: `통계 ${Number(s[2]) + 1}` };
  }
  $('keyScen').hidden = !out.scenario;
  $('keyAlt').hidden = !out.scenarioAlt;
  return out;
}

const TF_DAYS = { '1h': '30일', '4h': '30일', '1d': '30일', '1w': '1년', '1M': '5년' };
function renderTA(fc) {
  const ta = fc.ta_scenarios?.[state.tf];
  $('taCard').hidden = !ta;
  if (!ta) return;
  const ev = ta.evidence;
  $('taSub').textContent = `${TF_KO[state.tf]} · 앞으로 ${TF_DAYS[state.tf]}`;
  const last = ta.structure.pivots.slice(-4).map((p) => `${p.type === 'high' ? '고' : '저'} ${fmtCompact(p.price)}`).join(' → ');
  $('taStruct').innerHTML = `<b>${esc(ta.structure.label_ko)}</b><br>최근 스윙: ${esc(last)}`;
  const sel = state.scen.startsWith('ta') ? Number(state.scen[2]) : -1;
  $('taScens').innerHTML = ta.scenarios.map((sc, i) => {
    const sideN = sc.direction === 'up' ? ev.bull : sc.direction === 'down' ? ev.bear : ev.neutral;
    const steps = sc.steps.slice(0, 5).map((st) => `<li><span class="px">${fmtUSD(st.price)}</span> ${esc(st.note_ko)}</li>`).join('');
    const c = sc.stat_check || {};
    const days = c.days >= 365 ? `${Math.round(c.days / 365)}년` : `${c.days}일`;
    const chk = sc.box
      ? `통계 모델로 보면 ${days} 내내 박스 안에 머물 확률 ${pct0(c.box_kept ?? 0)}`
      : `통계 모델로 보면 ${days} 안에 1차 목표 도달 ${pct0(c.target_touch)}` +
        (c.target_first != null ? `, 무효화 가격보다 먼저 닿을 확률 ${pct0(c.target_first)}` : '');
    const kv = sc.box
      ? `<dt>박스</dt><dd>${fmtUSD(sc.box[0])} ~ ${fmtUSD(sc.box[1])}</dd>`
      : `<dt>1차 목표</dt><dd class="${cls(sc.first_target.change)}">${fmtUSD(sc.first_target.price)} (${fmtPct(sc.first_target.change)})</dd>` +
        (sc.furthest ? `<dt>기간 중 최대</dt><dd class="${cls(sc.furthest.change)}">${fmtUSD(sc.furthest.price)} (${fmtPct(sc.furthest.change)})</dd>` : '') +
        (sc.invalidation ? `<dt>무효화</dt><dd>${fmtUSD(sc.invalidation.price)} (${fmtPct(sc.invalidation.change)}) <small class="note">${esc(sc.invalidation.note_ko)}</small></dd>` : '');
    return `<div class="ta-sc ${sel === i ? 'sel' : ''}" data-scen="ta${i}">` +
      `<div class="hd"><b class="${sc.direction === 'up' ? 'up' : sc.direction === 'down' ? 'down' : ''}">${dirArrow(sc.direction)} ${esc(sc.label_ko)}</b>` +
      `<span class="tag ${i ? '' : 'main'}">${i ? '대안' : '주 시나리오'} · 근거 ${sideN}/${ev.items.length}</span></div>` +
      `<ol>${steps}</ol><dl class="kv">${kv}</dl><div class="chk">${esc(chk)} (${esc(ta.stat_model_ko || '')})</div></div>`;
  }).join('');
  $('taEvSum').textContent = `상승 ${ev.bull} · 하락 ${ev.bear} · 중립 ${ev.neutral}`;
  const SIG = { 1: 'bullish', '-1': 'bearish', 0: 'neutral' };
  $('taEvidence').innerHTML = ev.items.map((it) =>
    `<li><span class="name"><i class="dot ${SIG[it.signal]}"></i>${esc(it.name_ko)}</span><span>${esc(it.text_ko)}</span></li>`).join('');
  const bt = ta.backtest;
  $('taBt').innerHTML = bt
    ? `<b>과거에 이 방법이 맞았나?</b> ${bt.period[0]}~${bt.period[1]} ${bt.n}회(${bt.horizon_bars}봉 안): ` +
      `주 시나리오의 1차 목표가 무효화 가격보다 먼저 닿은 비율 <b>${pct0(bt.target_first_resolved)}</b>, ` +
      `방향 없이 무작위로 움직였다면 기대값 ${pct0(bt.baseline_resolved)}. ` +
      (Math.abs(bt.target_first_resolved - bt.baseline_resolved) < 0.03 ? '→ 무작위와 거의 차이 없음.'
        : bt.target_first_resolved > bt.baseline_resolved ? `→ 무작위보다 ${Math.round((bt.target_first_resolved - bt.baseline_resolved) * 100)}%p 나음.` : '→ 무작위보다 못함.')
    : '';
  $('taNote').textContent = `방법: ${ta.method_ko}. 파동 하나의 폭·기간은 이 봉의 최근 스윙 평균(오름 ${fmtPct(ta.swing.median_leg_up_pct, 0)}, 내림 -${Math.round(ta.swing.median_leg_down_pct * 100)}%, 약 ${ta.swing.median_leg_bars}봉)을 따릅니다. ` +
    '가상 캔들은 시나리오를 그림으로 보여 주는 한 예시일 뿐 정확한 시점·가격 예측이 아닙니다. 근거 수는 확률이 아니며, 확률은 아래 통계 모델 수치를 참고하세요.';
}

function renderHeader(fc) {
  $('price').textContent = fmtUSD(fc.price);
  $('chg').textContent = `24시간 ${fmtPct(fc.change_24h, 2)}`;
  $('chg').className = `chg ${cls(fc.change_24h)}`;
  const tState = fc.trend.state;
  $('trendBadge').textContent = `일봉 ${fc.trend.label_ko}`;
  $('trendBadge').className = `badge ${tState.includes('up') ? 'up' : tState.includes('down') ? 'down' : ''}`;
  updateClock();
}

function renderIndicators(fc) {
  const tech = fc.technicals[state.tf];
  $('indTf').textContent = TF_KO[state.tf];
  $('trendBox').innerHTML = `<b class="${tech.trend.state.includes('up') ? 'up' : tech.trend.state.includes('down') ? 'down' : ''}">${esc(tech.trend.label_ko)}</b>${esc(tech.trend.text_ko)}`;
  $('indicators').innerHTML = Object.entries(IND_KO).map(([k, name]) => {
    const it = tech.indicators[k];
    return `<li><span class="name"><i class="dot ${it.signal}"></i>${name}</span><span>${esc(it.text_ko)}</span></li>`;
  }).join('');
}

function renderLevels(fc, touches, title) {
  $('lvH').textContent = title;
  const lvs = [...touches].sort((a, b) => b.price - a.price);
  $('levelTable').innerHTML = '<tr><th>구분</th><th class="r">가격</th><th class="r">거리</th><th>도달 확률</th></tr>' +
    lvs.map((l) => {
      const d = l.price / fc.price - 1;
      return `<tr><td class="${l.type === 'support' ? 'down' : 'up'}">${l.type === 'support' ? '지지' : '저항'}</td><td class="r">${fmtUSD(l.price)}</td>` +
        `<td class="r ${cls(d)}">${fmtPct(d)}</td><td><span class="pbar"><i style="width:${l.prob * 100}%"></i></span>${pct0(l.prob)}</td></tr>`;
    }).join('');
}

function renderScenarioBars(hz, fc, title, sub) {
  $('scenarioTitle').innerHTML = `${title} <small>${sub}</small>`;
  const q = hz.quantiles;
  $('distLine').innerHTML =
    `중앙값 <b>${fmtUSD(q.p50)}</b> <span class="${cls(q.p50 / fc.price - 1)}">(${fmtPct(q.p50 / fc.price - 1)})</span><br>` +
    `80% 구간 <b>${fmtUSD(q.p10)} ~ ${fmtUSD(q.p90)}</b><br>` +
    `<small class="note">오를 확률 ${pct0(hz.prob_up)} · 95% 구간 ${fmtUSD(q.p2_5)} ~ ${fmtUSD(q.p97_5)}</small>`;
  const colors = { up: 'var(--up)', flat: 'var(--flat)', down: 'var(--down)' };
  $('scenarios').innerHTML = hz.scenarios.map((s) =>
    `<div class="scen-row"><span>${esc(s.label_ko)}</span><div class="bar"><i style="width:${(s.prob * 100).toFixed(1)}%;background:${colors[s.key]}"></i></div><span class="pct">${pct0(s.prob)}</span></div>`).join('');
}

function renderLong(fc, candles) {
  const lt = longView(fc);
  const H = curH();
  const hz = lt.horizons[String(H)];
  for (const id of ['cmpCard', 'analogCard']) $(id).hidden = true;
  $('longCard').hidden = false;
  const top = lt.top_scenarios;
  const si = state.scen.startsWith('st') ? Number(state.scen[2]) : -1;
  const sel = si >= 0 ? top[si] : null;

  chart.setData({
    asset: state.asset, tf: state.tf, horizon: H, candles, precision: precision(state.asset), levels: fc.levels,
    longFan: lt.fan[state.tf], ...pickScenario(fc),
  });
  renderTA(fc);

  renderScenarioBars(hz, fc, `${hz.label_ko} 뒤 분포`, `장기 · ${lt.label_ko || ''}`);
  $('longSub').textContent = `경로 모양별 5개 묶음 · ${lt.label_ko || ''}`;

  // 5개 묶음 목록 + 선택한 시나리오 상세
  $('longGroups').innerHTML = lt.scenario_groups.map((g, i) => {
    const pick = i < 2;
    const end = g.checkpoints[g.checkpoints.length - 1].price;
    return `<div class="grp ${pick ? 'pick' : ''} ${pick && si === i ? 'sel' : ''}" ${pick ? `data-scen="st${i}"` : ''}>` +
      `<span class="rk">${g.rank}</span><span class="nm">${esc(g.label_ko)}<small>5년 뒤 중심 ${fmtCompact(end)} (${fmtPct(end / fc.price - 1, 0)})</small></span>` +
      `<span class="bar"><i style="width:${g.prob * 100 / lt.scenario_groups[0].prob}%;background:var(--accent)"></i></span>` +
      `<span class="pct">${pct0(g.prob)}</span></div>`;
  }).join('');
  if (sel) {
    const r = sel.representative;
    $('longDetail').innerHTML = `<b>통계 시나리오 ${si + 1}: ${esc(sel.label_ko)}</b> (${pct0(sel.prob)})<br>${esc(sel.text_ko)}` +
      `<dl><dt>5년 뒤 (대표 경로)</dt><dd class="${cls(r.end_return)}">${fmtUSD(r.end_price)} (${fmtPct(r.end_return, 0)})</dd>` +
      `<dt>최고점</dt><dd>${fmtUSD(r.peak.price)} · ${r.peak.date.slice(0, 7)}</dd>` +
      `<dt>최저점</dt><dd>${fmtUSD(r.trough.price)} · ${r.trough.date.slice(0, 7)}</dd>` +
      `<dt>최대 낙폭</dt><dd class="down">${fmtPct(r.max_drawdown, 0)}</dd>` +
      `<dt>이 묶음 5년 뒤 80% 범위</dt><dd>${fmtCompact(sel.end_range80[0])} ~ ${fmtCompact(sel.end_range80[1])}</dd></dl>`;
  } else {
    $('longDetail').innerHTML = '';
  }
  $('longNote').textContent = `${lt.n_paths.toLocaleString()}개 가상 경로를 3개월 간격 모양으로 5개 묶음으로 나눈 비율입니다. ` +
    '시나리오가 "그대로" 일어날 확률이 아니라, 비슷한 모양의 경로들이 차지하는 비율이에요. 차트의 가상 캔들은 그 묶음의 대표 경로 하나입니다. ' +
    `방법: ${lt.method_ko}. ${lt.drift_note_ko || ''} 추세 가정을 바꿔도 묶음 비율은 같고(모든 경로가 같은 기울기로 움직임), 각 묶음의 가격 수준과 이름이 바뀝니다.`;

  renderLevels(fc, hz.level_touch, `${hz.label_ko} 안`);
  renderIndicators(fc);

  // 신뢰성
  const cal = lt.calibration[String(H)];
  $('calH').textContent = `장기 · ${hz.label_ko}`;
  if (!cal) {
    $('calib').innerHTML = '<p class="note" style="margin:0">검증할 수 있는 과거가 부족합니다(3년·5년 뒤 결과가 있는 시점이 2~3번뿐).</p>';
  } else {
    $('calib').innerHTML = '<div class="cal-legend"><span><i style="background:var(--text)"></i>목표</span><span><i style="background:var(--accent)"></i>실제 포함률</span></div>' +
      [['50', 0.5], ['80', 0.8], ['95', 0.95]].map(([k, target]) => {
        const v = cal.raw[`cov${k}`];
        return `<div class="cal-row"><span>${k}%</span><div class="cal-track"><span class="cal-target" style="left:${target * 100}%"></span>` +
          `<span class="cal-after" style="left:${v * 100}%"></span></div><span class="cal-val"><b>${pct0(v)}</b></span></div>`;
      }).join('');
  }
  // 추세 가정별 비교(같은 기간)
  const vs = fc.long_term.variants;
  if (cal && vs) {
    $('calib').innerHTML += `<div class="table-wrap" style="margin-top:10px"><table class="tbl"><tr><th>추세 가정</th><th class="r">80% 구간 포함</th><th class="r">실제 &gt; 중앙값</th></tr>` +
      ['shrunk', 'zero', 'historical'].map((k) => {
        const c = vs[k].calibration[String(H)];
        return `<tr class="${k === state.variant ? 'sel' : ''}"><td>${esc(vs[k].label_ko)}</td><td class="r">${pct0(c.raw.cov80)}</td><td class="r">${pct0(c.above_median)}</td></tr>`;
      }).join('') + '</table></div>';
  }
  $('calNote').textContent = lt.calibration.note_ko + (cal ? ` (검증 ${cal.n}회, 실제로 겹치지 않는 표본은 약 ${cal.independent_approx}개.` +
    ' "실제 > 중앙값"은 실제 가격이 예측 중앙값보다 높았던 비율로, 50%에 가까울수록 치우침이 없고 높을수록 예측이 비관적이었다는 뜻)' : '');
  renderMeta(fc);
}

function renderMeta(fc) {
  $('meta').innerHTML = `데이터: ${[...new Set(Object.values(fc.sources))].join(', ')} · 형식 v${esc(fc.schema_version)} · ` +
    `<a href="https://github.com/gozipgo/crypto-forecast">소스 코드</a> · 차트 <a href="https://www.tradingview.com/">TradingView</a> Lightweight Charts`;
  $('disclaimer').textContent = fc.disclaimer_ko;
}

function fmtCompact(v) {
  if (v >= 10000) return `$${(v / 1000).toFixed(1)}k`;
  return fmtUSD(v);
}

function renderCalibration(fc) {
  const cal = fc.calibration.models[state.model][String(state.horizon)];
  $('calH').textContent = `${MODEL_KO[state.model]} · ${state.horizon}일`;
  const rows = [['50', 0.5], ['80', 0.8], ['95', 0.95]].map(([k, target]) => {
    const raw = cal.raw[`cov${k}`], after = cal.after[`cov${k}`];
    const pos = (x) => `${(x * 100).toFixed(1)}%`;
    return `<div class="cal-row"><span>${k}%</span><div class="cal-track">` +
      `<span class="cal-target" style="left:${pos(target)}"></span>` +
      (cal.adjusted ? `<span class="cal-raw" style="left:${pos(raw)}" title="보정 전"></span>` : '') +
      `<span class="cal-after" style="left:${pos(after)}" title="${cal.adjusted ? '보정 후' : '실제'}"></span></div>` +
      `<span class="cal-val">${cal.adjusted ? `${pct0(raw)} → ` : ''}<b>${pct0(after)}</b></span></div>`;
  }).join('');
  $('calib').innerHTML =
    `<div class="cal-legend"><span><i style="background:var(--text)"></i>목표</span>` +
    (cal.adjusted ? '<span><i style="border:2px solid var(--flat)"></i>보정 전</span><span><i style="background:var(--accent)"></i>보정 후</span>'
      : '<span><i style="background:var(--accent)"></i>실제 포함률</span>') + '</div>' + rows;
  const t = cal.test_half;
  $('calNote').innerHTML =
    `${cal.period[0]}~${cal.period[1]} 동안 3일마다 그 시점까지의 데이터로만 예측(${cal.n}회)했을 때 실제 가격이 각 구간 안에 들어간 비율. ` +
    `${esc(cal.reason_ko)}.` +
    (cal.adjusted ? ` 표본 외 검증(${t.from}~): 80% 구간 ${pct0(t.raw.cov80)} → ${pct0(t.adjusted.cov80)}, 50% 구간 ${pct0(t.raw.cov50)} → ${pct0(t.adjusted.cov50)}.` : '');
}

function updateClock() {
  if (!manifest) return;
  const r = relTime(manifest.generated_at);
  $('updated').textContent = r.text + (r.stale ? ' · 업데이트가 늦어지고 있어요' : '');
  $('updated').classList.toggle('stale', r.stale);
}

function showError(e) {
  console.error(e);
  $('updated').textContent = '데이터를 불러오지 못했습니다.';
  const main = document.querySelector('main');
  if (!document.querySelector('.error')) {
    const div = document.createElement('div');
    div.className = 'error';
    div.textContent = `오류: ${e.message}`;
    main.prepend(div);
  }
}

async function refresh() {
  try {
    await loadManifest();
    document.querySelector('.error')?.remove();
    await render();
  } catch (e) { showError(e); }
}

// 테마: 자동 → 다크 → 라이트
const THEMES = ['auto', 'dark', 'light'];
const THEME_KO = { auto: '자동', dark: '다크', light: '라이트' };
function currentTheme() { return document.documentElement.dataset.theme || 'auto'; }
function setTheme(t) {
  if (t === 'auto') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
  try { localStorage.setItem('theme', t); } catch (e) { /* 무시 */ }
  $('themeLabel').textContent = THEME_KO[t];
  chart?.applyTheme();
}

function bind() {
  document.querySelectorAll('[data-asset]').forEach((b) => b.addEventListener('click', () => {
    state.asset = b.dataset.asset; saveView(); render().catch(showError);
  }));
  document.querySelectorAll('[data-ctl]').forEach((g) => g.addEventListener('click', (ev) => {
    const b = ev.target.closest('button'); if (!b) return;
    const key = g.dataset.ctl;
    if (key === 'horizon') {
      if (isLong()) state.hLong[state.tf] = Number(b.dataset.v); else state.horizon = Number(b.dataset.v);
    } else if (key === 'variant') {
      state.variant = b.dataset.v;
    } else if (key === 'scen') {
      state.scen = b.dataset.v;
    } else {
      state[key] = b.dataset.v;
    }
    saveView(); render().catch(showError);
  }));
  $('taScens').addEventListener('click', (ev) => {
    const el = ev.target.closest('[data-scen]'); if (!el) return;
    state.scen = el.dataset.scen; saveView(); render().catch(showError);
  });
  $('cmpTable').addEventListener('click', (ev) => {
    const tr = ev.target.closest('tr[data-model]'); if (!tr) return;
    state.model = tr.dataset.model; saveView(); render().catch(showError);
  });
  $('longGroups').addEventListener('click', (ev) => {
    const el = ev.target.closest('[data-scen]'); if (!el) return;
    state.scen = el.dataset.scen; saveView(); render().catch(showError);
  });
  $('themeBtn').addEventListener('click', () => setTheme(THEMES[(THEMES.indexOf(currentTheme()) + 1) % 3]));
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => chart?.applyTheme());
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  setInterval(updateClock, 30000);
  setInterval(refresh, 10 * 60000);
}

$('themeLabel').textContent = THEME_KO[currentTheme()];
chart = new PriceChart($('chart'), $('legend'));
bind();
refresh();

if ('serviceWorker' in navigator && location.protocol !== 'file:') {
  navigator.serviceWorker.register('sw.js').catch(() => {});
}
