# 결과 JSON 형식 (schema_version 1.x, 현재 1.3.0)

계산 엔진(`engine/`)이 만들고, 웹 화면·SwiftUI 앱·위젯·알림이 **읽기만** 하는 파일들입니다.
기계용 정의는 [`schema/forecast.v1.schema.json`](../schema/forecast.v1.schema.json)(JSON Schema 2020-12)이며,
엔진은 저장 전에 이 스키마로 검증하고 맞지 않으면 배포를 중단합니다.

## 버전 규칙
- `schema_version`은 모든 파일에 들어 있습니다(예: `"1.0.0"`).
- **minor**(1.0 → 1.1): 필드 추가 등 하위호환 변경. 앱은 모르는 필드를 무시하면 됩니다.
- **major**(1.x → 2.0): 필드 삭제·이름/의미 변경. 앱은 major가 다르면 "업데이트 필요"를 표시하세요.
- 공통 규칙: 시각은 UTC ISO-8601(`2026-11-17T05:00:00Z`) 또는 UNIX 초, 가격은 USD 숫자, 확률·비율은 0~1 소수.

## 변경 이력
- **1.3.0** (하위호환 추가): `forecast.json`의 `ta_scenarios.{1h,4h,1d,1w,1M}` — 차트 기술적 분석으로 만든 시나리오 2개(주·대안)와 가상 캔들, 근거 체크리스트, 통계 모델 교차 확인, 백테스트.
- **1.2.0** (하위호환 추가): `long_term.variants.{shrunk,zero,historical}`(추세 가정별 전체 결과: `label_ko`, `drift_annual`, `horizons`, `fan`, `scenario_groups`, `top_scenarios`, `calibration`), `long_term.default_variant`, `long_term.drift_note_ko`, 묶음별 `typical_max_drawdown`, 장기 백테스트 `above_median`. 최상위 `long_term.horizons` 등은 기본 가정(`shrunk`)과 같습니다.
- **1.1.0** (하위호환 추가): 주봉·월봉 `candles_1w.json`·`candles_1M.json`, `technicals.1w/1M`, `sources.1w/1M`,
  `forecast.json`의 `long_term`(최대 5년 전망·시나리오), `summary.json`의 `long_term_top`.
- **1.0.0**: 최초 버전.

## 파일 목록
```
data/
  manifest.json        목차: 생성 시각, 자산, 파일 경로
  summary.json         위젯·알림용 초경량 요약(1KB 내외)
  BTC/forecast.json    지표 요약·지지/저항·모델별 확률 분포·보정도 (~30KB)
  BTC/candles_1h.json  차트용 캔들(최근 720봉), candles_4h(540), candles_1d(1000), candles_1w(600), candles_1M(240)
  ETH/...
```
배포 주소 기준: `https://gozipgo.github.io/crypto-forecast/data/summary.json`

## manifest.json
| 필드 | 설명 |
|---|---|
| `generated_at` | 계산 완료 시각(= 화면의 "마지막 업데이트") |
| `assets` | `["BTC","ETH"]` |
| `summary` | `"summary.json"` |
| `files.{자산}.forecast` / `files.{자산}.candles.{1h,4h,1d}` | 상대 경로 |
| `build_seconds` | 계산 소요 시간 |

## summary.json (위젯용)
```json
{"schema_version":"1.0.0","generated_at":"2026-11-16T23:37:07Z",
 "assets":{"BTC":{"price":65196.63,"change_24h":-0.0024,"trend":"strong_down","trend_label_ko":"강한 하락 추세",
   "horizon_days":14,"median_14d":65619.55,"range80_14d":[57848.72,73906.3],
   "scenarios_14d":[{"key":"up","label_ko":"+10% 이상","prob":0.151},{"key":"flat","label_ko":"±10% 이내","prob":0.732},{"key":"down","label_ko":"-10% 이하","prob":0.117}],
   "prob_up_14d":0.535}},
 "disclaimer_ko":"투자 조언이 아니며, ..."}
```
요약 수치는 **혼합(ensemble) 모델, 14일** 기준입니다.
`long_term_top[2]`: 5년 시나리오 상위 2개 `{label_ko, prob, end_price_5y}` (위젯에서 "5년 시나리오" 표시용).

## {자산}/forecast.json
| 필드 | 설명 |
|---|---|
| `asset`, `quote` | `"BTC"`, `"USD"` |
| `sources` | 봉 단위별 실제 사용한 데이터 소스(`binance_vision`/`coinbase`/`kraken`/`coingecko`) |
| `generated_at`, `last_candle_at` | 계산 시각, 마지막(진행 중) 1시간봉 시작 시각 |
| `price`, `change_24h`, `atr_1d` | 현재가, 24시간 변동률, 일봉 ATR(14) |
| `trend` | 일봉 기준 추세. `state`: `strong_up`/`up`/`sideways`/`down`/`strong_down`, `label_ko`, `text_ko`, `adx`, `score`(-6~+6) |
| `technicals.{1h,4h,1d}` | 봉 단위별 `trend` + `indicators` |
| `technicals.*.indicators.{ma,rsi14,macd,bollinger,volume}` | 각 항목 `signal`(`bullish`/`bearish`/`neutral`/`overbought`/`oversold`), `text_ko`(한국어 1~2줄), 수치 필드 |
| `levels[]` | 지지/저항: `type`, `price`, `strength`(0~1), `touches`, `distance_pct`, `last_touch` |
| `forecast_origin` | 예측 출발점(현재가·시각)과 사용한 일봉 이력 구간 |
| `forecasts.{montecarlo,analog,ensemble}` | 모델별 결과(아래) |
| `calibration` | 백테스트 보정도(아래) |
| `disclaimer_ko` | 안내 문구 |

### forecasts.{모델}
| 필드 | 설명 |
|---|---|
| `label_ko` | `몬테카를로` / `유사 패턴` / `혼합` |
| `calibrated` | 백테스트 기반 재보정이 적용됐는지 |
| `info` | 모델 정보. analog는 `neighbors[]`(가장 비슷했던 과거 날짜 10개: `date`, `similarity`, `ret_7d/14d/30d`) |
| `path_daily[30]` | 1~30일 뒤 각 날짜의 가격 분위수 `p2_5,p10,p25,p50,p75,p90,p97_5` → fan chart (95%=p2_5~p97_5, 80%=p10~p90, 50%=p25~p75, 중앙값=p50) |
| `horizons.{7,14,30}.quantiles` | 그 기간 뒤 가격 분위수 |
| `horizons.*.prob_up` | 현재가보다 높을 확률 |
| `horizons.*.expected_return` | 기대 수익률(평균) |
| `horizons.*.scenarios[3]` | `up`(+임계 이상)/`flat`/`down` 확률. 임계값 `threshold`: 7일 5%, 14일 10%, 30일 15% |
| `horizons.*.level_touch[]` | 기간 안에 해당 지지/저항 가격에 **한 번이라도 닿을** 확률(장중 고가·저가 기준) |

미래 시각 계산: `day`일 뒤 = `forecast_origin.time` + `day`×24시간.

### long_term (1.1.0, 주봉·월봉 화면용 최대 5년 전망)
방법: 일간 수익률을 90일 블록째로 복원추출(추세 0, 최근 2년 변동성 수준) → 4,000개 5년 경로.
| 필드 | 설명 |
|---|---|
| `method_ko`, `n_paths`, `sigma_daily_recent` | 방법 설명, 경로 수, 최근 2년 일간 변동성 |
| `horizons.{91,182,365,1095,1826}` | 3개월/6개월/1년/3년/5년 뒤: `label_ko`, `quantiles`, `prob_up`, `expected_return`, `threshold_factor`, `scenarios[3]`(×f 이상 / 사이 / ÷f 이하), `level_touch[]` |
| `fan.1w[]`, `fan.1M[]` | 각 미래 주봉·월봉 **시작 시각** `t`(UNIX 초)마다 분위수. 첫 항목은 현재 진행 중인 봉 시작 시각 = 현재가 |
| `scenario_groups[5]` | 경로 모양(3개월 간격 20개 지점) k-means 5개 묶음, 확률 큰 순. `rank`, `prob`, `label_ko`(예: 박스권 횡보, 큰 하락, 폭등), `checkpoints[20]`(묶음 중심 경로: `day`, `price`), `end_range80` |
| `top_scenarios[2]` | 상위 2개 묶음 + `representative`(대표 경로: `end_price`, `end_return`, `peak`, `trough`, `max_drawdown`), `candles.{1w,1M}`(가상 캔들 `t,o,h,l,c`), `text_ko` |
| `calibration.{91,182,365}` | 장기 백테스트 포함률 `raw.cov50/80/95`, `n`, `independent_approx`(겹치지 않는 표본 수 근사). `1095`·`1826`은 `null`(검증 불가), `note_ko` |

추세 가정별 결과는 `variants.{shrunk|zero|historical}` 에 같은 구조로 들어 있습니다. 기본은 `default_variant`.
`calibration.{91,182,365}.above_median`: 실제 가격이 예측 중앙값보다 높았던 비율(0.5가 이상적).

`prob`는 "그 경로가 그대로 일어날 확률"이 아니라 **비슷한 모양의 경로들이 차지하는 비율**입니다.

### ta_scenarios (1.3.0, 봉별 차트 기술적 분석 시나리오)
확률 모델이 아니라 차트 규칙(다우 이론 고점·저점 구조, 지그재그 스윙, 지지·저항과 역할 전환, 피보나치 되돌림·확장, 측정 이동,
이동평균·MACD·RSI·볼린저·거래량 근거)으로 그린 경로입니다. 봉마다 하나씩(`1h`,`4h`,`1d` = 30일, `1w` = 1년, `1M` = 5년).

| 필드 | 설명 |
|---|---|
| `structure` | `code`(`HH_HL` 상승 구조, `LH_LL` 하락 구조, `HH_LL` 확산, `LH_HL` 수렴, `unknown`), `label_ko`, `pivots[]`(최근 스윙 `t`,`price`,`type` high/low) |
| `evidence` | `items[]`(`key`,`name_ko`,`signal` +1 상승/-1 하락/0 중립,`text_ko`), `bull`,`bear`,`neutral`, `score`(=(bull-bear)/개수). 점수 ±0.25 이상이면 주 시나리오가 추세형, 아니면 박스권 |
| `swing` | 최근 스윙 통계: `median_leg_up_pct`, `median_leg_down_pct`, `median_leg_bars`, `zigzag_atr`, `n_legs` |
| `scenarios[2]` | [0] = 주(`role: primary`), [1] = 대안(`alternate`). 아래 참고 |
| `stat_model_ko` | 교차 확인에 쓴 통계 모델 |
| `backtest` | 과거 각 시점에서 그때까지의 봉만으로 주 시나리오를 만들고 `horizon_bars`봉 안에 1차 목표와 무효화 중 무엇이 먼저 닿았는지: `n`, `period`, `target_first`, `invalidation_first`, `neither`, `target_first_resolved`(둘 중 하나가 닿은 경우 중 목표가 먼저인 비율), `baseline_resolved`(방향 없는 무작위라면 기대값 = 무효화 거리/(두 거리 합)의 평균), `range_n`, `range_kept`. 월봉은 `null` |

`scenarios[]` 항목:
| 필드 | 설명 |
|---|---|
| `kind` | `trend`(추세 지속), `reversal`(추세 전환), `range`(박스권), `breakout`(박스 돌파) |
| `direction` | `up` / `down` / `range` |
| `label_ko`, `text_ko` | 제목, 단계 요약(①→②→… + 무효화) |
| `evidence_share` | 이 시나리오 방향을 지지하는 근거 비중(확률 아님) |
| `first_target` | `price`, `change`(현재가 대비), `note_ko`(어떤 근거의 가격인지) |
| `furthest` | 기간 안 가장 멀리 간 경유점(박스권이면 `null`) |
| `invalidation` | 이 가격을 넘어 마감하면 시나리오 무효: `price`, `change`, `note_ko`. 박스권은 `null` |
| `box` | 박스권일 때 `[하단, 상단]`, 아니면 `null` |
| `steps[]` | 경유점: `t`(UNIX 초), `bars`(몇 봉 뒤), `price`, `kind`(pullback·impulse·correction·target·retest·range), `note_ko` |
| `candles` | 가상 캔들 `t,o,h,l,c`. `t`는 미래 봉 시작 시각(해당 봉 단위) |
| `stat_check` | 통계 모델 경로로 본 `days`일 안 `target_touch`, `invalidation_touch`, `target_first`(목표가 무효화보다 먼저), 박스권이면 `box_kept` |

### calibration
`calibration.models.{모델}.{7,14,30}`:
| 필드 | 설명 |
|---|---|
| `n`, `period` | 백테스트 표본 수(3일 간격), 기간 |
| `raw` | 원래 모델의 실제 포함률 `cov50/cov80/cov95` (목표 0.5/0.8/0.95) |
| `adjusted`, `reason_ko` | 재보정 적용 여부와 이유 |
| `after` | 재보정 후 포함률(전체 기간) |
| `test_half` | 앞 절반으로 맞추고 뒤 절반(`from` 이후)에서 잰 표본 외 포함률 `raw`/`adjusted` |
| `interval_map` | 목표 50/80/95% 구간을 원래 모델의 몇 % 구간으로 그리는지(예: `{"50":0.44}`) |
| `recal` | 재보정 지도(`c` → `c_raw`), 미적용 시 `null` |
| `pit_hist[10]` | 실제값이 예측 분포의 어느 10% 칸에 떨어졌는지 비율(고르면 이상적) |
| `share_below_median` | 실제값이 예측 중앙값보다 낮았던 비율(0.5가 이상적) |

## {자산}/candles_{1h,4h,1d}.json
열(column) 단위 배열입니다. 같은 인덱스끼리 한 봉입니다.
| 필드 | 설명 |
|---|---|
| `interval` | `1h`/`4h`/`1d`/`1w`/`1M` (주봉은 월요일, 월봉은 1일 00:00 UTC 시작) |
| `t` | 봉 시작 시각(UNIX 초, UTC) |
| `o,h,l,c,v` | 시가·고가·저가·종가·거래량(기준 통화 수량) |
| `sma20,sma50,sma200,bb_upper,bb_lower` | 차트 오버레이용 지표(계산 불가 구간은 `null`) |

마지막 봉은 진행 중인 봉입니다.
