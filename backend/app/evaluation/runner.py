"""
TeleRAG — Evaluation Runner
"""
import json
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.config import get_settings
from backend.app.models.schemas import QueryRequest
from backend.app.services.query_service import QueryService
from backend.app.storage.metadata_store import MetadataStore
from backend.app.storage.vector_store import VectorStore
from backend.app.retrieval.bm25 import BM25Store
from backend.app.evaluation.metrics import abstention_accuracy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_evaluation():
    settings = get_settings()

    # Initialize stores
    MetadataStore.initialize(settings.get_metadata_db_path())
    VectorStore.initialize(settings.get_vector_db_path(), settings.embedding_model)
    BM25Store.initialize(settings.get_bm25_index_path())

    questions_path = PROJECT_ROOT / "evaluation" / "questions.json"
    results_dir = PROJECT_ROOT / "evaluation" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    with open(questions_path) as f:
        questions = json.load(f)

    service = QueryService()
    results = []

    for q in questions:
        logger.info(f"Evaluating: {q['id']} — {q['question'][:60]}...")
        request = QueryRequest(query=q["question"], release="18")

        t0 = time.time()
        response = service.process_query(request)
        elapsed = time.time() - t0

        is_answerable = q["category"] == "answerable"
        abstained = response.grounding.abstained

        result = {
            "id": q["id"],
            "question": q["question"],
            "category": q["category"],
            "answer_preview": response.answer[:200],
            "abstained": abstained,
            "abstention_correct": abstention_accuracy(abstained, is_answerable),
            "num_citations": len(response.citations),
            "num_evidence": len(response.evidence),
            "evidence_score": response.grounding.evidence_score,
            "llm_used": response.llm_used,
            "total_ms": elapsed * 1000,
        }
        results.append(result)
        logger.info(f"  → {'ABSTAINED' if abstained else 'ANSWERED'} | "
                     f"Citations: {len(response.citations)} | "
                     f"{elapsed*1000:.0f}ms")

    # Summary
    total = len(results)
    correct_abstentions = sum(1 for r in results if r["abstention_correct"])
    avg_latency = sum(r["total_ms"] for r in results) / total if total else 0

    summary = {
        "total_questions": total,
        "abstention_accuracy": correct_abstentions / total if total else 0,
        "avg_latency_ms": avg_latency,
        "results": results,
    }

    output_path = results_dir / "eval_results.json"
    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2)

    logger.info(f"Evaluation complete. Results saved to {output_path}")
    logger.info(f"Abstention Accuracy: {summary['abstention_accuracy']:.1%}")
    logger.info(f"Average Latency: {avg_latency:.0f}ms")


if __name__ == "__main__":
    run_evaluation()
