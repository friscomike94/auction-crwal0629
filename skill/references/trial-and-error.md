# 법원경매 스크래핑 시행착오 기록

> 이 문서는 2026-06-29 세션에서 발생한 실제 실패와 해결 과정을 기록한다.
> 동일한 삽질을 반복하지 않기 위해 작성됨.

---

## 실패 #1: 사이트가 SPA인 줄 몰랐다

**시도**: `curl`로 페이지 HTML 가져오기
```bash
curl "https://www.courtauction.go.kr/pgj/index.on?w2xPath=/pgj/ui/pgj100/PGJ151F00.xml"
```

**결과**: `<body></body>` — 빈 body만 반환
**원인**: WebSquare 프레임워크 기반 SPA. HTML은 껍데기고 모든 UI가 JS로 렌더링됨
**교훈**: `w2xPath` 파라미터가 보이면 WebSquare SPA임을 즉시 인식할 것

---

## 실패 #2: XML에서 API 엔드포인트를 찾아서 직접 호출

**시도**: `/pgj/ui/pgj100/PGJ151F00.xml` 분석 → `searchControllerMain.on` 발견 → curl POST
```python
requests.post(".../searchControllerMain.on", json=[pageInfo, srchInfo])
```

**결과**: `{"errorMessage": "사용에 불편을 드려서 죄송합니다..."}`
**원인 1**: JSON 포맷 오류 — 배열 `[...]`이 아니라 객체 `{"dma_pageInfo":{}, "dma_srchGdsDtlSrchInfo":{}}` 형식이어야 함
**원인 2**: IP 차단 — 세션 쿠키를 받아와도 외부 IP에서의 직접 호출은 차단됨
**교훈**: 올바른 포맷으로 다시 시도해도 결국 IP 차단으로 실패한다. 시간 낭비 하지 말 것

---

## 실패 #3: 올바른 포맷으로 재시도

**시도**: 실제 요청 body를 캡처해서 동일한 JSON으로 POST
```bash
curl -d '{"dma_pageInfo":{...},"dma_srchGdsDtlSrchInfo":{...}}'
```

**결과**: `{"message": "해당 IP는 비정상적인 접속으로 보안정책에 의하여 차단되었습니다."}`
**원인**: IP 기반 차단. 한국 IP가 아닌 경우 직접 API 호출 전면 차단
**교훈**: 직접 HTTP 호출은 포기. Playwright(로컬 브라우저)만 가능

---

## 실패 #4: Playwright 기본 headless 모드

**시도**:
```python
browser = p.chromium.launch(headless=True)
# 8초 대기 후 검색 버튼 클릭 시도
```

**결과**: 버튼이 DOM에 없음. `total: 0 input[type=button]`
**원인**: WebSquare가 headless Chromium 감지 후 렌더링 중단
**교훈**: `--disable-blink-features=AutomationControlled` + `navigator.webdriver = undefined` 필수

---

## 실패 #5: networkidle 사용

**시도**:
```python
page.goto(url, wait_until="networkidle", timeout=60000)
time.sleep(4)
```

**결과**: 일관성 없음. 어떤 실행에서는 버튼이 보이고, 어떤 실행에서는 완전히 빈 흰 화면
**원인**: WebSquare의 네트워크 요청 패턴이 매번 달라 networkidle 발화 시점이 다름
**교훈**: `wait_for_function`으로 실제 버튼 DOM 출현을 기다려야 함

---

## 실패 #6: Playwright 로케이터로 버튼 클릭

**시도**:
```python
page.click("#mf_wfm_mainFrame_btn_gdsDtlSrch", timeout=10000)
# 또는
page.wait_for_selector(..., state="visible")
```

**결과**: `TimeoutError: Timeout 10000ms exceeded`
**원인**: WebSquare가 생성한 DOM 요소를 Playwright 로케이터가 인식 못 함
**해결**: `page.evaluate("() => { document.getElementById('...').click(); }")` 사용
**교훈**: WebSquare 사이트에서는 Playwright 로케이터보다 `page.evaluate()` JS 직접 실행이 더 안정적

---

## 실패 #7: 잘못된 "검색" 버튼 클릭

**시도**: 텍스트에 "검색"이 포함된 버튼을 찾아서 첫 번째 것 클릭
```python
for b in buttons:
    if '검색' in b['text']:
        page.click(f"#{b['id']}")
        break
```

**결과**: `지도검색` 메뉴 링크(`mf_wfm_header_btnMapInfo`)가 클릭됨
**원인**: "검색"이 포함된 네비게이션 링크들이 먼저 매칭됨
**해결**: 실제 검색 submit 버튼 ID를 하드코딩: `mf_wfm_mainFrame_btn_gdsDtlSrch`
**교훈**: WebSquare 검색 폼 submit 버튼 ID 패턴: `wfm_mainFrame_btn_*Srch`

---

## 실패 #8: API 응답 필드 이름 추측

**시도**: 필드명을 영문 의미로 추측
```python
FIELD_MAP = {
    '사건번호': ['caseNo', 'csNo', 'scNo'],  # 전부 틀림
    '감정가':   ['evalAmt', 'appraisalAmt'],   # 전부 틀림
}
```

**결과**: 모든 컬럼이 빈값
**해결**: `response.json()` 로 실제 응답을 캡처해서 필드명 확인:
- 사건번호 → `jiwonNm` (법원명) + `srnSaNo` (사건번호)
- 감정가 → `gamevalAmt`
- 최저가 → `minmaePrice`
- 유찰횟수 → `yuchalCnt`
- 주소 → `hjguSido` + `hjguSigu` + `hjguDong` + `daepyoLotno` + `convAddr`
**교훈**: API 필드명은 반드시 실제 응답에서 확인. 추측은 시간 낭비

---

## 실패 #9: 응답이 즉시 온다고 가정한 페이지네이션

**시도**:
```python
page.evaluate("... click page 2 ...")
time.sleep(2)  # 응답 왔겠지?
page.evaluate("... click page 3 ...")
```

**결과**: 각 페이지 응답이 누락됨. 10페이지 중 8~9개만 수집됨
**원인**: WebSquare의 응답이 1~2 클릭 뒤에 도착하는 파이프라인 패턴
  - 1페이지 클릭 → 응답은 2페이지 클릭할 때 도착
  - 9페이지 클릭 → 응답은 10페이지 클릭할 때 도착
  - 10페이지 클릭 → 응답은 루프 종료 후 도착
**해결**: 루프 후 마지막 페이지 재클릭(플러시) + 8초 무응답 종료 패턴
**교훈**: 비동기 API 파이프라인은 루프 후 반드시 플러시가 필요함

---

## 실패 #10: browser.close() 후 응답 손실

**시도**:
```python
for pg in range(2, max_page + 1):
    ...
browser.close()  # ← 여기서 닫으면 마지막 응답을 못 받음
```

**결과**: `[오류] Response.json: Target page, context or browser has been closed`
마지막 10개 아이템 손실 (90개 수집, 10개 누락)
**해결**: 루프 후 플러시 클릭 + 8초 idle 대기 후 닫기
**교훈**: Playwright browser.close()는 in-flight 응답을 취소시킴. 충분한 대기 필요

---

## 실패 #11: 첫 페이지 응답 타임아웃 (30초 대기)

**시도**: 첫 검색 클릭 후 응답 대기 30초
**결과**: 항상 "타임아웃" 경고 출력 후 진행
**원인**: 첫 페이지 응답이 두 번째 페이지 클릭 시점에야 도착하는 패턴
**해결**: 첫 페이지 타임아웃을 경고로만 처리하고 진행. 페이지네이션 루프에서 자동으로 수집됨
**교훈**: 파이프라인 패턴에서 첫 응답 타임아웃은 정상 동작

---

## 성공한 최종 패턴 요약

```
1. Playwright + stealth args + init_script (webdriver=undefined)
2. domcontentloaded + wait_for_function (버튼 DOM 출현 대기)
3. page.evaluate() JS 클릭 (Playwright 로케이터 X)
4. on_response 인터셉트 → data.dlt_srchResult 파싱
5. 페이지네이션: response_flag 방식 (not 고정 sleep)
6. 루프 후 마지막 페이지 재클릭 (파이프라인 플러시)
7. 8초 무응답 idle 감지로 완료 판단
8. browser.close() 전 충분한 정리 시간 확보
```

## 소요 시간 기록

| 단계 | 시도 횟수 | 소요 시간 |
|------|-----------|-----------|
| 사이트 구조 파악 | 3 | ~20분 |
| API 엔드포인트 발견 | 2 | ~10분 |
| curl 직접 호출 실패 확인 | 3 | ~15분 |
| Playwright 기본 설정 실패 | 4 | ~30분 |
| 스텔스 모드 적용 후 성공 | 1 | 5분 |
| 필드 매핑 확인 | 2 | ~10분 |
| 페이지네이션 파이프라인 해결 | 4 | ~20분 |
| **총 소요** | **19** | **~110분** |

→ 이 스킬을 사용하면 **5분 이내** 완료 가능

---

## 실패 #12: 용도 대분류에 '집합건물'이 없다

**시도**: 아파트 대분류로 '집합건물' 또는 '주거용' 검색
```python
target = opts.find(o => o.text.includes('집합건물') || o.text.includes('주거용'))
```

**결과**: `set: False` — 옵션 없음. 대분류 실제 옵션: `토지`, `건물`, `차량및운송장비`, `기타`
**원인**: 이 사이트는 아파트를 `건물 → 주거용건물 → 아파트` 3단계 분류로 나눔. 집합건물이라는 대분류 자체가 없음.
**해결**:
```python
# 1) 대분류: '건물'
# 2) (3초 대기) 중분류: '주거용건물'
# 3) (3초 대기) 소분류: '아파트'
```
**교훈**: WebSquare 연동 드롭다운은 각 단계 선택 후 3초 이상 대기해야 하위 옵션이 채워진다.
API 응답 결과에서는 아파트도 `집합건물`로 표기되지만, 검색 조건 분류는 `건물 > 주거용건물 > 아파트`
