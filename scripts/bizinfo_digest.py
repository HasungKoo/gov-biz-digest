#!/usr/bin/env python3
"""기업마당 공고 텍스트 보고.

저장된 원본만 읽는다. API를 호출하지 않는다.

세 섹션으로 나눈다.
    [신규]     직전 수집분에 없던 공고
    [마감임박]  D-N 이내에 마감되는 공고
    [창업자금]  창업 대상 자금성 공고 중 지정 지역·전국 대상만

지역은 해시태그로 판정한다. 기업마당은 신청 가능 지역을 해시태그에 단다.
시·군·구 공고는 그 지역 사업자만 신청할 수 있어 지정한 시만 남긴다.

신청기간은 자유 입력이라 절반 이상이 날짜가 아니다.
파싱에 실패하면 추측하지 않고 원문을 그대로 표시한다. (AGENTS.md 1-2)
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW = ROOT / "data" / "raw" / "bizinfo"

DEFAULT_KEYWORDS = [
 "AI", "인공지능", "ICT", "SW", "소프트웨어",
 "데이터", "클라우드", "디지털전환", "DX", "정보보호",
]

# 창업 자금 섹션. 제목·분야·대상 중 하나로 창업 공고를 고르고,
# 제목·해시태그로 자금성 여부를 본다. 본문은 검사하지 않는다.
DEFAULT_STARTUP_KEYWORDS = ["창업", "스타트업", "벤처"]
DEFAULT_FUNDING_KEYWORDS = [
 "자금", "융자", "보증", "투자", "지원금", "사업화",
 "바우처", "상금", "데모데이", "IR", "TIPS",
]

# 받을 지역. 창업 자금과 키워드 공고 모두에 쓴다. 전국 대상은 항상 포함.
DEFAULT_REGIONS = ["서울", "경기"]
DEFAULT_CITIES = ["수원시"]

# 해시태그에 쓰이는 광역 지역명. 이 중 NATIONAL_MIN 개 이상이면 전국 대상.
REGION_TAGS = {
 "서울", "부산", "대구", "인천", "광주", "전남광주", "대전", "울산", "세종",
 "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
}
NATIONAL_MIN = 10

# 2026-09-03 / 2026.09.03 / 20260903 을 모두 받는다
DATE_RE = re.compile(r"(\d{4})[-.]?(\d{2})[-.]?(\d{2})")
TAG_RE = re.compile(r"<[^>]+>")
# "[경기] 화성시 2026년 ..." 처럼 지역 괄호 바로 뒤의 시·군·구
LOCAL_RE = re.compile(r"^\s*\[[^\]]+\]\s*(\S+?[시군구])(?:\s|ㆍ|$)")
# 소관기관이 지자체인지. 중앙부처는 부·처·청·위원회로 끝난다.
LOCAL_HOST_RE = re.compile(r"[시도군구]$")


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


def hashtags(item: dict) -> set[str]:
    return {t.strip() for t in (item.get("hashtags") or "").split(",") if t.strip()}


def is_startup(item: dict, keywords: list[str]) -> bool:
    """분야가 창업이거나, 대상에 창업벤처가 있거나, 제목에 키워드가 있으면 참."""
    if item.get("pldirSportRealmLclasCodeNm") == "창업":
        return True
    if "창업벤처" in (item.get("trgetNm") or ""):
        return True
    title = item.get("pblancNm") or ""
    return any(k in title for k in keywords)


def is_funding(item: dict, keywords: list[str]) -> bool:
    """분야가 금융이거나, 제목·해시태그에 자금성 키워드가 있으면 참."""
    if item.get("pldirSportRealmLclasCodeNm") == "금융":
        return True
    text = (item.get("pblancNm") or "") + "," + ",".join(hashtags(item))
    return any(k in text for k in keywords)


def host_allowed(item: dict, regions: list[str]) -> bool:
    """소관기관이 다른 지방 지자체면 거짓.

    소관기관은 중앙부처이거나 광역 지자체(○○도, ○○광역시 등)로만 온다.
    전국 대상이라도 다른 지자체가 주관하면 사용자가 받지 않기로 했다.
    """
    host = (item.get("jrsdInsttNm") or "").strip()
    if not LOCAL_HOST_RE.search(host):
        return True
    return any(host.startswith(r) for r in regions)


def in_my_region(item: dict, regions: list[str], cities: list[str],
                 national_min: int = NATIONAL_MIN) -> str | None:
    """신청 가능 지역과 주관 기관 둘 다 통과하면 표시용 지역명, 아니면 None."""
    label = region_label(item, regions, cities, national_min)
    if label is None or not host_allowed(item, regions):
        return None
    return label


def region_label(item: dict, regions: list[str], cities: list[str],
                 national_min: int = NATIONAL_MIN) -> str | None:
    """보고 대상 지역이면 표시용 이름, 아니면 None.

    해시태그의 광역 지역명이 national_min 개 이상이면 전국.
    시·군·구 공고는 cities 에 있는 시만 통과한다.
    지역 해시태그가 하나도 없으면 판정하지 않고 버린다.
    """
    tags = hashtags(item)
    found = tags & REGION_TAGS
    if len(found) >= national_min:
        return "전국"
    hit = [r for r in regions if r in found]
    if not hit:
        return None

    title = item.get("pblancNm") or ""
    m = LOCAL_RE.match(title)
    local = "기초자치단체" in tags or m is not None
    if not local:
        return hit[0]

    where = (m.group(1) if m else "") + "," + ",".join(tags)
    for city in cities:
        if city in where:
            return city
    return None


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

def fmt_line(item: dict, today: date, label: str | None = None) -> str:
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
    # 지역 괄호가 없는 제목에만 판정한 지역을 붙인다. 원래 제목은 바꾸지 않는다.
    if label and not title.lstrip().startswith("["):
        title = f"[{label}] {title}"
    org = item.get("jrsdInsttNm") or ""
    field = item.get("pldirSportRealmLclasCodeNm") or ""
    url = item.get("pblancUrl") or ""
    tail = " · ".join(x for x in (field, org) if x)
    return f"· {period} | {title}\n  {tail}\n  {url}"


@dataclass
class StartupFilter:
    startup_keywords: list[str]
    funding_keywords: list[str]
    regions: list[str]
    cities: list[str]
    within: int
    national_min: int = NATIONAL_MIN


def startup_section(current: list[dict], fresh_ids: set[str], has_previous: bool,
                    cfg: StartupFilter, top: int, today: date) -> list[str]:
    """창업 자금 섹션. 상시 공고는 매일 반복하지 않도록 신규일 때만 싣는다."""
    picked = []
    for x in current:
        if not x.get("pblancUrl"):
            continue
        if not (is_startup(x, cfg.startup_keywords) and is_funding(x, cfg.funding_keywords)):
            continue
        label = in_my_region(x, cfg.regions, cfg.cities, cfg.national_min)
        if label is None:
            continue
        _, end = parse_period(x.get("reqstBeginEndDe") or "")
        left = days_left(end, today)
        if left is not None and left < 0:
            continue
        picked.append((left, label, x))

    fresh = [p for p in picked if p[2].get("pblancId") in fresh_ids]
    closing = sorted((p for p in picked if p[0] is not None and p[0] <= cfg.within),
                     key=lambda p: p[0])
    undated = sum(1 for p in picked if p[0] is None)

    where = "·".join(cfg.regions + cfg.cities + ["전국"])
    out = [f"■ 창업 자금 ({where})", "  [신규]"]
    if not has_previous:
        out.append("  비교 대상이 없어 신규 판정을 생략합니다. (첫 수집)")
    elif not fresh:
        out.append("  없음")
    else:
        for _, label, x in fresh[:top]:
            out.append(fmt_line(x, today, label))
        if len(fresh) > top:
            out.append(f"  … 외 {len(fresh) - top}건")

    out.append(f"  [마감 D-{cfg.within} 이내]")
    if not closing:
        out.append("  없음")
    else:
        for _, label, x in closing[:top]:
            out.append(fmt_line(x, today, label))
        if len(closing) > top:
            out.append(f"  … 외 {len(closing) - top}건")
    out.append(f"  상시·기간미표기 {undated}건은 신규일 때만 표시합니다.")
    return out


def build_report(current: list[dict], previous: list[dict] | None,
                 keywords: list[str], within: int, top: int,
                 as_of: datetime, snapshot: str, compare: str | None,
                 startup: StartupFilter | None = None,
                 region: tuple[list[str], list[str]] | None = None) -> str:
    """region 이 (광역 목록, 시 목록)이면 키워드 공고에도 지역 필터를 건다."""
    today = as_of.date()
    hits = [x for x in current if matches(x, keywords) and x.get("pblancUrl")]
    keyword_total = len(hits)
    labels: dict[str, str] = {}
    if region is not None:
        kept = []
        for x in hits:
            label = in_my_region(x, region[0], region[1])
            if label is not None:
                labels[x.get("pblancId")] = label
                kept.append(x)
        hits = kept

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

    # 창업 자금을 맨 위에 둔다. 키워드 공고는 그 아래에 이어진다.
    if startup is not None:
        out.append("")
        out.extend(startup_section(current, fresh_ids, previous is not None,
                                   startup, top, today))
        out.append("")
        out.append("━━━━━━━━━━")
        out.append("▶ IT·AI 키워드 공고")

    if region is None:
        out.append(f"전체 {len(current)}건 중 키워드 일치 {len(hits)}건")
    else:
        where = "·".join(region[0] + region[1] + ["전국"])
        out.append(f"전체 {len(current)}건 중 키워드 일치 {keyword_total}건, "
                   f"{where} 대상 {len(hits)}건")
    out.append("")

    out.append(f"■ 신규 (직전 수집 대비)")
    if previous is None:
        out.append("  비교 대상이 없어 신규 판정을 생략합니다. (첫 수집)")
    elif not fresh:
        out.append("  없음")
    else:
        for x in fresh[:top]:
            out.append(fmt_line(x, today, labels.get(x.get("pblancId"))))
        if len(fresh) > top:
            out.append(f"  … 외 {len(fresh) - top}건")
    out.append("")

    out.append(f"■ 마감 임박 (D-{within} 이내)")
    if not closing:
        out.append("  없음")
    else:
        for _, x in closing[:top]:
            out.append(fmt_line(x, today, labels.get(x.get("pblancId"))))
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
    parser.add_argument("--no-startup", action="store_true",
                        help="창업 자금 섹션을 끈다")
    parser.add_argument("--startup-keyword", action="append", default=None,
                        help="창업 판정 제목 키워드. 여러 번 지정 가능")
    parser.add_argument("--funding-keyword", action="append", default=None,
                        help="자금성 판정 키워드(제목·해시태그). 여러 번 지정 가능")
    parser.add_argument("--startup-within", type=int, default=30,
                        help="창업 자금 마감 기준 일수 (기본 30)")
    parser.add_argument("--region", action="append", default=None,
                        help="받을 광역 지역 (기본 서울, 경기). 전국 대상은 항상 포함. 여러 번 지정 가능")
    parser.add_argument("--city", action="append", default=None,
                        help="시·군·구 공고 중 받을 곳 (기본 수원시). 여러 번 지정 가능")
    parser.add_argument("--all-regions", action="store_true",
                        help="키워드 공고에 지역 필터를 걸지 않는다 (창업 자금 섹션은 그대로)")
    args = parser.parse_args()

    regions = args.region or DEFAULT_REGIONS
    cities = args.city or DEFAULT_CITIES
    region = None if args.all_regions else (regions, cities)

    startup = None
    if not args.no_startup:
        startup = StartupFilter(
            startup_keywords=args.startup_keyword or DEFAULT_STARTUP_KEYWORDS,
            funding_keywords=args.funding_keyword or DEFAULT_FUNDING_KEYWORDS,
            regions=regions,
            cities=cities,
            within=args.startup_within,
        )

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
        datetime.now(KST), current_dir.name, compare_name, startup, region,
    )
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
