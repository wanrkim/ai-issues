#!/usr/bin/env python3
"""수집한 글을 이슈로 묶고 판정한 뒤 순위를 매긴다.

data/items.json을 읽어 data/issues.json을 만든다.
묶기와 판정을 한 번의 LLM 호출로 처리한다. 무료 등급의 일일 요청 한도가
모델당 20회이기 때문이다. 자세한 내용은 wiki/01-architecture.md에 기록한다.

실행:
    python scripts/rank.py                 전체 항목으로 실행한다
    python scripts/rank.py --limit 100     최근 100건만 사용한다
    python scripts/rank.py --no-llm        LLM을 호출하지 않고 순위만 다시 계산한다
"""

from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ITEMS_PATH = DATA_DIR / "items.json"
ISSUES_PATH = DATA_DIR / "issues.json"

# 앞의 모델이 503을 반환하면 다음 모델로 넘어간다.
MODELS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"]
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
API_TIMEOUT = 180
RETRY_PER_MODEL = 3
RETRY_WAIT = 12

ISSUE_TTL_HOURS = 48
SURGE_THRESHOLD = 3  # 직전 실행보다 이만큼 순위가 오르면 급상승으로 본다.
FRESHNESS_HALFLIFE_HOURS = 18
SNIPPET_CHARS = 320

AXES = {"llm", "media", "hardware", "capital"}

# 판정이 돌려준 기업 도메인을 검증한다. 이 형태가 아니면 버린다.
DOMAIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,60}\.[a-z]{2,12}$")


def clean_domain(value):
    text = (value or "").strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = re.sub(r"^www\.", "", text)
    text = text.split("/")[0]
    return text if DOMAIN_PATTERN.match(text) else None

# 이슈 섬네일. 피드가 이미지를 주면 그대로 쓰고, 없으면 원문에서 og:image 를 읽는다.
# Google News 링크는 자바스크립트로 이동하는 구조라 원문에 닿지 못하므로 건너뛴다.
OG_FETCH_LIMIT = 25   # 실행당 원문 페이지를 여는 최대 횟수
OG_PER_ISSUE = 2      # 이슈 하나에서 시도할 기사 수
OG_TIMEOUT = 15
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
_Q = "[\"']"
OG_PATTERNS = [
    "<meta[^>]+property=" + _Q + "og:image" + _Q + "[^>]+content=" + _Q + "([^\"']+)",
    "<meta[^>]+content=" + _Q + "([^\"']+)" + _Q + "[^>]+property=" + _Q + "og:image",
    "<meta[^>]+name=" + _Q + "twitter:image" + _Q + "[^>]+content=" + _Q + "([^\"']+)",
]

PROMPT = """너는 AI 소식을 다루는 큐레이터다. 아래 "새 글" 목록을 사건 단위로 묶어라.

[규칙]
1. 같은 사건을 다룬 글은 하나의 이슈로 묶는다. 사건이 다르면 다른 이슈로 나눈다.
2. "현재 이슈" 목록에 이미 있는 사건을 다룬 글이면 assignments에 그 이슈 id와 함께 넣는다.
3. 현재 이슈에 없는 사건이면 new_issues에 새 이슈를 만들고 해당 글 번호를 items에 넣는다.
4. AI와 관계없는 글은 assignments에도 new_issues에도 넣지 않고 버린다. 검색어가 우연히 일치했을 뿐인 일반 소비재 기사, 단순 주가 시황, 광고성 글이 여기에 해당한다.
5. 글 하나는 최대 한 곳에만 넣는다.
6. 모든 문구는 한국어로 쓴다.
7. "현재 이슈" 목록에서 끝에 [도메인 없음] 이라고 표시된 이슈는 domains 에 그 이슈 id 와
   company_domain 을 넣는다. 제목과 부제만 보고 판단한다.

[새 이슈의 필드]
- title: 무엇이 일어났는지 한국어 한 줄로 쓴다. 12자 안팎으로 짧게 쓴다. 예: "클로드 6.0 출시"
- subtitle: 제목이 말하지 못한 핵심을 15자 안팎으로 덧붙인다. 목록에서 제목 바로 아래 한 줄로 보인다.
  제목에 이미 나온 말을 반복하지 않는다. 조사와 서술어를 줄이고 명사 중심으로 짧게 쓴다.
  예: 제목이 "앤스로픽 IPO 10월 추진"이면 subtitle 은 "기업가치 2조 달러 목표"로 쓴다.
- summary: 무슨 일이 있었고 왜 중요한지 한국어 세 문장에서 네 문장으로 쓴다. 200자 안팎으로 쓴다.
  읽는 사람이 원문 기사를 열지 않아도 사건을 이해할 수 있어야 한다.
  주어진 글에 없는 사실을 지어내지 않는다. 숫자와 회사 이름은 글에 있는 그대로 쓴다.
  "~한다" 형태의 평서문으로 쓴다.
- company_domain: 이 소식의 중심에 있는 기업이나 기관의 대표 웹사이트 도메인을 쓴다.
  회사 이름이 아니라 도메인만 쓴다. 예: openai.com, anthropic.com, nvidia.com, google.com, micron.com
  앞에 www 나 https 를 붙이지 않는다. 경로도 붙이지 않는다.
  기업 한 곳으로 좁혀지지 않으면 빈 문자열을 쓴다.
- axis: 다음 넷 중 하나를 고른다.
    llm      언어모델과 AI 서비스, 코딩 도구의 출시와 업데이트
    media    영상 생성 모델과 이미지 생성 모델
    hardware GPU, HBM, 반도체, 디바이스
    capital  IPO, 투자 유치, 인수, 규제, 소송
- impact: 1에서 5 사이의 정수를 고른다.
    5  주요 랩의 새 메이저 모델 출시, 대형 IPO, 대형 인수
    4  주요 랩의 마이너 모델 출시, 주요 제품 출시, 대형 투자 유치
    3  기능 업데이트, 중견 기업 소식, 하드웨어 로드맵
    2  파트너십, 소규모 출시
    1  그 외

[현재 이슈]
{live_issues}

[새 글]
{new_items}
"""

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "assignments": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "n": {"type": "INTEGER"},
                    "issue_id": {"type": "STRING"},
                },
                "required": ["n", "issue_id"],
            },
        },
        "new_issues": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "items": {"type": "ARRAY", "items": {"type": "INTEGER"}},
                    "title": {"type": "STRING"},
                    "subtitle": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                    "company_domain": {"type": "STRING"},
                    "axis": {"type": "STRING"},
                    "impact": {"type": "INTEGER"},
                },
                "required": ["items", "title", "subtitle", "summary",
                             "company_domain", "axis", "impact"],
            },
        },
    },
    "required": ["assignments", "new_issues"],
}
RESPONSE_SCHEMA["properties"]["domains"] = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "issue_id": {"type": "STRING"},
            "company_domain": {"type": "STRING"},
        },
        "required": ["issue_id", "company_domain"],
    },
}
RESPONSE_SCHEMA["required"].append("domains")


# ---------------------------------------------------------------- 공통 유틸


def now_kst() -> datetime:
    return datetime.now(KST)


def iso(dt: datetime) -> str:
    return dt.astimezone(KST).isoformat(timespec="seconds")


def parse_dt(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=KST) if parsed.tzinfo is None else parsed


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def read_api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("GEMINI_API_KEY="):
                return line.strip().split("=", 1)[1]
    return None


# ------------------------------------------------------------------- LLM


def call_gemini(api_key, prompt):
    """모델 목록을 순서대로 시도한다. 성공한 응답과 사용한 모델 이름을 반환한다."""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    last_error = None
    for model in MODELS:
        url = "%s/%s:generateContent" % (API_BASE, model)
        for attempt in range(RETRY_PER_MODEL):
            started = time.time()
            try:
                response = requests.post(url, headers=headers, json=body, timeout=API_TIMEOUT)
            except requests.RequestException as exc:
                last_error = "%s: %s" % (model, exc)
                time.sleep(RETRY_WAIT)
                continue
            if response.status_code == 200:
                payload = response.json()
                usage = payload.get("usageMetadata", {})
                print(
                    "  모델 %s / %.1f초 / 입력 %s 토큰 / 출력 %s 토큰 / 사고 %s 토큰"
                    % (
                        model,
                        time.time() - started,
                        usage.get("promptTokenCount", "?"),
                        usage.get("candidatesTokenCount", "?"),
                        usage.get("thoughtsTokenCount", 0),
                    )
                )
                text = payload["candidates"][0]["content"]["parts"][0]["text"]
                return json.loads(text), model
            last_error = "%s: HTTP %s %s" % (model, response.status_code, response.text[:200])
            print("  %s 응답 %s (%d회차)" % (model, response.status_code, attempt + 1))
            if response.status_code not in (429, 500, 503):
                break
            time.sleep(RETRY_WAIT)
    raise RuntimeError("모든 모델이 실패했다. 마지막 오류: %s" % last_error)


def build_prompt(live_issues, new_items):
    if live_issues:
        live_text = "\n".join(
            "%s | %s | %s | %s%s"
            % (
                i["id"],
                i["title"],
                i["subtitle"],
                i["axis"],
                "" if i.get("company_domain") else " [도메인 없음]",
            )
            for i in live_issues
        )
    else:
        live_text = "(없음)"
    item_text = "\n".join(
        "%d | %s | %s | %s"
        % (n, item["source"], item["title"], (item.get("snippet") or "")[:SNIPPET_CHARS])
        for n, item in enumerate(new_items)
    )
    return PROMPT.format(live_issues=live_text, new_items=item_text)


# ---------------------------------------------------------------- 섬네일


def og_image(session, url):
    """원문 페이지에서 대표 이미지 주소를 읽는다. 없으면 None을 돌려준다."""
    try:
        response = session.get(url, headers={"User-Agent": BROWSER_UA}, timeout=OG_TIMEOUT)
        response.raise_for_status()
        head = response.text[:200000]
    except (requests.RequestException, ValueError):
        return None
    for pattern in OG_PATTERNS:
        match = re.search(pattern, head, re.IGNORECASE)
        if match:
            found = html.unescape(match.group(1)).strip()
            if found.startswith("http"):
                return found
    return None


def fill_images(session, issues, by_id):
    """이슈마다 섬네일 주소를 채운다. 이미 있으면 건너뛴다."""
    budget = OG_FETCH_LIMIT
    fetched = 0
    for issue in issues:
        if issue.get("image"):
            continue

        # 피드가 직접 준 이미지를 먼저 쓴다. 추가 요청이 없다.
        for item_id in issue.get("item_ids", []):
            item = by_id.get(item_id)
            if item and item.get("image"):
                issue["image"] = item["image"]
                break
        if issue.get("image"):
            continue

        tried = set(issue.get("image_tried") or [])
        attempts = 0
        for item_id in issue.get("item_ids", []):
            if budget <= 0 or attempts >= OG_PER_ISSUE:
                break
            item = by_id.get(item_id)
            if not item or "news.google.com" in item["url"] or item["url"] in tried:
                continue
            tried.add(item["url"])
            attempts += 1
            budget -= 1
            fetched += 1
            found = og_image(session, item["url"])
            if found:
                issue["image"] = found
                break
        if tried:
            issue["image_tried"] = sorted(tried)[:20]
    return fetched


# ------------------------------------------------------------------ 순위


def score_issue(issue, reference):
    """점수를 계산한다. 식은 wiki/05-ranking.md에 기록한다."""
    last_seen = parse_dt(issue.get("last_seen")) or reference
    age_hours = max(0.0, (reference - last_seen).total_seconds() / 3600.0)
    freshness = 0.5 ** (age_hours / FRESHNESS_HALFLIFE_HOURS)
    source_count = max(1, issue.get("source_count", 1))
    velocity = issue.get("new_sources", 0) / source_count
    raw = issue["impact"] * math.log2(1 + source_count) * freshness * (1 + velocity)
    return round(raw, 3)


def rank_issues(issues, previous_ranks):
    reference = now_kst()
    for issue in issues:
        issue["score"] = score_issue(issue, reference)
    issues.sort(key=lambda i: (-i["score"], i["id"]))

    for position, issue in enumerate(issues, start=1):
        prev = previous_ranks.get(issue["id"])
        issue["rank"] = position
        issue["prev_rank"] = prev
        if prev is None:
            issue["badge"] = "new"
        elif prev - position >= SURGE_THRESHOLD:
            issue["badge"] = "surge"
        else:
            issue["badge"] = None
    return issues


# ------------------------------------------------------------------ 실행


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="사용할 최근 글 수. 0이면 전체")
    parser.add_argument("--no-llm", action="store_true", help="LLM 없이 순위만 다시 계산한다")
    parser.add_argument("--top", type=int, default=20, help="출력할 상위 이슈 수")
    args = parser.parse_args()

    items = load_json(ITEMS_PATH, {}).get("items", [])
    if not items:
        print("data/items.json이 비어 있다. 먼저 scripts/collect.py를 실행한다.")
        return 1

    previous = load_json(ISSUES_PATH, {})
    session = requests.Session()
    issues = previous.get("issues", [])
    next_id = previous.get("next_id", 1)
    previous_ranks = {i["id"]: i.get("rank") for i in issues}

    # 수명이 지난 이슈를 먼저 버린다.
    cutoff = now_kst() - timedelta(hours=ISSUE_TTL_HOURS)
    expired = [i for i in issues if (parse_dt(i.get("last_seen")) or cutoff) < cutoff]
    issues = [i for i in issues if i not in expired]

    by_id = {item["id"]: item for item in items}
    assigned = set()
    for issue in issues:
        issue["new_sources"] = 0
        for item_id in issue.get("item_ids", []):
            assigned.add(item_id)

    unassigned = [i for i in items if i["id"] not in assigned]
    if args.limit:
        unassigned = unassigned[: args.limit]

    print("보관 글 %d건 / 살아있는 이슈 %d개 / 만료 이슈 %d개" % (len(items), len(issues), len(expired)))
    print("이번에 판정할 새 글 %d건" % len(unassigned))

    used_model = None
    if unassigned and not args.no_llm:
        api_key = read_api_key()
        if not api_key:
            print("GEMINI_API_KEY를 찾지 못했다. 환경변수나 .env에 넣는다.")
            return 1
        prompt = build_prompt(issues, unassigned)
        print("프롬프트 %d자" % len(prompt))
        try:
            result, used_model = call_gemini(api_key, prompt)
        except RuntimeError as exc:
            # 모델이 모두 응답하지 않아도 파이프라인을 멈추지 않는다.
            # 묶기와 판정만 건너뛰고 남은 이슈로 순위를 다시 계산한다.
            print("LLM 호출 실패, 묶기와 판정을 건너뛴다: %s" % exc)
            result = None

        issue_index = {i["id"]: i for i in issues} if result else {}
        merged = 0
        for entry in (result or {}).get("assignments", []):
            issue = issue_index.get(entry.get("issue_id"))
            n = entry.get("n")
            if issue is None or not isinstance(n, int) or not 0 <= n < len(unassigned):
                continue
            item = unassigned[n]
            if item["id"] in issue["item_ids"]:
                continue
            issue["item_ids"].append(item["id"])
            issue["new_sources"] += 1
            merged += 1

        filled = 0
        for entry in (result or {}).get("domains", []):
            issue = issue_index.get(entry.get("issue_id"))
            if issue is None or issue.get("company_domain"):
                continue
            domain = clean_domain(entry.get("company_domain"))
            if domain:
                issue["company_domain"] = domain
                filled += 1

        created = 0
        for group in (result or {}).get("new_issues", []):
            picked = [
                unassigned[n]
                for n in group.get("items", [])
                if isinstance(n, int) and 0 <= n < len(unassigned)
            ]
            if not picked:
                continue
            axis = group.get("axis")
            impact = group.get("impact")
            if axis not in AXES or not isinstance(impact, int):
                continue
            stamps = [parse_dt(p.get("published_at")) or now_kst() for p in picked]
            issues.append(
                {
                    "id": "iss_%06d" % next_id,
                    "axis": axis,
                    "title": (group.get("title") or "").strip(),
                    "subtitle": (group.get("subtitle") or "").strip(),
                    "summary": (group.get("summary") or "").strip(),
                    "company_domain": clean_domain(group.get("company_domain")),
                    "impact": max(1, min(5, impact)),
                    "item_ids": [p["id"] for p in picked],
                    "new_sources": len(picked),
                    "first_seen": iso(min(stamps)),
                }
            )
            next_id += 1
            created += 1

        dropped = len(unassigned) - merged - sum(
            len(g.get("items", [])) for g in (result or {}).get("new_issues", [])
        )
        print("기존 이슈에 합침 %d건 / 새 이슈 %d개 / 관계없어 버림 %d건" % (merged, created, dropped))
        print("기업 도메인 %d개 채움" % filled)

    # 이슈마다 출처 수와 마지막 시각을 다시 계산한다.
    for issue in issues:
        members = [by_id[i] for i in issue.get("item_ids", []) if i in by_id]
        issue["item_ids"] = [m["id"] for m in members]
        issue["source_count"] = len(members)
        stamps = [parse_dt(m.get("published_at")) or now_kst() for m in members]
        issue["last_seen"] = iso(max(stamps)) if stamps else issue.get("last_seen")
        if not issue.get("first_seen") and stamps:
            issue["first_seen"] = iso(min(stamps))
        issue["sources"] = [
            {"name": m["source"], "url": m["url"], "published_at": m.get("published_at")}
            for m in sorted(members, key=lambda m: m.get("published_at") or "", reverse=True)
        ]

    # 글이 모두 만료된 이슈는 버린다.
    issues = [i for i in issues if i["source_count"] > 0]

    fetched = fill_images(session, issues, by_id)
    with_image = sum(1 for i in issues if i.get("image"))
    print("섬네일 %d/%d개 (원문 %d건 열어봄)" % (with_image, len(issues), fetched))

    issues = rank_issues(issues, previous_ranks)

    output = {
        "generated_at": iso(now_kst()),
        "model": used_model,
        "next_id": next_id,
        "issues": [
            {
                "id": i["id"],
                "rank": i["rank"],
                "prev_rank": i["prev_rank"],
                "badge": i["badge"],
                "axis": i["axis"],
                "title": i["title"],
                "subtitle": i["subtitle"],
                "summary": i.get("summary", ""),
                "company_domain": i.get("company_domain"),
                "image": i.get("image"),
                "image_tried": i.get("image_tried", []),
                "impact": i["impact"],
                "score": i["score"],
                "source_count": i["source_count"],
                "first_seen": i.get("first_seen"),
                "last_seen": i.get("last_seen"),
                "item_ids": i["item_ids"],
                "sources": i["sources"],
            }
            for i in issues
        ],
    }
    ISSUES_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    badge_label = {"new": "새로 진입", "surge": "급상승", None: ""}
    axis_label = {"llm": "LLM/서비스", "media": "영상/이미지", "hardware": "하드웨어", "capital": "기업/자본"}
    print()
    print("이슈 %d개. 상위 %d개:" % (len(issues), min(args.top, len(issues))))
    print("-" * 96)
    for issue in issues[: args.top]:
        print(
            "%2d. %-22s %-26s [%s] 임팩트%d 출처%2d 점수%6.2f %s"
            % (
                issue["rank"],
                issue["title"][:22],
                issue["subtitle"][:26],
                axis_label.get(issue["axis"], issue["axis"]),
                issue["impact"],
                issue["source_count"],
                issue["score"],
                badge_label.get(issue["badge"], ""),
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
