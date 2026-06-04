import os
import json
import requests

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama3-70b-8192"


def _api_key():
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        raise ValueError("GROQ_API_KEY not set")
    return key


def analyze_picks(picks: list[dict], user_question: str = "") -> str:
    """
    Send top value picks to Groq for AI analysis.

    picks: list of dicts with keys: player, team, line, over_odds, book_implied, fair_est, edge
    user_question: optional follow-up question from the user
    """
    picks_text = json.dumps(picks, indent=2)

    system_prompt = (
        "You are an expert sports betting analyst specializing in MLB player props. "
        "You analyze value bets based on probability edges between model fair estimates and book-implied odds. "
        "Speak concisely, confidently, and use plain English. Always remind users to bet responsibly."
    )

    if user_question:
        user_content = (
            f"Here are today's top MLB hits prop value bets:\n\n{picks_text}\n\n"
            f"User question: {user_question}\n\n"
            "Please answer the question in context of these picks."
        )
    else:
        user_content = (
            f"Here are today's top MLB hits prop value bets:\n\n{picks_text}\n\n"
            "Please give a sharp, concise breakdown: highlight the 3 best plays and why, "
            "note any patterns you see (same team stacking, pitcher matchups if known), "
            "and give a one-sentence overall board summary."
        )

    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.7,
        "max_tokens": 1024,
    }

    resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def quick_summary(board_stats: dict) -> str:
    """Generate a short board summary from aggregate stats."""
    system_prompt = (
        "You are a sharp sports betting analyst. Give a 2-3 sentence daily board summary. Be direct and concise."
    )
    user_content = (
        f"Today's MLB hits props board stats: {json.dumps(board_stats)}. "
        "Summarize the opportunity level and any standout observations in 2-3 sentences."
    )

    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.6,
        "max_tokens": 256,
    }

    resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=20)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
