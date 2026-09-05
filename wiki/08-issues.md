# 08. 이슈

아직 해결하지 않은 이슈만 적는다. 해결한 이슈는 `archive/issues/`로 옮긴다.

## I-001. Gemini 무료 티어 일일 요청 한도를 확인하지 않았다

15분 주기로 실행하면 하루 96회를 실행한다. 실행 한 번에 묶기 1회와 판정 N회를 호출하므로 실제 호출 수는 96회보다 많다. 무료 티어 한도 안에 들어가는지 확인하지 않았다.

- 확인 방법: Gemini API rate limits 문서에서 `gemini-3.8-flash`의 무료 티어 RPD를 확인한다.
- 반영 위치: [01-architecture.md](01-architecture.md) 무료 한도 표.
- 처리 시점: Phase 2.

## I-002. Anthropic은 공식 RSS를 제공하지 않는다

Anthropic 소식은 서비스의 주요 축인 LLM/서비스에 해당하는데 공식 피드가 없다.

- 1차 방법: `anthropic.com` sitemap을 폴링해서 새로 생긴 URL을 감지한다.
- 1차 방법이 동작하지 않을 때: RSSHub 라우트를 검토한다.
- 처리 시점: Phase 1. 결과를 [03-pipeline.md](03-pipeline.md)에 기록한다.

## I-003. 종합 순위가 한 축으로 채워질 수 있다

LLM/서비스 축의 소식 건수가 다른 축보다 많아서 상위 순위를 한 축이 차지할 수 있다.

- 축별 가중치는 미리 넣지 않는다. Phase 2에서 실제 순위 결과를 보고 결정한다.
- 처리 시점: Phase 2.
