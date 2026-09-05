# 03. 파이프라인

## 흐름

1. **수집** — `scripts/collect.py`가 정해진 출처에서 항목을 가져와 `data/items.json`에 저장한다.
2. **묶기** — 같은 사건을 다룬 글을 이슈 하나로 합친다. Phase 2에서 작성한다.
3. **판정** — 이슈마다 제목, 부제, 축, 임팩트를 생성한다. Phase 2에서 작성한다.
4. **순위** — 점수를 계산해 `data/issues.json`을 만든다. Phase 2에서 작성한다.

이 페이지는 1단계 수집을 기록한다. 2단계부터는 [04-prompt-engineering.md](04-prompt-engineering.md)와 [05-ranking.md](05-ranking.md)에 기록한다.

## 수집 출처

정해진 출처만 가져온다. 다른 사이트를 크롤링하지 않는다.

| 출처 | 방식 | 주소 | 축 힌트 |
|---|---|---|---|
| OpenAI | RSS | `https://openai.com/news/rss.xml` | llm |
| Google DeepMind | Atom | `https://deepmind.google/blog/feed/basic/` | llm |
| Hugging Face Blog | Atom | `https://huggingface.co/blog/feed.xml` | llm |
| NVIDIA Newsroom | RSS | `https://nvidianews.nvidia.com/releases.xml` | hardware |
| Anthropic | sitemap 폴링 | `https://www.anthropic.com/sitemap.xml` | llm |
| Google News | 쿼리별 RSS | `https://news.google.com/rss/search?q=<쿼리>&hl=en-US&gl=US&ceid=US:en` | 쿼리마다 지정 |
| Hacker News | Firebase API | `https://hacker-news.firebaseio.com/v0/topstories.json` | llm |
| Hugging Face Hub | REST API | `https://huggingface.co/api/models?sort=createdAt&direction=-1&limit=100` | llm |
| SEC EDGAR | 전문 검색 API | `https://efts.sec.gov/LATEST/search-index` | capital |

축 힌트는 수집 시점에 붙이는 임시값이다. 최종 축은 Phase 2의 판정 단계에서 결정한다.

### 출처별 규칙

**NVIDIA Newsroom.** `https://nvidianews.nvidia.com/rss`는 XML이 아니라 HTML을 반환한다. 실제 피드 주소는 `releases.xml`이다.

**Anthropic.** 공식 RSS를 제공하지 않으므로 sitemap을 폴링한다. 경로가 `/news/...`, `/research/...`, `/engineering/...` 인 URL만 대상으로 한다. 이전 실행에서 본 URL 목록을 `data/fetch_state.json`의 `anthropic:seen`에 저장하고, 목록에 없는 URL을 새 글로 판정한다. 첫 실행에서는 전체가 새 URL이 되므로 sitemap의 `lastmod`가 보관 기간 안에 있는 항목만 남긴다. sitemap에는 제목이 없으므로 새 URL마다 페이지를 한 번 받아 `<title>`을 읽는다. 한 번 실행에 최대 10개까지만 받는다.

**Google News.** 쿼리는 `Anthropic`, `OpenAI`, `Gemini AI`, `HBM memory`, `AI chip`, `AI IPO funding` 6개이다. 피드 한 개당 최대 100건을 반환한다. 매체명은 피드 항목의 `<source>` 태그에서 읽어 `Google News / <매체명>` 형태로 저장한다.

**Hacker News.** 프론트페이지 상위 100건만 가져온다. 신규글 전체는 건수가 많고 관련 없는 글이 대부분이므로 대상에 넣지 않는다. 제목이 AI 관련 키워드 정규식과 맞는 글만 남긴다. 본문 링크가 없는 글은 Hacker News 토론 페이지 주소를 사용한다.

**Hugging Face Hub.** 생성 시각 역순으로 100건을 받고 좋아요가 1개 이상인 모델만 남긴다. 좋아요가 없는 신규 모델은 대부분 개인 파인튜닝이다.

**SEC EDGAR.** 전문 검색 API는 기본값이 관련도순이라 오래된 제출이 앞에 온다. `dateRange=custom`과 `startdt`, `enddt`로 최근 3일로 좁힌다. SEC 정책에 따라 `User-Agent` 헤더에 이름과 이메일을 넣어야 한다. `ai-issues wanrkim@gmail.com`을 보낸다. 이 값은 SEC 요청에만 사용한다. 검색어는 `"artificial intelligence"`이고 서식은 S-1과 8-K이다.

## 조건부 요청

출처마다 응답의 `ETag`와 `Last-Modified`를 `data/fetch_state.json`에 저장하고, 다음 요청에 `If-None-Match`와 `If-Modified-Since`를 붙인다. 서버가 304를 반환하면 본문을 받지 않고 그 출처를 건너뛴다.

Google DeepMind, Hugging Face Blog, Anthropic sitemap은 이 헤더를 제공한다. OpenAI, NVIDIA, Google News는 제공하지 않으므로 매번 전체를 받는다.

## 정규화 규칙

**URL.** 스킴을 `https`로 맞추고, 호스트를 소문자로 바꾸고, 앞의 `www.`를 제거한다. 프래그먼트를 버린다. 쿼리에서 `utm_`, `fbclid`, `gclid`, `mc_`, `igshid`, `ref_src`, `_hs`로 시작하는 추적 파라미터를 제거한다. 경로 끝의 슬래시를 제거한다.

Google News 링크는 원문 주소가 아니라 리다이렉트 주소이다. Phase 1에서는 리다이렉트를 따라가지 않는다. 쿼리 6개에 각 100건이라 한 번 실행에 최대 600회의 추가 요청이 생기기 때문이다. 대신 제목 기준으로 중복을 제거한다. 리다이렉트 해석은 Phase 2에서 상위 이슈에 포함된 항목만 처리한다.

**제목.** HTML 엔티티를 문자로 되돌린다. Anthropic 페이지 제목 끝의 `\ Anthropic` 표기를 제거한다. SEC 제출자 이름 끝의 `(CIK 0001234567)` 표기를 제거한다.

**시각.** 모든 시각을 KST(+09:00) ISO 8601 문자열로 저장한다. SEC는 제출일만 제공하므로 그날 00:00 KST로 저장한다.

## 중복 제거

정규화한 URL의 SHA-1 앞 16자를 항목 `id`로 쓴다. `id`가 이미 있으면 버린다.

제목 중복도 함께 본다. 제목에서 끝에 붙은 매체명(` - 매체명`, ` | 매체명`)을 잘라내고, 문장부호를 공백으로 바꾸고, 소문자로 바꾸고, 연속 공백을 하나로 줄인 문자열을 비교 키로 쓴다. 같은 키가 이미 있으면 버린다. 먼저 저장한 항목을 남긴다.

## 보관 기간

`published_at`이 48시간을 넘긴 항목은 저장하지 않고, 이미 저장한 항목도 버린다. 피드가 과거 글까지 함께 반환하므로 병합하기 전에 먼저 거른다. `published_at`이 없으면 `fetched_at`을 기준으로 판정한다.

## 항목 필드

`data/items.json`은 다음 구조로 저장한다.

```json
{
  "updated_at": "2026-09-05T18:27:00+09:00",
  "count": 356,
  "items": [
    {
      "id": "3f2a1c9d0b7e5a41",
      "source": "Google News / Reuters",
      "axis_hint": "capital",
      "url": "https://news.google.com/rss/articles/...",
      "title": "기사 제목",
      "published_at": "2026-09-05T17:43:09+09:00",
      "fetched_at": "2026-09-05T18:27:00+09:00",
      "snippet": "요약 일부"
    }
  ]
}
```

| 필드 | 설명 |
|---|---|
| `id` | 정규화한 URL의 SHA-1 앞 16자 |
| `source` | 출처 이름. Google News는 `Google News / <매체명>` 형태 |
| `axis_hint` | 수집 시점에 붙인 임시 축. 판정 단계에서 덮어쓴다 |
| `url` | 정규화한 주소 |
| `title` | 정규화한 제목 |
| `published_at` | 발행 시각. KST ISO 8601 |
| `fetched_at` | 수집 시각. KST ISO 8601 |
| `snippet` | 요약 일부. HTML 태그를 제거하고 500자로 자른다 |

## 상태 파일

`data/fetch_state.json`은 다음을 저장한다.

- `feed:<주소>`, `gnews:<쿼리>`, `anthropic:sitemap`, `hn:top` — 각 출처의 `etag`와 `last_modified`
- `anthropic:seen` — Anthropic sitemap에서 이미 본 URL 목록

## 실패 처리

출처 하나가 실패해도 나머지 출처는 계속 진행한다. 실패한 출처의 이름과 예외 메시지를 실행 마지막에 출력한다. 모든 출처가 실패하면 종료 코드 1을 반환한다.

## 실행

```
pip install -r requirements.txt
python scripts/collect.py
```
