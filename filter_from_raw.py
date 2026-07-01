#!/usr/bin/env python3
"""raw_uijeongbu.json 에서 올바른 필드로 필터링.

정정된 필드 매핑:
  감정가        = gamevalAmt
  현재 최저가   = notifyMinmaePrice1  (없으면 minmaePrice)
  유찰횟수      = yuchalCnt
  저감율        = notifyMinmaePriceRate1
  소재지        = printSt
  전용면적      = convAddr/areaList 의 ㎡
조건: 유찰 1회 / 최저가 2억~5억 / 전용 85㎡ 이하
"""
import json, re

PRICE_MIN, PRICE_MAX, AREA_MAX = 200_000_000, 500_000_000, 85.0
AREA_RE = re.compile(r'([\d,]+(?:\.\d+)?)\s*㎡')

def area_of(it):
    src = (it.get('convAddr','') or '') + ' ' + (it.get('areaList','') or '')
    vals = [float(m.replace(',','')) for m in AREA_RE.findall(src)]
    return max(vals) if vals else None

def low_price(it):
    v = it.get('notifyMinmaePrice1') or it.get('minmaePrice') or 0
    return int(v)

items = json.load(open('raw_uijeongbu.json', encoding='utf-8'))
print(f"의정부 아파트(유찰1회 검색) 원본: {len(items)}건\n")

out = []
for it in items:
    if int(it.get('yuchalCnt', 0) or 0) != 1:
        continue
    low = low_price(it)
    if not (PRICE_MIN <= low <= PRICE_MAX):
        continue
    area = area_of(it)
    if area is None or area > AREA_MAX:
        continue
    out.append((it, low, area))

# 최저가 오름차순
out.sort(key=lambda x: x[1])

print(f"■ 유찰1회 · 최저가 2~5억 · 전용 85㎡ 이하 : {len(out)}건\n")
for it, low, area in out:
    gam  = int(it.get('gamevalAmt', 0) or 0)
    rate = it.get('notifyMinmaePriceRate1', '')
    sano = it.get('printCsNo','').replace('<br/>', ' ')
    addr = it.get('printSt','')
    giil = it.get('maeGiil','')
    giil_fmt = f"{giil[:4]}.{giil[4:6]}.{giil[6:]}" if len(str(giil))==8 else giil
    print(f"  {sano}")
    print(f"     {addr}")
    print(f"     전용 {area:g}㎡ | 감정 {gam:,} → 최저 {low:,} ({rate}%) | 유찰1회 | 매각 {giil_fmt}")
    print()
