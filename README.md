# 법원경매 아파트 물건 수집기

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
| `--court` | 의정부지방법원 | 법원명. `전체` 입력 시 전국 검색 |
| `--lcl` | 건물 | 용도 대분류 |
| `--mcl` | 주거용건물 | 용도 중분류 |
| `--scl` | 아파트 | 용도 소분류. `전체` 입력 시 중분류까지만 적용 |
| `--flbd-min` | 1회 | 유찰횟수 최솟값. `전체` 입력 시 조건 없음 |
| `-o` / `--output` | 자동 생성 | 출력 CSV 파일명 |

출력 파일명 자동 생성 예: `auction_의정부_아파트_유찰1회.csv`

## 기술 스택

- **Playwright** (로컬 브라우저 경유 — 사이트가 외부 IP 직접 호출을 차단함)
- **스텔스 모드** (`--disable-blink-features=AutomationControlled`) — WebSquare 프레임워크의 headless 감지 우회
- **파이프라인 플러시 패턴** — API 응답이 1~2 클릭 뒤에 도착하는 딜레이 처리
