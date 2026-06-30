#!/usr/bin/env python3
"""
법원경매 물건 목록 스크래퍼 (court-auction-scraper 스킬 번들)
=============================================================
검증된 작동 버전. 2026-06-29 세션에서 19번의 시행착오 끝에 완성.

주요 패턴:
  - Playwright + stealth (headless 감지 우회)
  - wait_for_function (WebSquare 초기화 감지)
  - page.evaluate() JS 클릭 (로케이터 대신)
  - 파이프라인 플러시 (응답 1~2 클릭 딜레이 처리)

사용법:
  pip3 install playwright --break-system-packages
  python3 -m playwright install chromium
  python3 scrape_auction.py

출력: auction_list.csv (사건번호, 물건소재지, 감정가, 최저가, 유찰횟수)

조건 변경: OUTPUT, cortOfcCd(법원코드), bidBgngYmd/bidEndYmd(입찰기간) 수정
"""

import csv
import time
from playwright.sync_api import sync_playwright

TARGET_URL = "https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml"
OUTPUT = "/Users/leomyung/auction_list.csv"
COLUMNS = ['사건번호', '물건소재지', '감정가', '최저가', '유찰횟수']

def fmt_money(val):
    try:
        return f"{int(val):,}원"
    except Exception:
        return str(val)

def build_address(item):
    parts = [item.get('hjguSido',''), item.get('hjguSigu',''),
             item.get('hjguDong',''), item.get('daepyoLotno','')]
    addr = ' '.join(p for p in parts if p.strip())
    extra = item.get('convAddr','').strip()
    return (addr + (' ' + extra if extra else '')).strip()

def build_case_no(item):
    court = item.get('jiwonNm','').strip()
    case  = item.get('srnSaNo','').strip()
    return f"{court} {case}".strip() if court else case or str(item.get('saNo',''))

def convert_item(item):
    return {
        '사건번호':  build_case_no(item),
        '물건소재지': build_address(item),
        '감정가':    fmt_money(item.get('gamevalAmt','')),
        '최저가':    fmt_money(item.get('minmaePrice','')),
        '유찰횟수':  str(item.get('yuchalCnt','')),
    }

def get_max_page(page):
    return page.evaluate("""
    () => {
        const links = Array.from(document.querySelectorAll('[id*="pgl_gdsDtlSrchPage_page_"]'));
        const nums = links.map(el => { const m = el.id.match(/_page_(\\d+)$/); return m ? +m[1] : 0; });
        return nums.length ? Math.max(...nums) : 0;
    }
    """)

def main():
    all_items = []
    response_flag = [False]
    last_count = [0]

    def on_response(response):
        if 'searchControllerMain' not in response.url:
            return
        try:
            body = response.json()
            items = body.get('data',{}).get('dlt_srchResult',[])
            if items:
                all_items.extend(items)
                response_flag[0] = True
                last_count[0] = len(items)
                print(f"  [+{len(items)}] 누적 {len(all_items)}개")
        except Exception as e:
            # 브라우저 닫힌 후 응답이 오면 무시
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-features=site-per-process',
                '--lang=ko-KR',
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ko-KR",
            viewport={"width": 1280, "height": 900},
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        # 자동화 감지 우회
        context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        window.chrome = {runtime: {}};
        """)
        page = context.new_page()
        page.on("response", on_response)

        print("▶ 페이지 로딩...")
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)

        # WebSquare 렌더링 완료 대기 (검색 버튼이 나타날 때까지)
        print("▶ WebSquare 초기화 대기 (최대 60초)...")
        try:
            page.wait_for_function(
                "() => !!document.getElementById('mf_wfm_mainFrame_btn_gdsDtlSrch')",
                timeout=60000
            )
            print("  검색 버튼 확인됨")
        except Exception as e:
            print(f"  [경고] 버튼 대기 실패: {e}")
            time.sleep(15)  # fallback 대기

        time.sleep(2)
        page.screenshot(path="/tmp/before_search.png")

        # 검색 버튼 클릭
        print("▶ 검색 실행...")
        click_result = page.evaluate("""
        () => {
            const b = document.getElementById('mf_wfm_mainFrame_btn_gdsDtlSrch');
            if(b) { b.click(); return 'ok: ' + b.value; }
            return 'not found';
        }
        """)
        print(f"  클릭 결과: {click_result}")

        # 첫 페이지 응답 대기 (최대 30초)
        print("▶ 첫 페이지 응답 대기...")
        for _ in range(30):
            time.sleep(1)
            if response_flag[0]:
                response_flag[0] = False
                print(f"  첫 페이지 수신 완료")
                break
        else:
            print("  [경고] 타임아웃 - 계속 진행")

        time.sleep(2)  # DOM 업데이트 대기

        # 페이지 수 확인 (결과가 로드된 후)
        max_page = get_max_page(page)
        print(f"▶ 총 페이지 수: {max_page} (현재 {len(all_items)}개 수집)")

        if max_page == 0:
            print("  [경고] 페이지네이션 없음, 현재 데이터만 저장")
        else:
            # 나머지 페이지 클릭 (1.5초 간격)
            for pg in range(2, max_page + 1):
                response_flag[0] = False
                time.sleep(0.5)

                clicked = page.evaluate(f"""
                () => {{
                    const el = document.getElementById('mf_wfm_mainFrame_pgl_gdsDtlSrchPage_page_{pg}');
                    if(el) {{ el.click(); return true; }}
                    return false;
                }}
                """)
                if not clicked:
                    print(f"  페이지 {pg} 버튼 없음, 중단")
                    break

                # 응답 대기 (최대 15초)
                for _ in range(15):
                    time.sleep(1)
                    if response_flag[0]:
                        break

            # 밀린 응답을 유도하기 위해 마지막 페이지 재클릭 (파이프라인 플러시)
            time.sleep(1)
            response_flag[0] = False
            page.evaluate(f"""
            () => {{
                const el = document.getElementById('mf_wfm_mainFrame_pgl_gdsDtlSrchPage_page_{max_page}');
                if(el) el.click();
            }}
            """)
            print(f"▶ 마지막 응답 대기 (최대 30초)...")
            no_change = 0
            for _ in range(30):
                time.sleep(1)
                if response_flag[0]:
                    response_flag[0] = False
                    no_change = 0
                    print(f"  응답 수신 (누적 {len(all_items)}개)")
                else:
                    no_change += 1
                    if no_change >= 8:
                        print(f"  8초간 신규 응답 없음, 완료")
                        break

        browser.close()

    print(f"\n▶ 최종 수집: {len(all_items)}개")

    if not all_items:
        print("❌ 데이터 없음")
        return

    rows = [convert_item(item) for item in all_items]
    with open(OUTPUT, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ {len(rows)}행 → {OUTPUT}")
    print("\n[미리보기 5행]")
    for r in rows[:5]:
        print(f"  사건번호: {r['사건번호']}")
        print(f"  소재지:   {r['물건소재지']}")
        print(f"  감정가:   {r['감정가']} / 최저가: {r['최저가']} / 유찰: {r['유찰횟수']}회")
        print()

if __name__ == '__main__':
    main()
