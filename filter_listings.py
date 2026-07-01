#!/usr/bin/env python3
"""수집된 경매 CSV에 후처리 필터 적용.

조건 (기본값, CLI로 변경 가능):
  - 유찰횟수 == 1
  - 최저가 2억 ~ 5억
  - 전용면적 85㎡ 이하

사용법:
  python3 filter_listings.py [입력CSV] [출력CSV]
"""

import csv
import re
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else 'auction_경기전체_아파트.csv'
DST = sys.argv[2] if len(sys.argv) > 2 else 'auction_경기_유찰1_2억5억_85㎡이하.csv'

PRICE_MIN = 200_000_000
PRICE_MAX = 500_000_000
AREA_MAX  = 85.0
YUCHAL    = '1'

AREA_RE = re.compile(r'([\d,]+(?:\.\d+)?)\s*㎡')


def parse_money(s):
    digits = re.sub(r'[^\d]', '', s or '')
    return int(digits) if digits else 0


def parse_area(r):
    """전용면적 컬럼 우선, 없으면 소재지 문자열의 ㎡ 값 최댓값."""
    src = (r.get('전용면적', '') or '') or (r.get('물건소재지', '') or '')
    vals = [float(m.replace(',', '')) for m in AREA_RE.findall(src)]
    return max(vals) if vals else None


def main():
    with open(SRC, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    out = []
    no_area = []
    for r in rows:
        if str(r.get('유찰횟수', '')).strip() != YUCHAL:
            continue
        price = parse_money(r.get('최저가', ''))   # notifyMinmaePrice1 기반 (정정됨)
        if not (PRICE_MIN <= price <= PRICE_MAX):
            continue
        area = parse_area(r)
        if area is None:
            no_area.append(r)
            continue
        if area > AREA_MAX:
            continue
        out.append(r)

    # 최저가 오름차순
    out.sort(key=lambda r: parse_money(r.get('최저가', '')))

    cols = ['사건번호', '물건소재지', '전용면적', '감정가', '최저가', '저감율', '유찰횟수', '매각기일']
    with open(DST, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(out)

    print(f"원본: {len(rows)}건")
    print(f"필터 통과: {len(out)}건  (유찰{YUCHAL}회 / 최저가 {PRICE_MIN//100000000}~{PRICE_MAX//100000000}억 / 전용 {AREA_MAX:g}㎡이하)")
    print(f"→ {DST}")
    if no_area:
        print(f"(면적 미상으로 제외: {len(no_area)}건)")
    print()
    for i, r in enumerate(out, 1):
        print(f"  [{i:02d}] {r['사건번호']}  |  전용 {r.get('전용면적','')}")
        print(f"       {r['물건소재지']}")
        print(f"       감정 {r['감정가']}  →  최저 {r['최저가']} ({r.get('저감율','')})  |  유찰{r['유찰횟수']}회  |  매각 {r.get('매각기일','')}")
        print()


if __name__ == '__main__':
    main()
