# 법원경매 스크래퍼 제작기 — Claude Code 협업 대화 로그

> **강의 활용 목적**: Claude Code와 실제 웹 스크래핑 프로젝트를 함께 개발한 세션 기록  
> **대화 일시**: 2026-06-29 ~ 2026-07-01  
> **프로젝트**: courtauction.go.kr 경매 물건 자동 수집기

---

## 목차

1. [프로젝트 시작 — 첫 요청](#1-프로젝트-시작)
2. [기술 장벽 발견 — IP 차단과 HeadlessBot 감지](#2-기술-장벽-발견)
3. [Playwright 스텔스 모드 적용](#3-playwright-스텔스-모드)
4. [WebSquare SPA 처리](#4-websquare-spa-처리)
5. [파이프라인 딜레이 문제 해결](#5-파이프라인-딜레이-문제)
6. [코드 정리 및 CLI 도구화](#6-코드-정리-및-cli-도구화)
7. [템플릿 시스템 도입](#7-템플릿-시스템)
8. [후처리 필터 구현](#8-후처리-필터)
9. [한계 발견 — 전국 검색과 임차인 필터](#9-한계-발견)
10. [핵심 학습 포인트](#10-핵심-학습-포인트)

---

## 1. 프로젝트 시작

### 사용자 요청
```
의정부지원 아파트 유찰1회 물건검색
```

### Claude의 접근
- 목표: `courtauction.go.kr`에서 의정부지방법원 아파트 경매물건(유찰 1회 이상) 수집 → CSV 저장
- 수집 항목: 사건번호, 물건소재지, 감정가, 최저가, 유찰횟수

---

## 2. 기술 장벽 발견

### 시도 #1 — requests 직접 호출 (실패)

```python
import requests
r = requests.post(
    "https://www.courtauction.go.kr/pgj/pgjsearch/searchControllerMain.on",
    data={...}
)
```

**결과:**
```json
{"message": "해당 IP는 비정상적인 접속으로 보안정책에 의하여 차단되었습니다."}
```

**원인 분석**: 사이트는 외부 IP의 직접 POST를 차단한다. 세션 쿠키를 먼저 받아도 동일하게 차단.

---

### 시도 #2 — Playwright 기본 headless 모드 (실패)

```python
browser = p.chromium.launch(headless=True)
```

**결과**: 페이지 DOM이 렌더링되지 않음. 버튼 ID를 찾을 수 없음.

**원인**: 사이트가 `WebSquare` 프레임워크를 사용하는데, headless 브라우저를 감지하면 렌더링을 중단한다.

```
navigator.webdriver === true  →  렌더링 중단
```

---

## 3. Playwright 스텔스 모드

### 해결 패턴

```python
browser = p.chromium.launch(
    headless=True,
    args=[
        '--no-sandbox',
        '--disable-blink-features=AutomationControlled',  # ← 핵심!
        '--disable-features=site-per-process',
        '--lang=ko-KR',
    ]
)
context = browser.new_context(
    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    locale="ko-KR",
    viewport={"width": 1280, "height": 900},
)
context.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    Object.defineProperty(navigator, 'plugins',  {get: () => [1,2,3,4,5]});
    window.chrome = {runtime: {}};
""")
```

**핵심 포인트**:
- `--disable-blink-features=AutomationControlled` : Chromium의 자동화 감지 플래그 비활성화
- `navigator.webdriver = undefined` : JS에서 확인되는 headless 신호 차단
- User-Agent를 실제 Chrome처럼 설정

---

## 4. WebSquare SPA 처리

### 문제: 초기화 시점 불명확

```python
time.sleep(8)  # ❌ 어떤 실행에선 되고 어떤 실행엔 안 됨
```

**WebSquare** = 한국 전자정부 JS 프레임워크. HTML body는 비어있고 JS로 DOM을 동적 생성한다.

### 해결: wait_for_function으로 버튼 출현 대기

```python
page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)

# 검색 버튼이 실제로 DOM에 나타날 때까지 대기
page.wait_for_function(
    "() => !!document.getElementById('mf_wfm_mainFrame_btn_gdsDtlSrch')",
    timeout=60000
)
```

### 문제: Playwright 로케이터 클릭 실패

```python
page.click("#mf_wfm_mainFrame_btn_gdsDtlSrch")  # ❌ TimeoutError
```

WebSquare 버튼은 Playwright 로케이터로 감지되지 않는다.

### 해결: page.evaluate()로 JS 직접 클릭

```python
page.evaluate("""
() => {
    const b = document.getElementById('mf_wfm_mainFrame_btn_gdsDtlSrch');
    if(b) b.click();
}
""")
```

---

## 5. 파이프라인 딜레이 문제

### 문제: 마지막 페이지 데이터 누락

페이지 3을 클릭했을 때 페이지 2의 데이터가 도착하는 **파이프라인 패턴** 발견.

```
클릭 순서:  [1페이지] → [2페이지] → [3페이지]
응답 도착:              [1페이지]   [2페이지]   (마지막 페이지 응답 못 받음)
```

`browser.close()` 직후 마지막 응답이 도착 → 수집 누락.

### 해결: 마지막 페이지 재클릭 + 무응답 대기

```python
# 페이지네이션 루프
for pg in range(2, max_page + 1):
    response_flag[0] = False
    time.sleep(0.5)
    page.evaluate(f"() => {{ document.getElementById('...page_{pg}')?.click(); }}")
    for _ in range(15):
        time.sleep(1)
        if response_flag[0]:
            break

# ← 마지막 페이지 재클릭 (파이프라인 플러시!)
page.evaluate(f"() => {{ document.getElementById('...page_{max_page}')?.click(); }}")

# 8초 무응답 시 종료
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
```

---

## 6. 코드 정리 및 CLI 도구화

### 사용자 요청
```
코드 정리해줘
다른 법원이나 조건으로도 검색해줘
```

### 코드 변화: 395줄 → 198줄

탐색 로직 제거, 헬퍼 함수화, CLI 인자 추가.

### set_select() 헬퍼

드롭다운 설정 로직을 재사용 가능한 함수로 추출:

```python
def set_select(page, el_id, value):
    result = page.evaluate(f"""
    () => {{
        const sel = document.getElementById('{el_id}');
        if (!sel) return {{ok: false, err: 'not found'}};
        const opts = Array.from(sel.options);
        const opt  = opts.find(o => 
            o.value === '{value}' || 
            o.text === '{value}' || 
            o.text.includes('{value}')
        );
        if (!opt) return {{ok: false, opts: opts.map(o => o.text)}};
        sel.value = opt.value;
        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
        return {{ok: true, text: opt.text}};
    }}
    """)
    if not result.get('ok'):
        print(f"  [경고] {el_id} 에서 '{value}' 없음. 옵션: {result.get('opts', [])}")
    return result.get('ok', False)
```

### CLI 인자

```bash
python3 scrape_uijeongbu_apt.py --court 서울중앙지방법원 --scl 아파트 --flbd-min 2회
python3 scrape_uijeongbu_apt.py --court 수원지방법원 --sgg 수원시 --max-price 500000000
```

---

## 7. 템플릿 시스템

### 사용자 요청
```
항상 결과물이 동일하도록 템플릿을 만들어서 관리하자
```

### 설계 원칙

```
우선순위: CLI 인자 > 템플릿 > 기본값(DEFAULTS)
```

### 템플릿 파일 (templates/*.json)

```json
// templates/uijeongbu_apt.json
{
  "court": "의정부지방법원",
  "lcl": "건물",
  "mcl": "주거용건물",
  "scl": "아파트",
  "flbd_min": "1회"
}
```

### 사용법

```bash
# 저장된 조건 그대로 실행
python3 scrape_uijeongbu_apt.py -t templates/uijeongbu_apt.json

# 템플릿 + CLI 오버라이드
python3 scrape_uijeongbu_apt.py -t templates/uijeongbu_apt.json --sgg 포천시 --flbd-min 3회
```

### parse_args() 병합 로직

```python
def parse_args():
    merged = dict(DEFAULTS)
    if args.template:
        with open(tpl_path, encoding='utf-8') as f:
            merged.update(json.load(f))  # 템플릿 덮어쓰기
    for key in ['court', 'sido', 'sgg', ...]:
        if getattr(args, key) is not None:
            merged[key] = getattr(args, key)  # CLI 인자 최종 덮어쓰기
```

---

## 8. 후처리 필터

### 배경

사이트 UI의 시도/시군구 드롭다운이 법원 선택 후 제대로 업데이트되지 않는 문제 발견.

**해결 방향**: 사이트 select 설정을 포기 → API 응답 필드로 후처리 필터링

### API 응답 필드 매핑

| CSV 컬럼 | API 필드 | 비고 |
|----------|---------|------|
| 시/도 필터 | `hjguSido` | "서울특별시", "경기도" 등 |
| 시/군/구 필터 | `hjguSigu` | "양주시", "금천구" 등 |
| 최저가 필터 | `minmaePrice` | 원 단위 정수 |
| 유찰횟수 | `yuchalCnt` | 정수 |

### 후처리 코드

```python
filtered = all_items

# 시/도 필터 (콤마 구분 다중값 지원)
if args.sido:
    sidos = [s.strip() for s in args.sido.split(',')]
    filtered = [i for i in filtered 
                if any(s in i.get('hjguSido', '') for s in sidos)]

# 시/군/구 필터
if args.sgg:
    filtered = [i for i in filtered if args.sgg in i.get('hjguSigu', '')]

# 최저가 상한 필터
if args.max_price:
    filtered = [i for i in filtered 
                if int(i.get('minmaePrice', 0) or 0) <= args.max_price]
```

---

## 9. 한계 발견

### 사용자 요청
```
서울시 경기도 아파트 최저가 5억이하, 유찰1회이상, 임차인이 없는 물건
```

### 한계 #1: 전국 검색 결과 제한

**발견**: 법원 없이 전국 검색 시 사이트가 결과를 약 7건으로 제한함.

```
서울 전국 검색: 7건 수집 → 3건 (최저가 5억 이하)
경기 전국 검색: 7건 수집 → 0건 (경기도 hjguSido 없음)
```

**원인**: 사이트 서버 측 제한. 법원을 선택해야 정상적인 결과 반환.

**해결 방향**: 서울 5개 법원 + 경기 주요 법원을 각각 검색 후 합산하는 방식 필요.

---

### 한계 #2: 임차인 정보 없음

**확인 방법**: API raw 필드 덤프 실행

```python
# 임시 스크립트로 API 응답 필드 전체 출력
body = response.json()
items = body.get('data', {}).get('dlt_srchResult', [])
if items:
    print(list(items[0].keys()))
```

**결과**: 검색 목록 API의 응답 필드 목록

```python
['saNo', 'srnSaNo', 'jiwonNm', 'cortOfcCd', 'dmsNo', 
 'minmaePrice', 'gamevalAmt', 'yuchalCnt',
 'hjguSido', 'hjguSigu', 'hjguDong', 'daepyoLotno', 'convAddr',
 'bidBgngYmd', 'bidEndYmd', ...]
# 임차인 관련 필드 없음
```

**결론**: 목록 API에 임차인 정보가 없다. 각 물건의 **상세 페이지를 개별 크롤링**해야만 확인 가능.

---

## 10. 핵심 학습 포인트

### A. 사이트 분석이 먼저

| 확인 항목 | 이 사이트의 경우 |
|-----------|----------------|
| 프레임워크 | WebSquare (JS 렌더링) |
| IP 차단 | 있음 (외부 직접 POST 차단) |
| Bot 감지 | navigator.webdriver 체크 |
| API 응답 | JSON (`dlt_srchResult` 배열) |

### B. Claude Code 협업 패턴

1. **실패를 공유하면 원인을 분석한다** — 에러 메시지를 붙여넣으면 근본 원인을 추적
2. **작동하는 최소 코드 → 점진적 확장** — 한 번에 완성하려 하지 않음
3. **탐색 로직은 제거** — 완성 후 불필요한 디버그 코드 정리
4. **재사용 가능하게** — 하드코딩 → CLI 인자 → 템플릿 시스템

### C. 웹 스크래핑 교훈

```
❌ requests 직접 호출        → IP 차단
❌ 기본 headless Playwright  → bot 감지
❌ 고정 sleep()              → 불안정
❌ Playwright 로케이터 클릭  → WebSquare에서 실패

✅ Playwright + 스텔스 옵션
✅ wait_for_function (동적 대기)
✅ page.evaluate()로 JS 클릭
✅ 파이프라인 플러시 패턴
✅ API 응답 후처리 필터
```

### D. 구현된 최종 기능

```bash
# 기본 실행 (의정부/아파트/유찰1회)
python3 scrape_uijeongbu_apt.py

# 다른 법원
python3 scrape_uijeongbu_apt.py --court 서울중앙지방법원

# 템플릿 사용
python3 scrape_uijeongbu_apt.py -t templates/suwon_apt.json

# 지역 + 가격 필터
python3 scrape_uijeongbu_apt.py --court 의정부지방법원 --sgg 양주시 --max-price 300000000
```

---

## 프로젝트 최종 구조

```
auction-crwal0629/
├── scrape_uijeongbu_apt.py        # 메인 스크래퍼
├── templates/
│   ├── uijeongbu_apt.json         # 의정부/아파트/유찰1회
│   ├── uijeongbu_yangju_apt.json  # 의정부/양주시/아파트/유찰1회
│   ├── nambu_geumcheon_dasedae.json # 서울남부/금천구/다세대
│   └── suwon_apt.json             # 수원지방법원/아파트/유찰1회
└── skill/
    ├── SKILL.md                   # 드롭다운 체계, API 필드 매핑
    └── references/
        └── trial-and-error.md    # 시행착오 12개 케이스
```

---

## 미해결 과제 (다음 세션)

- [ ] **서울+경기 다중 법원 검색**: `--court`에 쉼표로 여러 법원 입력 → 순차 검색 후 합산
- [ ] **임차인 필터**: 각 물건 상세 페이지 개별 크롤링 (속도 이슈 있음)

---

*이 대화 로그는 Claude Code와 법원경매 스크래퍼를 함께 개발한 실제 세션을 기반으로 재구성되었습니다.*
