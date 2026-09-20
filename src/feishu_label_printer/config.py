import json
from pathlib import Path


def read_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    config["_root"] = path.parent
    config["_path"] = path
    profiles = config.get("profiles", [])
    if not profiles or len({p["name"] for p in profiles}) != len(profiles):
        raise ValueError("Configure at least one profile with a unique name")
    if float(config.get("poll_seconds", 5)) < 1:
        raise ValueError("poll_seconds must be at least 1")
    queues = set()
    for p in profiles:
        if p["kind"] not in ("material", "prototype"):
            raise ValueError("kind must be material or prototype")
        if len(p["fields"]) != 3:
            raise ValueError("fields must contain exactly three queue field names")
        key = (p["base_token"], p["queue_table"])
        if key in queues:
            raise ValueError("Each profile must have its own queue table")
        queues.add(key)
    return config


def resolve(config, path):
    path = Path(path)
    return path if path.is_absolute() else config["_root"] / path


def profile_named(config, name):
    for profile in config["profiles"]:
        if profile["name"] == name:
            return profile
    raise ValueError(f"Unknown profile: {name}")
