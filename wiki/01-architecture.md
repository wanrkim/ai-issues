# 01. 아키텍처

## 구성 요소

| 구성 | 선택 | 이유 |
|---|---|---|
| 수집·묶기·판정 | Python 스크립트 | 고장 지점을 줄인다 |
| 실행 | GitHub Actions 예약 실행(cron), 15분 주기 | 공개 저장소는 실행 시간 제한이 없다 |
| 저장 | 저장소 안 JSON 파일 | 데이터베이스를 두지 않는다 |
| 화면 | GitHub Pages 정적 사이트 | 서버를 두지 않는다 |
| LLM | `gemini-3.8-flash`, Gemini API 무료 티어 | 무료이다. 3.6 및 3.7과 가격이 같아서 최신 버전을 선택했다 |
| 비밀값 | GitHub Actions Secrets (`GEMINI_API_KEY`) | 코드는 공개하므로 키를 저장소에 넣지 않는다 |

## 폴더 구조

```
/scripts/            수집·묶기·판정·순위 Python
/data/               items.json, issues.json (실행 결과)
/web/                index.html (GitHub Pages 진입점)
/.github/workflows/  15분 주기 cron
/wiki/               위키 SSOT
CLAUDE.md            Claude Code 작업 지침
```

## 실행 주기

GitHub Actions cron이 15분마다 수집·묶기·판정·순위를 실행하고 `data/issues.json`을 갱신한 뒤 커밋한다. 화면은 이 파일만 읽는다.

## 배포 방법

GitHub Pages를 `main` 브랜치의 루트(`/`) 폴더에서 배포한다. 브랜치 기반 Pages는 배포 폴더로 `/`와 `/docs`만 지원하므로 `/web`을 직접 지정할 수 없다. 루트를 배포 폴더로 지정하면 `web/index.html`과 `data/issues.json`이 모두 서비스되고, 화면이 `../data/issues.json` 경로로 데이터를 읽을 수 있다.

- 진입 URL: `https://<GitHub 사용자명>.github.io/ai-issues/web/`
- 저장소는 공개로 둔다. Actions 실행 시간 제한이 없고 Pages를 쓸 수 있다.
- Jekyll 처리를 막기 위해 저장소 루트에 `.nojekyll` 파일을 둔다.

## 무료 한도

| 항목 | 한도 | 확인 상태 |
|---|---|---|
| Gemini API 무료 티어 일일 요청 수 | 미확인 | Phase 2에서 rate limits 문서를 확인하고 이 표에 기록한다. 15분 주기는 하루 96회 실행이므로 실행당 LLM 호출 횟수를 곱한 값이 한도 안에 들어가야 한다 |
| GitHub Actions | 공개 저장소는 실행 시간 제한이 없다 | 확인함 |
| GitHub Pages | 저장소 1GB, 월 대역폭 100GB | 확인함 |

## 알고 진행하는 제약

- GitHub Actions 예약 실행은 혼잡한 시간대에 5분에서 20분까지 지연되거나 건너뛸 수 있다. POC에서는 최신성을 검증 대상으로 삼지 않는다.
- Gemini 무료 티어는 입력한 내용을 구글 제품 개선에 사용한다. 공개된 뉴스만 입력하므로 문제가 없다.
