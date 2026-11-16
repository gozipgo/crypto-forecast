# 결과 JSON 형식 (schema_version 1.x)

계산 엔진(`engine/`)이 만들고, 웹 화면·SwiftUI 앱·위젯·알림이 **읽기만** 하는 파일들입니다.
기계용 정의는 [`schema/forecast.v1.schema.json`](../schema/forecast.v1.schema.json)(JSON Schema 2020-12)이며,
엔진은 저장 전에 이 스키마로 검증하고 맞지 않으면 배포를 중단합니다.

## 버전 규칙
- `schema_version`은 모든 파일에 들어 있습니다(예: `"1.0.0"`).
- **minor**(1.0 → 1.1): 필드 추가 등 하위호환 변경. 앱은 모르는 필드를 무시하면 됩니다.
- **major**(1.x → 2.0): 필드 삭제·이름/의미 변경. 앱은 major가 다르면 "업데이트 필요"를 표시하세요.
- 공통 규칙: 시각은 UTC ISO-8601(`2026-11-17T05:00:00Z`) 또는 UNIX 초, 가격은 USD 숫자, 확률·비율은 0~1 소수.

## 파일 목록
```
data/
  manifest.json        목차: 생성 시각, 자산, 파일 경로
  summary.json         위젯·알림용 초경량 요약(1KB 내외)
  BTC/forecast.json    지표 요약·지지/저항·모델별 확률 분포·보정도 (~30KB)
  BTC/candles_1h.json  차트용 캔들(최근 720봉), candles_4h(540), candles_1d(1000)
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
| `interval` | `1h`/`4h`/`1d` |
| `t` | 봉 시작 시각(UNIX 초, UTC) |
| `o,h,l,c,v` | 시가·고가·저가·종가·거래량(기준 통화 수량) |
| `sma20,sma50,sma200,bb_upper,bb_lower` | 차트 오버레이용 지표(계산 불가 구간은 `null`) |

마지막 봉은 진행 중인 봉입니다.
