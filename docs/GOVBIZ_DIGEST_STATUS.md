# gov-biz-digest 프로젝트 — 재시작 요약본

> 갱신일 2026-09-07 · 브랜치 `main` · 기준 커밋 `af09fec`
> 자매 문서: `YOUTUBE_DIGEST_STATUS`, `HORSE_AGENT_STATUS`, `SESSION_2026-09-07`
> API 키·토큰·서비스키는 이 문서에 포함하지 않는다.

---

## 현재 위치 — 한 문장

기업마당 API로 중소기업 지원사업 공고 1,550건을 매일 두 번 수집해, IT·AI 키워드로 89건을 걸러
**Telegram 보고 + 웹페이지 공개**까지 자동으로 하며, 파이프라인 전 단계가 검증됐다.

- 공개 주소: `https://gov-biz-digest.vercel.app`
- 저장소: `https://github.com/HasungKoo/gov-biz-digest`
- 경로: `/home/geoheim/projects/gov-biz-digest`

**하루 만에 완성했다.** youtube-digest가 사흘 걸린 자리다. 패턴 이식이 실제로 빠르다.

---

## 1. 확인된 상태 (2026-09-07)

| 항목 | 결과 |
| --- | --- |
| 브랜치 | `main`, 커밋 `af09fec` |
| 테스트 | `28 passed` (깨뜨려 3 failed 확인 후 원복까지 검증) |
| 수집 | 1,550건, 필드 결손 0 |
| 필터 | 키워드 일치 89건 |
| 파이프라인 | 5단계 전부 통과, 8초 소요 |
| cron | `899ed48645bb`, `0 9,17 * * *` |

커밋 이력.

```
af09fec chore: 자동화 스크립트 사본 보관
a7b4bec chore: 웹페이지 자동 갱신 2026-09-07 20:45
b1be451 feat: HTML 보고서 생성 및 초기 페이지
1e8e863 feat: 기업마당 공고 수집기 추가
5731811 test: 날짜 파싱·키워드 필터·신규 판정 검증 추가
cac840c feat: 공고 텍스트 보고 추가 (제목 기준 키워드 필터)
4a17223 docs: 프로젝트 규칙과 에이전트 성격 정의
```

---

## 2. 전체 구조

```
[매일 09:00, 17:00 cron]  또는  [수동 실행]
              ↓
   ~/.hermes/scripts/govbiz_daily.sh
              ↓
1. bizinfo_collect_once.py  → 원본 저장 + SHA-256 + manifest
2. bizinfo_digest.py        → 텍스트 보고
3. curl sendMessage         → Telegram (gateway 경유하지 않음)
4. bizinfo_report.py        → docs/index.html
5. git push                 → Vercel 자동 배포
```

**LLM이 이 경로에 없다.** youtube와 같은 구조지만 이유가 다르다.
youtube는 Gemini 장애 회피, 여기는 **정확성**이다. 마감일이 그럴듯하게 틀리면 안 된다.

### 구성요소

| 구성요소 | 역할 | 위치 |
| --- | --- | --- |
| `bizinfo_collect_once.py` | API 1회 호출, 원본 저장 | `scripts/` |
| `bizinfo_digest.py` | 텍스트 보고 + 순수 함수 | `scripts/` |
| `bizinfo_report.py` | HTML 생성 (digest 함수 재사용) | `scripts/` |
| `govbiz_daily.sh` | 5단계 실행 | `~/.hermes/scripts/` · 사본 `ops/` |
| cron `899ed48645bb` | 09:00, 17:00 | `~/.hermes/cron/jobs.json` |
| AGENTS.md / SOUL.md | 규칙과 태도 | git 안 |

---

## 3. API — 기업마당 지원사업정보

```
GET https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do
```

| 파라미터 | 값 | 비고 |
| --- | --- | --- |
| `crtfcKey` | 인증키 | `.env`의 `BIZINFO_API_KEY` |
| `dataType` | `json` | rss도 가능하나 파싱이 번거롭다 |
| `searchCnt` | `0` | 0이면 전체 (1,550건, 3.6MB) |
| `searchLclasId` | 미사용 | 01금융 02기술 … 06창업 07경영 |
| `hashtags` | 미사용 | 분야+지역 한글 문자열 |

**분야로 좁히지 않는다.** 기술 코드로 좁히면 경영·수출에 흩어진 AI 공고를 놓친다.
전체를 받아 제목 키워드로 거른다. 호출은 어차피 1회다.

키 발급은 즉시였다. 하나의 서비스키로 지원사업API와 정책정보API를 모두 쓴다.

---

## 4. 명세와 실제 응답이 다르다 ★

가장 중요한 발견이다. **문서를 믿고 짰으면 전부 깨졌다.**

### 없는 필드

문서의 "필수(Y)" 필드 `title` `link` `seq` `author`가 **실제 응답에 없다.**

| 쓸 것 (실제) | 문서에만 있음 |
| --- | --- |
| `pblancNm` | `title` |
| `pblancUrl` | `link` |
| `pblancId` | `seq` |
| `jrsdInsttNm` | `author` |
| `reqstBeginEndDe` | `reqstDt` |

문서에 없던 `updtPnttm`(수정일자)이 실제로는 온다. 공고 연장·변경 추적에 쓸 수 있다.

### 날짜 형식

문서 샘플 `20220727 ~ 20220930` → 실제 `2026-09-03 ~ 2026-09-28` (하이픈)

### 신청기간 표기가 33종이다 ★★

**전체 1,550건 중 912건(59%)이 날짜 형식이 아니다.** 자유 입력이다.

```
617  예산 소진시까지
134  상시 접수
 37  선착순 접수
 33  모집 완료시
 23  세부사업별 상이
 11  차수별 상이
  …
  3  예산 소진시 까지     ← 띄어쓰기만 다름
  2  예산 소진 시까지     ← 또 다른 변형
  1  매월 10일 18:00까지
  1  2020.01.01 ~ 2026.12.31
```

**33종을 하나씩 매핑하지 않는다.** 다음 달에 34번째가 생긴다. 세 갈래로만 처리한다.

| 판정 | 처리 |
| --- | --- |
| 날짜 2개 파싱 성공 (638건) | D-day 계산, 임박순 정렬 |
| 파싱 실패 (912건) | 원문 그대로 표시, 하단 배치 |
| 구분자 변형 | 정규식이 `-` `.` 없음 모두 수용 |

`예산 소진시까지`를 화면에 그대로 쓰는 것이 억지 분류보다 정확하다.

---

## 5. 키워드 선정 과정 ★

youtube의 검색어 테스트와 같은 자리. **실제로 테스트해서 정했다.**

초기 목록(제목+본문 검사)은 276건이 걸렸는데 라이브커머스, 타이베이 여행박람회,
반려동물 큐텐 입점이 섞였다. 키워드별로 "이것 하나 때문에 들어온 건"을 세어 원인을 찾았다.

| 키워드 | 단독 유입 | 판정 |
| --- | --- | --- |
| `AI` | 32 | **유지.** 전부 정상 |
| `IT` | 9 | **제거.** 볼로냐, 이태리, ITF |
| `플랫폼` | 31 | **제거.** 쇼피 수출물류, 위조상품 차단 |
| `스마트` | 31 | **제거.** 스마트 HACCP, 농촌융복합 |
| `디지털` | 26 | **`디지털전환`으로 좁힘** |
| `소프트웨어` | 7 | 유지하되 본문 미검사로 정리 |
| `인공지능` | 0 | 유지. `AI`와 항상 함께 쓰인다 |

### 확정 키워드

```python
DEFAULT_KEYWORDS = [
    "AI", "인공지능", "ICT", "SW", "소프트웨어",
    "데이터", "클라우드", "디지털전환", "DX", "정보보호",
]
```

`반도체`는 검토했으나 대상 밖이라 제외.

### 본문을 검사하지 않는다 ★

오염의 상당수가 본문에서 왔다. 방산전시회 공고 본문에 "소프트웨어"가 스쳤다고
IT 공고가 되지 않는다. **공고명이 그 사업의 정체를 담는다.**

**276건 → 89건.** 목록 전체를 눈으로 확인했고 오염이 없다.
테스트에도 이 판단이 박혀 있다 (`test_matches_본문은_검사하지_않는다`).

---

## 6. 데이터 특성

| 항목 | 값 |
| --- | --- |
| 전체 | 1,550건 (`totCnt`와 일치, 페이징 불필요) |
| 지원대상 | 중소기업 1,202 · 소상공인 213 · 창업벤처 84 |
| 분야 | 경영 450 · 기술 311 · 금융 222 · 수출 205 · 인력 171 · 내수 110 · 창업 65 |
| 필드 결손 | **0.** 여섯 핵심 필드가 1,550건 전부 채워져 있다 |
| 크기 | 3.6MB (매일 저장해도 무방) |

지원대상 78%가 중소기업이라 별도 필터가 필요 없다.

manifest에 `field_coverage`를 기록한다. 어느 날 마감일이 빠지기 시작하면 이 숫자가 알려준다.

---

## 7. Telegram — gateway를 쓰지 않는다 ★

**봇을 새로 만들었다.** `@hasungkoo_govbiz_bot`. 경마·유튜브와 분리했다.

`--deliver telegram`을 쓰지 않고 스크립트가 Bot API를 직접 호출한다.

이유는 9월 7일 아침 유튜브 실패다. 수집·HTML·배포는 다 성공했는데
**gateway 배달만 죽었다.** 재시도 2회는 gateway가 정한 값이라 손댈 수 없었다.

직접 호출하면 재시도 횟수와 대기 시간을 정할 수 있다.
절전에서 깬 직후라는 조건을 아는 것은 스크립트 쪽이지 gateway가 아니다.

현재 3회 재시도, 10초 간격. 4096자 제한 대응으로 3800자 초과 시 3500자 단위 분할.

`chat_id`는 봇에게 먼저 말을 걸어야 생긴다. `getUpdates`는 오래된 메시지를 주지 않는다.

---

## 8. 웹페이지

youtube와 화면 구성이 다르다. **조회수 자리에 D-day가 들어간다.**

- 마감 임박순 정렬, D-day 배지 (D-3 이하 빨강, D-7 이하 주황)
- 분야 필터 버튼 (브라우저 JavaScript, 정적 사이트 유지)
- 마감된 공고 기본 숨김 + 토글
- 상시·미정 별도 섹션
- 다크모드 자동 대응
- 하단 출처 표기 (응답 `copyright` 필드가 `bizinfo`)

`bizinfo_report.py`가 `bizinfo_digest.py`의 순수 함수를 import해 쓴다.
**파싱 규칙이 두 곳에 갈라지면 화면과 Telegram이 다른 말을 한다.**

계산(`build_report`)과 출력(`render_html`)을 분리했다. `--json` 옵션이 그 증거다.

Vercel Root Directory는 `docs`. GitHub App 권한에 저장소를 추가해야 목록에 나온다.

---

## 9. 테스트

```bash
pytest -q      # 28 passed
```

`tests/test_bizinfo_digest.py`가 순수 함수만 검증한다. API를 호출하지 않는다.

| 대상 | 개수 |
| --- | --- |
| `parse_period` (날짜 3형식 + 비표준 11종 + 잘못된 값) | 15 |
| `days_left` | 4 |
| `strip_html` | 2 |
| `matches` | 4 |
| `new_ids` | 3 |

### 깨뜨려 확인함

```bash
sed -i 's/if len(found) >= 2:/if len(found) >= 3:/' scripts/bizinfo_digest.py
pytest -q                                  # 3 failed
git checkout -- scripts/bizinfo_digest.py
pytest -q                                  # 28 passed
```

깨졌을 때 25건은 통과했다. 테스트가 서로 독립적이라는 뜻이다.

`bizinfo_report.py`에 대한 테스트는 없다.

---

## 10. 아직 하지 않은 것

### 즉시 처리 필요

**youtube cron이 9시로 겹친다.** youtube가 `0 9,21`, govbiz가 `0 9,17`이라
아침 9시에 동시 실행되어 git push가 충돌할 수 있다.

```bash
hermes cron edit 8b92e4108dcf --schedule "0 8,20 * * *"
```

**이 명령은 아직 실행하지 않았다.**

### 알려진 문제

**"오늘 마감"이 목록 상단을 차지한다.** 저녁 17시 보고에서 오늘 마감은 이미 늦었는데
자리를 차지하고, D-2~D-7의 여유 있는 공고가 밀린다.
오늘 마감은 별도로 짧게 표시하고 목록은 D-1부터 시작하는 편이 낫다.

### 확장 후보

- K-Startup API 추가 — 이때 **공고ID 체계가 달라 중복 판정이 필요해진다.**
  기업마당 안에서는 `pblancId`로 깔끔하게 되지만 소스가 늘면 제목 정규화가 필요하다
- 중소벤처24 API (중기부 유관기관 공고 통합)
- IRIS·NIPA — 공개 API가 없어 스크래핑. HTML 구조가 바뀌면 조용히 깨진다. 후순위
- 날짜별 이력·변동 추이 (데이터가 며칠 쌓여야 의미가 생긴다)
- `bizinfo_report.py` 테스트
- `.hermes/skills/` 스킬 작성

---

## 11. 다음 대화에 붙여넣을 재시작 프롬프트

```
나는 Windows 노트북에서 WSL2 Ubuntu 24.04를 사용한다.
프로젝트 경로는 /home/geoheim/projects/gov-biz-digest 이다.

완료 상태:
1. 기업마당 지원사업정보 API 인증키를 .env의 BIZINFO_API_KEY에 저장했다.
   URL은 https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do
   searchCnt=0으로 전체 1,550건을 한 번에 받는다. 값은 출력하지 않는다.
2. scripts/bizinfo_collect_once.py — 원본 JSON·SHA-256·manifest 저장.
   저장 경로 data/raw/bizinfo/<타임스탬프>/ (topic 구분 없음)
3. scripts/bizinfo_digest.py — 제목 키워드로 89건 필터, D-day 계산,
   직전 수집분과 pblancId 비교해 신규 판정. [신규]와 [마감임박] 두 섹션.
4. scripts/bizinfo_report.py — digest의 순수 함수를 재사용해 docs/index.html 생성.
   --json 옵션 있음.
5. 키워드는 AI 인공지능 ICT SW 소프트웨어 데이터 클라우드 디지털전환 DX 정보보호.
   본문은 검사하지 않는다. IT 플랫폼 스마트는 오염이 심해 제거했다.
6. 신청기간은 자유 입력이라 59%가 날짜가 아니다(33종 표기).
   파싱 실패하면 원문을 그대로 표시한다.
7. pytest 28 passed. tests/test_bizinfo_digest.py
8. Telegram 봇 @hasungkoo_govbiz_bot. gateway --deliver를 쓰지 않고
   스크립트가 Bot API를 직접 호출한다. .env에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
9. ~/.hermes/scripts/govbiz_daily.sh 를 cron이 09:00, 17:00에 실행한다.
   작업 ID 899ed48645bb, --no-agent, Deliver: local.
   수집 → 보고 → Telegram → HTML → git push 5단계.
   저장소 사본은 ops/govbiz_daily.sh
10. 공개 주소 https://gov-biz-digest.vercel.app (Root Directory: docs)
11. 브랜치 main, 커밋 af09fec 이후. AGENTS.md와 SOUL.md가 저장소 안에 있다.

주의사항:
- 프로젝트를 옮길 때 deactivate 후 그 프로젝트의 .venv를 활성화한다.
- 100줄 넘는 파일은 터미널 붙여넣기로 만들지 않는다. 파일로 받아 cp 한다.
  몇 줄 수정은 nano로 한다 (Ctrl+W 찾기, Ctrl+K 줄 삭제, Ctrl+O 저장).
- .env를 고친 뒤에는 source .env 를 다시 한다.
- API 키·토큰·서비스키는 출력하거나 요구하지 마.
- API 명세와 실제 응답이 다르다. 필드를 추가할 때는 실제 응답을 다시 받아 확인한다.

먼저 실행할 명령:
cd ~/projects/gov-biz-digest
source .venv/bin/activate
git log --oneline -5
git status --short
pytest -q
hermes cron list

다음 작업 후보:
- youtube cron을 0 8,20으로 옮겨 9시 충돌 해소 (아직 안 함)
- "오늘 마감"이 목록 상단을 차지하는 문제 수정
- K-Startup API 추가 (공고ID 체계가 달라 중복 판정 필요)

명령을 한꺼번에 많이 주지 말고, 한 단계씩 결과를 확인하며 코치해 줘.
```

---

## 12. 세 프로젝트 비교

| 항목 | youtube-digest | horse-agent | gov-biz-digest |
| --- | --- | --- | --- |
| 상태 | 운영 중 | 모의 데이터 | **운영 중** |
| AGENTS.md | 프로젝트 안 | 프로젝트 안 | 프로젝트 안 |
| SOUL.md | 공용 | 없음 | **전용** |
| Telegram | gateway 배달 | — | **직접 호출** |
| cron | `8b92e4108dcf` | 없음 | `899ed48645bb` |
| 성격 | 요약 | 근거·기권 | **전달·판정 안 함** |
| 정렬 기준 | 조회수 | — | 마감일 |

**SOUL.md를 프로젝트별로 나누는 첫 사례다.** 경마는 근거와 기권 판단이,
유튜브는 요약이, 여기는 "판정하지 않고 전달"이 중심이라 성격이 다르다.

---

## 13. 이 프로젝트가 포트폴리오로 갖는 의미

`SESSION_2026-09-07` 9장의 연장이다.

**같은 뼈대를 다른 도메인에 옮길 수 있다는 증명**이 됐다. 유튜브에서 사흘 걸린 것을
하루에 했고, 재사용한 것과 새로 만든 것이 명확하다.

새로 배운 것은 두 가지뿐이었다 — 자유 입력 날짜 파싱, 마감일 기반 로직.
나머지는 이식이다.

**실패 기록도 늘었다.**

- API 명세의 "필수" 필드가 실제 응답에 없었다
- 신청기간 59%가 날짜가 아니었다 (33종 자유 입력)
- 키워드 `IT`가 볼로냐·이태리·ITF를 끌고 왔다
- Vercel GitHub App 권한에 새 저장소를 추가해야 했다

교육 커리큘럼으로 그대로 쓸 수 있다.

```
API 명세 검증 → 실데이터 탐색 → 필터 설계 → 테스트 → 자동화 → 배포
```

"명세를 믿지 말고 실제 응답을 보라"는 것이 이 프로젝트의 교훈이고,
AI가 코드를 대신 써주는 시대에 사람이 해야 할 판단이 정확히 그 자리다.

---

*— 요약 끝 —*

*2026-09-07 · 확인 방법: `git log --oneline -5`, `pytest -q`, `hermes cron list`*
