#!/usr/bin/env python3
"""
fetch_kiscon.py - 국토교통부 키스콘 건설업체정보(공시) 전체 이력 다운로드 (2003~현재)
API: https://apis.data.go.kr/1613000/ConAdminInfoSvc1/GongsiReg (공시기간 단위 조회, 자동승인)
출력: _rawdata/kiscon_events.json (공시 이벤트 전체: 신규/정정/변경/철회)

사용법: python scripts/fetch_kiscon.py [--since 2003]
환경: DATA_GO_KR_KEY (없으면 기본 공용키 사용)
"""
import os, sys, json, time, argparse, datetime
from pathlib import Path
import requests

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent.parent
OUT = ROOT / "_rawdata" / "kiscon_events.json"
URL = "https://apis.data.go.kr/1613000/ConAdminInfoSvc1/GongsiReg"
KEY = os.environ.get("DATA_GO_KR_KEY", "9490b1d34e92aa9e25b32a4cff1438fc7b9c71e5d332413916a391e867f61e86")
PAGE = 3000


def call(s, e, page):
    for attempt in range(4):
        try:
            r = requests.get(URL, params={"serviceKey": KEY, "pageNo": page, "numOfRows": PAGE,
                                          "sDate": s, "eDate": e, "_type": "json"}, timeout=120)
            r.raise_for_status()
            return r.json()["response"]["body"]
        except Exception:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", type=int, default=2003)
    args = ap.parse_args()
    this_year = datetime.date.today().year

    events = []
    for y in range(args.since, this_year + 1):
        page = 1
        while True:
            body = call(f"{y}0101", f"{y}1231", page)
            items = body.get("items") or {}
            items = items.get("item", []) if isinstance(items, dict) else items
            if isinstance(items, dict):
                items = [items]
            events += items
            if len(items) < PAGE:
                break
            page += 1
            time.sleep(0.3)
        print(f"{y}: 누적 {len(events):,}건", flush=True)

    if OUT.exists():
        old = len(json.loads(OUT.read_text(encoding="utf-8")))
        if len(events) < old * 0.5:
            raise SystemExit(f"수집 {len(events)}건이 기존 {old}건의 절반 미만 — 저장 중단")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
    print(f"저장 완료: {OUT} ({len(events):,}건)")


if __name__ == "__main__":
    main()
