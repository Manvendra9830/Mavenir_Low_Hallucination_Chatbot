"""
TeleRAG — LLM Gateway
Handles failover from Gemini to Groq.
"""
import logging
from typing import Tuple

from backend.app.generation.gemini import GeminiClient
from backend.app.generation.groq import GroqClient

logger = logging.getLogger(__name__)


class LLMGateway:
    def __init__(self):
        self.gemini = GeminiClient()
        self.groq = GroqClient()
        
    def generate(self, question: str, evidence: list[dict]) -> Tuple[str, str]:
        """Generate answer using Gemini, falling back to Groq.
        
        Returns:
            Tuple[answer_text, llm_used]
        """
        # Try Primary
        logger.info("Attempting generation with Gemini...")
        answer = self.gemini.generate(question, evidence)
        if answer:
            return answer, "gemini"
            
        # Try Fallback
        logger.warning("Gemini failed. Falling back to Groq...")
        answer = self.groq.generate(question, evidence)
        if answer:
            return answer, "groq"
            
        # Both failed
        logger.error("Both Gemini and Groq failed to generate an answer.")
        return "I encountered a system error and could not generate a response. Please try again later.", "none"
