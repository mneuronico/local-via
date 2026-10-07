"""Starts the lab PC agent: `python -m worker` from the repository root."""
import asyncio
import logging
from worker.app.agent import Agent
from worker.app.config import settings

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(Agent(settings).run())
    except KeyboardInterrupt:
        pass
