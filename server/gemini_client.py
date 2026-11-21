"""All Gemini calls go through here: 8 concurrent, 8 s timeout, one retry.
A failed call returns None (the caller keeps the previous state); nothing raises."""
import asyncio
import logging
import time

from google import genai

from . import config as C

log = logging.getLogger("gemini")


class Gemini:
    def __init__(self):
        self.client = genai.Client(http_options={"api_version": "v1beta"})
        # Separate lanes, so slow Hydrogen asks never hold up the ring calls.
        self.sem = asyncio.Semaphore(C.API_CONCURRENCY)
        self.slow_sem = asyncio.Semaphore(C.API_CONCURRENCY)
        self.calls = []          # per-call stats since the last drain()

    async def _call(self, name, make, timeout=C.API_TIMEOUT, sem=None):
        async with (sem or self.sem):
            for attempt in range(2):
                t0 = time.time()
                try:
                    res = await asyncio.wait_for(make(), timeout)
                    usage = getattr(res, "usage", None)
                    self.calls.append({"name": name, "ms": round((time.time() - t0) * 1000),
                                       "tokens": getattr(usage, "total_tokens", 0) or 0, "ok": True})
                    return res
                except Exception as e:
                    log.warning("%s failed (attempt %d): %s: %s", name, attempt + 1, type(e).__name__, str(e)[:300])
                    self.calls.append({"name": name, "ms": round((time.time() - t0) * 1000), "tokens": 0, "ok": False})
                    if attempt == 0:
                        await asyncio.sleep(0.4)
        return None

    async def decisions(self, name, audio_b64, text, questions):
        """Decisions API on an audio clip + a features line. Returns {key: answer dict} or None."""
        res = await self._call(name, lambda: self.client.aio.decisions.create(
            model=C.MODEL_DECISIONS,
            input=[{"type": "audio", "data": audio_b64, "mime_type": "audio/wav"},
                   {"type": "text", "text": text}],
            questions=questions))
        if res is None:
            return None
        return res.model_dump().get("answers") or {}

    async def structured(self, name, model, system, prompt, schema, thinking="low", timeout=C.API_TIMEOUT):
        """Interactions API with a JSON schema; returns a validated pydantic object or None."""
        res = await self._call(name, lambda: self.client.aio.interactions.create(
            model=model, input=prompt, system_instruction=system,
            response_format={"type": "text", "mime_type": "application/json", "schema": schema.model_json_schema()},
            generation_config={"thinking_level": thinking}, store=False), timeout, self.slow_sem)
        if res is None:
            return None
        try:
            return schema.model_validate_json(res.output_text)
        except Exception as e:
            log.warning("%s returned unparseable JSON: %s", name, e)
            return None

    def drain(self):
        """Stats for the tick log: latency, tokens and failures since the last call."""
        calls, self.calls = self.calls, []
        return {"latency_ms": {c["name"]: c["ms"] for c in calls if c["ok"]},
                "tokens": sum(c["tokens"] for c in calls),
                "failures": [c["name"] for c in calls if not c["ok"]]}
