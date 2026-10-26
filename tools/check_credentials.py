#!/usr/bin/env python3
"""只检查指定配置文件中的变量是否填写；不联网，不回显内容。"""
from __future__ import annotations

import argparse
from pathlib import Path


def load_env(path: Path) -> dict[str, str]:
    env = {}
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip().strip('"').strip("'")
    return env


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", default=".env.local")
    config = load_env(Path(parser.parse_args().env))
    for name in ("VOLCENGINE_TTS_API_KEY", "ARK_IMAGE_API_KEY", "MINIMAX_API_KEY", "PEXELS_API_KEY"):
        print(name, "PRESENT" if config.get(name) else "ABSENT")
