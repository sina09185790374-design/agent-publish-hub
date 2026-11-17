"""State storage for agent-publish-hub.

The hub is a directory with two files:

- ``hub.json`` — the whole state (episodes, platforms, metrics).
- ``events.jsonl`` — an append-only event log, one JSON object per line,
  so every change is traceable even if hub.json is hand-edited.

Both files are plain JSON/UTF-8. No network, no keys.
"""

import json
import os

STATE_FILE = "hub.json"
EVENTS_FILE = "events.jsonl"


def empty_state():
    return {"version": 1, "episodes": {}}


def ensure_root(root):
    os.makedirs(root, exist_ok=True)
    return root


def state_path(root):
    return os.path.join(root, STATE_FILE)


def events_path(root):
    return os.path.join(root, EVENTS_FILE)


def load(root):
    """Load state; a missing file is an empty hub, a corrupt file is an error."""
    path = state_path(root)
    if not os.path.exists(path):
        return empty_state()
    with open(path, "r", encoding="utf-8") as fh:
        state = json.load(fh)
    if not isinstance(state, dict) or "episodes" not in state:
        raise ValueError("corrupt hub state: %s" % path)
    return state


def save(root, state):
    ensure_root(root)
    tmp = state_path(root) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, state_path(root))


def log_event(root, event):
    ensure_root(root)
    with open(events_path(root), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")


def read_events(root):
    path = events_path(root)
    if not os.path.exists(path):
        return []
    events = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events
