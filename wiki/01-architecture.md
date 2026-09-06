# 01. 아키텍처

## 구성 요소

| 구성 | 선택 | 이유 |
|---|---|---|
| 수집 | `scripts/collect.py` | 정해진 출처에서 항목을 가져온다 |
| 묶기·판정·순위 | `scripts/rank.py` | 한 번의 LLM 호출로 묶기와 판정을 함께 처리한다 |
| 실행 | GitHub Actions 예약 실행(cron), 2시간 주기 | 공개 저장소는 실행 시간 제한이 없다 |
| 저장 | 저장소 안 JSON 파일 | 데이터베이스를 두지 않는다 |
| 화면 | GitHub Pages 정적 사이트 | 서버를 두지 않는다 |
| LLM | `gemini-3.8-flash`, Gemini API 무료 등급 | 무료이다. 503이면 3.7, 3.6 순으로 넘어간다 |
| 비밀값 | GitHub Actions Secrets (`GEMINI_API_KEY`) | 코드는 공개하므로 키를 저장소에 넣지 않는다 |

## 폴더 구조

```
/scripts/            collect.py, rank.py
/data/               items.json, fetch_state.json, issues.json
/web/                index.html (GitHub Pages 진입점)
/.github/workflows/  update.yml (2시간 주기)
/wiki/               위키 SSOT
CLAUDE.md            Claude Code 작업 지침
requirements.txt     requests, feedparser
.env                 GEMINI_API_KEY (커밋하지 않는다)
```

## 실행 주기

GitHub Actions cron이 2시간마다 수집과 순위 계산을 실행하고 `data/`를 갱신한 뒤 커밋한다. Pages가 그 커밋을 배포한다. 화면은 `data/issues.json`만 읽는다.

주기를 2시간으로 정한 근거는 아래 무료 한도이다. 하루 12회 실행이고, 실행 한 번에 LLM을 1회 부른다. 모델을 바꿔 재시도하는 경우를 더해도 한도 안에 들어간다.

착수 시점에는 15분 주기로 계획했다. 무료 등급의 일일 요청 한도가 모델당 20회라는 것을 확인하고 바꿨다. 15분 주기는 하루 96회 실행이라 한도의 약 5배이다.

## 배포 방법

GitHub Pages를 `main` 브랜치의 루트(`/`) 폴더에서 배포한다. 브랜치 기반 Pages는 배포 폴더로 `/`와 `/docs`만 지원하므로 `/web`을 직접 지정할 수 없다. 루트를 지정하면 `web/index.html`과 `data/issues.json`이 모두 서비스되고, 화면이 `../data/issues.json` 경로로 데이터를 읽을 수 있다.

- 진입 URL: `https://wanrkim.github.io/ai-issues/web/`
- 저장소는 공개로 둔다. Actions 실행 시간 제한이 없고 Pages를 쓸 수 있다.
- Jekyll 처리를 막기 위해 저장소 루트에 `.nojekyll` 파일을 둔다.

## 무료 한도

Gemini API 무료 등급의 한도는 문서에 공개되어 있지 않다. AI Studio의 rate limit 화면에서 로그인한 상태로만 확인할 수 있다. 2026-09-05에 확인한 값이다.

| 모델 | RPM | TPM | RPD |
|---|---|---|---|
| Gemini 3.8 Flash | 5 | 250,000 | 20 |
| Gemini 3.7 Flash | 5 | 250,000 | 20 |
| Gemini 3.6 Flash | 5 | 250,000 | 20 |

제약이 되는 것은 RPD 하나이다. TPM 250,000은 한 번 호출에 쓰는 양(입력 약 17,000 토큰)보다 훨씬 크다.

| 항목 | 한도 | 확인 상태 |
|---|---|---|
| GitHub Actions | 공개 저장소는 실행 시간 제한이 없다 | 확인함 |
| GitHub Pages | 저장소 1GB, 월 대역폭 100GB | 확인함 |

## 결제 상태

AI Studio에 선불 크레딧이 있지만 결제 계정이 비활성 상태여서 Gemini API에 연결되지 않는다. 등급은 무료이다. 결제 계정을 복구하면 RPD 제한이 풀리고 주기를 줄일 수 있다. [09-backlog.md](09-backlog.md)에 기록한다.

## 여러 환경에서 작업하기

저장소가 GitHub에 있으므로 어느 기기에서도 이어서 작업할 수 있다.

- **웹**: `claude.ai/code`에서 `wanrkim/ai-issues` 저장소를 연결한다. 휴대폰 브라우저에서도 동작한다.
- **맥과 윈도우**: Claude 데스크톱 앱에서 폴더를 열거나, `git clone` 후 `claude` 명령을 실행한다.

새 세션은 이전 대화를 이어받지 않는다. `CLAUDE.md`와 이 위키를 읽고 현재 상태를 파악한다. Phase마다 위키에 기록하는 이유가 이것이다.

`.env`는 커밋하지 않으므로 새 환경에서는 `GEMINI_API_KEY`를 다시 넣어야 한다. GitHub Actions는 Secrets에 등록한 값을 쓰므로 자동 실행은 기기와 무관하게 동작한다.

여러 기기에서 만지면 충돌하므로 작업을 시작할 때 `git pull`을 먼저 실행한다.

## 알고 진행하는 제약

- GitHub Actions 예약 실행은 혼잡한 시간대에 5분에서 20분까지 지연되거나 건너뛸 수 있다. POC에서는 최신성을 검증 대상으로 삼지 않는다.
- Gemini 무료 등급은 입력한 내용을 구글 제품 개선에 사용한다. 공개된 뉴스만 입력하므로 문제가 없다.
- `gemini-3.8-flash`는 503(high demand)을 자주 반환한다. 모델을 바꿔 재시도하면 판정 기준이 실행마다 달라질 수 있다.
