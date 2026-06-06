"""
Player News / Injury Feed
=========================
Pulls recent player news from ESPN RSS feeds and matches headlines
to players currently on the props board.

Usage:
    from news_feed import get_matched_news
    news = get_matched_news(["Shohei Ohtani", "Aaron Judge"], sport="MLB")
    # returns list of {player, headline, url, published, relevance_score}

Supported sports: MLB, NBA, WNBA, NHL
"""

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from functools import lru_cache

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

try:
    import streamlit as st
    _HAS_ST = True
except ImportError:
    _HAS_ST = False


# ── ESPN RSS endpoints ────────────────────────────────────────────────────────

ESPN_RSS: dict[str, str] = {
    "MLB":  "https://www.espn.com/espn/rss/mlb/news",
    "NBA":  "https://www.espn.com/espn/rss/nba/news",
    "WNBA": "https://www.espn.com/espn/rss/wnba/news",
    "NHL":  "https://www.espn.com/espn/rss/nhl/news",
}

ROTOWIRE_RSS: dict[str, str] = {
    "MLB":  "https://www.rotowire.com/updates/rss.php?sport=baseball",
    "NBA":  "https://www.rotowire.com/updates/rss.php?sport=basketball",
    "WNBA": "https://www.rotowire.com/updates/rss.php?sport=basketball",
    "NHL":  "https://www.rotowire.com/updates/rss.php?sport=hockey",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 SBP-NewsFeed/1.0",
    "Accept": "application/rss+xml, application/xml, text/xml",
}

# Flag words that indicate the news is injury/availability-related
INJURY_KEYWORDS = {
    "injured", "injury", "out", "questionable", "doubtful", "day-to-day",
    "il", "inactive", "scratch", "scratched", "dtd", "day to day",
    "hamstring", "shoulder", "knee", "ankle", "back", "concussion",
    "wrist", "elbow", "hip", "quad", "calf", "thumb", "oblique",
    "suspension", "suspended", "did not practice", "limited", "sore",
}


# ── RSS fetch + parse ─────────────────────────────────────────────────────────

def _fetch_rss(url: str, timeout: int = 8) -> list[dict]:
    """Fetch an RSS feed and return list of {title, link, pubDate, summary}."""
    if not _HAS_REQUESTS:
        return []
    try:
        r = _requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        items = root.findall(".//item")
        entries = []
        for item in items:
            title   = (item.findtext("title") or "").strip()
            link    = (item.findtext("link") or "").strip()
            pub     = (item.findtext("pubDate") or "").strip()
            desc    = (item.findtext("description") or "").strip()
            # Strip HTML tags from description
            desc = re.sub(r"<[^>]+>", " ", desc).strip()
            entries.append({
                "title":     title,
                "link":      link,
                "pubDate":   pub,
                "summary":   desc,
            })
        return entries
    except Exception:
        return []


@lru_cache(maxsize=8)
def _cached_feed(sport: str, _hour_bucket: int) -> list[dict]:
    """
    Cache-busted by hour so we don't hit ESPN more than once per hour.
    _hour_bucket = int(time.time() // 3600)
    """
    entries = []
    for url in [ESPN_RSS.get(sport), ROTOWIRE_RSS.get(sport)]:
        if url:
            entries.extend(_fetch_rss(url))
    return entries


def fetch_sport_news(sport: str) -> list[dict]:
    """Fetch all recent news for a sport (cached 1 hr)."""
    import time
    bucket = int(time.time() // 3600)
    return _cached_feed(sport, bucket)


# ── Player name matching ──────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    """Lowercase, strip punctuation for fuzzy matching."""
    return re.sub(r"[^a-z ]", "", name.lower().strip())


def _player_in_headline(player: str, title: str, summary: str) -> float:
    """
    Return a relevance score 0.0–1.0 for how closely a headline mentions the player.

    Scoring:
      1.0 — full name exact match in title
      0.8 — last name exact match in title + first initial
      0.5 — last name-only match in title
      0.3 — last name anywhere in summary
      0.0 — no match
    """
    p_norm = _normalize(player)
    t_norm = _normalize(title)
    s_norm = _normalize(summary)

    parts  = p_norm.split()
    if len(parts) < 2:
        return 0.0

    first, last = parts[0], parts[-1]

    # Full name in title
    if p_norm in t_norm:
        return 1.0

    # Last name + first initial in title
    if last in t_norm and f"{first[0]} {last}" in t_norm:
        return 0.8

    # Last name in title
    if re.search(rf"\b{re.escape(last)}\b", t_norm):
        return 0.5

    # Last name in summary
    if re.search(rf"\b{re.escape(last)}\b", s_norm):
        return 0.3

    return 0.0


def _is_injury_news(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in INJURY_KEYWORDS)


# ── Public API ────────────────────────────────────────────────────────────────

def get_matched_news(
    players: list[str],
    sport: str,
    min_relevance: float = 0.3,
    max_per_player: int = 3,
) -> list[dict]:
    """
    Fetch news for a sport and return items mentioning any player in the list.

    Args:
        players:       List of player name strings (from current props board).
        sport:         "MLB", "NBA", "WNBA", or "NHL"
        min_relevance: Minimum relevance score to include (0.0–1.0).
        max_per_player: Max headlines per player.

    Returns:
        List of dicts sorted by (relevance desc, recency desc):
        {
          player, headline, url, published, summary,
          relevance_score, is_injury
        }
    """
    feed    = fetch_sport_news(sport)
    results = []
    seen    = set()

    for item in feed:
        title   = item["title"]
        summary = item["summary"]
        url     = item["link"]
        pub     = item["pubDate"]

        for player in players:
            score = _player_in_headline(player, title, summary)
            if score < min_relevance:
                continue
            key = (player, url)
            if key in seen:
                continue
            seen.add(key)

            results.append({
                "player":          player,
                "headline":        title,
                "url":             url,
                "published":       pub,
                "summary":         summary[:200] + ("…" if len(summary) > 200 else ""),
                "relevance_score": score,
                "is_injury":       _is_injury_news(title, summary),
            })

    # Sort: injury news first (high relevance), then by score desc
    results.sort(key=lambda x: (-x["is_injury"], -x["relevance_score"]))

    # Limit per player
    per_player: dict[str, int] = {}
    final = []
    for r in results:
        p = r["player"]
        per_player[p] = per_player.get(p, 0) + 1
        if per_player[p] <= max_per_player:
            final.append(r)

    return final


def render_news_sidebar(players: list[str], sport: str):
    """
    Streamlit helper: render a news expander for matched players.
    Designed for use inside a with st.expander(...) block or directly in sidebar.
    """
    if not _HAS_ST:
        return

    news = get_matched_news(players, sport)
    if not news:
        st.caption("No recent news found for current props players.")
        return

    injury_news = [n for n in news if n["is_injury"]]
    other_news  = [n for n in news if not n["is_injury"]]

    if injury_news:
        st.markdown("#### 🚨 Injury / Status Alerts")
        for item in injury_news:
            st.markdown(
                f"""<div style="background:#2a1a1a;border:1px solid #ff6060;border-radius:8px;
                               padding:10px 14px;margin-bottom:8px;">
                  <div style="color:#ff8080;font-size:0.78rem;font-weight:600;text-transform:uppercase;
                              letter-spacing:0.5px;">{item['player']}</div>
                  <div style="color:#e8e8f0;font-size:0.88rem;margin:4px 0;">
                    <a href="{item['url']}" target="_blank" style="color:#e8e8f0;text-decoration:none;">
                      {item['headline']}
                    </a>
                  </div>
                  <div style="color:#888;font-size:0.75rem;">{item['summary']}</div>
                </div>""",
                unsafe_allow_html=True,
            )

    if other_news:
        st.markdown("#### 📰 Recent News")
        for item in other_news[:6]:
            st.markdown(
                f"""<div style="background:#1a1a24;border:1px solid #2a2a3a;border-radius:8px;
                               padding:8px 12px;margin-bottom:6px;">
                  <div style="color:#a78bfa;font-size:0.78rem;font-weight:600;">{item['player']}</div>
                  <div style="color:#c8c8d8;font-size:0.85rem;margin:3px 0;">
                    <a href="{item['url']}" target="_blank" style="color:#c8c8d8;text-decoration:none;">
                      {item['headline']}
                    </a>
                  </div>
                </div>""",
                unsafe_allow_html=True,
            )


if __name__ == "__main__":
    import sys
    sport_arg = sys.argv[1] if len(sys.argv) > 1 else "MLB"
    players_arg = sys.argv[2:] or ["Shohei Ohtani", "Aaron Judge", "Freddie Freeman"]
    print(f"Fetching {sport_arg} news for: {players_arg}")
    items = get_matched_news(players_arg, sport_arg)
    if not items:
        print("No matched news found.")
    for item in items:
        inj = " 🚨 INJURY" if item["is_injury"] else ""
        print(f"\n[{item['player']}]{inj} score={item['relevance_score']:.1f}")
        print(f"  {item['headline']}")
        print(f"  {item['summary'][:100]}")
