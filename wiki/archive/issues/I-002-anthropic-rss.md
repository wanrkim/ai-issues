# I-002. Anthropic은 공식 RSS를 제공하지 않는다 (해결)

해결일: 2026-09-05 (Phase 1)

## 내용

Anthropic 소식은 서비스의 주요 축인 LLM/서비스에 해당하는데 공식 피드가 없었다. sitemap 폴링으로 감지하고, 동작하지 않으면 RSSHub 라우트를 검토하기로 했다.

## 결과

sitemap 폴링이 동작한다. `https://www.anthropic.com/sitemap.xml`에서 경로가 `/news/`, `/research/`, `/engineering/`인 URL을 걸러내고, 이전 실행에서 본 URL 목록과 비교해 새 글을 감지한다. 2026-09-05 실행에서 최근 48시간 기사 4건을 감지했다.

sitemap에는 제목이 없으므로 새 URL마다 페이지를 한 번 받아 `<title>`을 읽는다. 페이지 제목 끝에 `\ Anthropic`이 붙어 있어서 제거한다.

RSSHub 라우트는 검토하지 않았다.

## 반영 위치

[../../03-pipeline.md](../../03-pipeline.md) 출처별 규칙의 Anthropic 항목.
