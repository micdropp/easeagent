"""EaseAgent entry point — sets the correct event loop policy on Windows
before starting uvicorn, so that paho-mqtt (used by aiomqtt) can use
add_reader / add_writer."""

import asyncio
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

no_proxy = os.environ.get("NO_PROXY", "")
for host in ("localhost", "127.0.0.1"):
    if host not in no_proxy:
        no_proxy = f"{no_proxy},{host}" if no_proxy else host
os.environ["NO_PROXY"] = no_proxy

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "core.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
