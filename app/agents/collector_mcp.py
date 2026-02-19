# app/agents/collector_mcp.py
from __future__ import annotations
import asyncio, json, os
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

from langchain_mcp_adapters.client import MultiServerMCPClient
from app.graph.state import WeeklyResearchState, ContentItem
from app.mcp.multi_client import build_mcp_server_config, call_tool, list_tools
from app.utils.logger import get_logger, log_with_run_id
from app.mcp.errors import format_exception

logger = get_logger(__name__)

SOURCES_PATH = "data/sources.json"

def _jst_now_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()

def _make_item_id(source: str, url: str) -> str:
    # dedup安定化：URLを主キーにする（titleは揺れる）
    return f"{source}:{url}"

def _item(title: str, url: str, source_type: str, published_at: Optional[str]=None, venue: str="") -> ContentItem:
    return {
        "item_id": _make_item_id(source_type, url),
        "title": title.strip() if title else "(no title)",
        "url": url,
        "source_type": source_type,
        "published_at": published_at or datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat(),
        "venue": venue,
        "collector_meta": {"collected_at": _jst_now_iso()},
    }

def _load_sources() -> dict:
    with open(SOURCES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
    
def _unwrap_mcp_content(res):
    """
    arxiv-mcp-server が返す形式:
      [
        {"type": "text", "text": "{...json...}"}
      ]
    を想定して JSON(dict) に戻す。
    """
    if isinstance(res, list) and res:
        first = res[0]
        if isinstance(first, dict) and first.get("type") == "text" and isinstance(first.get("text"), str):
            txt = first["text"].strip()
            # たまに前後に余計な文字があるケースもあるので軽くガード
            if txt.startswith("{") and txt.endswith("}"):
                return json.loads(txt)
    return res

async def _collect_arxiv(client: MultiServerMCPClient, queries: List[str]) -> List[ContentItem]:
    """
    arXiv MCPで論文を収集。
    重要：tool名やレスポンス形はMCP実装ごとに違うので、
    初回は tools一覧を出して、"search"/"query" などに合わせる。
    """
    items: List[ContentItem] = []
    for q in queries:
        logger.info(f"[arxiv] run query={q!r}")
        res = await call_tool(client, "arxiv", "search_papers", {"query": q, "max_results": 20, "sort_by": "date"},)
        
        res = _unwrap_mcp_content(res)
        if not isinstance(res, dict):
            logger.warning(f"[arxiv] unexpected res after unwrap: {type(res)}")
            continue

        papers = res.get("papers", [])
        logger.info(f"[arxiv] papers_extracted={len(papers)} total_results={res.get('total_results')}")

        for p in papers:
            if not isinstance(p, dict):
                continue
            arxiv_id = p.get("id", "")
            items.append({
                "source": "arxiv",
                "source_query": q,
                "id": f"arxiv:{arxiv_id}" if arxiv_id else (p.get("url") or ""),
                "title": p.get("title", ""),
                "url": p.get("url") or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else ""),
                "published": p.get("published") or p.get("updated") or "",
                "authors": p.get("authors") or [],
                "summary": p.get("abstract") or p.get("summary") or "",
                "raw": p,
            })

    return items

async def _collect_rss(client: MultiServerMCPClient, feeds: List[str]) -> List[ContentItem]:
    """
    RSS/Atom MCPでフィードを取得・パース。
    実装例が複数あるので tool名は要調整（fetch/parseなど）。
    """
    out: List[ContentItem] = []
    for feed in feeds:
        res = await call_tool(client, "rss", "fetch_feed", {"url": feed, "limit": 20})
        entries = res.get("entries", []) if isinstance(res, dict) else []
        for e in entries:
            url = e.get("link") or e.get("url")
            if not url:
                continue
            out.append(_item(
                title=e.get("title",""),
                url=url,
                source_type="web",
                published_at=e.get("published") or e.get("date"),
                venue="RSS/Atom",
            ))
    return out

async def _collect_blogs(client: MultiServerMCPClient, urls: List[str]) -> List[ContentItem]:
    """
    Blogスクレイピング（Playwright系MCP推奨）。
    - JSレンダリングが必要なサイトでも取れる可能性が高い
    """
    out: List[ContentItem] = []
    for u in urls:
        res = await call_tool(client, "scrape", "scrape", {"url": u, "format": "markdown"})
        # ここはMVP：ブログのトップから記事リンク抽出が必要。
        # まずは "links" が返る実装ならそれを使う、無ければ今後追加。
        links = res.get("links", []) if isinstance(res, dict) else []
        for link in links[:20]:
            href = link.get("url") or link.get("href")
            title = link.get("title") or ""
            if href:
                out.append(_item(title=title, url=href, source_type="web", venue="Blog"))
    return out

async def _collect_twitter(client: MultiServerMCPClient, topics: List[str]) -> List[ContentItem]:
    """
    Twitter/X トピック収集。
    注意：XはAPI制限/規約/レート制限が強い。MCP実装により認証方式も異なる。
    """
    out: List[ContentItem] = []
    for t in topics:
        res = await call_tool(client, "twitter", "search", {"query": t, "limit": 20})
        tweets = res.get("results", []) if isinstance(res, dict) else []
        for tw in tweets:
            url = tw.get("url") or tw.get("link")
            if not url:
                continue
            out.append(_item(
                title=(tw.get("text","")[:80] + "…") if tw.get("text") else f"Tweet about {t}",
                url=url,
                source_type="twitter",
                published_at=tw.get("created_at"),
                venue="X(Twitter)",
            ))
    return out

def collector_node(state: WeeklyResearchState) -> WeeklyResearchState:
    run_id = state.get("run_id")
    log_with_run_id(logger, "info", run_id, "MCP Collector started (arXiv/RSS/Blog/Twitter).")

    sources = _load_sources()
    logger.info(f"[sources] keys={list(sources.keys())}")
    logger.info(f"[sources] arxiv_queries={sources.get('arxiv_queries')}")
    logger.info(f"[sources] rss_feeds={sources.get('rss_feeds')}")
    server_cfg = build_mcp_server_config()

    async def _run() -> List[ContentItem]:
        log_with_run_id(logger, "debug", run_id, f"ARXIV_SERVER_CFG={server_cfg.get('arxiv')}")

        client = MultiServerMCPClient(server_cfg)

        # まず tools 一覧（serverごと）。動いたらコメントアウトでOK。
        # for name in ["arxiv", "rss", "scrape"]:
        for name in ["arxiv"]:
            try:
                tools = await list_tools(client, name)
                log_with_run_id(logger, "debug", run_id, f"TOOLS {name}={list(tools.keys())}")
            except Exception as e:
                log_with_run_id(logger, "warning", run_id, f"Skip tool listing for {name}:\n{format_exception(e)}")
                state.setdefault("errors", []).append({"node": "collector", "error": f"{name}: {type(e).__name__}: {e}"})

                
            items: List[ContentItem] = []

        try:
            items += await _collect_arxiv(client, sources.get("arxiv_queries", []))
            qs = sources.get("arxiv_queries", [])
            logger.info(f"[arxiv] queries={len(qs)} -> {qs[:3]}")

        except Exception as e:
            log_with_run_id(logger, "warning", run_id, f"arXiv collect skipped:\n{format_exception(e)}")
            state.setdefault("errors", []).append({"node": "collector", "error": f"arxiv: {type(e).__name__}: {e}"})

        """
        try:
            items += await _collect_rss(client, sources.get("rss_feeds", []))
        except Exception as e:
            log_with_run_id(logger, "warning", run_id, f"RSS collect skipped: {e}")
            state.setdefault("errors", []).append({"node": "collector", "error": f"rss: {e}"})

        try:
            items += await _collect_blogs(client, sources.get("blog_urls", []))
        except Exception as e:
            log_with_run_id(logger, "warning", run_id, f"Scrape collect skipped: {e}")
            state.setdefault("errors", []).append({"node": "collector", "error": f"scrape: {e}"})
        """

        """
        try:
            items += await _collect_twitter(client, sources.get("twitter_topics", []))
        except Exception as e:
            log_with_run_id(logger, "warning", run_id, f"Twitter collect skipped: {e}")
            state.setdefault("errors", []).append({"node": "collector", "error": f"twitter: {e}"})
        """

        return items


    items = asyncio.run(_run())
    logger.info(f"[collector_node] returning items={len(items)} keys={list(state.keys())}")

    # 収集段階でも軽くURL重複を落とす（後段dedupもあるが、無駄を減らす）
    seen = set()
    uniq = []
    for it in items:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        uniq.append(it)

    state["collected_items"] = uniq
    log_with_run_id(logger, "info", run_id, f"MCP Collector finished: items={len(uniq)}")
    return state
