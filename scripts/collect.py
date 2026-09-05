#!/usr/bin/env python3
"""AI 소식 수집기.

정해진 출처에서 항목을 가져와 data/items.json에 저장한다.
출처 목록과 정규화 규칙은 wiki/03-pipeline.md에 기록한다.

실행: python scripts/collect.py
"""

from __future__ import annotations

import calendar
import hashlib
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

import feedparser
import requests

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ITEMS_PATH = DATA_DIR / "items.json"
STATE_PATH = DATA_DIR / "fetch_state.json"

RETENTION_HOURS = 48
TIMEOUT = 20
USER_AGENT = "ai-issues/0.1 (+https://github.com/wanrkim/ai-issues)"
SEC_USER_AGENT = "ai-issues wanrkim@gmail.com"

# 축 키는 wiki/00-direction.md의 표와 같다. 여기서 붙이는 값은 힌트이며
# 최종 축은 Phase 2의 판정 단계에서 결정한다.
FEEDS = [
    ("OpenAI", "llm", "https://openai.com/news/rss.xml"),
    ("Google DeepMind", "llm", "https://deepmind.google/blog/feed/basic/"),
    ("Hugging Face Blog", "llm", "https://huggingface.co/blog/feed.xml"),
    # /rss 는 HTML을 반환한다. 뉴스룸의 실제 피드는 releases.xml 이다.
    ("NVIDIA Newsroom", "hardware", "https://nvidianews.nvidia.com/releases.xml"),
]

GOOGLE_NEWS_QUERIES = [
    ("Anthropic", "llm"),
    ("OpenAI", "llm"),
    ("Gemini AI", "llm"),
    ("HBM memory", "hardware"),
    ("AI chip", "hardware"),
    ("AI IPO funding", "capital"),
]

ANTHROPIC_SITEMAP = "https://www.anthropic.com/sitemap.xml"
ANTHROPIC_PATH_PATTERN = re.compile(r"^/(news|research|engineering)/[^/]+$")
ANTHROPIC_TITLE_FETCH_LIMIT = 10

HN_TOPSTORIES = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"
HN_STORY_LIMIT = 100

HF_MODELS_API = "https://huggingface.co/api/models"
HF_MODEL_LIMIT = 100
HF_MIN_LIKES = 1

SEC_FTS = "https://efts.sec.gov/LATEST/search-index"
SEC_QUERIES = [
    ('"artificial intelligence"', "S-1"),
    ('"artificial intelligence"', "8-K"),
]
# 전문 검색은 기본값이 관련도순이라 오래된 제출도 앞에 온다. 날짜 범위로 좁힌다.
SEC_LOOKBACK_DAYS = 3

AI_PATTERN = re.compile(
    r"\b("
    r"ai|llms?|gpt|chatgpt|claude|anthropic|openai|gemini|deepmind|grok|xai|"
    r"mistral|llama|deepseek|qwen|nvidia|gpu|hbm|tpu|asic|"
    r"transformers?|diffusion|inference|neural|agentic|copilot|midjourney|"
    r"sora|veo|runway|cursor|codex|benchmark"
    r")\b",
    re.IGNORECASE,
)

TRACKING_PARAM = re.compile(r"^(utm_|fbclid|gclid|mc_|igshid|ref_src|_hs)", re.IGNORECASE)

STATE: dict = {}
ERRORS: list = []


# ---------------------------------------------------------------- 공통 유틸


def now_kst() -> datetime:
    return datetime.now(KST)


def iso(dt: datetime) -> str:
    return dt.astimezone(KST).isoformat(timespec="seconds")


def normalize_url(url: str) -> str:
    """추적 파라미터와 프래그먼트를 제거하고 호스트를 소문자로 맞춘다."""
    parsed = urlparse(url.strip())
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not TRACKING_PARAM.match(k)
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(("https", netloc, path, "", urlencode(query), ""))


def title_key(title: str) -> str:
    """제목 기준 중복 판정에 쓸 문자열을 만든다.

    Google News 제목은 끝에 매체명이 붙으므로 잘라낸다.
    """
    text = re.sub(r"\s+[-–|]\s+[^-–|]{2,40}$", "", title.strip())
    text = re.sub(r"[^\w\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def make_item(source, axis, url, title, published_at, snippet=""):
    if not url or not title:
        return None
    norm = normalize_url(url)
    return {
        "id": hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16],
        "source": source,
        "axis_hint": axis,
        "url": norm,
        "title": html.unescape(title).strip(),
        "published_at": published_at,
        "fetched_at": iso(now_kst()),
        "snippet": html.unescape(re.sub(r"<[^>]+>", " ", snippet or "")).strip()[:500],
    }


def struct_to_iso(struct):
    if not struct:
        return None
    return iso(datetime.fromtimestamp(calendar.timegm(struct), timezone.utc))


def is_recent(item: dict, hours: int = RETENTION_HOURS) -> bool:
    stamp = item.get("published_at") or item.get("fetched_at")
    if not stamp:
        return True
    try:
        parsed = datetime.fromisoformat(stamp)
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed >= now_kst() - timedelta(hours=hours)


def http_get(session, url, state_key=None, **kwargs):
    """조건부 요청으로 가져온다. 서버가 304를 반환하면 None을 반환한다."""
    headers = {"User-Agent": USER_AGENT}
    headers.update(kwargs.pop("headers", {}))
    cached = STATE.get(state_key, {}) if state_key else {}
    if cached.get("etag"):
        headers["If-None-Match"] = cached["etag"]
    if cached.get("last_modified"):
        headers["If-Modified-Since"] = cached["last_modified"]

    response = session.get(url, headers=headers, timeout=TIMEOUT, **kwargs)
    if response.status_code == 304:
        return None
    response.raise_for_status()
    if state_key:
        fresh = {k: v for k, v in cached.items() if k not in ("etag", "last_modified")}
        if response.headers.get("ETag"):
            fresh["etag"] = response.headers["ETag"]
        if response.headers.get("Last-Modified"):
            fresh["last_modified"] = response.headers["Last-Modified"]
        STATE[state_key] = fresh
    return response


# ------------------------------------------------------------- 출처별 수집


def collect_feed(session, source, axis, url):
    response = http_get(session, url, state_key="feed:" + url)
    if response is None:
        return []
    parsed = feedparser.parse(response.content)
    items = []
    for entry in parsed.entries:
        published = struct_to_iso(
            entry.get("published_parsed") or entry.get("updated_parsed")
        )
        item = make_item(
            source,
            axis,
            entry.get("link"),
            entry.get("title", ""),
            published,
            entry.get("summary", ""),
        )
        if item:
            items.append(item)
    return items


def collect_google_news(session, query, axis):
    url = (
        "https://news.google.com/rss/search?q="
        + quote(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )
    response = http_get(session, url, state_key="gnews:" + query)
    if response is None:
        return []
    parsed = feedparser.parse(response.content)
    items = []
    for entry in parsed.entries:
        # Google News 링크는 리다이렉트 URL이다. Phase 1에서는 따라가지 않는다.
        source_info = entry.get("source") or {}
        publisher = source_info.get("title") or "Google News"
        item = make_item(
            "Google News / " + publisher,
            axis,
            entry.get("link"),
            entry.get("title", ""),
            struct_to_iso(entry.get("published_parsed")),
            entry.get("summary", ""),
        )
        if item:
            items.append(item)
    return items


def _parse_lastmod(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(KST)
    except ValueError:
        return None


def _slug_title(url: str) -> str:
    return urlparse(url).path.rstrip("/").split("/")[-1].replace("-", " ").title()


def _page_title(session, url: str):
    try:
        response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        response.raise_for_status()
        match = re.search(r"<title[^>]*>(.*?)</title>", response.text, re.S | re.I)
        if not match:
            return None
        title = re.sub(r"\s+", " ", match.group(1)).strip()
        # Anthropic 페이지 제목은 끝에 " \ Anthropic" 이 붙는다.
        return re.sub(r"\s*[\\|]\s*Anthropic\s*$", "", title)
    except requests.RequestException:
        return None


def collect_anthropic(session):
    """공식 피드가 없으므로 sitemap에서 새 URL을 감지한다."""
    response = http_get(session, ANTHROPIC_SITEMAP, state_key="anthropic:sitemap")
    if response is None:
        return []

    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    root = ET.fromstring(response.content)
    entries = {}
    for node in root.iter(ns + "url"):
        loc = node.findtext(ns + "loc")
        if not loc:
            continue
        if ANTHROPIC_PATH_PATTERN.match(urlparse(loc).path):
            entries[loc] = node.findtext(ns + "lastmod")

    seen = set(STATE.get("anthropic:seen", []))
    first_run = not seen
    new_urls = [u for u in entries if u not in seen]
    STATE["anthropic:seen"] = sorted(set(entries) | seen)

    if first_run:
        # 첫 실행에서는 전체가 새 URL이 되므로 최근 항목만 남긴다.
        cutoff = now_kst() - timedelta(hours=RETENTION_HOURS)
        recent = []
        for url in new_urls:
            lastmod = _parse_lastmod(entries.get(url))
            if lastmod and lastmod >= cutoff:
                recent.append(url)
        new_urls = recent

    items = []
    for url in new_urls[:ANTHROPIC_TITLE_FETCH_LIMIT]:
        title = _page_title(session, url) or _slug_title(url)
        lastmod = _parse_lastmod(entries.get(url))
        item = make_item("Anthropic", "llm", url, title, iso(lastmod) if lastmod else None)
        if item:
            items.append(item)
    return items


def collect_hackernews(session):
    response = http_get(session, HN_TOPSTORIES, state_key="hn:top")
    if response is None:
        return []
    story_ids = response.json()[:HN_STORY_LIMIT]
    items = []
    for story_id in story_ids:
        try:
            story = session.get(
                HN_ITEM.format(story_id),
                headers={"User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            ).json()
        except (requests.RequestException, ValueError):
            continue
        if not story or story.get("type") != "story":
            continue
        title = story.get("title", "")
        if not AI_PATTERN.search(title):
            continue
        url = story.get("url") or "https://news.ycombinator.com/item?id=%s" % story_id
        published = iso(datetime.fromtimestamp(story.get("time", 0), timezone.utc))
        item = make_item("Hacker News", "llm", url, title, published)
        if item:
            items.append(item)
    return items


def collect_hf_models(session):
    response = session.get(
        HF_MODELS_API,
        params={"sort": "createdAt", "direction": "-1", "limit": HF_MODEL_LIMIT},
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    items = []
    for model in response.json():
        if model.get("likes", 0) < HF_MIN_LIKES:
            continue
        model_id = model.get("modelId") or model.get("id")
        if not model_id:
            continue
        created = model.get("createdAt")
        item = make_item(
            "Hugging Face Hub",
            "llm",
            "https://huggingface.co/" + model_id,
            "신규 모델 공개: " + model_id,
            iso(_parse_lastmod(created)) if _parse_lastmod(created) else None,
            "likes %s / downloads %s" % (model.get("likes", 0), model.get("downloads", 0)),
        )
        if item:
            items.append(item)
    return items


def collect_sec(session):
    items = []
    today = now_kst().date()
    start = today - timedelta(days=SEC_LOOKBACK_DAYS)
    for query, form in SEC_QUERIES:
        response = session.get(
            SEC_FTS,
            params={
                "q": query,
                "forms": form,
                "dateRange": "custom",
                "startdt": start.isoformat(),
                "enddt": today.isoformat(),
            },
            headers={"User-Agent": SEC_USER_AGENT, "Accept": "application/json"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        hits = response.json().get("hits", {}).get("hits", [])
        for hit in hits:
            source = hit.get("_source", {})
            adsh = source.get("adsh", "")
            ciks = source.get("ciks") or []
            doc = hit.get("_id", "").split(":")[-1]
            if not (adsh and ciks and doc):
                continue
            url = "https://www.sec.gov/Archives/edgar/data/%s/%s/%s" % (
                int(ciks[0]),
                adsh.replace("-", ""),
                doc,
            )
            names = source.get("display_names") or ["Unknown filer"]
            filer = re.sub(r"\s*\(CIK\s+\d+\)\s*$", "", names[0])
            filer = re.sub(r"\s+", " ", filer).strip()
            file_date = source.get("file_date")
            published = file_date + "T00:00:00+09:00" if file_date else None
            item = make_item(
                "SEC EDGAR " + form,
                "capital",
                url,
                "%s %s 제출" % (filer, form),
                published,
                query,
            )
            if item:
                items.append(item)
    return items


# ------------------------------------------------------------------- 실행


def run_source(label, fn, *args):
    try:
        items = fn(*args)
        print("  %-34s %4d건" % (label, len(items)))
        return items
    except Exception as exc:  # 출처 하나가 실패해도 나머지는 계속 진행한다.
        ERRORS.append((label, "%s: %s" % (type(exc).__name__, exc)))
        print("  %-34s  실패  %s: %s" % (label, type(exc).__name__, exc))
        return []


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def main() -> int:
    global STATE
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE = load_json(STATE_PATH, {})
    previous = load_json(ITEMS_PATH, {}).get("items", [])

    session = requests.Session()
    collected = []

    print("수집 시작", iso(now_kst()))
    for source, axis, url in FEEDS:
        collected += run_source(source, collect_feed, session, source, axis, url)
    collected += run_source("Anthropic (sitemap)", collect_anthropic, session)
    for query, axis in GOOGLE_NEWS_QUERIES:
        collected += run_source(
            "Google News: " + query, collect_google_news, session, query, axis
        )
    collected += run_source("Hacker News", collect_hackernews, session)
    collected += run_source("Hugging Face Hub", collect_hf_models, session)
    collected += run_source("SEC EDGAR", collect_sec, session)

    # 피드는 과거 글까지 함께 반환한다. 보관 기간이 지난 항목은 병합 전에 버린다.
    recent = [i for i in collected if is_recent(i)]

    # 중복 제거. URL이 같거나 제목이 같으면 먼저 저장한 항목을 남긴다.
    merged = {}
    for item in previous:
        merged[item["id"]] = item
    titles = set(title_key(i["title"]) for i in previous)
    added = 0
    for item in recent:
        key = title_key(item["title"])
        if item["id"] in merged or key in titles:
            continue
        merged[item["id"]] = item
        titles.add(key)
        added += 1

    kept = sorted(
        (i for i in merged.values() if is_recent(i)),
        key=lambda i: i.get("published_at") or i.get("fetched_at") or "",
        reverse=True,
    )
    dropped = len(merged) - len(kept)

    ITEMS_PATH.write_text(
        json.dumps(
            {"updated_at": iso(now_kst()), "count": len(kept), "items": kept},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    STATE_PATH.write_text(
        json.dumps(STATE, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print()
    print(
        "수집 %d건 / 최근 48시간 %d건 / 신규 %d건 / 보관 %d건 / 만료 제거 %d건"
        % (len(collected), len(recent), added, len(kept), dropped)
    )
    if ERRORS:
        print("실패한 출처 %d개:" % len(ERRORS))
        for label, message in ERRORS:
            print("  - %s: %s" % (label, message))

    total_sources = len(FEEDS) + len(GOOGLE_NEWS_QUERIES) + 4
    return 1 if len(ERRORS) == total_sources else 0


if __name__ == "__main__":
    sys.exit(main())
