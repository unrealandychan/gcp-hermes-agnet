"""
agent.py — ADK Web UI / CLI entry point

This file exposes `root_agent` so the ADK toolchain can discover
and run this project locally:

    adk web .        # opens browser UI at http://localhost:8000
    adk run .        # interactive CLI
    adk api_server . # headless REST API

The agent is built with the same code used in production (gateway/main.py),
so behaviour is identical — the only difference is session/memory storage
is in-process (no Vertex AI / Firestore) unless you set credentials in .env.

Usage
─────
    cd ~/gcp-hermes-agnet
    cp .env.example .env       # fill in GOOGLE_CLOUD_PROJECT etc.
    adk web .                  # → http://localhost:8000
"""
import os
from dotenv import load_dotenv

load_dotenv()  # pick up .env for local dev

from config import get_settings
from agents.orchestrator import build_orchestrator

_settings = get_settings()
root_agent = build_orchestrator(_settings)
