#!/usr/bin/env python3
"""의정부지방법원 물건 검증 — 가격비율로 실제 유찰횟수 역산 후 yuchalCnt 필드와 교차 대조.

경기 저감율 30% 가정 → 최저가/감정가 비율:
  1.00→유찰0회, 0.70→1회, 0.49→2회, 0.343→3회, 0.240→4회 ...
"""
import csv, re, math

SRC = 'auction_경기전체_아파트.csv'

def money(s):
    d = re.sub(r'[^\d]', '', s or ''); return int(d) if d else 0

def infer_yuchal(ratio):
    """비율로 실제 유찰횟수 역산 (30% 저감)."""
    if ratio >= 0.95:
        return 0
    n = round(math.log(ratio) / math.log(0.7))
    return n

rows = [r for r in csv.DictReader(open(SRC, encoding='utf-8-sig'))
        if '의정부지방법원' in r.get('사건번호', '')]

print(f"의정부지방법원 물건: {len(rows)}건\n")

# 교차표: yuchalCnt 필드값 vs 가격비율로 역산한 실제 유찰
cross = {}
detail = []
for r in rows:
    field_n = int(re.sub(r'[^\d]', '', r.get('유찰횟수', '0')) or 0)
    gam, low = money(r.get('감정가','')), money(r.get('최저가',''))
    if gam == 0:
        continue
    ratio = low / gam
    real_n = infer_yuchal(ratio)
    cross[(field_n, real_n)] = cross.get((field_n, real_n), 0) + 1
    detail.append((r['사건번호'], field_n, real_n, ratio, gam, low, r['물건소재지']))

print("■ 교차표  (yuchalCnt 필드값 → 가격비율로 역산한 실제 유찰횟수)")
print("   yuchalCnt | 실제유찰 | 건수")
for (f, real), c in sorted(cross.items()):
    flag = '' if (real == f or real == f-1) else '  ⚠'
    print(f"      {f:2d}     |   {real:2d}    | {c:2d}{flag}")

# 필드값과 실제가 어긋나는 규칙 판정
rule_minus1 = sum(c for (f, real), c in cross.items() if real == f-1 and f >= 1)
rule_equal  = sum(c for (f, real), c in cross.items() if real == f)
print(f"\n■ 규칙 판정")
print(f"   실제 = yuchalCnt (필드=실제 유찰): {rule_equal}건")
print(f"   실제 = yuchalCnt − 1 (필드=매각회차): {rule_minus1}건")

# 실제 1회 유찰 물건 (비율 0.7 근처)
print(f"\n■ 실제 1회 유찰 물건 (비율 0.65~0.73, = 감정가의 70%)")
real1 = [d for d in detail if d[2] == 1]
for sano, f, real, ratio, gam, low, addr in sorted(real1, key=lambda x: x[5]):
    print(f"   {sano}  (필드유찰{f})  {gam:,}→{low:,}  비율{ratio:.2f}")
    print(f"        {addr[:50]}")
print(f"   小계: {len(real1)}건")
