#!/usr/bin/env python3
"""기업마당 공고 텍스트 보고.

저장된 원본만 읽는다. API를 호출하지 않는다.

두 섹션으로 나눈다.
    [신규]     직전 수집분에 없던 공고
    [마감임박]  D-N 이내에 마감되는 공고

신청기간은 자유 입력이라 절반 이상이 날짜가 아니다.
파싱에 실패하면 추측하지 않고 원문을 그대로 표시한다. (AGENTS.md 1-2)
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW = ROOT / "data" / "raw" / "bizinfo"

DEFAULT_KEYWORDS = [
 "AI", "인공지능", "ICT", "SW", "소프트웨어",
 "데이터", "클라우드", "디지털전환", "DX", "정보보호",
]

# 2026-09-03 / 2026.09.03 / 20260903 을 모두 받는다
DATE_RE = re.compile(r"(\d{4})[-.]?(\d{2})[-.]?(\d{2})")
TAG_RE = re.compile(r"<[^>]+>")


# ---------- 순수 함수 (테스트 대상) ----------

def parse_period(text: str) -> tuple[date | None, date | None]:
    """신청기간 문자열에서 시작일과 종료일을 뽑는다.

    날짜를 두 개 찾지 못하면 (None, None)을 돌려준다.
    억지로 추측하지 않는다.
    """
    if not text:
        return (None, None)
    found = []
    for m in DATE_RE.finditer(text):
        try:
            found.append(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            continue
    if len(found) >= 2:
        return (found[0], found[1])
    return (None, None)


def days_left(end: date | None, today: date) -> int | None:
    """마감까지 남은 일수. 마감일이 없으면 None."""
    if end is None:
        return None
    return (end - today).days


def strip_html(text: str) -> str:
    """공고 본문의 태그와 개체 참조를 걷어낸다. 내용은 바꾸지 않는다."""
    if not text:
        return ""
    plain = TAG_RE.sub(" ", text)
    plain = html.unescape(plain)
    return re.sub(r"\s+", " ", plain).strip()


def matches(item: dict, keywords: list[str]) -> bool:
    """제목에 키워드가 하나라도 있으면 참. 본문은 검사하지 않는다."""
    title = item.get("pblancNm") or ""
    return any(k in title for k in keywords)

def new_ids(current: list[dict], previous: list[dict] | None) -> set[str]:
    """직전 수집분에 없던 공고ID. 비교 대상이 없으면 빈 집합."""
    if previous is None:
        return set()
    old = {x.get("pblancId") for x in previous}
    return {x.get("pblancId") for x in current if x.get("pblancId") not in old}


# ---------- 저장소 읽기 ----------

def run_dirs(raw_root: Path) -> list[Path]:
    if not raw_root.exists():
        return []
    return sorted((p for p in raw_root.iterdir() if p.is_dir()), key=lambda p: p.name)


def load_items(run_dir: Path) -> list[dict]:
    payload = json.loads((run_dir / "bizinfo.json").read_text(encoding="utf-8"))
    items = payload.get("jsonArray")
    if not isinstance(items, list):
        raise ValueError(f"jsonArray 없음: {run_dir}")
    return items


# ---------- 보고 ----------

def fmt_line(item: dict, today: date) -> str:
    start, end = parse_period(item.get("reqstBeginEndDe") or "")
    left = days_left(end, today)
    if left is None:
        period = item.get("reqstBeginEndDe") or "기간 미표기"
    elif left < 0:
        period = f"마감 ({end:%m/%d})"
    elif left == 0:
        period = f"오늘 마감 ({end:%m/%d})"
    else:
        period = f"D-{left} ({end:%m/%d})"

    title = item.get("pblancNm") or "(제목 없음)"
    org = item.get("jrsdInsttNm") or ""
    field = item.get("pldirSportRealmLclasCodeNm") or ""
    url = item.get("pblancUrl") or ""
    tail = " · ".join(x for x in (field, org) if x)
    return f"· {period} | {title}\n  {tail}\n  {url}"


def build_report(current: list[dict], previous: list[dict] | None,
                 keywords: list[str], within: int, top: int,
                 as_of: datetime, snapshot: str, compare: str | None) -> str:
    today = as_of.date()
    hits = [x for x in current if matches(x, keywords) and x.get("pblancUrl")]

    fresh_ids = new_ids(current, previous)
    fresh = [x for x in hits if x.get("pblancId") in fresh_ids]

    closing = []
    for x in hits:
        _, end = parse_period(x.get("reqstBeginEndDe") or "")
        left = days_left(end, today)
        if left is not None and 0 <= left <= within:
            closing.append((left, x))
    closing.sort(key=lambda p: p[0])

    undated = sum(1 for x in hits if parse_period(x.get("reqstBeginEndDe") or "")[1] is None)

    out = []
    out.append(f"기업마당 지원사업 다이제스트 · {as_of:%Y-%m-%d %H:%M} KST")
    out.append(f"전체 {len(current)}건 중 키워드 일치 {len(hits)}건")
    out.append("")

    out.append(f"■ 신규 (직전 수집 대비)")
    if previous is None:
        out.append("  비교 대상이 없어 신규 판정을 생략합니다. (첫 수집)")
    elif not fresh:
        out.append("  없음")
    else:
        for x in fresh[:top]:
            out.append(fmt_line(x, today))
        if len(fresh) > top:
            out.append(f"  … 외 {len(fresh) - top}건")
    out.append("")

    out.append(f"■ 마감 임박 (D-{within} 이내)")
    if not closing:
        out.append("  없음")
    else:
        for _, x in closing[:top]:
            out.append(fmt_line(x, today))
        if len(closing) > top:
            out.append(f"  … 외 {len(closing) - top}건")
    out.append("")

    out.append(f"상시·기간미표기 {undated}건은 위 목록에 포함되지 않습니다.")
    out.append(f"snapshot {snapshot}")
    out.append(f"compare_with {compare or '없음'}")
    out.append("출처: 기업마당(bizinfo)")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="기업마당 공고 텍스트 보고")
    parser.add_argument("--raw-root", default=str(DEFAULT_RAW))
    parser.add_argument("--keyword", action="append", default=None,
                        help="필터 키워드. 여러 번 지정 가능")
    parser.add_argument("--within", type=int, default=7,
                        help="마감 임박 기준 일수 (기본 7)")
    parser.add_argument("--top", type=int, default=10,
                        help="섹션별 최대 건수 (기본 10)")
    parser.add_argument("--compare-with", default="previous",
                        help="previous | none | 폴더명")
    args = parser.parse_args()

    keywords = args.keyword or DEFAULT_KEYWORDS
    runs = run_dirs(Path(args.raw_root))
    if not runs:
        print("[보고] 수집분이 없습니다. 먼저 수집기를 실행하세요.", file=sys.stderr)
        return 1

    current_dir = runs[-1]
    current = load_items(current_dir)

    previous = None
    compare_name = None
    if args.compare_with == "previous":
        if len(runs) >= 2:
            previous = load_items(runs[-2])
            compare_name = runs[-2].name
    elif args.compare_with != "none":
        target = Path(args.raw_root) / args.compare_with
        previous = load_items(target)
        compare_name = target.name

    report = build_report(
        current, previous, keywords, args.within, args.top,
        datetime.now(KST), current_dir.name, compare_name,
    )
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
