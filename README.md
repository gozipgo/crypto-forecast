# crypto-forecast

BTC·ETH 기술적 분석과 7/14/30일 가격 **확률 분포(fan chart)** 를 보여 주는 웹앱입니다.
아이폰 사파리(홈 화면 추가 시 앱처럼 동작)를 우선으로 만들었습니다.

> ⚠️ 투자 조언이 아니며, 확률은 과거 데이터에 기반한 통계적 추정입니다.

## 진행 상황
- [x] ① 조사·설계 — [docs/DESIGN.md](docs/DESIGN.md)
- [x] ② 데이터 수집과 지표 계산
- [x] ③ 확률 모델과 백테스트
- [x] ④ 모바일 화면
- [ ] ⑤ 배포

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
- BTC/ETH 탭, 봉(1시간/4시간/일), 예측 기간(7/14/30일), 모델(혼합/몬테카를로/유사 패턴) 전환. 선택은 기기에 기억됩니다.
- 차트: 캔들·MA20/50/200·거래량·지지/저항선 + 오른쪽 미래 구간에 **확률 전개(95/80/50% 음영, 점선=중앙값)**. 두 손가락 확대, 좌우 이동, 누르면 그 시점의 값(미래 구간이면 분위수) 표시.
- 색은 한국식: **상승 빨강, 하락 파랑**.
- 카드: 시나리오 확률, 모델 비교, 지지/저항 도달 확률, 지표 요약(선택한 봉 기준), 가장 비슷했던 과거 5개, 신뢰성(백테스트 포함률).
- PWA: 사파리 공유 → **홈 화면에 추가** 하면 주소창 없이 앱처럼 열립니다. 아이콘은 `scripts/make_icons.py`로 생성.
- 차트 라이브러리: TradingView Lightweight Charts v5.2.1 (Apache-2.0, `site/vendor/`에 라이선스 포함).
