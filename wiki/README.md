# ai-issues 위키

## 한 줄 정의

AI 소식(모델·서비스 출시, 영상·이미지 모델, 하드웨어, 기업·자본)을 수집해서 "지금 많이 언급되는 이슈"를 순위로 보여주는 웹사이트이다.

## SSOT 원칙

1. 이 위키는 현재 기준 사실만 담는다. 옛 결정, 폐기한 구조, 진행 중인 상태는 본문에 두지 않는다.
2. 코드 변경과 위키 변경은 같은 커밋에 함께 넣는다.
3. 은유와 비유 어휘를 쓰지 않는다. 주어·목적어·동사를 살린 완성 문장으로 쓴다.
4. 해결한 이슈와 폐기한 결정은 `archive/` 아래로 옮긴다.

## 언어 원칙

화면 문구와 이슈 요약은 한국어로 작성한다. 수집한 출처 원문은 영어가 대부분이다. 위키 본문도 한국어로 작성한다.

## 페이지 인덱스

| 페이지 | 내용 | 상태 |
|---|---|---|
| [00-direction.md](00-direction.md) | 가치 우선순위, 제품 결정, 대상 사용자 | 작성함 |
| [01-architecture.md](01-architecture.md) | 구성 요소, 외부 의존, 실행 주기, 비밀값, 배포, 무료 한도 | 작성함 |
| [02-data-model.md](02-data-model.md) | JSON 스키마 확정본, 필드 정의 | 작성함 |
| [03-pipeline.md](03-pipeline.md) | 수집 출처 목록, 정규화 규칙 | 작성함 |
| [04-prompt-engineering.md](04-prompt-engineering.md) | 묶기·판정 프롬프트 전문, 임팩트 기준표 | 작성함 |
| [05-ranking.md](05-ranking.md) | 순위 식, 가중치, 배지 기준, 이슈 수명 | 작성함 |
| [06-frontend.md](06-frontend.md) | 화면 구조, 상태 관리, 로컬 저장 키 | 작성함 |
| [07-design-guidelines.md](07-design-guidelines.md) | 색·폰트·라운드·간격 토큰, 안티패턴 | 작성함 |
| [08-issues.md](08-issues.md) | 아직 해결하지 않은 이슈 | 작성함 |
| [09-backlog.md](09-backlog.md) | 아직 시작하지 않은 작업 | 작성함 |
| [10-worklog.md](10-worklog.md) | 완료한 작업 누적, 최신이 위 | 작성함 |

해결한 이슈는 `archive/issues/`에 보관한다. `archive/decisions/`와 `archive/worklog/`는 보관이 필요해질 때 만든다.
