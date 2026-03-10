#!/usr/bin/env python3
"""AlphaXiv Skill.

Search and retrieve research papers from AlphaXiv API.
Supports authenticated chat/ask via ALPHAXIV_TOKEN.
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error

BASE_URL = "https://api.alphaxiv.org"


def _read_zshrc(key: str) -> str | None:
    zshrc = os.path.expanduser("~/.zshrc")
    if not os.path.exists(zshrc):
        return None
    with open(zshrc) as f:
        for line in f:
            if key in line and "=" in line and not line.strip().startswith("#"):
                val = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
                if val:
                    return val
    return None


def _resolve_token() -> str | None:
    return os.environ.get("ALPHAXIV_TOKEN") or _read_zshrc("ALPHAXIV_TOKEN")


def _headers(extra: dict = None) -> dict:
    h = {"Accept": "application/json", "Content-Type": "application/json"}
    token = _resolve_token()
    if token:
        h["Authorization"] = f"Bearer {token}"
    if extra:
        h.update(extra)
    return h


def _get(path: str, params: dict = None) -> dict | list | None:
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    try:
        req = urllib.request.Request(url, headers=_headers())
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"HTTP {e.code}: {body}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return None



def _post_stream(path: str, body: dict) -> str | None:
    """POST and read SSE stream via curl subprocess."""
    import subprocess
    url = BASE_URL + path
    token = _resolve_token()
    cmd = [
        "curl", "-s", "--max-time", "180", "-X", "POST", url,
        "-H", f"Authorization: Bearer {token}",
        "-H", "Content-Type: application/json",
        "-H", "Accept: text/event-stream",
        "-d", json.dumps(body),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=200)
        if result.returncode != 0:
            print(f"Error: {result.stderr}", file=sys.stderr)
            return None
        answer_parts = []
        chat_id = None
        for line in result.stdout.splitlines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload in ("", "[DONE]"):
                continue
            try:
                obj = json.loads(payload)
                delta = obj.get("delta") or obj.get("content") or obj.get("text") or ""
                if isinstance(delta, str) and delta:
                    answer_parts.append(delta)
                if not chat_id:
                    chat_id = obj.get("llmChatId") or obj.get("chatId")
            except json.JSONDecodeError:
                if payload:
                    answer_parts.append(payload)
        text = "".join(answer_parts)
        if chat_id:
            text += f"\n\n[Chat ID: {chat_id}  — pass --chat-id {chat_id} to continue]"
        return text or None
    except subprocess.TimeoutExpired:
        print("Error: request timed out", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return None


def _fmt_paper(p: dict) -> str:
    lines = []
    title = p.get("title") or p.get("name", "")
    if title:
        lines.append(f"Title: {title}")
    arxiv_id = p.get("arxivId") or p.get("upid") or p.get("id", "")
    if arxiv_id:
        lines.append(f"arXiv ID: {arxiv_id}")
        lines.append(f"URL: https://alphaxiv.org/abs/{arxiv_id}")
    authors = p.get("authors") or p.get("authorNames") or []
    if isinstance(authors, list) and authors:
        if isinstance(authors[0], dict):
            names = [a.get("name", "") for a in authors]
        else:
            names = authors
        lines.append(f"Authors: {', '.join(names[:5])}" + (" et al." if len(names) > 5 else ""))
    date = p.get("submittedDate") or p.get("firstPublicationDate") or p.get("publishedDate", "")
    if date:
        lines.append(f"Date: {date}")
    abstract = p.get("abstract", "")
    if abstract:
        lines.append(f"Abstract: {abstract[:400]}{'...' if len(abstract) > 400 else ''}")
    return "\n".join(lines)


def cmd_search(args):
    data = _get("/search/v2/paper/fast", {"q": args.query, "includePrivate": "false"})
    if not data:
        print("No results found.")
        return
    results = data if isinstance(data, list) else data.get("papers", [])
    results = results[: args.limit]
    if not results:
        print("No results found.")
        return
    for i, item in enumerate(results, 1):
        paper_id = item.get("paperId") or item.get("link", "")
        print(f"\n[{i}] {item.get('title', paper_id)}")
        if paper_id:
            print(f"    arXiv ID: {paper_id}")
            print(f"    URL: https://alphaxiv.org/abs/{paper_id}")


def cmd_paper(args):
    data = _get(f"/papers/v3/{args.id}")
    if not data:
        return
    paper = data.get("data", data) if isinstance(data, dict) else data
    print(_fmt_paper(paper))


def cmd_metrics(args):
    data = _get(f"/papers/v3/{args.id}/metrics")
    if not data:
        return
    d = data.get("data", data) if isinstance(data, dict) else data
    print(f"arXiv ID: {args.id}")
    print(f"Views:    {d.get('visitsAll', 'N/A')}")
    print(f"Votes:    {d.get('publicTotalVotes', 'N/A')}")
    print(f"Comments: {d.get('commentsCount', 'N/A')}")


def _resolve_uuids(id_or_arxiv: str) -> tuple[str, str]:
    """Return (versionId, groupId) for a given arXiv ID or UUID.
    If already a UUID, fetch paper to get both. If arXiv ID, fetch paper."""
    data = _get(f"/papers/v3/{id_or_arxiv}")
    if not data:
        return id_or_arxiv, id_or_arxiv
    p = data.get("data", data) if isinstance(data, dict) else data
    return p.get("versionId", id_or_arxiv), p.get("groupId", id_or_arxiv)


def cmd_overview(args):
    lang = args.language or "en"
    version_id, _ = _resolve_uuids(args.id)
    data = _get(f"/papers/v3/{version_id}/overview/{lang}")
    if not data:
        status = _get(f"/papers/v3/{version_id}/overview/status")
        if status:
            print(f"Overview status: {json.dumps(status, indent=2)}")
        return
    d = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(d, str):
        print(d)
    elif isinstance(d, dict):
        print(json.dumps(d, indent=2, ensure_ascii=False))
    else:
        print(str(d))


def cmd_similar(args):
    data = _get(f"/papers/v3/{args.id}/similar-papers", {"limit": str(args.limit)})
    if not data:
        return
    papers = data if isinstance(data, list) else data.get("data", [])
    if not papers:
        print("No similar papers found.")
        return
    for i, p in enumerate(papers, 1):
        print(f"\n[{i}]")
        print(_fmt_paper(p))


def cmd_top(args):
    data = _get("/retrieve/v1/top-papers", {"limit": str(args.limit), "skip": "0"})
    if not data:
        return
    papers = data if isinstance(data, list) else (data.get("data") or data.get("papers") or [])
    if not papers:
        print("No papers found.")
        return
    for i, p in enumerate(papers, 1):
        print(f"\n[{i}]")
        print(_fmt_paper(p))


def cmd_feed(args):
    params = {
        "pageNum": "1",
        "pageSize": str(args.limit),
        "sort": args.sort,
        "interval": args.interval,
    }
    data = _get("/papers/v3/feed", params)
    if not data:
        return
    papers = data.get("papers", data) if isinstance(data, dict) else data
    if not papers:
        print("No papers found.")
        return
    for i, p in enumerate(papers, 1):
        print(f"\n[{i}]")
        print(_fmt_paper(p))


def cmd_implementations(args):
    _, group_id = _resolve_uuids(args.id)
    data = _get(f"/papers/v3/{group_id}/implementations")
    if not data:
        return
    d = data.get("data", data) if isinstance(data, dict) else data
    ax = d.get("alphaXivImplementations", [])
    resources = d.get("paperResources", [])
    if not ax and not resources:
        print("No implementations found.")
        return
    if ax:
        print("AlphaXiv Implementations:")
        for item in ax:
            print(f"  [{item.get('type','')}] {item.get('url','')}")
    if resources:
        print("Paper Resources:")
        for item in resources:
            print(f"  [{item.get('type','')}] {item.get('url','')} - {item.get('description','')}")


def cmd_sota(args):
    if args.slug:
        data = _get(f"/sota/v1/tasks/{args.slug}")
        if not data:
            return
        d = data.get("data", data) if isinstance(data, dict) else data
        task = d.get("task", d)
        print(f"Task: {task.get('name','')}")
        print(f"Type: {task.get('type','')}")
        print(f"Description: {task.get('description','')}")
        benchmarks = d.get("benchmarks", [])
        if benchmarks:
            print(f"\nBenchmarks ({len(benchmarks)}):")
            for b in benchmarks[:5]:
                print(f"  - {b.get('name','')}: {b.get('shortDescription','')}")
    else:
        data = _get("/sota/v1/tasks")
        if not data:
            return
        tasks = data if isinstance(data, list) else data.get("data", [])
        print(f"SOTA Tasks ({len(tasks)}):")
        for t in tasks:
            print(f"  [{t.get('type','')}] {t.get('name','')} (slug: {t.get('slug','')}) - {t.get('numDatasets',0)} datasets")


def cmd_metadata(args):
    data = _get(f"/v2/papers/{args.id}/metadata")
    if not data:
        return
    d = data.get("data", data) if isinstance(data, dict) else data
    pv = d.get("paper_version", {})
    pg = d.get("paper_group", {})
    print(f"Title: {pv.get('title', '')}")
    print(f"arXiv ID: {pv.get('universal_paper_id', '')}")
    print(f"Version: {pv.get('version_label', '')}")
    print(f"Published: {pv.get('publication_date', '')}")
    topics = pg.get("topics", [])
    if topics:
        print(f"Topics: {', '.join(topics)}")
    authors = d.get("authors", [])
    if authors:
        names = [a.get("full_name", "") for a in authors]
        print(f"Authors: {', '.join(names)}")
    orgs = d.get("organization_info", [])
    if orgs:
        org_names = [o.get("name", "") for o in orgs]
        print(f"Institutions: {', '.join(org_names)}")
    impl = d.get("implementation", {})
    if impl and impl.get("url"):
        print(f"GitHub: {impl.get('url', '')} ({impl.get('stars', 0)} stars)")
    citation = pv.get("citation", {})
    if citation and args.bibtex:
        print(f"\nBibTeX:\n{citation.get('bibtex', '')}")




def cmd_ask(args):
    """Ask a question about a paper. Requires ALPHAXIV_TOKEN."""
    token = _resolve_token()
    if not token:
        print("Error: 'ask' requires authentication.\n"
              "Set ALPHAXIV_TOKEN in ~/.zshrc:\n"
              "  export ALPHAXIV_TOKEN=your_api_key\n\n"
              "To get an API key, run:\n"
              "  python3 alphaxiv.py --token SHORT_LIVED_JWT create-api-key\n"
              "(get the JWT from DevTools → Network → any api.alphaxiv.org request)")
        sys.exit(1)

    # Auto-resolve paperVersionId from arXiv ID
    paper_version_id = args.paper_version_id
    if args.paper and not paper_version_id:
        data = _get(f"/papers/v3/{args.paper}")
        if data:
            paper = data.get("data", data) if isinstance(data, dict) else data
            paper_version_id = paper.get("versionId")

    payload = {
        "message": args.question,
        "files": [],
        "llmChatId": args.chat_id,
        "thinking": args.thinking,
        "deepResearch": args.deep_research,
        "parentMessageId": None,
        "paperVersionId": paper_version_id,
        "selectionPageRange": None,
        "model": args.model,
        "webSearch": "off",
    }

    result = _post_stream("/assistant/v2/chat", payload)
    if result:
        print(result)


def main():
    parser = argparse.ArgumentParser(description="AlphaXiv API skill")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="Search papers")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=10)

    p_paper = sub.add_parser("paper", help="Get paper details")
    p_paper.add_argument("id", help="arXiv ID or UUID")

    p_metrics = sub.add_parser("metrics", help="Get paper metrics")
    p_metrics.add_argument("id", help="arXiv ID or UUID")

    p_overview = sub.add_parser("overview", help="Get AI overview of a paper")
    p_overview.add_argument("id", help="arXiv ID or UUID")
    p_overview.add_argument("--language", default="en", help="Language code (default: en)")

    p_similar = sub.add_parser("similar", help="Get similar papers")
    p_similar.add_argument("id", help="arXiv ID or UUID")
    p_similar.add_argument("--limit", type=int, default=5)

    p_top = sub.add_parser("top", help="Get top AI papers")
    p_top.add_argument("--limit", type=int, default=10)

    p_feed = sub.add_parser("feed", help="Get feed papers")
    p_feed.add_argument("--sort", default="Hot",
        choices=["Hot", "Comments", "Views", "Likes", "GitHub", "Twitter (X)"])
    p_feed.add_argument("--interval", default="7 Days",
        choices=["3 Days", "7 Days", "30 Days"])
    p_feed.add_argument("--limit", type=int, default=10)

    p_impl = sub.add_parser("implementations", help="Get paper implementations")
    p_impl.add_argument("id", help="arXiv ID or UUID")

    p_sota = sub.add_parser("sota", help="Get SOTA tasks")
    p_sota.add_argument("--slug", default=None, help="Task slug for details")

    p_meta = sub.add_parser("metadata", help="Get paper authors, institutions, topics, GitHub")
    p_meta.add_argument("id", help="arXiv ID")
    p_meta.add_argument("--bibtex", action="store_true", help="Also print BibTeX citation")

    p_ask = sub.add_parser("ask", help="Ask a question about a paper (requires token)")
    p_ask.add_argument("question", help="Your question about the paper")
    p_ask.add_argument("--paper", default=None, metavar="ARXIV_ID",
        help="arXiv ID to ask about (e.g. 1706.03762). Auto-resolves to paperVersionId.")
    p_ask.add_argument("--url", action="append", metavar="PDF_URL",
        help="PDF URL(s) to ask about. Can be repeated.")
    p_ask.add_argument("--chat-id", default=None, dest="chat_id",
        help="Continue an existing chat session (UUID from previous ask)")
    p_ask.add_argument("--paper-version-id", default=None, dest="paper_version_id",
        help="AlphaXiv paper version UUID (optional)")
    p_ask.add_argument("--model", default="gemini-3-flash",
        choices=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3-flash", "gemini-3-pro",
                 "claude-4.5-sonnet", "grok-4", "qwen-3", "qwen-3-next",
                 "gpt-5", "gpt-oss-120b", "llama-4-maverick", "kimi-k2", "aurelle-1"],
        help="LLM model to use (default: gemini-2.5-flash)")
    p_ask.add_argument("--thinking", action="store_true", help="Enable extended thinking")
    p_ask.add_argument("--deep-research", action="store_true", dest="deep_research",
        help="Enable deep research mode")

    args = parser.parse_args()

    {
        "search": cmd_search,
        "paper": cmd_paper,
        "metrics": cmd_metrics,
        "overview": cmd_overview,
        "similar": cmd_similar,
        "top": cmd_top,
        "feed": cmd_feed,
        "implementations": cmd_implementations,
        "sota": cmd_sota,
        "metadata": cmd_metadata,
        "ask": cmd_ask,
    }[args.command](args)


if __name__ == "__main__":
    main()
