"""
hermes_app/agent.py — ADK Web UI entry point

Exposes `root_agent` for:
    adk web .            # browser UI at http://localhost:8000
    adk run hermes_app   # interactive CLI
    adk api_server .     # headless REST

Run from project root:
    cd ~/gcp-hermes-agnet
    adk web . --session_service_uri=sqlite:///local_sessions.db --reload_agents
"""
import sys
import os

# Make sure project root is on the path so all imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from config import get_settings
from agents.orchestrator import build_orchestrator

_settings = get_settings()
root_agent = build_orchestrator(_settings)
