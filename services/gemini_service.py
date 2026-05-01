"""
ClauseClear AI — Unified AI Service (Gemini primary, Claude fallback).

Architecture:
  - Gemini is the PRIMARY model for all analysis calls.
  - Claude (Anthropic) is the FALLBACK — used automatically when Gemini
    hits its daily quota, a rate-limit, or any unrecoverable error.
  - Single unified analysis call returning full structured JSON
  - Contract-type-specific prompt templates
  - Benchmark injection
  - Self-critique agent loop (disabled by default to save tokens)
  - Legacy feature prompts retained for summarize/translate/compare/multilingual
"""

import json
import math
import re
import time
import logging
import anthropic
from google import genai

from config import Config
from services.benchmark_service import format_benchmark_for_prompt
from services.playbooks import PLAYBOOKS, DEFAULT_STANDARD

logger = logging.getLogger(__name__)

# ── Client factories ──────────────────────────────────────────
def _get_gemini_client():
    return genai.Client(api_key=Config.GEMINI_API_KEY)

def _get_claude_client():
    return anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

# Set to True on paid plan to enable self-critique for higher accuracy.
ENABLE_SELF_CRITIQUE = False


# ═══════════════════════════════════════════════════════════════
# CONTRACT TYPE DETECTION
# ═══════════════════════════════════════════════════════════════

CONTRACT_TYPES = ["NDA", "EMPLOYMENT", "SAAS_TOS", "FREELANCE", "RENTAL", "LOAN", "PARTNERSHIP", "UNKNOWN"]

CLASSIFY_ONLY_PROMPT = """You are a contract classifier. Read the contract text below and return ONLY a single JSON object:
{"contract_type": "<TYPE>"}
Where <TYPE> is exactly one of: NDA, EMPLOYMENT, SAAS_TOS, FREELANCE, RENTAL, LOAN, PARTNERSHIP, UNKNOWN
No other output. No markdown. No explanation.

CONTRACT TEXT:
{contract_text}
"""

# ═══════════════════════════════════════════════════════════════
# BASE SYSTEM PROMPT (shared across all unified calls)
# ═══════════════════════════════════════════════════════════════

BASE_SYSTEM_PROMPT = """You are a senior legal contract analyst at ClauseClear AI. You provide structured, actionable analysis.

ABSOLUTE RULES:
1. Return ONLY valid JSON — no markdown, no preamble, no text outside the JSON object.
2. NEVER fabricate clauses not present in the contract text.
3. NEVER provide binding legal advice.
4. If uncertain about a clause, flag it explicitly in the explanation.
5. All risk explanations MUST reference the market benchmark standards provided.
"""


# ═══════════════════════════════════════════════════════════════
# UNIFIED ANALYSIS PROMPT TEMPLATE
# ═══════════════════════════════════════════════════════════════

_UNIFIED_TEMPLATE = BASE_SYSTEM_PROMPT + """
{benchmark_context}
__PLAYBOOK_INSTRUCTION__

{historical_context}

=== TASK: FULL CONTRACT ANALYSIS ===
Analyze the contract below. Return this EXACT JSON schema (all fields required):

{{
  "contract_type": "{contract_type}",
  "health_score": <integer 0-100>,
  "health_grade": "<A|B|C|D|F>",
  "health_verdict": "<one sentence plain English verdict>",
  "risks": [
    {{
      "clause": "<clause name>",
      "severity": "<HIGH|MEDIUM|LOW>",
      "explanation": "<plain English explanation WITH explicit market benchmark comparison>",
      "standard_justification": "<cite the exact Indian statute and section that makes this HIGH_RISK — empty string for LOW/MEDIUM>",
      "suggested_redline": "<one or two sentence proposed rewrite>"
    }}
  ],
  "obligations": [
    {{
      "obligation": "<obligation description>",
      "deadline_description": "<timing or deadline>",
      "party": "<responsible party>",
      "section": "<contract section reference>"
    }}
  ],
  "summary": "<3-5 sentence plain language summary of the whole contract>",
  "key_entities": {{
    "parties": ["<party name>"],
    "effective_date": "<date or empty string>",
    "governing_law": "<jurisdiction or empty string>",
    "termination_notice": "<notice period or empty string>"
  }}
}}

Health score guide: 90-100=A (excellent), 80-89=B (good), 70-79=C (acceptable), 60-69=D (concerning), 0-59=F (dangerous).

{memory_block}

=== CONTRACT TEXT ===
{contract_text}
"""


# Contract-type-specific addenda
_NDA_ADDENDUM = """NDA FOCUS AREAS: Analyze mutual vs one-sided scope, IP assignment breadth, residuals clauses,
duration against 2-3 year market standard, jurisdiction, and definition of "Confidential Information"."""

_EMPLOYMENT_ADDENDUM = """EMPLOYMENT FOCUS AREAS: At-will provisions, non-compete duration+geography vs 6-12 month standard,
equity vesting cliff+acceleration (standard: 4yr/1yr cliff), IP ownership of side projects,
arbitration waivers, and severance terms."""

_SAAS_ADDENDUM = """SAAS_TOS FOCUS AREAS: Auto-renewal + cancellation notice windows (standard: 30-60 days),
data ownership clauses, liability caps vs 12-month fees standard, SLA definitions,
unilateral modification rights, and data retention on termination."""

_FREELANCE_ADDENDUM = """FREELANCE FOCUS AREAS: Payment terms + kill fees (standard: Net-30, 25-50% kill fee),
IP transfer timing (should transfer only on full payment), revision limits,
non-solicit clauses, and one-sided indemnification."""

_RENTAL_ADDENDUM = """RENTAL FOCUS AREAS: Security deposit vs 1-2 months standard, early termination penalties,
maintenance responsibility allocation, subletting rights, notice periods (standard: 30 days),
and rent increase mechanisms."""

_LOAN_ADDENDUM = """LOAN FOCUS AREAS: Interest rate vs market standard (6-12% APR for personal loans),
prepayment penalties, default cure periods (standard: 10-30 days), collateral scope,
and acceleration clauses."""

_PARTNERSHIP_ADDENDUM = """PARTNERSHIP FOCUS AREAS: Profit distribution fairness, deadlock resolution mechanisms,
dissolution and exit provisions, post-dissolution non-compete scope,
IP ownership assignment, and fiduciary duty language."""

_UNKNOWN_ADDENDUM = """GENERAL FOCUS: Apply balanced general legal analysis. Identify all liability, termination,
payment, IP, and dispute resolution clauses. Flag any terms that deviate from typical
commercial contract standards."""

PROMPT_TEMPLATES = {
    "NDA": _NDA_ADDENDUM, "EMPLOYMENT": _EMPLOYMENT_ADDENDUM,
    "SAAS_TOS": _SAAS_ADDENDUM, "FREELANCE": _FREELANCE_ADDENDUM,
    "RENTAL": _RENTAL_ADDENDUM, "LOAN": _LOAN_ADDENDUM,
    "PARTNERSHIP": _PARTNERSHIP_ADDENDUM, "UNKNOWN": _UNKNOWN_ADDENDUM,
}


SELF_CRITIQUE_PROMPT = """You are a senior legal QA reviewer at ClauseClear AI.

Review the original contract text and the generated analysis JSON below.
Check for:
1. Any risks that were overstated or understated
2. Any critical obligations that were missed
3. Any health_score that seems too high or too low given the risks found
4. Any suggested_redlines that are impractical
5. Any standard_justification that is vague, missing, or does not cite a specific Indian statute section.

Return the corrected, finalized JSON in the EXACT same schema as the input analysis.
If the analysis is accurate, return it unchanged. Return ONLY the JSON object, no other text.

=== ORIGINAL CONTRACT TEXT ===
{contract_text}

=== GENERATED ANALYSIS JSON TO REVIEW ===
{analysis_json}
"""

# ═══════════════════════════════════════════════════════════════
# LEGACY FEATURE PROMPTS
# ═══════════════════════════════════════════════════════════════

CLAUSE_SUMMARIZATION_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: CLAUSE-LEVEL SUMMARIZATION ===
Break the contract into individual clauses and generate a short plain-language summary for each.

Return ONLY this JSON schema:
{
  "quick_summary": "A 1-2 sentence overview of the entire contract",
  "total_clauses": <number>,
  "clauses": [
    {
      "clause_number": <number>,
      "title": "Short descriptive title",
      "original_text_snippet": "First 1-2 sentences of the original clause",
      "plain_summary": "Clear plain-language summary",
      "key_points": ["Important point 1", "Important point 2"]
    }
  ],
  "recommendations": ["Actionable recommendation 1"]
}

{memory_block}

=== CONTRACT TEXT ===
{contract_text}
"""

PLAIN_LANGUAGE_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: PLAIN LANGUAGE TRANSLATION ===
Rewrite the entire contract in simple everyday English, section by section.

Return ONLY this JSON schema:
{
  "quick_summary": "One-liner summary in plain English",
  "overall_complexity": "HIGH or MEDIUM or LOW",
  "sections": [
    {
      "section_number": <number>,
      "original_heading": "Original heading",
      "original_text_snippet": "First 1-2 sentences",
      "plain_language": "Full plain-English rewrite",
      "complexity_rating": "HIGH or MEDIUM or LOW",
      "why_it_matters": "Why this section is important"
    }
  ],
  "jargon_glossary": [{"term": "Legal term", "plain_meaning": "Plain meaning"}],
  "recommendations": ["Recommendation 1"]
}

{memory_block}

=== CONTRACT TEXT ===
{contract_text}
"""


CLAUSE_TAGGING_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: STRUCTURED CLAUSE TAGGING ===
Tag every clause with a category from: Payment, Termination, Liability, Confidentiality,
Governing Law, Dispute Resolution, Warranties, Non-Compete, Data Privacy, IP Rights,
Force Majeure, Indemnification, Representations, Amendments, Assignment, Notices,
Severability, Entire Agreement, Other.

Return ONLY this JSON schema:
{
  "quick_summary": "One-liner overview of the contract structure",
  "total_clauses": <number>,
  "category_frequency": {"Payment": <n>, "Termination": <n>},
  "tagged_clauses": [
    {
      "clause_number": <number>,
      "text_snippet": "First 1-2 sentences",
      "primary_category": "Main category",
      "secondary_tags": ["Tag 1"],
      "confidence": "HIGH or MEDIUM or LOW",
      "brief_note": "One-sentence note"
    }
  ],
  "missing_categories": ["Categories not found but commonly expected"],
  "recommendations": ["Recommendation 1"]
}

{memory_block}

=== CONTRACT TEXT ===
{contract_text}
"""

ENTITY_EXTRACTION_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: KEY ENTITY EXTRACTION ===
Extract all critical metadata and named entities from the contract.

Return ONLY this JSON schema:
{
  "quick_summary": "One-liner describing contract type and parties",
  "parties": [{"role": "Buyer/Seller/etc", "name": "Legal name", "key_obligations": ["Obligation 1"]}],
  "important_dates": [{"label": "Effective Date", "value": "Date", "note": "Significance"}],
  "payment_terms": {"amount": "Amount or N/A", "currency": "USD or N/A", "schedule": "Monthly/etc", "late_penalty": "Penalty or N/A"},
  "governing_law": {"jurisdiction": "State/Country", "court_or_arbitration": "Forum", "risk_note": "Note"},
  "notice_period": "30 days or N/A",
  "defined_terms": [{"term": "Term", "definition": "Definition"}],
  "missing_entities": ["Fields not found"],
  "recommendations": ["Recommendation 1"]
}

{memory_block}

=== CONTRACT TEXT ===
{contract_text}
"""

CONTRACT_COMPARE_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: CONTRACT COMPARISON & SEMANTIC REDLINING ===
Compare Version A (original) and Version B (revised). Identify every meaningful change and its legal impact.

Return ONLY this JSON schema:
{
  "quick_summary": "One-liner on how the revision changed the overall balance",
  "overall_verdict": "FAVORABLE_TO_A or FAVORABLE_TO_B or NEUTRAL or MIXED",
  "total_changes": <number>,
  "changes": [
    {
      "change_number": <number>,
      "clause_or_section": "Which clause changed",
      "original_text_snippet": "Brief quote from Version A",
      "revised_text_snippet": "Brief quote from Version B",
      "change_type": "ADDITION or DELETION or MODIFICATION or REORDERING",
      "impact_severity": "HIGH or MEDIUM or LOW",
      "plain_explanation": "What changed and why it matters",
      "who_benefits": "Party A, Party B, or Both/Neutral",
      "negotiation_note": "Counter-position or acceptance rationale"
    }
  ],
  "unchanged_key_clauses": ["Important unchanged clauses"],
  "executive_recommendation": "Overall recommendation",
  "recommendations": ["Specific recommendation 1"]
}

{memory_block}

=== CONTRACT TEXT — VERSION A (ORIGINAL) ===
{contract_text}

=== CONTRACT TEXT — VERSION B (REVISED) ===
{extra_context}
"""


MULTILINGUAL_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: MULTILINGUAL PLAIN-LANGUAGE TRANSLATION ===
Translate the contract into the TARGET LANGUAGE below in plain everyday language.

=== TARGET LANGUAGE ===
{extra_context}

Return ONLY this JSON schema:
{
  "target_language": "{extra_context}",
  "quick_summary": "One-sentence overview in the target language",
  "sections": [
    {
      "section_number": <number>,
      "original_heading": "Original heading",
      "translated_heading": "Heading in target language",
      "translated_text": "Full plain-language translation",
      "key_obligation": "Most important obligation from this section"
    }
  ],
  "critical_terms_glossary": [
    {"original_term": "Legal term", "translated_term": "Term in target language", "plain_explanation": "Meaning"}
  ],
  "translation_notes": ["Notes about terms without direct equivalents"],
  "recommendations": ["Recommendation 1"]
}

{memory_block}

=== CONTRACT TEXT ===
{contract_text}
"""

CHAT_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: FOLLOW-UP CONVERSATION ===
Answer the user's question about the contract using contract text and conversation history.

Return ONLY this JSON schema:
{
  "answer": "Detailed plain-English answer",
  "relevant_clauses": ["Brief clause reference"],
  "confidence": "HIGH or MEDIUM or LOW",
  "follow_up_suggestions": ["Suggested follow-up 1", "Suggested follow-up 2"]
}

=== CONVERSATION MEMORY (last {turn_count} turns) ===
{memory_block}

=== CONTRACT TEXT ===
{contract_text}

=== USER QUESTION ===
{user_question}
"""

HIGHLIGHT_PROMPT = """__PLAYBOOK_INSTRUCTION__
You are a senior legal risk analyst. Read the contract and classify every distinct clause or sentence into exactly ONE of these 4 tiers:

- HIGH_RISK  : Severely one-sided, potentially illegal, or creates major liability
- RISK       : Moderately unfavorable or worth negotiating
- NEUTRAL    : Standard boilerplate with no significant advantage to either party
- POSITIVE   : Explicitly protects or benefits the reader

Return ONLY valid JSON:
{
  "quick_summary": "<one sentence overall risk assessment>",
  "highlighted_clauses": [
    {
      "text": "<exact clause or sentence from contract>",
      "classification": "HIGH_RISK|RISK|NEUTRAL|POSITIVE",
      "reason": "<one sentence explaining why>",
      "standard_justification": "<cite exact Indian statute/section if HIGH_RISK>",
      "negotiation_tip": "<one sentence actionable tip — only for HIGH_RISK and RISK, empty string otherwise>"
    }
  ],
  "high_risk_count": <int>,
  "risk_count": <int>,
  "neutral_count": <int>,
  "positive_count": <int>
}

{memory_block}

CONTRACT:
{contract_text}
"""

FEATURE_PROMPTS = {
    "summarize": CLAUSE_SUMMARIZATION_PROMPT,
    "translate": PLAIN_LANGUAGE_PROMPT,
    "tags": CLAUSE_TAGGING_PROMPT,
    "entities": ENTITY_EXTRACTION_PROMPT,
    "compare": CONTRACT_COMPARE_PROMPT,
    "multilingual": MULTILINGUAL_PROMPT,
    "highlight": HIGHLIGHT_PROMPT,
}

FEATURE_LABELS = {
    "unified": "Full Contract Analysis",
    "summarize": "Clause Summarization",
    "translate": "Plain Language",
    "summary_plain": "Summary & Plain Language",
    "risks": "Risk Highlight",
    "tags": "Tag Clauses",
    "highlight": "HIGH_RISK Clause Highlighter",
    "entities": "Extract Entities",
    "compare": "Compare Contracts",
    "multilingual": "Translate Language",
    "checklist": "Contract Checklist",
}


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _build_memory_block(memory_turns):
    if not memory_turns:
        return ""
    lines = ["=== CONVERSATION MEMORY ==="]
    for i, turn in enumerate(memory_turns, 1):
        label = "USER" if turn["role"] == "user" else "ASSISTANT"
        lines.append(f"Turn {i} [{label}]: {turn['content'][:500]}")
    return "\n".join(lines)


def _call_gemini(prompt_text: str, temperature: float = 0.3) -> dict:
    """Call Gemini API (PRIMARY). Returns parsed JSON dict or error dict."""
    if not Config.GEMINI_API_KEY:
        return {"error": "NO_GEMINI_KEY"}

    client = _get_gemini_client()

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=Config.GEMINI_MODEL,
                contents=prompt_text,
                config=genai.types.GenerateContentConfig(
                    temperature=temperature,
                    max_output_tokens=8192,
                ),
            )
            raw = response.text.strip()
            if raw.startswith("```"):
                first_nl = raw.index("\n")
                last_fence = raw.rfind("```")
                raw = raw[first_nl + 1:last_fence].strip()
            return json.loads(raw)

        except json.JSONDecodeError:
            logger.error("Gemini returned invalid JSON (attempt %d/%d)", attempt + 1, MAX_RETRIES)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            return {"error": "GEMINI_BAD_JSON"}

        except Exception as exc:
            err = str(exc)
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                retry_delay = RETRY_DELAY_SECONDS * (2 ** attempt)
                try:
                    match = re.search(r"retryDelay.*?(\d+)s", err)
                    if match:
                        retry_delay = min(int(match.group(1)), 60)
                except Exception:
                    pass
                if attempt < MAX_RETRIES - 1:
                    logger.warning("Gemini quota/rate-limit (attempt %d/%d). Retrying in %ds...", attempt + 1, MAX_RETRIES, retry_delay)
                    time.sleep(retry_delay)
                    continue
                logger.warning("Gemini quota exhausted after %d retries — triggering Claude fallback.", MAX_RETRIES)
                return {"error": "GEMINI_QUOTA_EXCEEDED"}
            if "503" in err or "UNAVAILABLE" in err:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                    continue
                return {"error": "GEMINI_UNAVAILABLE"}
            logger.error("Gemini API error: %s", err, exc_info=True)
            return {"error": f"GEMINI_ERROR: {err}"}

    return {"error": "GEMINI_MAX_RETRIES"}


def _call_claude(prompt_text: str, temperature: float = 0.3) -> dict:
    """Call Claude API (FALLBACK). Returns parsed JSON dict or error dict."""
    if not Config.ANTHROPIC_API_KEY:
        return {"error": "Anthropic API key is not configured. Please add ANTHROPIC_API_KEY to your .env file."}

    client = _get_claude_client()

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=Config.CLAUDE_MODEL,
                max_tokens=8192,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt_text}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                first_nl = raw.index("\n")
                last_fence = raw.rfind("```")
                raw = raw[first_nl + 1:last_fence].strip()
            return json.loads(raw)

        except json.JSONDecodeError:
            logger.error("Claude returned invalid JSON (attempt %d/%d)", attempt + 1, MAX_RETRIES)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            return {"error": "The AI returned an unexpected format. Please try again."}

        except anthropic.RateLimitError:
            retry_delay = RETRY_DELAY_SECONDS * (2 ** attempt)
            if attempt < MAX_RETRIES - 1:
                logger.warning("Claude rate limit (attempt %d/%d). Waiting %ds...", attempt + 1, MAX_RETRIES, retry_delay)
                time.sleep(retry_delay)
                continue
            return {"error": "Rate limit exceeded on both AI providers. Please wait a moment and try again."}

        except anthropic.AuthenticationError:
            logger.error("Claude authentication failed — check ANTHROPIC_API_KEY in .env")
            return {"error": "Invalid Anthropic API key. Please check your .env file."}

        except anthropic.APIStatusError as exc:
            logger.error("Claude API status error: %s", str(exc), exc_info=True)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                continue
            return {"error": "Both AI services are temporarily unavailable. Please try again shortly."}

        except Exception as exc:
            logger.error("Unexpected Claude API error: %s", str(exc), exc_info=True)
            return {"error": "An unexpected error occurred. Please try again."}

    return {"error": "Failed after maximum retries on fallback provider."}


# Sentinel prefixes that signal a Gemini failure worth falling back from
_GEMINI_FALLBACK_SIGNALS = (
    "GEMINI_QUOTA_EXCEEDED", "GEMINI_UNAVAILABLE",
    "GEMINI_MAX_RETRIES", "GEMINI_BAD_JSON",
    "GEMINI_ERROR", "NO_GEMINI_KEY",
)


def _call_ai(prompt_text: str, temperature: float = 0.3) -> dict:
    """
    Primary dispatcher: tries Gemini first.
    Falls back to Claude automatically on quota exhaustion or any Gemini failure.
    """
    result = _call_gemini(prompt_text, temperature)

    if "error" in result and any(result["error"].startswith(s) for s in _GEMINI_FALLBACK_SIGNALS):
        gemini_err = result["error"]
        logger.warning("Gemini failed (%s) — switching to Claude fallback.", gemini_err)
        result = _call_claude(prompt_text, temperature)
        if "error" not in result:
            logger.info("Claude fallback succeeded.")
        else:
            logger.error("Claude fallback also failed: %s", result["error"])

    return result


# ═══════════════════════════════════════════════════════════════
# EMBEDDING & RAG (lightweight keyword similarity — no extra API)
# ═══════════════════════════════════════════════════════════════

def generate_embedding(text: str) -> list:
    """
    Generate a simple TF-IDF-style keyword vector for RAG similarity.
    No external embedding API required.
    """
    try:
        words = re.findall(r'\b[a-z]{3,}\b', text.lower()[:8000])
        freq = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        total = sum(freq.values()) or 1
        # Return a stable sorted list of (word, normalized_freq) pairs as a flat float list
        top_words = sorted(freq.items(), key=lambda x: -x[1])[:300]
        vec = [v / total for _, v in top_words]
        # Pad or truncate to fixed length 300
        vec = vec[:300] + [0.0] * (300 - len(vec))
        return vec
    except Exception as exc:
        logger.error("Embedding generation failed: %s", exc)
        return []


def cosine_similarity(a: list, b: list) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def find_similar_analysis(new_embedding: list, past_embeddings: list) -> dict:
    """Find the most similar past analysis using cosine similarity."""
    if not new_embedding or not past_embeddings:
        return None
    best_score = 0.0
    best_match = None
    for entry in past_embeddings:
        score = cosine_similarity(new_embedding, entry.get("embedding", []))
        if score > best_score:
            best_score = score
            best_match = entry
    if best_match and best_score > 0.75:
        return best_match
    return None


# ═══════════════════════════════════════════════════════════════
# UNIFIED ANALYSIS
# ═══════════════════════════════════════════════════════════════

def classify_contract(contract_text: str) -> str:
    """Quick single-call classification. Returns contract type string."""
    prompt = CLASSIFY_ONLY_PROMPT.replace("{contract_text}", contract_text[:5000])
    result = _call_ai(prompt, temperature=0.1)
    if "error" in result:
        logger.warning("Classification failed, defaulting to UNKNOWN: %s", result["error"])
        return "UNKNOWN"
    ct = result.get("contract_type", "UNKNOWN").upper()
    return ct if ct in CONTRACT_TYPES else "UNKNOWN"


def unified_analyze(
    contract_text: str,
    memory_turns: list = None,
    past_embeddings: list = None,
    session_id: str = "",
    filename: str = "",
    evaluation_standard: str = DEFAULT_STANDARD,
) -> dict:
    """
    Single unified Claude call: classify + analyze + obligations + health score.
    Implements self-critique loop and historical RAG context injection.
    Returns the full analysis JSON dict.
    """
    start_time = time.time()

    if not contract_text or not contract_text.strip():
        return {"error": "No contract text provided."}

    # Step 1: Classify contract type
    logger.info("Classifying contract for session=%s file=%s", session_id, filename)
    contract_type = classify_contract(contract_text)
    logger.info("Contract classified as: %s", contract_type)

    # Step 2: Generate embedding for RAG
    logger.info("Generating embedding for session=%s", session_id)
    rag_embedding = generate_embedding(contract_text[:8000])

    # Step 3: Build RAG historical context
    historical_context = ""
    if past_embeddings and rag_embedding:
        similar = find_similar_analysis(rag_embedding, past_embeddings)
        if similar:
            historical_context = (
                f"=== HISTORICAL CONTEXT ===\n"
                f"We analyzed a similar {similar['contract_type']} contract before "
                f"(file: {similar['filename']}) which received a health score of {similar['health_score']}/100. "
                f"Compare this contract against that precedent."
            )
            logger.info("RAG context injected from analysis_id=%s", similar.get("analysis_id"))

    # Step 4: Build the full analysis prompt
    benchmark_context = format_benchmark_for_prompt(contract_type)
    type_addendum = PROMPT_TEMPLATES.get(contract_type, PROMPT_TEMPLATES["UNKNOWN"])
    memory_block = _build_memory_block(memory_turns or [])

    prompt = _UNIFIED_TEMPLATE.format(
        benchmark_context=benchmark_context + "\n" + type_addendum,
        historical_context=historical_context,
        contract_type=contract_type,
        memory_block=memory_block,
        contract_text=contract_text[:15000],
    )

    playbook_text = PLAYBOOKS.get(evaluation_standard, PLAYBOOKS[DEFAULT_STANDARD])
    prompt = prompt.replace("__PLAYBOOK_INSTRUCTION__", playbook_text)

    # Step 5: Primary analysis call
    logger.info("Running primary analysis call for session=%s", session_id)
    analysis = _call_ai(prompt, temperature=0.3)

    if "error" in analysis:
        return analysis

    # Step 6: Optional self-critique loop
    if ENABLE_SELF_CRITIQUE:
        logger.info("Running self-critique call for session=%s", session_id)
        critique_prompt = SELF_CRITIQUE_PROMPT.format(
            contract_text=contract_text[:8000],
            analysis_json=json.dumps(analysis, indent=2)[:6000],
        )
        critiqued = _call_ai(critique_prompt, temperature=0.2)
        if "error" not in critiqued and isinstance(critiqued, dict) and "health_score" in critiqued:
            analysis = critiqued
            logger.info("Self-critique applied successfully")
        else:
            logger.warning("Self-critique returned unusable result, keeping original analysis")
    else:
        logger.info("Self-critique skipped (ENABLE_SELF_CRITIQUE=False)")

    duration_ms = int((time.time() - start_time) * 1000)
    logger.info(
        "Analysis complete | session=%s | file=%s | type=%s | score=%s | duration=%dms",
        session_id, filename, contract_type,
        analysis.get("health_score", "?"), duration_ms,
    )

    analysis["_contract_type"] = contract_type
    analysis["_embedding"] = rag_embedding
    analysis["_duration_ms"] = duration_ms

    return analysis


# ═══════════════════════════════════════════════════════════════
# LEGACY FEATURE ANALYZE
# ═══════════════════════════════════════════════════════════════

def analyze_contract(feature, contract_text, memory_turns=None, extra_context="", evaluation_standard=DEFAULT_STANDARD):
    """Run a legacy feature-specific analysis."""
    if feature not in FEATURE_PROMPTS:
        return {"error": f"Unknown feature: {feature}"}
    if not contract_text or not contract_text.strip():
        return {"error": "No contract text provided."}
    if feature == "compare" and not (extra_context or "").strip():
        return {"error": "Contract Comparison requires a second (revised) contract text."}
    if feature == "multilingual" and not (extra_context or "").strip():
        return {"error": "Multilingual Translation requires a target language (e.g. 'Spanish')."}

    template = FEATURE_PROMPTS[feature]
    memory_block = _build_memory_block(memory_turns or [])
    prompt = (template
              .replace("{memory_block}", memory_block)
              .replace("{contract_text}", contract_text[:15000])
              .replace("{extra_context}", (extra_context or "")[:8000]))
    prompt = prompt.replace("__PLAYBOOK_INSTRUCTION__", PLAYBOOKS.get(evaluation_standard, PLAYBOOKS[DEFAULT_STANDARD]))
    return _call_ai(prompt)


def chat_followup(user_question, contract_text, memory_turns=None):
    """Handle a follow-up chat question."""
    if not user_question or not user_question.strip():
        return {"error": "No question provided."}
    turns = memory_turns or []
    memory_block = _build_memory_block(turns)
    prompt = (CHAT_PROMPT
              .replace("{turn_count}", str(len(turns)))
              .replace("{memory_block}", memory_block)
              .replace("{contract_text}", (contract_text or "No contract uploaded yet.")[:15000])
              .replace("{user_question}", user_question))
    return _call_ai(prompt)


# ═══════════════════════════════════════════════════════════════
# CONTRACT CHECKLIST
# ═══════════════════════════════════════════════════════════════

_CHECKLIST_PROMPT = """You are a contract compliance expert. Analyze the contract text below and check for the presence of 10 essential legal clauses.

Return ONLY a valid JSON object — no markdown, no text outside JSON:
{
  "score": <integer 0-10>,
  "overall_summary": "<one sentence overall assessment>",
  "checklist": [
    {
      "name": "Governing Law / Jurisdiction",
      "present": <true|false>,
      "status": "<present|missing|partial>",
      "importance": "HIGH",
      "detail": "<what you found or what is missing>",
      "recommendation": "<actionable fix if missing, else empty string>"
    }
  ]
}

Check EXACTLY these 10 items in this order:
1. Governing Law / Jurisdiction
2. Termination Clause
3. Confidentiality / NDA
4. Limitation of Liability
5. Indemnification
6. Dispute Resolution / Arbitration
7. Payment Terms
8. Intellectual Property Rights
9. Force Majeure
10. Non-Compete / Non-Solicitation

CONTRACT TEXT:
{contract_text}
"""


def run_checklist(contract_text: str) -> dict:
    """Run a 10-point contract compliance checklist."""
    if not contract_text or not contract_text.strip():
        return {"error": "No contract text provided."}
    prompt = _CHECKLIST_PROMPT.replace("{contract_text}", contract_text[:15000])
    result = _call_ai(prompt)
    if "error" in result:
        return result
    if "checklist" in result:
        passed = sum(1 for i in result["checklist"] if i.get("present") is True or i.get("status") == "present")
        result["score"] = passed
        result.setdefault("items", result["checklist"])
    return result
