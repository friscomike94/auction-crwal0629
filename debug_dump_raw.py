#!/usr/bin/env python3
"""의정부 아파트 유찰1회 검색 → 원본 API 필드 전체 덤프.

목적: minmaePrice 외에 '현재 최저매각가격' 을 담은 진짜 필드를 찾는다.
사이트 표시값(70%)과 대조할 것.
"""
import json, time
from playwright.sync_api import sync_playwright

TARGET_URL = "https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml"
TARGETS = ['5529', '89159', '4278', '73443', '73461', '70090']  # 대조할 사건번호 끝자리

raw_items = []

def on_response(response):
    if 'searchControllerMain' not in response.url:
        return
    try:
        body = response.json()
        items = body.get('data', {}).get('dlt_srchResult', [])
        if items:
            raw_items.extend(items)
            print(f"  [+{len(items)}] 누적 {len(raw_items)}")
    except Exception:
        pass

def set_select(page, el_id, value):
    return page.evaluate(f"""
    () => {{
        const sel = document.getElementById('{el_id}');
        if (!sel) return false;
        const opt = Array.from(sel.options).find(o => o.text.includes('{value}') || o.value==='{value}');
        if (!opt) return false;
        sel.value = opt.value; sel.dispatchEvent(new Event('change', {{bubbles:true}})); return true;
    }}""")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        '--no-sandbox','--disable-blink-features=AutomationControlled',
        '--disable-features=site-per-process','--lang=ko-KR'])
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        locale="ko-KR", viewport={"width":1280,"height":900})
    ctx.add_init_script("""
        Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
        Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
        window.chrome={runtime:{}};""")
    page = ctx.new_page()
    page.on("response", on_response)

    page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_function("() => !!document.getElementById('mf_wfm_mainFrame_btn_gdsDtlSrch')", timeout=60000)
    time.sleep(2)

    set_select(page, 'mf_wfm_mainFrame_sbx_rletCortOfc', '의정부지방법원')
    set_select(page, 'mf_wfm_mainFrame_sbx_rletFlbdCntMin', '1회')
    set_select(page, 'mf_wfm_mainFrame_sbx_rletLclLst', '건물'); time.sleep(3)
    set_select(page, 'mf_wfm_mainFrame_sbx_rletMclLst', '주거용건물'); time.sleep(3)
    set_select(page, 'mf_wfm_mainFrame_sbx_rletSclLst', '아파트'); time.sleep(1)

    page.evaluate("() => document.getElementById('mf_wfm_mainFrame_btn_gdsDtlSrch').click()")
    for _ in range(30):
        time.sleep(1)
        if raw_items: break
    time.sleep(3)
    # 페이지 넘겨 파이프라인 플러시
    for pg in range(2, 12):
        page.evaluate(f"() => document.getElementById('mf_wfm_mainFrame_pgl_gdsDtlSrchPage_page_{pg}')?.click()")
        time.sleep(2)
    browser.close()

# 전체 원본 저장
with open('raw_uijeongbu.json', 'w', encoding='utf-8') as f:
    json.dump(raw_items, f, ensure_ascii=False, indent=2)
print(f"\n총 {len(raw_items)}건 → raw_uijeongbu.json")

# 대조 대상만 전체 필드 출력
print("\n===== 대조 대상 물건 전체 필드 =====")
for it in raw_items:
    sano = str(it.get('srnSaNo','')) + str(it.get('saNo',''))
    if any(t in sano or t in str(it.get('userCsNo','')) for t in TARGETS):
        print(f"\n--- {it.get('jiwonNm')} {it.get('srnSaNo') or it.get('saNo')} ---")
        for k, v in sorted(it.items()):
            if v not in (None, '', '0'):
                print(f"   {k} = {v}")
