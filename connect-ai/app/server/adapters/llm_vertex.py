"""Gemini on Vertex AI through google-genai."""

from __future__ import annotations

import json
import re

from app.core.prompts import (
    INTRO_SETTINGS,
    PARSE_SETTINGS,
    SIM_SETTINGS,
    TRANSLATE_SETTINGS,
    IntroInput,
    ParseInput,
    SimReplyInput,
    intro_system,
    intro_user,
    parse_system,
    parse_user,
    sim_reply_prompt,
    translate_system,
)

TIMEOUT_MS = 30_000


class VertexLlm:
    def __init__(self, project: str, location: str, model: str, client=None) -> None:
        self.model = model
        if client is None:
            from google import genai
            from google.genai import types

            client = genai.Client(
                vertexai=True, project=project, location=location, http_options=types.HttpOptions(timeout=TIMEOUT_MS)
            )
        self.client = client

    def _generate(self, system: str | None, user: str, settings: dict, *, as_json: bool) -> str:
        from google.genai import types

        cfg = types.GenerateContentConfig(
            system_instruction=system,
            temperature=settings["temperature"],
            max_output_tokens=settings["max_output_tokens"],
            response_mime_type="application/json" if as_json else "text/plain",
            # DECISION: thinking budget 0. These are short extraction/writing tasks; thinking only adds latency and cost.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        resp = self.client.models.generate_content(model=self.model, contents=user, config=cfg)
        return resp.text or ""

    @staticmethod
    def _json(text: str) -> object:
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)  # tolerate a fenced block
        return json.loads(text)

    def write_intro(self, inp: IntroInput) -> object:
        return self._json(self._generate(intro_system(inp), intro_user(inp), INTRO_SETTINGS, as_json=True))

    def parse_reply(self, inp: ParseInput) -> object:
        return self._json(self._generate(parse_system(inp), parse_user(inp), PARSE_SETTINGS, as_json=True))

    def write_sim_reply(self, inp: SimReplyInput) -> str:
        return self._generate(None, sim_reply_prompt(inp), SIM_SETTINGS, as_json=False).strip()

    def translate(self, text: str, target: str) -> str:
        return self._generate(translate_system(target), text, TRANSLATE_SETTINGS, as_json=False).strip()
