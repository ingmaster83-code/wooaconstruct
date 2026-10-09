#!/usr/bin/env python3
"""
process_data.py - 키스콘 공시 이벤트(_rawdata/kiscon_events.json)를 "현재 등록 건설업체" 명단으로 복원해
Jekyll 생성용 JSON(시도별 shard)과 검색 인덱스로 가공.

주의: 키스콘 공시 피드에는 신규 등록 공시만 있고 폐업·말소가 없다(철회는 오기재 정정). 따라서 결과는 '등록 공시된 업체'이며 현재 영업 여부는 알 수 없다.
복원 규칙:
  - 업체 = 사업자등록번호, 등록 단위 = (사업자등록번호, 업종등록번호)
  - 공시순번(ncrGsSeq) 순으로 훑어 마지막 이벤트가 '철회'이면 그 업종은 말소/철회로 보고 제외
  - 활성 업종이 하나도 없는 업체는 제외
출력: _rawdata/con_{시도}.json, search_index.json
사용법: python scripts/process_data.py
"""
import json, re, sys, hashlib
from pathlib import Path
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
RAW = ROOT / "_rawdata" / "kiscon_events.json"
RAWDATA_DIR = ROOT / "_rawdata"
SEARCH_INDEX_OUT = ROOT / "search_index.json"

DONG_TOKEN = re.compile(r"^[가-힣][가-힣0-9]*(?:동|읍|면)$|^[가-힣]+\d+가$")


def clean(s):
    return re.sub(r"\s+", " ", str(s if s is not None else "").strip())


def fmt_date(v):
    s = str(v or "")
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 and s.isdigit() else ""


BUILDING_LABEL = re.compile(r"^[가나다라마바사아자차카타파하]동$")


def dong_from_addr(addr):
    m = re.search(r"\(([^)]*)\)\s*$", addr)
    if m:
        for part in re.split(r"[,\s]+", m.group(1)):
            if DONG_TOKEN.match(part) and not BUILDING_LABEL.match(part):
                return part
    toks = [t.strip("(),") for t in addr.split()]
    for t in toks[2:6]:
        if DONG_TOKEN.match(t) and not BUILDING_LABEL.match(t):
            return t
    return None


MIN_YEAR = 2008  # 폐업 정보가 없어 오래된 등록분은 제외 (용량 한도 + 정확도)


def main():
    events = json.loads(RAW.read_text(encoding="utf-8"))
    print(f"이벤트 {len(events):,}건 로드")

    by_biz = defaultdict(list)
    for e in events:
        biz = str(e.get("ncrMasterNum") or "").strip().zfill(10)
        if biz == "0000000000":
            continue
        by_biz[biz].append(e)

    flags = Counter(e.get("ncrGsFlag") for e in events)
    withdraw_reasons = Counter(clean(e.get("ncrGsReason")) for e in events if e.get("ncrGsFlag") == "철회")
    print("공시구분:", dict(flags))
    print("철회 사유 상위:", withdraw_reasons.most_common(10))

    companies = []
    n_closed = 0
    n_old = 0
    for biz, evs in by_biz.items():
        evs.sort(key=lambda x: int(x.get("ncrGsSeq") or 0))
        trades = {}
        for ev in evs:
            key = clean(ev.get("ncrItemregno")) or clean(ev.get("ncrItemName"))
            if ev.get("ncrGsFlag") == "철회":
                if key in trades:
                    trades[key]["active"] = False
                continue
            t = trades.get(key)
            if t is None:
                t = trades[key] = {"first": ev.get("ncrGsDate"), "newDate": None}
            t.update({"active": True, "name": clean(ev.get("ncrItemName")), "regno": clean(ev.get("ncrItemregno")), "last": ev})
            if ev.get("ncrGsFlag") == "신규" and not t["newDate"]:
                t["newDate"] = ev.get("ncrGsDate")
        active = [t for t in trades.values() if t["active"]]
        if not active:
            n_closed += 1
            continue
        latest = max((t["last"] for t in active), key=lambda x: int(x.get("ncrGsSeq") or 0))
        sido = clean(latest.get("ncrAreaName"))
        sigungu = clean(latest.get("ncrAreaDetailName"))
        addr = clean(latest.get("ncrGsAddr"))
        name = clean(latest.get("ncrGsKname"))
        if sigungu in ("-", ""):
            # 피드에 시군구가 비어 있는 업체(약 18%)는 주소의 두 번째 토큰으로 보정 (scripts/fix_missing_sigungu.py 와 동일 규칙)
            toks = re.sub(r"\s+", " ", addr).split()
            if len(toks) > 1 and re.match(r"^[가-힣]+(?:시|군|구)$", toks[1]):
                sigungu = toks[1]
        if not (sido and sigungu and name):
            continue
        dong = dong_from_addr(addr) or "기타"
        first_all = min(int(t["first"]) for t in active if t["first"])
        if first_all // 10000 < MIN_YEAR:
            n_old += 1
            continue
        slug = hashlib.md5(biz.encode()).hexdigest()[:10]
        history = [{"d": fmt_date(e.get("ncrGsRegdate")), "f": clean(e.get("ncrGsFlag")), "r": clean(e.get("ncrGsReason")),
                    "t": clean(e.get("ncrItemName")), "n": clean(e.get("ncrGsNumber"))}
                   for e in evs[-3:][::-1]]
        companies.append({
            "slug": slug,
            "companyName": name,
            "bizMask": f"{biz[:3]}-{biz[3:5]}-{biz[5:7]}***",
            "master": clean(latest.get("ncrGsMaster")),
            "addr": addr,
            "tel": clean(latest.get("ncrOffTel")),
            "doShort": sido,
            "sigungu": sigungu,
            "sgSlug": sigungu.replace(" ", "-"),
            "dong": dong,
            "trades": sorted(({"n": t["name"], "r": t["regno"], "d": fmt_date(t["newDate"]), "f": fmt_date(t["first"])} for t in active), key=lambda x: x["n"]),
            "firstDate": fmt_date(first_all),
            "lastDate": fmt_date(latest.get("ncrGsRegdate")),
            "history": history,
        })

    print(f"업체 {len(companies):,}곳 (전체 {len(by_biz):,}, 활성 없음 제외 {n_closed:,}, {MIN_YEAR}년 이전 등록 제외 {n_old:,})")

    by_dong = defaultdict(list)
    for c in companies:
        by_dong[(c["doShort"], c["sigungu"], c["dong"])].append(c)
    for lst in by_dong.values():
        lst.sort(key=lambda x: (x["firstDate"] or "9999", x["slug"]))
        for rank, c in enumerate(lst, 1):
            c["dongCount"] = len(lst)
            c["dongRank"] = rank

    RAWDATA_DIR.mkdir(parents=True, exist_ok=True)
    for old in RAWDATA_DIR.glob("con_*.json"):
        old.unlink()
    by_do = defaultdict(list)
    for c in companies:
        by_do[c["doShort"]].append(c)
    for do, group in by_do.items():
        out = RAWDATA_DIR / f"con_{do}.json"
        out.write_text(json.dumps(group, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"  {do}: {len(group)}곳 → {out.name} ({out.stat().st_size/1024/1024:.1f}MB)")

    trade_counts = Counter(t["n"] for c in companies for t in c["trades"])
    print(f"시도 {len(by_do)}개, 시군구 {len({(c['doShort'], c['sigungu']) for c in companies})}개, 동/읍/면 {len(by_dong)}개, 업종 {len(trade_counts)}종")
    print("업종 상위:", trade_counts.most_common(8))
    no_dong = sum(1 for c in companies if c["dong"] == "기타")
    print(f"동 추출 실패(기타): {no_dong} ({no_dong/len(companies)*100:.1f}%)")

    index = [{"n": c["companyName"], "s": c["slug"], "do": c["doShort"], "sg": c["sigungu"], "dg": c["dong"]} for c in companies]
    SEARCH_INDEX_OUT.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"검색 인덱스 {len(index):,}건 ({SEARCH_INDEX_OUT.stat().st_size/1024/1024:.1f}MB)")


if __name__ == "__main__":
    main()
