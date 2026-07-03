# 법원경매 아파트 물건 수집기

> **Mono Signal 대시보드**: [`docs/index.html`](docs/index.html)
> CSV 수집 결과를 PropTech AI 리포트 형태로 시각화합니다.

의정부지방법원 관할 아파트 경매물건 중 유찰 1회 이상인 건을 자동 수집하여 CSV로 저장합니다.

## 수집 항목

사건번호, 물건소재지, 감정가, 최저가, 유찰횟수 → CSV 저장

## 사용법

```bash
pip3 install playwright
python3 -m playwright install chromium

# 기본 (의정부지방법원 / 아파트 / 유찰 1회 이상)
python3 scrape_uijeongbu_apt.py

# 법원 변경
python3 scrape_uijeongbu_apt.py --court 서울중앙지방법원

# 유찰 조건 변경
python3 scrape_uijeongbu_apt.py --court 수원지방법원 --flbd-min 3회

# 용도 변경 (대분류 > 중분류 > 소분류)
python3 scrape_uijeongbu_apt.py --lcl 건물 --mcl 주거용건물 --scl 연립다세대

# 전국 / 소분류 전체
python3 scrape_uijeongbu_apt.py --court 전체 --scl 전체

# 출력 파일명 지정
python3 scrape_uijeongbu_apt.py --court 인천지방법원 -o incheon_apt.csv
```

### 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `-t` / `--template` | — | 템플릿 JSON 파일 경로 |
| `--court` | 의정부지방법원 | 법원명. `전체` 입력 시 전국 검색 |
| `--sido` | — | 시/도 (예: 서울특별시) |
| `--sgg` | — | 시/군/구 (예: 금천구, 양주시) |
| `--lcl` | 건물 | 용도 대분류 |
| `--mcl` | 주거용건물 | 용도 중분류 |
| `--scl` | 아파트 | 용도 소분류. `전체` 입력 시 중분류까지만 적용 |
| `--flbd-min` | 1회 | 유찰횟수 최솟값. `전체` 입력 시 조건 없음 |
| `-o` / `--output` | 자동 생성 | 출력 CSV 파일명 |

출력 파일명 자동 생성 예: `auction_의정부_양주시_아파트_유찰1회.csv`

### 템플릿

자주 쓰는 검색 조건을 `templates/*.json`으로 저장해 재사용할 수 있습니다.
CLI 인자를 함께 쓰면 템플릿 값을 덮어씁니다.

```bash
# 저장된 조건 그대로 실행
python3 scrape_uijeongbu_apt.py -t templates/uijeongbu_apt.json
python3 scrape_uijeongbu_apt.py -t templates/uijeongbu_yangju_apt.json
python3 scrape_uijeongbu_apt.py -t templates/nambu_geumcheon_dasedae.json

# 템플릿 기반으로 일부 조건만 변경
python3 scrape_uijeongbu_apt.py -t templates/uijeongbu_apt.json --sgg 포천시
python3 scrape_uijeongbu_apt.py -t templates/uijeongbu_apt.json --flbd-min 3회
```

**템플릿 추가 방법** — `templates/` 에 JSON 파일 생성:

```json
{
  "court": "수원지방법원",
  "sgg": "수원시",
  "lcl": "건물",
  "mcl": "주거용건물",
  "scl": "아파트",
  "flbd_min": "2회"
}
```

**우선순위**: CLI 인자 > 템플릿 > 기본값

## 프로젝트 구조

```
auction-crwal0629/
├── scrape_uijeongbu_apt.py        # 메인 스크래퍼 (CLI 인자 지원)
├── auction_list.csv               # 초기 수집 결과 샘플
├── templates/                     # 검색 조건 템플릿
│   ├── uijeongbu_apt.json         # 의정부지방법원 / 아파트 / 유찰1회
│   ├── uijeongbu_yangju_apt.json  # 의정부지방법원 / 양주시 / 아파트 / 유찰1회
│   └── nambu_geumcheon_dasedae.json  # 서울남부 / 금천구 / 다세대주택 / 유찰1회
└── skill/                         # Claude Code 재사용 스킬
    ├── SKILL.md                   # 올바른 패턴, 드롭다운 체계, API 필드 매핑
    ├── references/
    │   └── trial-and-error.md    # 시행착오 12개 케이스 기록
    └── scripts/
        └── scrape_auction.py     # 기본 스크래퍼 번들 (서울중앙지방법원 기준)
```

`skill/` 폴더는 Claude Code 스킬 형식으로 작성된 재사용 가이드입니다.
이 사이트를 처음 접할 때 반복하기 쉬운 실수들(IP 차단, headless 감지, 파이프라인 딜레이 등)을
사전에 방지하기 위해 시행착오와 해결 패턴을 문서화했습니다.

## 기술 스택

- **Playwright** (로컬 브라우저 경유 — 사이트가 외부 IP 직접 호출을 차단함)
- **스텔스 모드** (`--disable-blink-features=AutomationControlled`) — WebSquare 프레임워크의 headless 감지 우회
- **파이프라인 플러시 패턴** — API 응답이 1~2 클릭 뒤에 도착하는 딜레이 처리
