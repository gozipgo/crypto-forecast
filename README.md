# crypto-forecast

BTC·ETH 기술적 분석과 7/14/30일 가격 **확률 분포(fan chart)** 를 보여 주는 웹앱입니다.
아이폰 사파리(홈 화면 추가 시 앱처럼 동작)를 우선으로 만들었습니다.

**접속 주소: https://gozipgo.github.io/crypto-forecast/** (1시간마다 자동 업데이트)

> ⚠️ 투자 조언이 아니며, 확률은 과거 데이터에 기반한 통계적 추정입니다.

## 진행 상황
- [x] ① 조사·설계 — [docs/DESIGN.md](docs/DESIGN.md)
- [x] ② 데이터 수집과 지표 계산
- [x] ③ 확률 모델과 백테스트
- [x] ④ 모바일 화면
- [x] ⑤ 배포

## 구조 (요약)
- `engine/` — 계산(데이터 수집 → 지표 → 확률 모델 → 백테스트 → JSON). Python.
- `site/` — 화면. JSON을 **읽기만** 하는 정적 HTML/JS.
- `schema/`, `docs/SCHEMA.md` — 결과 JSON 형식(버전 관리). SwiftUI 앱·위젯도 같은 JSON 사용.


## 로컬에서 실행
```powershell
# 1) 준비 (처음 한 번)
py -3.12 -m venv .venv            # 또는: python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt

# 2) 데이터 수집·계산 → site/data/*.json  (약 20초)
.venv\Scripts\python -m engine.run --out site/data
#    개발 중 반복 실행 시 캔들 캐시(분): --cache 60

# 3) 화면 띄우기
.venv\Scripts\python -m http.server 8000 -d site
#    → 브라우저에서 http://localhost:8000

# 테스트
.venv\Scripts\python -m pytest -q
```

### PC에서 아이폰 화면 크기로 보기
1. Chrome 또는 Edge에서 `http://localhost:8000` 열기
2. `F12` → `Ctrl+Shift+M`(기기 툴바) → 상단 기기 목록에서 **iPhone 14 Pro Max / iPhone 12 Pro** 등 선택
3. 다크 모드 확인: 개발자 도구 `Ctrl+Shift+P` → "Rendering" → *Emulate CSS prefers-color-scheme: dark* (또는 화면 오른쪽 위 테마 버튼)

### 실제 아이폰에서 (같은 Wi-Fi)
1. PC IP 확인: `ipconfig` → IPv4 주소(예: 192.168.0.12)
2. `python -m http.server 8000 -d site --bind 0.0.0.0` 로 실행, Windows 방화벽에서 Python 허용
3. 아이폰 사파리에서 `http://192.168.0.12:8000`

## 데이터 소스 (API 키 불필요, 실패 시 자동으로 다음 소스)
| 순위 | 소스 | 로컬(한국) | GitHub Actions(미국) | 비고 |
|---|---|---|---|---|
| 1 | data-api.binance.vision | ✅ | ✅ | USDT, 2017-08~ 일봉 전체 |
| 2 | Coinbase Exchange | ✅ | ✅ | USD, 4h는 1h를 재집계 |
| 3 | Kraken | ✅ | ✅ | 최근 720봉만 |
| 4 | CoinGecko | ✅ | ✅ | 일봉만(종가 기반) |
| – | api.binance.com | ❌ | ❌ 451 차단 | 사용 안 함 |

`scripts/probe_sources.py`(Actions의 `probe-sources` 워크플로)로 언제든 다시 실측할 수 있습니다.

## 확률 모델
| 모델 | 방법 |
|---|---|
| 몬테카를로 | 필터드 히스토리컬 시뮬레이션: 과거 일간 수익률을 EWMA 변동성으로 표준화 → 5일 블록 부트스트랩 → 현재 변동성(장기 평균으로 서서히 회귀)으로 재스케일. 10,000 경로, 정규분포 가정 없음 |
| 유사 패턴 | 수익률(5/20/60일)·이동평균 괴리·RSI·MACD·볼린저 %b·거래량·변동성 국면 12개 특징으로 과거에서 가장 비슷한 50일을 찾고, 그 뒤 30일 실제 경로를 변동성 비율로 스케일해 분포화 |
| 혼합 | 두 모델 경로를 50:50으로 섞음 |
| 장기(주봉·월봉, 최대 5년) | 일간 수익률을 90일 블록째로 복원추출(강세·약세 국면 덩어리 보존), 변동성은 최근 2년 수준, 추세 0. 4,000개 5년 경로 |

### 5년 시나리오 (주봉·월봉 화면)
5년 경로들을 3개월 간격 모양으로 **5개 묶음**(k-means)으로 나누고, 가장 큰 묶음 2개를 **가상 캔들**로 그립니다.
- 확률 = 그 모양 묶음에 속한 경로 비율(그 경로가 그대로 일어날 확률이 아님). 5개 묶음 비율은 모두 카드에 표시됩니다.
- 가상 캔들 = 묶음 중심에 가장 가까운 실제 시뮬레이션 경로 1개(그 묶음의 '예시').
- **추세 가정 3가지**를 화면에서 전환합니다. 경로의 흔들림은 같고 방향성만 다릅니다.
  - 줄인 추세(기본): 최근일수록 크게 반영한 과거 평균(반감기 3년)의 절반. 현재 BTC 연 +10%, ETH 연 +4%
  - 추세 0: 중앙값이 현재가 근처
  - 과거 추세 그대로: 2017년 이후 평균(BTC 연 +34%, ETH 연 +21%). 초기 급성장기 포함이라 낙관적
  - 추세를 바꿔도 묶음 비율은 같고(모든 경로가 같은 기울기로 움직임) 각 묶음의 가격 수준과 이름이 바뀝니다.
  - 3개월~1년 백테스트를 가정별로 비교해 보여 줍니다("실제 > 중앙값" 비율이 50%에 가까울수록 치우침이 적음).
- 반감기 주기는 반영하지 않습니다.
- 3개월~1년은 백테스트 포함률을 보여 주고, 3년·5년은 비교할 과거가 부족해 검증하지 않습니다.
- 주봉·월봉 화면은 가격축이 로그 눈금입니다.

### 차트로 본 시나리오 2개 (모든 봉)
통계 음영과 별도로, **차트 기술적 분석 규칙만으로** 앞으로의 경로를 주 시나리오·대안 시나리오 2개로 그리고 가상 캔들로 보여 줍니다
(1시간·4시간·일봉: 30일, 주봉: 1년, 월봉: 5년). 엔진: `engine/ta_scenarios.py`.
1. **스윙 찾기**: ATR의 2~3배 이상 움직인 고점·저점만 남기는 지그재그. 고점·저점이 높아지는지 낮아지는지로 다우 이론 구조 판정.
2. **근거 점수**: 이동평균 배열, 가격 vs 50선, 50선 기울기, 고점·저점 구조, MACD, RSI, 볼린저 중심선, 거래량 쏠림 → 상승/하락/중립.
   한쪽이 뚜렷하면 주 시나리오 = 추세 지속, 대안 = 추세 전환. 애매하면 주 = 박스권, 대안 = 박스 돌파.
3. **경로 그리기**: 되돌림 중이면 피보나치 38.2~61.8% 안의 지지(겹치는 가격 우선)까지 눌림 → 지지·저항, 측정 이동(직전 파동 폭), 피보나치 1.618 확장으로 만든
   목표가(최대 3개)를 차례로 → 목표 뒤에는 돌파한 가격대 재시험(역할 전환) 또는 피보나치 되돌림(50/38.2/61.8% 교대) → 목표를 다 쓰면 횡보.
   파동 하나의 폭과 걸리는 봉 수는 그 봉의 최근 스윙 평균을 따르고, 캔들마다 최근 변동성만큼 흔들림을 넣습니다.
4. **무효화 가격**: 직전 스윙 저점(상승)·고점(하락) — 다우 이론에서 추세가 깨지는 곳. 너무 멀면 가까운 반대편 가격대.
5. **정직하게 보여 주기**: 근거 수는 확률이 아니므로, 통계 모델로 "1차 목표가 무효화보다 먼저 닿을 확률"을 함께 표시하고,
   과거 백테스트(주 시나리오 1차 목표가 먼저 닿은 비율 vs 무작위 기준)를 보여 줍니다. 2026-11 기준 BTC 일봉 73% vs 무작위 69%, 주봉 69% vs 64%,
   4시간봉은 무작위와 비슷 — 기술적 시나리오의 우위는 크지 않습니다.

참고 자료: [StockCharts ChartSchool – 지지와 저항](https://chartschool.stockcharts.com/table-of-contents/chart-analysis/support-and-resistance),
[측정 이동](https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-patterns/measured-move-bullish),
[피보나치 되돌림](https://chartschool.stockcharts.com/table-of-contents/chart-analysis/fibonacci-retracements),
[Fidelity – 지지·저항 역할 전환](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/support-and-resistance),
[다우 이론 추세](https://www.incrediblecharts.com/technical/dow_theory_trends.php), Murphy의 [기술적 분석 10원칙](https://stockcharts.com/ten-laws/murphys-ten-laws.pdf).

## 신뢰성 검증(백테스트)
2019-01부터 3일 간격 워크포워드(그 시점까지의 데이터만 사용, 테스트로 미래 정보 누수 없음을 확인).
50/80/95% 구간에 실제 가격이 들어간 비율을 화면에 표시합니다.

**조정 내용:** 몬테카를로는 50% 구간이 너무 넓고(실제 55~57%) 95% 구간은 약간 좁았습니다(94%).
폭을 한 배율로 줄이면 95%가 더 나빠져서, **대칭 분위수 재보정**을 씁니다. 목표 c% 구간을 그릴 때
과거에 실제로 c%가 들어갔던 원래 모델의 구간을 대신 씁니다(예: 50% 구간 → 원래의 44% 구간).
앞 절반 기간으로 맞추고 뒤 절반에서 나아질 때만 적용하며, 중앙값은 건드리지 않습니다.
자세한 수치는 화면의 '신뢰성' 카드와 `forecast.json`의 `calibration`에 있습니다.

## JSON 형식
[docs/SCHEMA.md](docs/SCHEMA.md) 참고.

## 화면
- BTC/ETH 탭, 봉(1시간/4시간/일/주/월), 예측 기간(1시간~일봉: 7/14/30일, 주봉: 3개월/6개월/1년, 월봉: 1년/3년/5년), 모델(단기) 또는 시나리오(장기) 전환. 선택은 기기에 기억됩니다.
- 주소로 보기 지정: `?asset=ETH&tf=1M&h=1826&scen=ta0` (scen: ta0=차트 주 시나리오, ta1=대안, st0/st1=통계 묶음 1·2번(주봉·월봉), off=음영만)
- 차트: 캔들·MA20/50/200·거래량·지지/저항선 + 오른쪽 미래 구간에 **확률 전개(95/80/50% 음영, 점선=중앙값)**. 두 손가락 확대, 좌우 이동, 누르면 그 시점의 값(미래 구간이면 분위수) 표시.
- 색은 한국식: **상승 빨강, 하락 파랑**.
- 카드: 차트로 본 시나리오 2개(경유점·목표·무효화·근거·백테스트), 시나리오 확률, 모델 비교, 지지/저항 도달 확률, 지표 요약(선택한 봉 기준), 가장 비슷했던 과거 5개, 신뢰성(백테스트 포함률).
- PWA: 사파리 공유 → **홈 화면에 추가** 하면 주소창 없이 앱처럼 열립니다. 아이콘은 `scripts/make_icons.py`로 생성.
- 차트 라이브러리: TradingView Lightweight Charts v5.2.1 (Apache-2.0, `site/vendor/`에 라이선스 포함).

## 배포와 자동 업데이트 (비용 0원, API 키 없음)
- `.github/workflows/update.yml`: 매시 7분(UTC)마다 계산 → `site/`를 GitHub Pages로 배포. 수동 실행: Actions 탭 → *update-and-deploy* → *Run workflow*.
- 결과 JSON은 커밋하지 않고 Pages에만 올립니다. 계산이 실패하면 배포하지 않으므로 직전 결과가 그대로 유지되고, 화면에 "업데이트가 늦어지고 있어요"가 표시됩니다(2.5시간 초과 시).
- GitHub는 60일간 커밋이 없으면 예약 실행을 끕니다 → 같은 워크플로의 `keepalive` 작업이 하루 한 번 다시 활성화합니다.
- GitHub 예약 실행은 혼잡 시 수 분~수십 분 늦어질 수 있습니다.
- 다른 워크플로: `test`(push마다 pytest), `probe-sources`(데이터 소스 실측, 수동).

## 폴더 구조
```
engine/            계산 (Python)
  sources/         데이터 소스 + 폴백 체인
  indicators.py    MA·RSI·MACD·볼린저·ATR·ADX·거래량
  levels.py        지지/저항   trend.py 추세   narrative.py 한국어 요약
  ta_scenarios.py  차트 기술적 분석 시나리오 2개 + 가상 캔들
  models/          montecarlo.py · analog.py · ensemble.py · common.py
  backtest.py      워크포워드 보정도 + 재보정
  schema.py        JSON 스키마 검증     run.py 진입점
site/              화면 (정적 HTML/JS, data/ 는 생성물)
schema/            JSON Schema (배포 시 site/schema/ 로 공개)
docs/              DESIGN.md(조사·설계), SCHEMA.md(JSON 형식)
scripts/           probe_sources.py, make_icons.py
tests/             pytest
```

## SwiftUI 앱·위젯에서 쓰기
- 위젯: `https://gozipgo.github.io/crypto-forecast/data/summary.json` (1KB 내외)
- 앱: `manifest.json` → `{자산}/forecast.json`, `{자산}/candles_{1h,4h,1d}.json`
- `schema_version`의 major가 1이 아니면 업데이트 안내. 필드 설명은 [docs/SCHEMA.md](docs/SCHEMA.md).

## 참고한 오픈소스
[docs/DESIGN.md](docs/DESIGN.md)의 조사표 참고. 코드를 가져다 쓴 것은 TradingView Lightweight Charts(Apache-2.0)뿐이고, 나머지는 방법·아이디어만 참고했습니다.
