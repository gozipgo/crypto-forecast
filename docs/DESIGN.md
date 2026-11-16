# BTC/ETH 기술적 분석 + 확률 전개(fan chart) 웹앱 — 조사·설계안

## Context
아이폰 사파리에서 볼 BTC/ETH 차트 분석 웹앱. 핵심은 7/14/30일 뒤 가격 분포를 fan chart로 보여 주는 것(몬테카를로 + 유사 패턴 검색), 그리고 백테스트로 "80% 구간이 실제로 80% 맞는지"를 보여 주는 것. 계산(Python) → JSON → 화면(정적 HTML/JS) 완전 분리. 같은 JSON을 나중에 SwiftUI 앱·위젯·알림이 재사용하므로 스키마를 버전 관리한다.

확정된 결정: **Public 저장소 + GitHub Pages**, **USD(USDT) 기준**, **winget으로 Python 3.12 설치**. 작업 폴더 `C:\Users\sming\dev\crypto-forecast`는 비어 있고 git 저장소 아님. `gh`는 gozipgo 계정으로 로그인됨(repo, workflow 권한). Node 불필요.

---

## ① 조사 결과 (오픈소스 5개)

| 프로젝트 | 하는 일 | 장점 | 단점 | 라이선스 | 우리가 참고할 점 |
|---|---|---|---|---|---|
| [tradingview/lightweight-charts](https://github.com/tradingview/lightweight-charts) (★17.9k) | 캔버스 기반 금융 차트 | 매우 가볍고(~45KB) 핀치 줌·스크롤 지원, 플러그인(series primitive)으로 밴드 그리기 가능 | 밴드 음영은 기본 제공 X → primitive 직접 작성 | Apache-2.0 | **그대로 사용**(vendor 포함, LICENSE/NOTICE 동봉, TradingView 저작자 표시 유지). 공식 plugin-examples의 "bands" 패턴 참고 |
| [AccursedGalaxy/wasserstein-btc](https://github.com/AccursedGalaxy/wasserstein-btc) | 크립토 수익률 분포 예측 + fan chart + walk-forward 백테스트(CRPS) | 분포 예측을 HS-Bootstrap·GARCH 기준선과 정직하게 비교, JSON 출력 | 연구용, 모델이 복잡 | MIT | 백테스트 설계(walk-forward, CRPS·커버리지 평가), "기준선과 비교" 문화. 코드 복사 대신 방법만 차용 |
| [jofpin/synthBTC](https://github.com/jofpin/synthBTC) (★528) | BTC 몬테카를로 시나리오 대량 생성 | 단순·직관적 | 정규분포 GBM 위주, 보정 검증 없음 | MIT | 경로 생성·백분위 요약 출력 방식. 정규분포 가정의 한계(꼬리 과소추정)는 피함 |
| [gaborvecsei/Stocks-Pattern-Analyzer](https://github.com/gaborvecsei/Stocks-Pattern-Analyzer) (★264) | 과거 유사 패턴 검색(유사도 + 이후 움직임 표시) | 유사 패턴 아이디어를 시각적으로 보여 줌 | 2023년 이후 정체 | **자체 커스텀 라이선스** | **코드 사용 안 함.** 아이디어(정규화된 창 비교 → 이후 경로)만 참고 |
| [emerzon/mtdata-mcp](https://github.com/emerzon/mtdata-mcp) | MT5 연구 툴킷의 analog forecasting(kNN, ckdtree/HNSW, 정규화 옵션) | 거리 척도·정규화·겹침 제외 등 설계가 잘 문서화 | MT5 의존, 범위가 너무 큼 | MIT | 특징 정규화, 겹치는 창 제외, 거리 가중 kNN 설계 참고 |

(참고만: freqtrade/frequi는 GPL-3.0이라 코드 차용 금지, TradingView "K-NN Pattern Forecast" Pine 스크립트는 로그수익률로 모양 비교하는 아이디어만.)

## 데이터 소스 실측 (이 PC, 2026-11-17)
| 소스 | 결과 | 비고 |
|---|---|---|
| data-api.binance.vision | ✅ 200 | USDT, 1h/4h/1d, 1000개/요청, 2017-08~ → **1순위** |
| api.exchange.coinbase.com | ✅ 200 | USD, 1h/1d(4h 없음 → 1h로 재집계), 300개/요청 → **2순위** |
| api.kraken.com | ✅ 200 | 최근 720개만 → **3순위**(최근분만) |
| api.coingecko.com | ✅ 200 | OHLC 해상도 거칠고 거래량 없음 → 최후 수단(일봉) |
| api.binance.com / api.upbit.com / okx | ❌ 연결 실패 | 사용 안 함 |

→ ②단계 첫 작업으로 GitHub Actions(미국 러너)에서 같은 probe 스크립트를 실행해 실제 결과로 우선순위를 확정. 각 소스 실패 시 자동 폴백, 결과 JSON에 `source` 기록.

---

## ② 설계

### 폴더 구조
```
crypto-forecast/
├─ engine/                    # 계산 (Python, numpy+pandas만)
│  ├─ sources/                # binance_vision.py, coinbase.py, kraken.py, coingecko.py, base.py(폴백 체인)
│  ├─ indicators.py           # SMA20/50/200, RSI14, MACD(12,26,9), BB(20,2), 거래량 비율
│  ├─ levels.py               # 스윙 고저점 클러스터링 → 지지/저항
│  ├─ trend.py                # MA 배열+기울기+ADX풍 판정 → 상승/하락/횡보
│  ├─ narrative.py            # 지표별 한국어 1~2줄 요약
│  ├─ models/montecarlo.py    # (a) 필터드 히스토리컬 부트스트랩
│  ├─ models/analog.py        # (b) 유사 패턴 kNN
│  ├─ models/ensemble.py      # (c) a+b 혼합
│  ├─ backtest.py             # walk-forward 보정도 + 폭 조정 계수
│  ├─ export.py               # JSON 생성 + 스키마 검증
│  └─ run.py                  # 진입점: python -m engine.run --out site/data
├─ site/                      # 화면 (빌드 없는 정적 HTML/JS)
│  ├─ index.html, app.js, chart.js, fan-primitive.js, style.css
│  ├─ manifest.webmanifest, sw.js, icons/
│  ├─ vendor/lightweight-charts.standalone.production.js (+LICENSE)
│  └─ data/                   # 생성물(.gitignore, 로컬/배포 시만 존재)
├─ schema/forecast.v1.schema.json   # JSON Schema
├─ docs/SCHEMA.md             # 필드 설명(한국어)
├─ scripts/probe_sources.py   # 데이터 소스 실측
├─ tests/                     # pytest: 지표 값, 누수(look-ahead) 없음, 스키마 적합성
├─ .github/workflows/update.yml, probe.yml, test.yml
├─ requirements.txt, README.md(한국어), LICENSE(MIT)
```

### 확률 모델
- 공통: 일봉 로그수익률 기반으로 1~30일 경로 분포 계산(봉 단위 전환은 표시만 바뀌고 분포는 동일; 1h/4h 차트에서는 일 단위 분위수를 선형 보간해 미래 시간축에 그림).
- **(a) 몬테카를로 – 필터드 히스토리컬 부트스트랩**: EWMA(λ=0.94) 변동성으로 과거 수익률을 표준화 → 잔차를 블록 부트스트랩(블록 5일) → 현재 변동성으로 재스케일, 변동성은 장기 평균으로 서서히 회귀. 10,000 경로. 정규분포 가정 없이 두꺼운 꼬리 반영.
- **(b) 유사 패턴 검색**: 매일의 상태 벡터 = 5/20/60일 수익률, MA20/50/200 대비 괴리, RSI, MACD 히스토그램(가격 정규화), BB %b, 거래량 비율, 실현변동성 백분위. z-score 정규화 → 거리 가중 kNN(k≈60), 현재 시점과 겹치는 창 제외·서로 너무 가까운 이웃 중복 제거. 이웃들의 이후 1~30일 실제 경로(변동성 비율로 스케일)를 가중 분위수로 요약. 상위 유사 구간 날짜·유사도도 출력(화면에 "가장 비슷했던 과거 5개").
- **(c) 앙상블**: 두 분포의 경로 혼합(기본 50:50, 백테스트 점수로 가중 조정 가능).
- **출력**: 각 모델·기간별 일자별 분위수(2.5/10/25/50/75/90/97.5) → 50/80/95% 음영 + 중앙값. 시나리오 확률(기간별 임계값: 7일 ±5%, 14일 ±10%, 30일 ±15%). 지지/저항 **도달(터치) 확률** = 경로의 최고/최저가가 해당 가격을 건드린 비율.

### 신뢰성 검증(백테스트)
- 2019-01 ~ 현재, 3일 간격 walk-forward. 각 시점에서 그 이전 데이터만 사용(analog는 `t-h` 이전 창만 후보) → look-ahead 없음을 테스트로 보장.
- 지표: 50/80/95% 구간 실제 포함률(커버리지), PIT 히스토그램, 핀볼 손실/CRPS.
- **조정**: 커버리지가 목표에서 ±5%p 넘게 벗어나면 모델·기간별 "폭 배율"(분위수를 중앙값 기준으로 늘리고 줄이는 계수)을 앞쪽 절반 기간에서 맞추고 뒤쪽 절반에서 검증. 조정 전/후 커버리지와 배율을 JSON `calibration`에 기록 → 화면과 단계 보고에서 설명.
- 계산량이 작아(numpy 벡터화, 경로 수 축소 2,000) 매시간 같이 돌림. 느리면 하루 1회로 분리.

### 결과 JSON (schema_version 1.0.0)
```
site/data/
  manifest.json            # 버전, 생성시각, 자산 목록, 파일 경로
  summary.json             # 위젯/알림용 초경량(자산별 가격·24h 변동·추세·14일 시나리오)
  BTC/forecast.json        # 지표 요약·레벨·모델 분포·시나리오·도달확률·보정도
  BTC/candles_1h.json      # 최근 720개 / 4h 540개 / 1d 1000개 [t,o,h,l,c,v]
  ETH/...
```
`BTC/forecast.json` 예시(축약):
```json
{
  "schema_version": "1.0.0",
  "asset": "BTC", "quote": "USD", "source": "binance_vision",
  "generated_at": "2026-11-17T05:03:12Z", "last_candle_at": "2026-11-17T04:00:00Z",
  "price": 65319.65,
  "trend": {"state": "down", "label_ko": "하락 추세", "text_ko": "가격이 50·200일선 아래, 50일선 하락 중"},
  "indicators": {
    "rsi14": {"value": 38.2, "signal": "neutral_bearish", "text_ko": "RSI 38, 과매도 근처지만 아직 반등 신호 없음"},
    "macd": {...}, "bollinger": {...}, "ma": {...}, "volume": {...}
  },
  "levels": [{"type": "support", "price": 62000, "strength": 0.8, "touches": 4}, ...],
  "forecasts": {
    "montecarlo": {
      "horizons": {
        "14": {
          "quantiles": {"p2_5": 55100, "p10": 58900, "p25": 62100, "p50": 65200, "p75": 68300, "p90": 71800, "p97_5": 76400},
          "scenarios": [{"label_ko": "+10% 이상", "prob": 0.18}, {"label_ko": "±10% 이내", "prob": 0.66}, {"label_ko": "-10% 이하", "prob": 0.16}],
          "level_touch": [{"price": 62000, "prob": 0.47}, ...]
        }
      },
      "path_daily": [{"day": 1, "p2_5": ..., "p50": ..., "p97_5": ...}, ... 30개]
    },
    "analog": {..., "neighbors": [{"date": "2022-06-10", "similarity": 0.91, "ret_14d": -0.08}, ...]},
    "ensemble": {...}
  },
  "calibration": {
    "period": ["2019-01-01", "2026-11-14"], "n": 940,
    "montecarlo": {"14": {"cov50": 0.51, "cov80": 0.78, "cov95": 0.93, "width_mult": 1.06, "adjusted": true}}, ...
  },
  "disclaimer_ko": "투자 조언이 아니며, 확률은 과거 데이터에 기반한 통계적 추정입니다."
}
```
- 규칙: 하위호환 추가는 minor(1.1.0), 필드 삭제/의미 변경은 major(2.0.0). 모든 시각 UTC ISO-8601, 가격 USD 숫자, 확률 0~1.
- `schema/forecast.v1.schema.json`으로 export 시 검증(pytest + 런타임). `docs/SCHEMA.md`와 README에 한국어 설명.

### 화면 (아이폰 세로 우선, 빌드 없는 HTML/JS)
1. 상단: BTC | ETH 탭, 현재가·24h 변동, "마지막 업데이트 n분 전(시각)"
2. 세그먼트: 봉 1h/4h/1D · 예측 7/14/30일 · 모델 MC/유사패턴/혼합
3. 차트(lightweight-charts): 캔들+MA20/50/200+거래량, 미래 구간에 fan(95/80/50% 음영 + 중앙값 선), 지지/저항 수평선. 핀치 줌·스크롤
4. 시나리오 카드(막대) + 지지/저항 도달 확률 표
5. 지표 요약 리스트(한국어 1~2줄씩) + 추세 배지
6. 유사 패턴 상위 5개(날짜·유사도·이후 수익률)
7. 신뢰성 카드: 50/80/95% 구간 실제 포함률, 조정 여부
8. 하단 고정 안내문
- 다크 모드(시스템 따름 + 토글), safe-area 대응, PWA(manifest, apple-touch-icon, standalone, 서비스워커: 앱 셸 캐시 + 데이터는 network-first)
- lightweight-charts는 vendor 파일로 동봉(외부 CDN 의존 없음), TradingView 저작자 표시 유지.

### 배포·자동 업데이트
- `update.yml`: cron `7 * * * *`(정각 혼잡 회피) + 수동 실행 → Python 설치 → `python -m engine.run` → `site/`를 `actions/upload-pages-artifact` + `actions/deploy-pages`로 배포. **데이터는 커밋하지 않음**(저장소 이력 비대화 방지).
- 주의: public 저장소도 60일간 커밋이 없으면 예약 워크플로가 자동 비활성화됨 → 월 1회 `keepalive` 빈 커밋(또는 workflow enable API 호출) 스텝 추가.
- `test.yml`: push 시 pytest. `probe.yml`: 수동 실행으로 데이터 소스 실측.
- 접속 주소: `https://gozipgo.github.io/crypto-forecast/`

---

## 단계별 진행 (각 단계 끝에 결과 보고 → 커밋 → push)
① 조사·설계(이 문서) — 승인 후: `winget install Python.Python.3.12`, `git init`, `gh repo create gozipgo/crypto-forecast --public`, README 골격·LICENSE·스키마 초안 커밋
② 데이터 수집·지표: sources 폴백 체인, probe 워크플로를 Actions에서 실행해 미국 러너 결과 확인, 지표·레벨·추세·한국어 요약, pytest
③ 확률 모델·백테스트: MC/analog/ensemble, walk-forward 보정도, 폭 배율 조정 → 조정 전/후 수치 보고
④ 모바일 화면: 위 화면 구성, PWA, 다크 모드
⑤ 배포: Pages 활성화, update.yml 매시간, keepalive, README 완성

## 검증 방법
- `pytest`: 지표값을 손계산/알려진 값과 비교, 백테스트 look-ahead 방지 테스트, 생성 JSON이 스키마에 맞는지
- 로컬 실행: `python -m engine.run --out site/data` → `python -m http.server 8000 -d site` → `http://localhost:8000`
- PC에서 아이폰 크기 확인: Chrome/Edge F12 → 기기 툴바(Ctrl+Shift+M) → iPhone 14/15 Pro 선택. 실제 아이폰: 같은 Wi-Fi에서 `http://<PC IP>:8000` 접속(Windows 방화벽 허용 필요)
- 배포 후: Actions 실행 로그로 소스·소요시간 확인, 아이폰 사파리 접속 → 공유 → 홈 화면에 추가 → 앱처럼 열리는지, 업데이트 시각이 매시간 바뀌는지 확인
