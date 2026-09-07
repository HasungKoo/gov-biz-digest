#!/usr/bin/env python3
"""기업마당 공고 HTML 보고서.

저장된 원본만 읽는다. API를 호출하지 않는다.
digest 와 분리한 이유: cron 이 매일 쓰는 digest 를 건드리다 깨지면
아침 보고가 안 온다. HTML 은 하루 안 나와도 된다.

계산과 출력을 분리했다. build_report() 는 파이썬 자료구조를 돌려주므로
나중에 JSON API 가 필요하면 그대로 재사용할 수 있다. --json 이 그 증거다.
"""

from __future__ import annotations

import argparse
import html as html_mod
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RAW = ROOT / "data" / "raw" / "bizinfo"
DEFAULT_OUT = ROOT / "docs" / "index.html"

# digest 의 순수 함수를 재사용한다. 파싱 규칙이 두 곳에 갈라지면 안 된다.
_spec = importlib.util.spec_from_file_location(
    "bizinfo_digest", Path(__file__).resolve().parent / "bizinfo_digest.py")
digest = importlib.util.module_from_spec(_spec)
sys.modules["bizinfo_digest"] = digest
_spec.loader.exec_module(digest)


def run_dirs(raw_root: Path) -> list[Path]:
    if not raw_root.exists():
        return []
    return sorted((p for p in raw_root.iterdir() if p.is_dir()), key=lambda p: p.name)


def build_report(raw_root: Path, keywords: list[str], as_of: datetime) -> dict:
    """계산만 한다. HTML 을 만들지 않는다."""
    runs = run_dirs(raw_root)
    if not runs:
        raise SystemExit("수집분이 없습니다.")

    current_dir = runs[-1]
    items = digest.load_items(current_dir)
    today = as_of.date()

    hits = [x for x in items if digest.matches(x, keywords) and x.get("pblancUrl")]

    rows = []
    for x in hits:
        _, end = digest.parse_period(x.get("reqstBeginEndDe") or "")
        left = digest.days_left(end, today)
        rows.append({
            "id": x.get("pblancId"),
            "title": x.get("pblancNm") or "",
            "url": x.get("pblancUrl") or "",
            "org": x.get("jrsdInsttNm") or "",
            "field": x.get("pldirSportRealmLclasCodeNm") or "기타",
            "target": x.get("trgetNm") or "",
            "period_raw": x.get("reqstBeginEndDe") or "",
            "end": end.isoformat() if end else None,
            "days_left": left,
        })

    # 마감일 있는 것 먼저, 임박한 순. 그다음 상시·미정.
    dated = sorted((r for r in rows if r["days_left"] is not None),
                   key=lambda r: r["days_left"])
    undated = [r for r in rows if r["days_left"] is None]

    fields = sorted({r["field"] for r in rows})

    return {
        "as_of": as_of.isoformat(),
        "snapshot": current_dir.name,
        "run_count": len(runs),
        "total_items": len(items),
        "matched": len(rows),
        "keywords": keywords,
        "fields": fields,
        "dated": dated,
        "undated": undated,
    }


def esc(s: str) -> str:
    return html_mod.escape(s or "")


def badge(left: int | None) -> tuple[str, str]:
    """(표시문자, CSS 클래스)"""
    if left is None:
        return ("상시·미정", "b-none")
    if left < 0:
        return (f"마감 {-left}일 전", "b-closed")
    if left == 0:
        return ("오늘 마감", "b-today")
    if left <= 3:
        return (f"D-{left}", "b-urgent")
    if left <= 7:
        return (f"D-{left}", "b-soon")
    return (f"D-{left}", "b-later")


def row_html(r: dict) -> str:
    text, cls = badge(r["days_left"])
    end = f' · {r["end"]}' if r["end"] else f' · {esc(r["period_raw"])}'
    meta = " · ".join(x for x in (r["field"], r["org"], r["target"]) if x)
    return f"""      <li class="row" data-field="{esc(r['field'])}" data-closed="{'1' if (r['days_left'] is not None and r['days_left'] < 0) else '0'}">
        <span class="badge {cls}">{esc(text)}</span>
        <div class="body">
          <a href="{esc(r['url'])}" target="_blank" rel="noopener">{esc(r['title'])}</a>
          <div class="meta">{esc(meta)}{end}</div>
        </div>
      </li>"""


def render_html(rep: dict) -> str:
    as_of = datetime.fromisoformat(rep["as_of"])
    closed = sum(1 for r in rep["dated"] if r["days_left"] < 0)

    field_buttons = "".join(
        f'<button class="chip" data-f="{esc(f)}">{esc(f)}</button>'
        for f in rep["fields"]
    )
    dated_rows = "\n".join(row_html(r) for r in rep["dated"])
    undated_rows = "\n".join(row_html(r) for r in rep["undated"])

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>중소기업 IT·AI 지원사업 다이제스트</title>
<style>
:root {{
  --bg: #fff; --fg: #1a1a1a; --dim: #666; --line: #e5e5e5; --card: #fafafa;
  --urgent: #d32f2f; --soon: #ed6c02; --later: #2e7d32; --none: #757575;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #16181c; --fg: #e8e8e8; --dim: #9aa0a6; --line: #2c2f34; --card: #1e2126;
    --urgent: #ef5350; --soon: #ffa726; --later: #66bb6a; --none: #90959c;
  }}
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; padding: 24px 16px 64px; background: var(--bg); color: var(--fg);
  font: 15px/1.6 -apple-system, "Segoe UI", "Noto Sans KR", sans-serif;
}}
.wrap {{ max-width: 860px; margin: 0 auto; }}
h1 {{ font-size: 21px; margin: 0 0 6px; }}
.sub {{ color: var(--dim); font-size: 13px; margin-bottom: 20px; }}
.controls {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }}
.chip {{
  border: 1px solid var(--line); background: var(--card); color: var(--fg);
  border-radius: 999px; padding: 5px 12px; font-size: 13px; cursor: pointer;
}}
.chip.on {{ background: var(--fg); color: var(--bg); border-color: var(--fg); }}
.toggle {{ font-size: 13px; color: var(--dim); margin: 12px 0 20px; }}
.toggle label {{ cursor: pointer; }}
h2 {{ font-size: 15px; margin: 28px 0 10px; padding-top: 18px; border-top: 1px solid var(--line); }}
h2 .cnt {{ color: var(--dim); font-weight: normal; }}
ul {{ list-style: none; margin: 0; padding: 0; }}
.row {{ display: flex; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--line); }}
.row.hide {{ display: none; }}
.badge {{
  flex: 0 0 84px; font-size: 12px; font-weight: 600; padding-top: 2px;
}}
.b-today, .b-urgent {{ color: var(--urgent); }}
.b-soon {{ color: var(--soon); }}
.b-later {{ color: var(--later); }}
.b-none, .b-closed {{ color: var(--none); }}
.body a {{ color: var(--fg); text-decoration: none; }}
.body a:hover {{ text-decoration: underline; }}
.meta {{ color: var(--dim); font-size: 12.5px; margin-top: 3px; }}
footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--line);
          color: var(--dim); font-size: 12.5px; }}
footer code {{ font-size: 11.5px; }}
</style>
</head>
<body>
<div class="wrap">

  <h1>중소기업 IT·AI 지원사업 다이제스트</h1>
  <div class="sub">
    {as_of:%Y-%m-%d %H:%M} KST 기준 · 전체 {rep['total_items']:,}건 중 키워드 일치 {rep['matched']}건
  </div>

  <div class="controls">
    <button class="chip on" data-f="all">전체</button>
    {field_buttons}
  </div>
  <div class="toggle">
    <label><input type="checkbox" id="showClosed"> 마감된 공고도 보기 ({closed}건)</label>
  </div>

  <h2>마감일이 있는 공고 <span class="cnt">{len(rep['dated'])}건</span></h2>
  <ul id="dated">
{dated_rows}
  </ul>

  <h2>상시 · 기간 미표기 <span class="cnt">{len(rep['undated'])}건</span></h2>
  <ul id="undated">
{undated_rows}
  </ul>

  <footer>
    출처: 기업마당(bizinfo) · 데이터는 기업마당 지원사업정보 API에서 받았습니다.<br>
    신청 자격과 마감 시각은 반드시 공고 원문에서 확인하세요.<br>
    키워드: {esc(', '.join(rep['keywords']))}<br>
    <code>snapshot {esc(rep['snapshot'])}</code>
  </footer>

</div>
<script>
(function () {{
  var chips = document.querySelectorAll('.chip');
  var showClosed = document.getElementById('showClosed');
  var current = 'all';

  function apply() {{
    document.querySelectorAll('.row').forEach(function (row) {{
      var okField = (current === 'all') || (row.dataset.field === current);
      var okClosed = showClosed.checked || row.dataset.closed === '0';
      row.classList.toggle('hide', !(okField && okClosed));
    }});
  }}

  chips.forEach(function (c) {{
    c.addEventListener('click', function () {{
      chips.forEach(function (x) {{ x.classList.remove('on'); }});
      c.classList.add('on');
      current = c.dataset.f;
      apply();
    }});
  }});
  showClosed.addEventListener('change', apply);
  apply();
}})();
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="기업마당 공고 HTML 보고서")
    parser.add_argument("--raw-root", default=str(DEFAULT_RAW))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--keyword", action="append", default=None)
    parser.add_argument("--json", action="store_true",
                        help="HTML 대신 계산 결과를 JSON 으로 출력")
    args = parser.parse_args()

    keywords = args.keyword or digest.DEFAULT_KEYWORDS
    rep = build_report(Path(args.raw_root), keywords, datetime.now(KST))

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(rep), encoding="utf-8")
    print(f"[HTML] {rep['matched']}건 · {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
