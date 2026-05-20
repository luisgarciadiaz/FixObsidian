import os
import sys
import json

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"Config file not found: {CONFIG_PATH}")
        print("Copy config.json.example to config.json and edit the paths.")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.pop("_description", None)
    cfg.pop("_notes", None)

    env_vault = os.environ.get("VAULT_PATH")
    env_library = os.environ.get("LIBRARY_PATH")
    env_organize = os.environ.get("ORGANIZE_NOTES")
    if env_vault:
        cfg["vault_path"] = env_vault
    if env_library:
        cfg["library_path"] = env_library
    if env_organize and env_organize.lower() in ("true", "1", "yes"):
        cfg["organize"] = True

    return cfg
