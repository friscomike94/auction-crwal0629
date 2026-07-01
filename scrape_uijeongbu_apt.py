#!/usr/bin/env python3
"""
법원경매 물건 수집기 (courtauction.go.kr)

사용 예:
  python3 scrape_uijeongbu_apt.py
  python3 scrape_uijeongbu_apt.py -t templates/uijeongbu_yangju_apt.json
  python3 scrape_uijeongbu_apt.py -t templates/nambu_geumcheon_dasedae.json
  python3 scrape_uijeongbu_apt.py --court 서울중앙지방법원 --scl 아파트 --flbd-min 2회
  python3 scrape_uijeongbu_apt.py -t templates/uijeongbu_apt.json --sgg 포천시
"""

import argparse
import csv
import json
import os
import re
import time
from playwright.sync_api import sync_playwright

TARGET_URL = "https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml"
COLUMNS = ['사건번호', '물건소재지', '전용면적', '감정가', '최저가', '저감율', '유찰횟수', '매각기일']
AREA_RE = re.compile(r'([\d,]+(?:\.\d+)?)\s*㎡')

# 법원 그룹 — 여러 법원을 한 번에 순차 검색
COURT_GROUPS = {
    '서울전체': [
        '서울중앙지방법원', '서울동부지방법원', '서울남부지방법원',
        '서울북부지방법원', '서울서부지방법원',
    ],
    '경기전체': [
        '의정부지방법원', '수원지방법원', '인천지방법원',
        '성남지원', '부천지원', '고양지원', '안산지원', '안양지원',
    ],
}


DEFAULTS = {
    'court':     '의정부지방법원',
    'sido':      None,
    'sgg':       None,
    'lcl':       '건물',
    'mcl':       '주거용건물',
    'scl':       '아파트',
    'flbd_min':  '1회',
    'max_price': None,
    'output':    None,
}


def parse_args():
    parser = argparse.ArgumentParser(description='법원경매 물건 수집기')
    parser.add_argument('-t', '--template', default=None,        help='템플릿 JSON 파일 경로 (templates/*.json)')
    parser.add_argument('--court',          default=None,        help='법원명 ("전체" 입력 시 전국)')
    parser.add_argument('--sido',           default=None,        help='시/도 (예: 서울특별시)')
    parser.add_argument('--sgg',            default=None,        help='시/군/구 (예: 금천구)')
    parser.add_argument('--lcl',            default=None,        help='용도 대분류')
    parser.add_argument('--mcl',            default=None,        help='용도 중분류')
    parser.add_argument('--scl',            default=None,        help='용도 소분류 ("전체" 입력 시 생략)')
    parser.add_argument('--flbd-min',       default=None,        help='유찰횟수 최솟값 ("전체" 입력 시 생략)')
    parser.add_argument('--max-price',      default=None, type=int, help='최저가 상한 (원 단위, 예: 500000000)')
    parser.add_argument('-o', '--output',   default=None,        help='출력 CSV 파일명 (기본: 자동 생성)')
    args = parser.parse_args()

    # 우선순위: CLI 인자 > 템플릿 > 기본값
    merged = dict(DEFAULTS)
    if args.template:
        tpl_path = args.template
        if not os.path.isabs(tpl_path):
            tpl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), tpl_path)
        with open(tpl_path, encoding='utf-8') as f:
            merged.update(json.load(f))
        print(f"▶ 템플릿 로드: {args.template}")
    for key in ['court', 'sido', 'sgg', 'lcl', 'mcl', 'scl', 'output', 'max_price']:
        if getattr(args, key) is not None:
            merged[key] = getattr(args, key)
    if args.flbd_min is not None:
        merged['flbd_min'] = args.flbd_min

    # argparse Namespace로 변환
    for key, val in merged.items():
        setattr(args, key, val)
    return args


def make_output_path(args):
    if args.output:
        return args.output
    court = args.court.replace('지방법원', '').replace('전체', '전국')
    # --sido가 쉼표로 여러 지역일 경우 축약
    if args.sido:
        sido_parts = [s.strip().replace('특별시','').replace('광역시','').replace('특별자치도','').replace('도','') for s in args.sido.split(',')]
        area = '+'.join(sido_parts)
    else:
        area = args.sgg or ''
    scl   = args.scl if args.scl != '전체' else args.mcl
    flbd  = args.flbd_min.replace('전체', '전체유찰')
    price = f'최저{args.max_price//100000000}억이하' if args.max_price else ''
    parts = [p for p in [court, area, scl, f'유찰{flbd}', price] if p]
    name  = f"auction_{'_'.join(parts)}.csv"
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
    # printCsNo 는 중복사건(<br/>...(중복))까지 포함한 완전한 표기
    p = item.get('printCsNo', '')
    if p:
        return ' '.join(p.replace('<br/>', ' ').split())
    court = item.get('jiwonNm', '').strip()
    case  = item.get('srnSaNo', '').strip()
    return f"{court} {case}".strip() if court else case or str(item.get('saNo', ''))


def low_price(item):
    """현재 최저매각가격. notifyMinmaePrice1 이 정답(minmaePrice 는 최초가=감정가인 경우가 많음)."""
    v = item.get('notifyMinmaePrice1') or item.get('minmaePrice') or 0
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def fmt_giil(v):
    s = str(v or '')
    return f"{s[:4]}.{s[4:6]}.{s[6:]}" if len(s) == 8 else s


def parse_area(item):
    """전용면적(㎡) — convAddr/areaList/pjbBuldList 의 ㎡ 값 중 최댓값."""
    src = ' '.join(str(item.get(k, '') or '') for k in ('convAddr', 'areaList', 'pjbBuldList'))
    vals = [float(m.replace(',', '')) for m in AREA_RE.findall(src)]
    return max(vals) if vals else None


def convert_item(item):
    rate = item.get('notifyMinmaePriceRate1', '')
    area = parse_area(item)
    return {
        '사건번호':   build_case_no(item),
        '물건소재지': (item.get('printSt', '') or '').strip() or build_address(item),
        '전용면적':   f"{area:g}㎡" if area else '',
        '감정가':     fmt_money(item.get('gamevalAmt', '')),
        '최저가':     fmt_money(low_price(item)),
        '저감율':     f"{rate}%" if rate not in (None, '') else '',
        '유찰횟수':   str(item.get('yuchalCnt', '')),
        '매각기일':   fmt_giil(item.get('maeGiil', '')),
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
    result = page.evaluate(f"""
    () => {{
        const sel = document.getElementById('{el_id}');
        if (!sel) return {{ok: false, err: 'not found'}};
        const opts = Array.from(sel.options);
        const opt  = opts.find(o => o.value === '{value}' || o.text === '{value}' || o.text.includes('{value}'));
        if (!opt) return {{ok: false, opts: opts.map(o => o.text)}};
        sel.value = opt.value;
        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
        return {{ok: true, text: opt.text}};
    }}
    """)
    if not result.get('ok'):
        print(f"  [경고] {el_id} 에서 '{value}' 없음. 옵션: {result.get('opts', [])}")
    return result.get('ok', False)


def load_search_form(page):
    """검색 폼 페이지 로드 + WebSquare 초기화 대기 (매 검색 전 폼 리셋용)."""
    page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_function(
            "() => !!document.getElementById('mf_wfm_mainFrame_btn_gdsDtlSrch')",
            timeout=60000
        )
    except Exception as e:
        print(f"  [경고] 초기화 대기 실패: {e}")
        time.sleep(15)
    time.sleep(2)


def run_search(page, args, court, response_flag):
    """단일 법원에 대해 검색 조건 설정 → 검색 실행 → 페이지네이션 수집."""
    # 검색 후 폼이 결과 화면으로 바뀌므로 매 법원마다 폼을 새로 로드
    load_search_form(page)

    print(f"\n▶ [{court or '전체'}] 검색 조건 설정...")

    # 법원
    if court and court != '전체':
        set_select(page, 'mf_wfm_mainFrame_sbx_rletCortOfc', court)
        print(f"  법원: {court}")

    # 유찰횟수
    if args.flbd_min != '전체':
        set_select(page, 'mf_wfm_mainFrame_sbx_rletFlbdCntMin', args.flbd_min)
        print(f"  유찰횟수: {args.flbd_min} 이상")

    # 지역 (시/도 → 시/군/구 순서)
    if args.sido:
        set_select(page, 'mf_wfm_mainFrame_sbx_rletAdongSdS', args.sido)
        time.sleep(2)
        print(f"  시/도: {args.sido}")
    if args.sgg:
        set_select(page, 'mf_wfm_mainFrame_sbx_rletAdongSggS', args.sgg)
        print(f"  시/군/구: {args.sgg}")
        time.sleep(1)

    # 용도 대분류 > 중분류 > 소분류
    set_select(page, 'mf_wfm_mainFrame_sbx_rletLclLst', args.lcl)
    time.sleep(3)
    set_select(page, 'mf_wfm_mainFrame_sbx_rletMclLst', args.mcl)
    time.sleep(3)
    if args.scl != '전체':
        set_select(page, 'mf_wfm_mainFrame_sbx_rletSclLst', args.scl)
    print(f"  용도: {args.lcl} > {args.mcl}" + (f" > {args.scl}" if args.scl != '전체' else ''))
    time.sleep(1)

    # 검색 실행
    print("▶ 검색 실행...")
    response_flag[0] = False
    page.evaluate("() => { document.getElementById('mf_wfm_mainFrame_btn_gdsDtlSrch').click(); }")
    for _ in range(30):
        time.sleep(1)
        if response_flag[0]:
            response_flag[0] = False
            break
    time.sleep(2)

    # 페이지네이션
    max_page = get_max_page(page)
    print(f"▶ 총 {max_page}페이지")
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


def main():
    args   = parse_args()
    output = make_output_path(args)

    # 법원 그룹 확장 (서울전체 / 경기전체) 또는 쉼표 구분 다중 법원
    if args.court in COURT_GROUPS:
        courts = COURT_GROUPS[args.court]
        print(f"▶ 법원 그룹 '{args.court}' → {len(courts)}개 법원 순차 검색")
    elif args.court and ',' in args.court:
        courts = [c.strip() for c in args.court.split(',')]
    else:
        courts = [args.court]

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

        # ── 법원별 순차 검색 (각 검색 전 폼 리로드) ────────────────────
        for court in courts:
            run_search(page, args, court, response_flag)

        browser.close()

    # 사건번호 기준 중복 제거 (그룹 검색 시 안전장치)
    seen, deduped = set(), []
    for it in all_items:
        key = build_case_no(it)
        if key and key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    if len(deduped) < len(all_items):
        print(f"  중복 제거: {len(all_items)}개 → {len(deduped)}개")
    all_items = deduped

    print(f"\n▶ 최종 수집: {len(all_items)}개")

    if not all_items:
        print("❌ 데이터 없음")
        return

    # 후처리 필터
    filtered = all_items
    if args.sido:
        sidos = [s.strip() for s in args.sido.split(',')]
        filtered = [i for i in filtered if any(s in i.get('hjguSido', '') for s in sidos)]
        if len(filtered) < len(all_items):
            print(f"  시/도 필터: {len(all_items)}개 → {len(filtered)}개 ({args.sido})")
    if args.sgg:
        before = len(filtered)
        filtered = [i for i in filtered if args.sgg in i.get('hjguSigu', '')]
        if len(filtered) < before:
            print(f"  시/군/구 필터: {before}개 → {len(filtered)}개 ({args.sgg})")
    if args.max_price:
        before = len(filtered)
        filtered = [i for i in filtered if low_price(i) <= args.max_price]
        print(f"  최저가 필터: {before}개 → {len(filtered)}개 (≤ {args.max_price:,}원)")

    rows = [convert_item(item) for item in filtered]
    with open(output, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ {len(rows)}행 → {output}")
    print("\n[미리보기]")
    for i, r in enumerate(rows[:10], 1):
        print(f"  [{i:02d}] 사건번호: {r['사건번호']}")
        print(f"       소재지:   {r['물건소재지']}")
        print(f"       감정가:   {r['감정가']}  /  최저가: {r['최저가']} ({r['저감율']})  /  유찰: {r['유찰횟수']}회  /  매각: {r['매각기일']}")
        print()


if __name__ == '__main__':
    main()
