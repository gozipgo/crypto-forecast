# crypto-forecast

BTC·ETH 기술적 분석과 7/14/30일 가격 **확률 분포(fan chart)** 를 보여 주는 웹앱입니다.
아이폰 사파리(홈 화면 추가 시 앱처럼 동작)를 우선으로 만들었습니다.

> ⚠️ 투자 조언이 아니며, 확률은 과거 데이터에 기반한 통계적 추정입니다.

## 진행 상황
- [x] ① 조사·설계 — [docs/DESIGN.md](docs/DESIGN.md)
- [x] ② 데이터 수집과 지표 계산
- [ ] ③ 확률 모델과 백테스트
- [ ] ④ 모바일 화면
- [ ] ⑤ 배포

## 구조 (요약)
- `engine/` — 계산(데이터 수집 → 지표 → 확률 모델 → 백테스트 → JSON). Python.
- `site/` — 화면. JSON을 **읽기만** 하는 정적 HTML/JS.
- `schema/`, `docs/SCHEMA.md` — 결과 JSON 형식(버전 관리). SwiftUI 앱·위젯도 같은 JSON 사용.

자세한 실행 방법과 JSON 형식은 단계가 진행되면서 채워집니다.

## 데이터 소스 (API 키 불필요, 실패 시 자동으로 다음 소스)
| 순위 | 소스 | 로컬(한국) | GitHub Actions(미국) | 비고 |
|---|---|---|---|---|
| 1 | data-api.binance.vision | ✅ | ✅ | USDT, 2017-08~ 일봉 전체 |
| 2 | Coinbase Exchange | ✅ | ✅ | USD, 4h는 1h를 재집계 |
| 3 | Kraken | ✅ | ✅ | 최근 720봉만 |
| 4 | CoinGecko | ✅ | ✅ | 일봉만(종가 기반) |
| – | api.binance.com | ❌ | ❌ 451 차단 | 사용 안 함 |

`scripts/probe_sources.py`(Actions의 `probe-sources` 워크플로)로 언제든 다시 실측할 수 있습니다.
