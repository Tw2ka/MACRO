"""Runtime credentials shared by the runner and provider."""
import os
from pathlib import Path

from dotenv import dotenv_values


def openai_api_key():
    """Read the working directory's .env, retaining environment compatibility."""
    key = dotenv_values(Path.cwd() / ".env").get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY is missing; set it in the project's .env file")
    return key
