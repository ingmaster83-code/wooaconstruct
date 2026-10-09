#!/usr/bin/env python3
"""키스콘 피드의 시군구(ncrAreaDetailName)가 '-'인 업체(약 18%)의 시군구를 주소에서 보정해 샤드·검색 인덱스를 고친다.
형식은 피드와 같은 시 단위('수원시', '강남구')를 쓴다. 보정 불가한 업체는 그대로 둔다(허브 페이지에서 '-'로 남음)."""
import json, re, sys
from pathlib import Path
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).parent.parent
RAWDATA = ROOT / "_rawdata"
SG_OK = re.compile(r"^[가-힣]+(?:시|군|구)$")
SIDO_TOKENS = {"서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
               "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원도",
               "강원특별자치도", "충청북도", "충청남도", "전라북도", "전북특별자치도", "전라남도", "경상북도", "경상남도", "제주특별자치도", "제주도"}


def fix_sigungu(addr):
    toks = re.sub(r"\s+", " ", addr or "").split()
    if len(toks) < 2 or toks[0] not in SIDO_TOKENS:
        return None
    cand = toks[1]
    return cand if SG_OK.match(cand) else None


fixed = unfixed = total = 0
by_key = Counter()
for p in sorted(RAWDATA.glob("con_*.json")):
    items = json.loads(p.read_text(encoding="utf-8"))
    changed = False
    for it in items:
        total += 1
        if it.get("sigungu") not in ("-", "", None):
            continue
        sg = fix_sigungu(it.get("addr"))
        if sg:
            it["sigungu"] = sg
            it["sgSlug"] = sg.replace(" ", "-")
            fixed += 1
            changed = True
        else:
            unfixed += 1
    if changed:
        p.write_text(json.dumps(items, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

idx_path = ROOT / "search_index.json"
if idx_path.exists():
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    slug_sg = {}
    for p in RAWDATA.glob("con_*.json"):
        for it in json.loads(p.read_text(encoding="utf-8")):
            slug_sg[it["slug"]] = it["sigungu"]
    for e in idx:
        if e.get("sg") in ("-", "", None) and e["s"] in slug_sg:
            e["sg"] = slug_sg[e["s"]]
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

print(f"전체 {total:,}건 중 시군구 보정 {fixed:,}건, 보정 불가 {unfixed:,}건")
