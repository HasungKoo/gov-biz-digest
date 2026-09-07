#!/usr/bin/env python3
"""기업마당 지원사업정보 API 수집기.

한 번 호출해 전체 공고를 받아 원본 그대로 저장한다.
필터·정렬·보고는 하지 않는다. 그것은 digest 단계의 일이다.

저장 구조:
    data/raw/bizinfo/<타임스탬프>/
        bizinfo.json
        bizinfo.json.sha256
        manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

API_URL = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"
KST = timezone(timedelta(hours=9))

# 프로젝트 루트 = 이 파일의 상위의 상위
ROOT = Path(__file__).resolve().parent.parent


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_params(args, key: str) -> dict:
    """요청 파라미터를 만든다. 값이 없는 항목은 보내지 않는다."""
    params = {
        "crtfcKey": key,
        "dataType": "json",
        "searchCnt": str(args.search_cnt),
    }
    if args.lclas_id:
        params["searchLclasId"] = args.lclas_id
    if args.hashtags:
        params["hashtags"] = args.hashtags
    return params


def redact(params: dict) -> dict:
    """manifest 기록용. 인증키는 절대 남기지 않는다."""
    safe = {k: v for k, v in params.items() if k != "crtfcKey"}
    safe["crtfcKey"] = "<redacted>"
    return safe


def fetch(params: dict, timeout: int, retries: int) -> dict:
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            res = requests.get(API_URL, params=params, timeout=timeout)
            res.raise_for_status()
            return res.json()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"[수집] 시도 {attempt}/{retries} 실패: {exc}", file=sys.stderr)
    raise RuntimeError(f"API 호출 실패: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="기업마당 지원사업 공고 수집")
    parser.add_argument("--search-cnt", type=int, default=0,
                        help="조회건수. 0이면 전체 (기본 0)")
    parser.add_argument("--lclas-id", default="",
                        help="분야 코드. 01금융 02기술 03인력 04수출 05내수 06창업 07경영 09기타")
    parser.add_argument("--hashtags", default="",
                        help="해시태그. 쉼표로 다중 입력")
    parser.add_argument("--out-root", default=str(ROOT / "data" / "raw" / "bizinfo"),
                        help="저장 최상위 경로")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    key = os.getenv("BIZINFO_API_KEY", "").strip()
    if not key:
        print("[수집] BIZINFO_API_KEY 가 없습니다. .env 를 확인하세요.", file=sys.stderr)
        return 1

    params = build_params(args, key)
    collected_at = datetime.now(KST)

    payload = fetch(params, args.timeout, args.retries)
    items = payload.get("jsonArray")
    if not isinstance(items, list):
        print("[수집] 응답에 jsonArray 가 없습니다. 형식이 바뀌었을 수 있습니다.",
              file=sys.stderr)
        return 1

    stamp = collected_at.strftime("%Y%m%dT%H%M%S%z")
    out_dir = Path(args.out_root) / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_path = out_dir / "bizinfo.json"
    raw_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    digest = sha256_of(raw_path)
    (out_dir / "bizinfo.json.sha256").write_text(
        f"{digest}  bizinfo.json\n", encoding="utf-8"
    )

    # 건강 지표. 판정은 하지 않고 세기만 한다.
    with_url = sum(1 for x in items if x.get("pblancUrl"))
    with_id = sum(1 for x in items if x.get("pblancId"))
    with_period = sum(1 for x in items if x.get("reqstBeginEndDe"))

    manifest = {
        "source": "bizinfo",
        "api_url": API_URL,
        "collected_at": collected_at.isoformat(),
        "request_params": redact(params),
        "api_key_recorded": False,
        "item_count": len(items),
        "reported_total": items[0].get("totCnt") if items else None,
        "field_coverage": {
            "pblancId": with_id,
            "pblancUrl": with_url,
            "reqstBeginEndDe": with_period,
        },
        "files": [
            {"name": "bizinfo.json", "sha256": digest,
             "bytes": raw_path.stat().st_size},
        ],
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"[수집] {len(items)}건 저장 · {out_dir}")
    if with_id < len(items):
        print(f"[수집] 경고: 공고ID 없는 항목 {len(items) - with_id}건")
    if with_url < len(items):
        print(f"[수집] 경고: 공고URL 없는 항목 {len(items) - with_url}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
