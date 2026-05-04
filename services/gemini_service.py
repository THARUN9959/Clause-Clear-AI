"""ClauseClear AI — Public AI Service API.

This module is the single import surface for app.py and all routes.
It re-exports the constants needed by routes, and implements the five
high-level analysis functions that coordinate prompts + providers.

Internal structure:
  services/prompts.py   -- all prompt templates & constants
  services/providers.py -- Gemini / DeepSeek / OpenAI / Claude callers + dispatcher
  services/gemini_service.py (this file) -- public API used by app.py
"""

import json
import logging
import time

from config import Config
from services.benchmark_service import format_benchmark_for_prompt
from services.playbooks import PLAYBOOKS, DEFAULT_STANDARD

# ── Import everything needed from the two focused sub-modules ─────────────────
from services.prompts import (
    ENABLE_SELF_CRITIQUE,
    CONTRACT_TYPES,
    CLASSIFY_ONLY_PROMPT,
    BASE_SYSTEM_PROMPT,
    _UNIFIED_TEMPLATE,
    PROMPT_TEMPLATES,
    SELF_CRITIQUE_PROMPT_TEMPLATE,
    FEATURE_PROMPTS,
    FEATURE_LABELS,
    CHAT_PROMPT,
    _CHECKLIST_PROMPT,
)
from services.providers import (
    _call_ai,
    _build_memory_block,
    generate_embedding,
    find_similar_analysis,
)

logger = logging.getLogger(__name__)


# ─── Contract classification ──────────────────────────────────────────────────

def classify_contract(contract_text: str) -> str:
    """Quick single-call classification. Returns one of CONTRACT_TYPES."""
    prompt = CLASSIFY_ONLY_PROMPT.replace("TEXT_PLACEHOLDER", contract_text[:5000])
    result = _call_ai(prompt, temperature=0.1)
    if "error" in result:
        logger.warning("Classification failed, defaulting to UNKNOWN: %s", result["error"])
        return "UNKNOWN"
    ct = result.get("contract_type", "UNKNOWN").upper()
    return ct if ct in CONTRACT_TYPES else "UNKNOWN"


# ─── Full unified analysis ────────────────────────────────────────────────────

def unified_analyze(
    contract_text: str,
    memory_turns: list = None,
    past_embeddings: list = None,
    session_id: str = "",
    filename: str = "",
    evaluation_standard: str = DEFAULT_STANDARD,
) -> dict:
    """
    Full contract analysis pipeline:
      classify → embed → RAG context → analyze → optional self-critique.
    Returns a parsed JSON dict or {"error": "..."}.
    """
    start_time = time.time()
    if not contract_text or not contract_text.strip():
        return {"error": "No contract text provided."}
    if len(contract_text.strip()) < 100:
        return {"error": "Contract text is too short. Please provide a complete contract."}

    logger.info("Classifying contract | session=%s file=%s", session_id, filename)
    contract_type = classify_contract(contract_text)
    logger.info("Contract type: %s", contract_type)

    rag_embedding = generate_embedding(contract_text[:8000])

    historical_context = ""
    if past_embeddings and rag_embedding:
        similar = find_similar_analysis(rag_embedding, past_embeddings)
        if similar:
            historical_context = (
                f"=== HISTORICAL CONTEXT ===\n"
                f"We analyzed a similar {similar['contract_type']} contract before "
                f"(file: {similar['filename']}) which scored {similar['health_score']}/100. "
                f"Compare this contract against that precedent."
            )
            logger.info("RAG context injected from analysis_id=%s", similar.get("analysis_id"))

    benchmark_context = format_benchmark_for_prompt(contract_type)
    type_addendum = PROMPT_TEMPLATES.get(contract_type, PROMPT_TEMPLATES["UNKNOWN"])
    memory_block = _build_memory_block(memory_turns or [])
    playbook_text = PLAYBOOKS.get(evaluation_standard, PLAYBOOKS[DEFAULT_STANDARD])

    # Safe .replace() injection — never .format(), contract text may contain { } braces
    prompt = (_UNIFIED_TEMPLATE
        .replace("SYSTEM_PROMPT_PLACEHOLDER", BASE_SYSTEM_PROMPT)
        .replace("BENCHMARK_PLACEHOLDER", benchmark_context + "\n" + type_addendum)
        .replace("PLAYBOOK_PLACEHOLDER", playbook_text)
        .replace("HISTORICAL_PLACEHOLDER", historical_context)
        .replace("CONTRACT_TYPE_PLACEHOLDER", contract_type)
        .replace("MEMORY_PLACEHOLDER", memory_block)
        .replace("CONTRACT_TEXT_PLACEHOLDER", contract_text[:15000])
    )

    logger.info("Running primary analysis | session=%s", session_id)
    analysis = _call_ai(prompt, temperature=0.3)
    if "error" in analysis:
        return analysis

    if ENABLE_SELF_CRITIQUE:
        logger.info("Running self-critique | session=%s", session_id)
        critique_prompt = (SELF_CRITIQUE_PROMPT_TEMPLATE
            .replace("ORIGINAL_TEXT_PLACEHOLDER", contract_text[:8000])
            .replace("ANALYSIS_JSON_PLACEHOLDER", json.dumps(analysis, indent=2)[:6000])
        )
        critiqued = _call_ai(critique_prompt, temperature=0.2)
        if "error" not in critiqued and isinstance(critiqued, dict) and "health_score" in critiqued:
            analysis = critiqued
            logger.info("Self-critique applied.")
        else:
            logger.warning("Self-critique unusable — keeping original.")

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "Analysis done | session=%s | file=%s | type=%s | score=%s | %dms",
        session_id, filename, contract_type, analysis.get("health_score", "?"), duration_ms,
    )
    analysis["_contract_type"] = contract_type
    analysis["_embedding"] = rag_embedding
    analysis["_duration_ms"] = duration_ms
    return analysis


# ─── Feature-specific analysis ────────────────────────────────────────────────

def analyze_contract(
    feature: str,
    contract_text: str,
    memory_turns: list = None,
    extra_context: str = "",
    evaluation_standard: str = DEFAULT_STANDARD,
) -> dict:
    """Run a single feature analysis (summarize, tags, highlight, compare, etc.)."""
    if feature not in FEATURE_PROMPTS:
        return {"error": f"Unknown feature: {feature}"}
    if not contract_text or not contract_text.strip():
        return {"error": "No contract text provided."}
    if feature == "compare" and not (extra_context or "").strip():
        return {"error": "Contract Comparison requires a second (revised) contract text."}
    if feature == "multilingual" and not (extra_context or "").strip():
        return {"error": "Multilingual Translation requires a target language (e.g. 'Spanish')."}

    memory_block = _build_memory_block(memory_turns or [])
    playbook_text = PLAYBOOKS.get(evaluation_standard, PLAYBOOKS[DEFAULT_STANDARD])

    prompt = (FEATURE_PROMPTS[feature]
        .replace("MEMORY_PLACEHOLDER", memory_block)
        .replace("CONTRACT_TEXT_PLACEHOLDER", contract_text[:15000])
        .replace("EXTRA_CONTEXT_PLACEHOLDER", (extra_context or "")[:8000])
        .replace("PLAYBOOK_PLACEHOLDER", playbook_text)
    )
    return _call_ai(prompt)


# ─── Follow-up chat ───────────────────────────────────────────────────────────

def chat_followup(
    user_question: str,
    contract_text: str,
    memory_turns: list = None,
) -> dict:
    """Handle a follow-up question about the loaded contract."""
    if not user_question or not user_question.strip():
        return {"error": "No question provided."}
    memory_block = _build_memory_block(memory_turns or [])
    prompt = (CHAT_PROMPT
        .replace("MEMORY_PLACEHOLDER", memory_block)
        .replace("CONTRACT_TEXT_PLACEHOLDER", (contract_text or "No contract uploaded yet.")[:15000])
        .replace("QUESTION_PLACEHOLDER", user_question)
    )
    return _call_ai(prompt)


# ─── Checklist ────────────────────────────────────────────────────────────────

def run_checklist(contract_text: str) -> dict:
    """Run the 10-point contract compliance checklist."""
    if not contract_text or not contract_text.strip():
        return {"error": "No contract text provided."}
    prompt = _CHECKLIST_PROMPT.replace("CONTRACT_TEXT_PLACEHOLDER", contract_text[:15000])
    result = _call_ai(prompt)
    if "error" in result:
        return result
    # Normalise the checklist: compute score from 'present' booleans if not provided
    checklist = result.get("checklist", [])
    if checklist:
        passed = sum(
            1 for item in checklist
            if item.get("present") is True or item.get("status") == "present"
        )
        result["score"] = passed
    # Ensure top-level score is always an int 0-10
    if not isinstance(result.get("score"), int):
        result["score"] = 0
    return result
