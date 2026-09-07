"""bizinfo_digest.py 의 순수 함수 검증.

API를 호출하지 않는다. 저장된 파일도 읽지 않는다.
날짜 파싱, 키워드 필터, 신규 판정만 본다.
"""

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "bizinfo_digest.py"

spec = importlib.util.spec_from_file_location("bizinfo_digest", SCRIPT)
digest = importlib.util.module_from_spec(spec)
sys.modules["bizinfo_digest"] = digest
spec.loader.exec_module(digest)


# ---------- parse_period ----------
# 실제 응답에서 확인한 표기를 그대로 쓴다. (2026-09-07 기준 1,550건)

@pytest.mark.parametrize("text, expected", [
    # 실제 응답 형식
    ("2026-09-03 ~ 2026-09-28", (date(2026, 9, 3), date(2026, 9, 28))),
    # API 문서의 샘플 형식
    ("20220727 ~ 20220930", (date(2022, 7, 27), date(2022, 9, 30))),
    # 점 구분자. 실제로 1건 존재
    ("2020.01.01 ~ 2026.12.31", (date(2020, 1, 1), date(2026, 12, 31))),
])
def test_parse_period_날짜형식(text, expected):
    assert digest.parse_period(text) == expected


@pytest.mark.parametrize("text", [
    "예산 소진시까지",
    "예산 소진시 까지",     # 띄어쓰기 변형
    "예산 소진 시까지",     # 또 다른 변형
    "상시 접수",
    "선착순 접수",
    "모집 완료시",
    "세부사업별 상이",
    "추후 공지",
    "매월 10일 18:00까지",  # 숫자가 있지만 날짜가 아니다
    "매월 1일~20일",
    "",
])
def test_parse_period_비표준표기는_추측하지_않는다(text):
    """자유 입력이라 표기가 33종이다. 날짜가 아니면 (None, None)."""
    assert digest.parse_period(text) == (None, None)


def test_parse_period_잘못된_날짜값():
    """13월 같은 값은 날짜로 인정하지 않는다."""
    assert digest.parse_period("2026-13-45 ~ 2026-99-99") == (None, None)


# ---------- days_left ----------

@pytest.mark.parametrize("end, today, expected", [
    (date(2026, 9, 14), date(2026, 9, 7), 7),
    (date(2026, 9, 7), date(2026, 9, 7), 0),    # 오늘 마감
    (date(2026, 9, 1), date(2026, 9, 7), -6),   # 이미 마감
])
def test_days_left(end, today, expected):
    assert digest.days_left(end, today) == expected


def test_days_left_마감일_없으면_None():
    assert digest.days_left(None, date(2026, 9, 7)) is None


# ---------- strip_html ----------

def test_strip_html_태그와_개체참조를_걷어낸다():
    raw = "<p>소상공인의&nbsp;온라인시장 진출을</p>\r\n<p>지원합니다</p>"
    assert digest.strip_html(raw) == "소상공인의 온라인시장 진출을 지원합니다"


def test_strip_html_빈값():
    assert digest.strip_html("") == ""
    assert digest.strip_html(None) == ""


# ---------- matches ----------

KW = ["AI", "인공지능", "ICT", "SW", "소프트웨어",
      "데이터", "클라우드", "디지털전환", "DX", "정보보호"]


def test_matches_제목에_키워드가_있으면_참():
    item = {"pblancNm": "2026년 AI선박 기자재 및 첨단부품 실증지원사업 공고"}
    assert digest.matches(item, KW) is True


def test_matches_제목에_없으면_거짓():
    item = {"pblancNm": "[제주] 타이베이 국제여전(ITF) 참가업체 모집 공고"}
    assert digest.matches(item, KW) is False


def test_matches_본문은_검사하지_않는다():
    """본문에 스쳐 지나간 단어가 오염을 만들었다.
    276건 -> 89건으로 줄인 근거."""
    item = {
        "pblancNm": "2026년 하반기 방산전시회 참가 지원사업 모집 공고",
        "bsnsSumryCn": "<p>소프트웨어 및 데이터 분야 기업도 참여 가능합니다</p>",
    }
    assert digest.matches(item, KW) is False


def test_matches_제목_없는_항목():
    assert digest.matches({}, KW) is False


# ---------- new_ids ----------

def test_new_ids_직전에_없던_것만():
    previous = [{"pblancId": "PBLN_001"}, {"pblancId": "PBLN_002"}]
    current = [{"pblancId": "PBLN_002"}, {"pblancId": "PBLN_003"}]
    assert digest.new_ids(current, previous) == {"PBLN_003"}


def test_new_ids_비교대상_없으면_빈집합():
    """첫 수집에서 전부 신규로 찍으면 보고가 무의미해진다."""
    current = [{"pblancId": "PBLN_001"}, {"pblancId": "PBLN_002"}]
    assert digest.new_ids(current, None) == set()


def test_new_ids_변화_없으면_빈집합():
    same = [{"pblancId": "PBLN_001"}]
    assert digest.new_ids(same, same) == set()
