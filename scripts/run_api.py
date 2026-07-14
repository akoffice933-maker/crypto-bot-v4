#!/usr/bin/env python
"""
Crypto Bot v4.5 — API Server Runner

Usage:
    python scripts/run_api.py                       # start API on :8000
    python scripts/run_api.py --host 0.0.0.0 --port 8080
    python scripts/run_api.py --env production      # load production config
"""

import argparse
import os
import sys

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Crypto Bot v4.5 — API Server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--env", default=os.getenv("BOT_ENV", "paper"),
                       choices=["production", "paper", "backtest"])
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev only)")
    args = parser.parse_args()

    # Set environment
    os.environ["BOT_ENV"] = args.env

    # Add project root to path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    uvicorn.run(
        "api.server:create_app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
