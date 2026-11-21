"""Phase 0 API check: print raw responses for one Decisions call with audio and
one Hydrogen structured call with audio. Usage: python -m server.api_check clip.wav"""
import asyncio, base64, os, sys, time

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel

load_dotenv()


class Heard(BaseModel):
    section: str
    rising: bool


async def main(path):
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    client = genai.Client(http_options={"api_version": "v1beta"})
    audio = {"type": "audio", "data": b64, "mime_type": "audio/wav"}

    t0 = time.time()
    res = await client.aio.decisions.create(
        model=os.environ["MODEL_DECISIONS"],
        input=[audio, {"type": "text", "text": "t=1:00 energy=0.5"}],
        questions={
            "house_section": {"type": "choice", "instructions": "Which part of a dance track is this?",
                              "criteria": {"build": "tension rising", "drop": "full energy, kick and bass",
                                           "breakdown": "no kick, sparse", "groove": "steady beat"}},
            "house_rising": {"type": "noul", "instructions": "Is the energy building right now?"},
            "a1_push": {"type": "score", "instructions": "How hard would a keen fan push forward?",
                        "criteria": ["gently", "firmly", "hard"]},
        },
    )
    print("DECISIONS %.2fs" % (time.time() - t0))
    print(res.model_dump_json(indent=1) if hasattr(res, "model_dump_json") else res)

    t0 = time.time()
    it = await client.aio.interactions.create(
        model=os.environ["MODEL_HYDROGEN"],
        input=[audio, {"type": "text", "text": "What section of a dance track is this, and is it rising?"}],
        response_format={"type": "text", "mime_type": "application/json", "schema": Heard.model_json_schema()},
        generation_config={"thinking_level": "low"},
        store=False,
    )
    print("HYDROGEN %.2fs" % (time.time() - t0))
    print(it.output_text)
    print(getattr(it, "usage", None))


asyncio.run(main(sys.argv[1]))
