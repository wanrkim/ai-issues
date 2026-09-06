# 02. 데이터 모델

파일은 세 개이다. 수집 결과는 `data/items.json`, 조건부 요청 상태는 `data/fetch_state.json`, 화면이 읽는 최종 결과는 `data/issues.json`이다. 앞의 두 개는 [03-pipeline.md](03-pipeline.md)에 기록한다. 이 페이지는 `data/issues.json`을 기록한다.

## data/issues.json

```json
{
  "generated_at": "2026-09-05T19:22:17+09:00",
  "model": "gemini-3.6-flash",
  "next_id": 26,
  "issues": [
    {
      "id": "iss_000001",
      "rank": 1,
      "prev_rank": 3,
      "badge": "surge",
      "axis": "llm",
      "title": "오픈AI GPT-6 아스트라 출시",
      "subtitle": "유료 사용자 대상 배포 및 성능·보안 논란",
      "summary": "오픈AI가 GPT-6 아스트라를 유료 사용자에게 배포했다. ...",
      "impact": 5,
      "score": 42.29,
      "source_count": 40,
      "first_seen": "2026-09-04T18:10:00+09:00",
      "last_seen": "2026-09-05T17:55:00+09:00",
      "item_ids": ["3f2a1c9d0b7e5a41"],
      "sources": [
        {
          "name": "Google News / Reuters",
          "url": "https://news.google.com/rss/articles/...",
          "published_at": "2026-09-05T17:55:00+09:00"
        }
      ]
    }
  ]
}
```

## 최상위 필드

| 필드 | 형 | 설명 |
|---|---|---|
| `generated_at` | 문자열 | 이 파일을 만든 시각. KST ISO 8601 |
| `model` | 문자열 또는 null | 이번 실행에서 실제로 응답한 모델 이름. LLM을 부르지 않았으면 null |
| `next_id` | 정수 | 다음에 만들 이슈에 붙일 번호. 실행 사이에 이어진다 |
| `issues` | 배열 | 점수 내림차순으로 정렬한 이슈 목록 |

## 이슈 필드

| 필드 | 형 | 설명 |
|---|---|---|
| `id` | 문자열 | `iss_` + 여섯 자리 번호. 한 번 붙으면 바뀌지 않는다 |
| `rank` | 정수 | 이번 실행의 순위. 1부터 시작한다 |
| `prev_rank` | 정수 또는 null | 직전 실행의 순위. 직전에 없던 이슈는 null |
| `badge` | 문자열 또는 null | `new`, `surge`, null 중 하나. 기준은 [05-ranking.md](05-ranking.md) |
| `axis` | 문자열 | `llm`, `media`, `hardware`, `capital` 중 하나 |
| `title` | 문자열 | 한국어 한 줄. 12자 안팎 |
| `subtitle` | 문자열 | 한국어 한 줄 |
| `summary` | 문자열 | 한국어 세 문장에서 네 문장. 200자 안팎. 항목을 펼쳤을 때 보여준다. 이 필드를 넣기 전에 만들어진 이슈는 빈 문자열이다 |
| `impact` | 정수 | 1에서 5 사이 |
| `score` | 실수 | 순위 점수. 소수점 셋째 자리에서 반올림한다 |
| `source_count` | 정수 | 이 이슈에 묶인 글의 수 |
| `first_seen` | 문자열 | 묶인 글 중 가장 이른 발행 시각 |
| `last_seen` | 문자열 | 묶인 글 중 가장 늦은 발행 시각. 수명 판정 기준이다 |
| `item_ids` | 배열 | 묶인 글의 `id` 목록. 실행 사이에 어떤 글이 배정되었는지 이어가는 데 쓴다 |
| `sources` | 배열 | 화면에 보여줄 출처 목록. 발행 시각 내림차순 |

## 출처 필드

| 필드 | 형 | 설명 |
|---|---|---|
| `name` | 문자열 | 출처 이름. Google News는 `Google News / <매체명>` 형태 |
| `url` | 문자열 | 정규화한 주소 |
| `published_at` | 문자열 또는 null | 발행 시각 |

## 규칙

- 모든 시각은 KST(+09:00) ISO 8601 문자열이다.
- `item_ids`에 있는 글이 `data/items.json`에서 만료되어 사라지면 그 글은 `sources`에서도 빠지고 `source_count`가 줄어든다. 남은 글이 없으면 이슈 자체를 목록에서 제외한다.
- 화면은 이 파일만 읽는다. 다른 파일을 읽지 않는다.
