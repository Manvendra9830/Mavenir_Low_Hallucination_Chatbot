"""
TeleRAG — Gemini Generation Client
"""
import logging
import time
from typing import Optional

from google import genai
from google.genai import types

from backend.app.config import get_settings
from backend.app.generation.prompts import SYSTEM_PROMPT, build_prompt

logger = logging.getLogger(__name__)


class GeminiClient:
    def __init__(self):
        self.settings = get_settings()
        if not self.settings.gemini_api_key:
            logger.warning("GEMINI_API_KEY is missing!")
            self.client = None
        else:
            self.client = genai.Client(api_key=self.settings.gemini_api_key)
            
    def generate(self, question: str, evidence: list[dict]) -> Optional[str]:
        if not self.client:
            return None
            
        prompt = build_prompt(question, evidence)
        
        # 1 retry for transient errors; rate limits fail immediately to allow Groq failover
        for attempt in range(2):
            try:
                response = self.client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=self.settings.temperature,
                        max_output_tokens=self.settings.max_output_tokens,
                    ),
                )
                return response.text
            except Exception as e:
                error_str = str(e).lower()
                # Rate limit / quota errors → fail fast to Groq
                if "429" in str(e) or "quota" in error_str or "rate" in error_str:
                    logger.warning(f"Gemini rate limited: {e}")
                    return None
                # Transient error on first attempt → retry once after brief delay
                if attempt == 0:
                    logger.warning(f"Gemini transient error (retrying): {e}")
                    time.sleep(1)
                else:
                    logger.error(f"Gemini generation failed after retry: {e}")
                    return None
