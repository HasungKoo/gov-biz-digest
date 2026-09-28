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


# ---------- 창업 자금: is_startup / is_funding ----------
# 2026-09-28 수집분의 실제 제목·해시태그를 줄여 쓴다.

SK = ["창업", "스타트업", "벤처"]
FK = ["자금", "융자", "보증", "투자", "지원금", "사업화",
      "바우처", "상금", "데모데이", "IR", "TIPS"]
ALL_REGIONS = ("서울,부산,대구,인천,전남광주,대전,울산,세종,경기,강원,"
               "충북,충남,전북,경북,경남,제주")


def test_is_startup_분야_대상_제목():
    assert digest.is_startup({"pldirSportRealmLclasCodeNm": "창업"}, SK)
    assert digest.is_startup({"trgetNm": "창업벤처"}, SK)
    assert digest.is_startup({"pblancNm": "2026년 AI 창업 경진대회 참가자 모집 공고"}, SK)


def test_is_startup_일반_중소기업_공고는_거짓():
    item = {"pblancNm": "[경기] 수원시 2026년 중소기업 특례보증 지원계획 공고",
            "pldirSportRealmLclasCodeNm": "금융", "trgetNm": "중소기업"}
    assert digest.is_startup(item, SK) is False


def test_is_funding_해시태그로도_판정한다():
    """제목에 자금 단어가 없어도 해시태그의 사업화·상금으로 잡는다."""
    item = {"pblancNm": "2026년 에너지 창업 경연대회 참여자 모집 공고",
            "hashtags": "2026,경영,사업화,예비창업자"}
    assert digest.is_funding(item, FK) is True


def test_is_funding_멘토링만_있으면_거짓():
    item = {"pblancNm": "[경기] 용인시 2026년 창업 멘토링(1:1) 희망기업 모집 공고",
            "pldirSportRealmLclasCodeNm": "창업",
            "hashtags": "2026,경기도,경영,멘토링,용인시,창업"}
    assert digest.is_funding(item, FK) is False


# ---------- 창업 자금: region_label ----------

def test_region_label_지역이_10곳_이상이면_전국():
    item = {"pblancNm": "2026년 울산 스타트업 페스타 참가자 모집 공고",
            "hashtags": ALL_REGIONS + ",스타트업"}
    assert digest.region_label(item, ["서울", "경기"], ["수원시"]) == "전국"


def test_region_label_광역_공고는_통과():
    item = {"pblancNm": "[서울] 2026년 하반기 SBA 맞춤형 Kibo-Star밸리기업 지원계획 공고",
            "hashtags": "금융,서울,2026"}
    assert digest.region_label(item, ["서울", "경기"], ["수원시"]) == "서울"


def test_region_label_지정한_시만_통과():
    suwon = {"pblancNm": "[경기] 수원시 2026년 중소기업 동행지원 사업계획 공고",
             "hashtags": "금융,경기,수원시,기초자치단체"}
    assert digest.region_label(suwon, ["서울", "경기"], ["수원시"]) == "수원시"


def test_region_label_다른_시는_기초자치단체_태그_없어도_제외():
    """화성시 공고에는 기초자치단체 태그가 없었다. 제목으로 잡는다."""
    item = {"pblancNm": "[경기] 화성시 2026년 하반기 벤처인증 비용 지원사업 참여기업 모집 공고",
            "hashtags": "기타,경기,벤처투자유형,화성산업진흥원,경기도,벤처기업"}
    assert digest.region_label(item, ["서울", "경기"], ["수원시"]) is None


def test_region_label_서울_구_공고는_제외():
    item = {"pblancNm": "[서울] 서대문구 2026년 청년창업기업 경영컨설팅 모집 공고",
            "hashtags": "2026,서울,기초자치단체,서대문구"}
    assert digest.region_label(item, ["서울", "경기"], ["수원시"]) is None


def test_region_label_여러_시_공동공고에_수원이_있으면_통과():
    item = {"pblancNm": "[경기] 수원시ㆍ용인시ㆍ화성시 2026년 청년일자리도약장려금 모집 공고",
            "hashtags": "인력,경기,수원시,용인시,화성시"}
    assert digest.region_label(item, ["서울", "경기"], ["수원시"]) == "수원시"


def test_region_label_다른_광역과_지역태그_없음은_제외():
    busan = {"pblancNm": "[부산] 2026년 창업 지원 공고", "hashtags": "부산,창업"}
    none = {"pblancNm": "2026년 창업 지원 공고", "hashtags": "창업"}
    assert digest.region_label(busan, ["서울", "경기"], ["수원시"]) is None
    assert digest.region_label(none, ["서울", "경기"], ["수원시"]) is None


# ---------- 창업 자금: startup_section ----------

CFG = digest.StartupFilter(SK, FK, ["서울", "경기"], ["수원시"], within=30)
TODAY = date(2026, 9, 28)


def _item(pid, title, period, tags, field="창업"):
    return {"pblancId": pid, "pblancNm": title, "reqstBeginEndDe": period,
            "hashtags": tags, "pldirSportRealmLclasCodeNm": field,
            "pblancUrl": f"https://example.invalid/{pid}"}


def test_startup_section_상시공고는_신규일_때만():
    old = _item("P1", "2026년 팁스(TIPS) 창업기업 지원계획", "예산 소진시까지", ALL_REGIONS)
    new = _item("P2", "2026년 창업BuS 투자 라운드 상시 모집", "상시 접수", ALL_REGIONS)
    text = "\n".join(digest.startup_section([old, new], {"P2"}, True, CFG, 10, TODAY))
    assert "창업BuS" in text
    assert "팁스" not in text
    assert "상시·기간미표기 2건" in text


def test_startup_section_마감지난것과_기간밖은_뺀다():
    past = _item("P1", "창업 투자 공고 A", "2026-09-01 ~ 2026-09-27", ALL_REGIONS)
    far = _item("P2", "창업 투자 공고 B", "2026-09-01 ~ 2026-12-31", ALL_REGIONS)
    soon = _item("P3", "창업 투자 공고 C", "2026-09-01 ~ 2026-10-07", ALL_REGIONS)
    text = "\n".join(digest.startup_section([past, far, soon], set(), True, CFG, 10, TODAY))
    assert "공고 C" in text and "D-9" in text
    assert "공고 A" not in text and "공고 B" not in text


def test_startup_section_전국_제목에만_지역표시를_붙인다():
    item = _item("P1", "창업 투자 공고", "2026-09-01 ~ 2026-10-07", ALL_REGIONS)
    text = "\n".join(digest.startup_section([item], set(), True, CFG, 10, TODAY))
    assert "[전국] 창업 투자 공고" in text


def test_build_report_창업자금이_키워드_공고보다_먼저():
    from datetime import datetime
    items = [_item("P1", "창업 투자 공고", "2026-09-01 ~ 2026-10-07", ALL_REGIONS),
             _item("P2", "2026년 AI 실증 지원사업", "2026-09-01 ~ 2026-10-01", ALL_REGIONS, "기술")]
    text = digest.build_report(items, items, ["AI"], 14, 10,
                               datetime(2026, 9, 28, 10, 0, tzinfo=digest.KST),
                               "s", "c", CFG)
    assert text.index("■ 창업 자금") < text.index("■ 신규 (직전 수집 대비)")
    assert text.index("■ 창업 자금") < text.index("■ 마감 임박")


# ---------- 창업 자금: host_allowed ----------

@pytest.mark.parametrize("host, expected", [
    ("중소벤처기업부", True),       # 중앙부처는 통과
    ("기후에너지환경부", True),
    ("서울특별시", True),
    ("경기도", True),              # 수원시 공고도 소관기관은 경기도로 온다
    ("강원특별자치도", False),      # 전국 대상이라도 다른 지자체 주관은 제외
    ("울산광역시", False),
    ("전남광주통합특별시", False),
    ("", True),
])
def test_host_allowed(host, expected):
    assert digest.host_allowed({"jrsdInsttNm": host}, ["서울", "경기"]) is expected


def test_startup_section_다른_지자체_주관_전국공고는_뺀다():
    ulsan = _item("P1", "2026년 울산 스타트업 페스타 상금 공고", "2026-09-01 ~ 2026-10-07", ALL_REGIONS)
    ulsan["jrsdInsttNm"] = "울산광역시"
    mss = _item("P2", "초격차 스타트업 투자유치 공고", "2026-09-01 ~ 2026-10-07", ALL_REGIONS)
    mss["jrsdInsttNm"] = "중소벤처기업부"
    text = "\n".join(digest.startup_section([ulsan, mss], set(), True, CFG, 10, TODAY))
    assert "초격차" in text
    assert "울산" not in text


def test_build_report_키워드_공고도_지방은_뺀다():
    """국가기관 전국 공고는 남기고, 지방 지자체 주관·지방 한정 공고는 뺀다."""
    from datetime import datetime
    national = _item("P1", "2026년 AI 실증 지원사업", "2026-09-01 ~ 2026-10-01", ALL_REGIONS, "기술")
    national["jrsdInsttNm"] = "과학기술정보통신부"
    gyeongnam = _item("P2", "[경남] 2026년 산업안전 AI 스마트공장 구축 지원사업",
                      "2026-09-01 ~ 2026-10-01", "기술,경남", "기술")
    gyeongnam["jrsdInsttNm"] = "경상남도"
    sejong = _item("P3", "[세종] 2026년 2차 중소기업 정보보호 지원 사업",
                   "2026-09-01 ~ 2026-10-01", "경영,세종", "경영")
    sejong["jrsdInsttNm"] = "과학기술정보통신부"   # 국가기관이라도 세종 한정
    items = [national, gyeongnam, sejong]
    text = digest.build_report(items, items, ["AI", "정보보호"], 14, 10,
                               datetime(2026, 9, 28, 10, 0, tzinfo=digest.KST),
                               "s", "c", None, (["서울", "경기"], ["수원시"]))
    assert "[전국] 2026년 AI 실증" in text
    assert "경남" not in text
    assert "세종" not in text
    assert "키워드 일치 3건, 서울·경기·수원시·전국 대상 1건" in text
