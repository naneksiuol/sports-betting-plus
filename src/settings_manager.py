"""settings_manager.py — Load/save bankroll & unit-size settings."""
import json
import os

_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "settings.json")

_DEFAULTS: dict = {
    "starting_bankroll": 1000.0,
    "unit_size": 10.0,
    "kelly_multiplier": 0.25,
}


def load_settings() -> dict:
    """Return settings from data/settings.json, falling back to defaults."""
    try:
        with open(_SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        # Merge with defaults so new keys are always present
        merged = dict(_DEFAULTS)
        merged.update(data)
        return merged
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(_DEFAULTS)


def save_settings(d: dict) -> None:
    """Persist settings dict to data/settings.json."""
    os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
    with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
