#!/usr/bin/env python3
"""
법원경매 물건 수집기 (courtauction.go.kr)

사용 예:
  python3 scrape_uijeongbu_apt.py
  python3 scrape_uijeongbu_apt.py --court 서울중앙지방법원 --scl 아파트 --flbd-min 2회
  python3 scrape_uijeongbu_apt.py --court 전체 --mcl 주거용건물 -o results.csv
"""

import argparse
import csv
import os
import time
from playwright.sync_api import sync_playwright

TARGET_URL = "https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml"
COLUMNS = ['사건번호', '물건소재지', '감정가', '최저가', '유찰횟수']


def parse_args():
    parser = argparse.ArgumentParser(description='법원경매 물건 수집기')
    parser.add_argument('--court',    default='의정부지방법원', help='법원명 (기본: 의정부지방법원, "전체" 입력 시 전국)')
    parser.add_argument('--lcl',      default='건물',          help='용도 대분류 (기본: 건물)')
    parser.add_argument('--mcl',      default='주거용건물',     help='용도 중분류 (기본: 주거용건물)')
    parser.add_argument('--scl',      default='아파트',         help='용도 소분류 (기본: 아파트, "전체" 입력 시 생략)')
    parser.add_argument('--flbd-min', default='1회',           help='유찰횟수 최솟값 (기본: 1회, "전체" 입력 시 생략)')
    parser.add_argument('-o', '--output', default=None,        help='출력 CSV 파일명 (기본: 자동 생성)')
    return parser.parse_args()


def make_output_path(args):
    if args.output:
        return args.output
    court = args.court.replace('지방법원', '').replace('전체', '전국')
    scl   = args.scl if args.scl != '전체' else args.mcl
    flbd  = args.flbd_min.replace('전체', '전체유찰')
    name  = f"auction_{court}_{scl}_유찰{flbd}.csv"
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), name)


def fmt_money(val):
    try:
        return f"{int(val):,}원"
    except Exception:
        return str(val)


def build_address(item):
    parts = [item.get('hjguSido', ''), item.get('hjguSigu', ''),
             item.get('hjguDong', ''), item.get('daepyoLotno', '')]
    addr  = ' '.join(p for p in parts if p.strip())
    extra = item.get('convAddr', '').strip()
    full  = (addr + (' ' + extra if extra else '')).strip()
    return ' '.join(full.split())


def build_case_no(item):
    court = item.get('jiwonNm', '').strip()
    case  = item.get('srnSaNo', '').strip()
    return f"{court} {case}".strip() if court else case or str(item.get('saNo', ''))


def convert_item(item):
    return {
        '사건번호':   build_case_no(item),
        '물건소재지': build_address(item),
        '감정가':     fmt_money(item.get('gamevalAmt', '')),
        '최저가':     fmt_money(item.get('minmaePrice', '')),
        '유찰횟수':   str(item.get('yuchalCnt', '')),
    }


def get_max_page(page):
    return page.evaluate("""
    () => {
        const links = Array.from(document.querySelectorAll('[id*="pgl_gdsDtlSrchPage_page_"]'));
        const nums  = links.map(el => { const m = el.id.match(/_page_(\\d+)$/); return m ? +m[1] : 0; });
        return nums.length ? Math.max(...nums) : 0;
    }
    """)


def set_select(page, el_id, value):
    return page.evaluate(f"""
    () => {{
        const sel = document.getElementById('{el_id}');
        if (!sel) return false;
        const opt = Array.from(sel.options).find(o => o.value === '{value}' || o.text === '{value}');
        if (!opt) return false;
        sel.value = opt.value;
        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
        return true;
    }}
    """)


def main():
    args   = parse_args()
    output = make_output_path(args)

    all_items     = []
    response_flag = [False]

    def on_response(response):
        if 'searchControllerMain' not in response.url:
            return
        try:
            body  = response.json()
            items = body.get('data', {}).get('dlt_srchResult', [])
            if items:
                all_items.extend(items)
                response_flag[0] = True
                print(f"  [+{len(items)}] 누적 {len(all_items)}개")
        except Exception:
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
        )
        context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins',  {get: () => [1,2,3,4,5]});
        window.chrome = {runtime: {}};
        """)
        page = context.new_page()
        page.on("response", on_response)

        print("▶ 페이지 로딩...")
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)

        print("▶ WebSquare 초기화 대기...")
        try:
            page.wait_for_function(
                "() => !!document.getElementById('mf_wfm_mainFrame_btn_gdsDtlSrch')",
                timeout=60000
            )
        except Exception as e:
            print(f"  [경고] {e}")
            time.sleep(15)

        time.sleep(2)

        # ── 검색 조건 설정 ────────────────────────────────────────────
        print("▶ 검색 조건 설정...")

        # 법원
        if args.court != '전체':
            set_select(page, 'mf_wfm_mainFrame_sbx_rletCortOfc', args.court)
            print(f"  법원: {args.court}")

        # 유찰횟수
        if args.flbd_min != '전체':
            set_select(page, 'mf_wfm_mainFrame_sbx_rletFlbdCntMin', args.flbd_min)
            print(f"  유찰횟수: {args.flbd_min} 이상")

        # 용도 대분류
        set_select(page, 'mf_wfm_mainFrame_sbx_rletLclLst', args.lcl)
        time.sleep(3)  # 중분류 DOM 업데이트 대기

        # 용도 중분류
        set_select(page, 'mf_wfm_mainFrame_sbx_rletMclLst', args.mcl)
        time.sleep(3)  # 소분류 DOM 업데이트 대기

        # 용도 소분류
        if args.scl != '전체':
            set_select(page, 'mf_wfm_mainFrame_sbx_rletSclLst', args.scl)
        print(f"  용도: {args.lcl} > {args.mcl}" + (f" > {args.scl}" if args.scl != '전체' else ''))

        time.sleep(1)

        # ── 검색 실행 ─────────────────────────────────────────────────
        print("▶ 검색 실행...")
        page.evaluate("() => { document.getElementById('mf_wfm_mainFrame_btn_gdsDtlSrch').click(); }")

        for _ in range(30):
            time.sleep(1)
            if response_flag[0]:
                response_flag[0] = False
                break

        time.sleep(2)

        # ── 페이지네이션 ──────────────────────────────────────────────
        max_page = get_max_page(page)
        print(f"▶ 총 {max_page}페이지 ({len(all_items)}개 수신 중)")

        for pg in range(2, max_page + 1):
            response_flag[0] = False
            time.sleep(0.5)
            clicked = page.evaluate(f"""
            () => {{
                const el = document.getElementById('mf_wfm_mainFrame_pgl_gdsDtlSrchPage_page_{pg}');
                if (el) {{ el.click(); return true; }}
                return false;
            }}
            """)
            if not clicked:
                break
            for _ in range(15):
                time.sleep(1)
                if response_flag[0]:
                    break

        # 파이프라인 플러시
        if max_page > 0:
            response_flag[0] = False
            page.evaluate(f"""
            () => {{
                const el = document.getElementById('mf_wfm_mainFrame_pgl_gdsDtlSrchPage_page_{max_page}');
                if (el) el.click();
            }}
            """)
            no_change = 0
            for _ in range(30):
                time.sleep(1)
                if response_flag[0]:
                    response_flag[0] = False
                    no_change = 0
                else:
                    no_change += 1
                    if no_change >= 8:
                        break

        browser.close()

    print(f"\n▶ 최종 수집: {len(all_items)}개")

    if not all_items:
        print("❌ 데이터 없음")
        return

    rows = [convert_item(item) for item in all_items]
    with open(output, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ {len(rows)}행 → {output}")
    print("\n[미리보기]")
    for r in rows[:10]:
        print(f"  {r['사건번호']} | {r['물건소재지'][:40]} | {r['감정가']} | {r['최저가']} | 유찰{r['유찰횟수']}회")


if __name__ == '__main__':
    main()
