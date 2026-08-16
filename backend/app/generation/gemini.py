"""
TeleRAG — Gemini Generation Client
"""
import logging
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
            logger.error(f"Gemini generation failed: {e}")
            return None
