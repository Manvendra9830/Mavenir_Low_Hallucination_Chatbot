"""
TeleRAG — Groq Generation Client (Fallback)
"""
import logging
import time
from typing import Optional

try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False

from backend.app.config import get_settings
from backend.app.generation.prompts import SYSTEM_PROMPT, build_prompt

logger = logging.getLogger(__name__)


class GroqClient:
    def __init__(self):
        self.settings = get_settings()
        if not HAS_GROQ or not self.settings.groq_api_key:
            logger.warning("Groq SDK not installed or GROQ_API_KEY is missing!")
            self.client = None
        else:
            self.client = Groq(api_key=self.settings.groq_api_key)
            
    def generate(self, question: str, evidence: list[dict]) -> Optional[str]:
        if not self.client:
            return None
            
        prompt = build_prompt(question, evidence)
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        # 1 retry for transient errors
        for attempt in range(2):
            try:
                response = self.client.chat.completions.create(
                    model=self.settings.groq_model,
                    messages=messages,
                    temperature=self.settings.temperature,
                    max_tokens=self.settings.max_output_tokens,
                )
                return response.choices[0].message.content
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"Groq transient error (retrying): {e}")
                    time.sleep(1)
                else:
                    logger.error(f"Groq generation failed after retry: {e}")
                    return None
