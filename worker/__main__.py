"""Starts the lab PC agent: `python -m worker` from the repository root."""
import asyncio
import logging
from logging.handlers import RotatingFileHandler
from worker.app.agent import Agent
from worker.app.config import settings

if __name__ == "__main__":
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_error = None
    if settings.log_file:
        try:
            settings.log_file.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(RotatingFileHandler(settings.log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8"))
        except OSError as error:  # A log that cannot be written must not keep the agent from working.
            log_error = error
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)
    if log_error: logging.warning("No se puede escribir el log en %s: %s", settings.log_file, log_error)
    # httpx logs every request (a claim every 20 s, progress every 5 s); the agent logs what matters itself.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        asyncio.run(Agent(settings).run())
    except KeyboardInterrupt:
        pass
