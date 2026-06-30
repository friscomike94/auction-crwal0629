# 법원경매 아파트 물건 수집기

의정부지방법원 관할 아파트 경매물건 중 유찰 1회 이상인 건을 자동 수집하여 CSV로 저장합니다.

## 수집 대상

- **법원**: 의정부지방법원
- **용도**: 아파트 (건물 > 주거용건물 > 아파트)
- **조건**: 유찰횟수 1회 이상
- **출처**: [대한민국 법원경매정보](https://www.courtauction.go.kr)

## 결과 파일

`auction_list.csv` — 사건번호, 물건소재지, 감정가, 최저가, 유찰횟수

## 사용법

```bash
pip3 install playwright
python3 -m playwright install chromium

python3 scrape_uijeongbu_apt.py
# → auction_list.csv 생성
```

## 기술 스택

- **Playwright** (로컬 브라우저 경유 — 사이트가 외부 IP 직접 호출을 차단함)
- **스텔스 모드** (`--disable-blink-features=AutomationControlled`) — WebSquare 프레임워크의 headless 감지 우회
- **파이프라인 플러시 패턴** — API 응답이 1~2 클릭 뒤에 도착하는 딜레이 처리
