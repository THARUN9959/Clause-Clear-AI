"""
ClauseClear AI — Gemini Service with Context Engineering.

Every Gemini API call follows these context engineering principles:
1. System Prompt: Role definition + behavioral guidelines + capability boundaries
2. Structured I/O: JSON input schema → JSON output schema (no markdown, no preamble)
3. Session Memory: Last 10 conversation turns injected as CONVERSATION MEMORY
4. RAG-style Context: Contract text injected as GROUNDING CONTEXT
5. Instruction Hierarchy: Safety > User constraints > Output format > Enhancement
6. Progressive Disclosure: Summary → Detailed analysis → Recommendations
"""

import json
import time
from google import genai
from config import Config

# Initialize the Gemini client
client = genai.Client(api_key=Config.GEMINI_API_KEY)

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

# ═══════════════════════════════════════════════════════════════
# BASE SYSTEM PROMPT — shared across all features
# ═══════════════════════════════════════════════════════════════

BASE_SYSTEM_PROMPT = """You are a senior legal contract analyst with expertise in corporate law, contract drafting, and regulatory compliance. You work for ClauseClear AI, a contract simplification platform.

=== INSTRUCTION HIERARCHY (strict priority order) ===
PRIORITY 1 — SAFETY:
- NEVER fabricate clauses, legal terms, or provisions not present in the provided text.
- NEVER provide binding legal advice. Always clarify your output is for informational purposes.
- If uncertain about a clause's meaning, explicitly flag it as "UNCERTAIN" with an explanation.
- If the text doesn't appear to be a legal contract, say so clearly.

PRIORITY 2 — USER CONSTRAINTS:
- ONLY analyze the text provided in GROUNDING CONTEXT below.
- Do NOT invent or assume clauses that are not present.
- If the contract is incomplete, note which sections appear missing.

PRIORITY 3 — OUTPUT FORMAT:
- ALWAYS return valid JSON only. No markdown, no preamble, no explanation outside JSON.
- Follow the exact JSON schema specified in the task instructions below.
- Ensure all JSON strings are properly escaped.

PRIORITY 4 — ENHANCEMENT:
- Add actionable recommendations where possible.
- Highlight areas that would benefit from professional legal review.
- Suggest improvements to protect the user's interests.

=== BEHAVIORAL GUIDELINES ===
- Use plain, everyday English — avoid legal jargon unless quoting the original text.
- Be thorough but concise — every sentence should add value.
- When quoting original clause text, keep quotes brief (max 2 sentences).
- Always maintain a professional, neutral, analytical tone.
"""

# ═══════════════════════════════════════════════════════════════
# FEATURE 1: Clause-Level Summarization
# ═══════════════════════════════════════════════════════════════

CLAUSE_SUMMARIZATION_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: CLAUSE-LEVEL SUMMARIZATION ===
Break the contract into individual clauses and generate a short plain-language summary for each.

=== REQUIRED JSON OUTPUT SCHEMA ===
{
  "quick_summary": "A 1-2 sentence overview of the entire contract",
  "total_clauses": <number>,
  "clauses": [
    {
      "clause_number": <number>,
      "title": "Short descriptive title for this clause",
      "original_text_snippet": "First 1-2 sentences of the original clause text",
      "plain_summary": "Clear plain-language summary of what this clause means",
      "key_points": ["Important point 1", "Important point 2"]
    }
  ],
  "recommendations": ["Actionable recommendation 1", "Actionable recommendation 2"]
}

Return ONLY the JSON object above. No other text.

{memory_block}

=== GROUNDING CONTEXT (CONTRACT TEXT) ===
{contract_text}
"""

# ═══════════════════════════════════════════════════════════════
# FEATURE 2: Plain Language Translation
# ═══════════════════════════════════════════════════════════════

PLAIN_LANGUAGE_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: PLAIN LANGUAGE TRANSLATION ===
Rewrite the entire contract in simple everyday English that a non-lawyer can understand, section by section.

=== REQUIRED JSON OUTPUT SCHEMA ===
{
  "quick_summary": "One-liner summary of the entire contract in plain English",
  "overall_complexity": "HIGH or MEDIUM or LOW",
  "sections": [
    {
      "section_number": <number>,
      "original_heading": "Original section heading or inferred heading",
      "original_text_snippet": "First 1-2 sentences of original text",
      "plain_language": "Full plain-English rewrite of this section",
      "complexity_rating": "HIGH or MEDIUM or LOW",
      "why_it_matters": "Brief explanation of why this section is important to the user"
    }
  ],
  "jargon_glossary": [
    {
      "term": "Legal term found in the contract",
      "plain_meaning": "What this term means in everyday English"
    }
  ],
  "recommendations": ["Actionable recommendation 1", "Actionable recommendation 2"]
}

Return ONLY the JSON object above. No other text.

{memory_block}

=== GROUNDING CONTEXT (CONTRACT TEXT) ===
{contract_text}
"""

# ═══════════════════════════════════════════════════════════════
# FEATURE 3: Risk Highlight Generation
# ═══════════════════════════════════════════════════════════════

RISK_HIGHLIGHT_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: RISK HIGHLIGHT GENERATION ===
Detect risky or potentially unfair clauses in the contract. Look specifically for:
- Auto-renewal clauses
- Liability caps or limitations
- Indemnification traps
- IP assignment or transfer
- Penalty clauses
- Data rights or privacy concerns
- Non-compete restrictions
- Unilateral termination rights
- Broad force majeure clauses
- Governing law in unfavorable jurisdictions

Rate each risk as HIGH / MEDIUM / LOW and provide negotiation recommendations.

=== REQUIRED JSON OUTPUT SCHEMA ===
{
  "quick_summary": "One-liner overview of the contract's risk profile",
  "overall_risk_level": "HIGH or MEDIUM or LOW",
  "total_risks": <number>,
  "risk_breakdown": {"HIGH": <n>, "MEDIUM": <n>, "LOW": <n>},
  "risks": [
    {
      "risk_number": <number>,
      "clause_text_snippet": "Brief quote of the risky clause",
      "risk_type": "e.g. Auto-Renewal, Liability Cap, IP Assignment",
      "severity": "HIGH or MEDIUM or LOW",
      "explanation": "Plain-English explanation of why this is risky",
      "potential_impact": "What could happen if this clause is enforced",
      "negotiation_tip": "Specific suggestion for how to negotiate or modify this clause"
    }
  ],
  "safe_clauses_note": "Brief note about clauses that appear standard and fair",
  "recommendations": ["Overall recommendation 1", "Overall recommendation 2"]
}

Return ONLY the JSON object above. No other text.

{memory_block}

=== GROUNDING CONTEXT (CONTRACT TEXT) ===
{contract_text}
"""

# ═══════════════════════════════════════════════════════════════
# FEATURE 4: Structured Clause Tagging
# ═══════════════════════════════════════════════════════════════

CLAUSE_TAGGING_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: STRUCTURED CLAUSE TAGGING ===
Tag every clause in the contract with a category label from this taxonomy:
Payment, Termination, Liability, Confidentiality, Governing Law, Dispute Resolution,
Warranties, Non-Compete, Data Privacy, IP Rights, Force Majeure, Indemnification,
Representations, Amendments, Assignment, Notices, Severability, Entire Agreement, Other.

=== REQUIRED JSON OUTPUT SCHEMA ===
{
  "quick_summary": "One-liner overview of the contract's structure and composition",
  "total_clauses": <number>,
  "category_frequency": {
    "Payment": <n>,
    "Termination": <n>,
    "Liability": <n>,
    ...
  },
  "tagged_clauses": [
    {
      "clause_number": <number>,
      "text_snippet": "First 1-2 sentences of the clause",
      "primary_category": "Main category from the taxonomy above",
      "secondary_tags": ["Additional relevant tag 1", "Additional relevant tag 2"],
      "confidence": "HIGH or MEDIUM or LOW",
      "brief_note": "One-sentence note about what this clause does"
    }
  ],
  "missing_categories": ["Categories NOT found in this contract that are commonly expected"],
  "recommendations": ["Recommendation 1", "Recommendation 2"]
}

Return ONLY the JSON object above. No other text.

{memory_block}

=== GROUNDING CONTEXT (CONTRACT TEXT) ===
{contract_text}
"""

# ═══════════════════════════════════════════════════════════════
# FEATURE 5: Key Entity Extraction (NER)
# ═══════════════════════════════════════════════════════════════

ENTITY_EXTRACTION_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: KEY ENTITY EXTRACTION ===
Extract all critical metadata and named entities from the contract into a structured table.
Focus on: party names, effective/expiration dates, payment terms, governing law/jurisdiction,
key obligations for each party, notice periods, and any defined monetary amounts.

=== REQUIRED JSON OUTPUT SCHEMA ===
{
  "quick_summary": "One-liner describing what kind of contract this is and who the parties are",
  "parties": [
    {
      "role": "e.g. Buyer, Seller, Licensor, Licensee, Employer, Employee",
      "name": "Legal name as written in the contract",
      "key_obligations": ["Main obligation 1", "Main obligation 2"]
    }
  ],
  "important_dates": [
    {
      "label": "e.g. Effective Date, Expiration Date, Renewal Deadline",
      "value": "Date or period as written in the contract",
      "note": "Brief plain-English note about the significance of this date"
    }
  ],
  "payment_terms": {
    "amount": "Total amount or rate, or N/A",
    "currency": "Currency code or N/A",
    "schedule": "Payment schedule plain description (e.g. monthly, on delivery)",
    "late_penalty": "Penalty clause for late payment, or N/A"
  },
  "governing_law": {
    "jurisdiction": "State/Country",
    "court_or_arbitration": "Specified forum for disputes",
    "risk_note": "Brief note on whether this jurisdiction is favorable or concerning"
  },
  "notice_period": "e.g. 30 days written notice, or N/A",
  "defined_terms": [
    {
      "term": "Defined term as used in the contract",
      "definition": "Its definition from the contract"
    }
  ],
  "missing_entities": ["Critical fields that could not be found in the contract"],
  "recommendations": ["Recommendation 1", "Recommendation 2"]
}

Return ONLY the JSON object above. No other text.

{memory_block}

=== GROUNDING CONTEXT (CONTRACT TEXT) ===
{contract_text}
"""

# ═══════════════════════════════════════════════════════════════
# FEATURE 6: Contract Comparison / Semantic Redlining
# ═══════════════════════════════════════════════════════════════

CONTRACT_COMPARE_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: CONTRACT COMPARISON & SEMANTIC REDLINING ===
The user has provided TWO versions of a contract: the ORIGINAL (Version A) and a REVISED version (Version B).
Identify every meaningful difference — not just textual changes, but their LEGAL and PRACTICAL impact.
Do NOT simply list word changes; explain what each change means for each party.

=== REQUIRED JSON OUTPUT SCHEMA ===
{
  "quick_summary": "One-liner overview of how the revision changed the contract's overall balance",
  "overall_verdict": "FAVORABLE_TO_A or FAVORABLE_TO_B or NEUTRAL or MIXED",
  "total_changes": <number>,
  "changes": [
    {
      "change_number": <number>,
      "clause_or_section": "Which clause/section was changed",
      "original_text_snippet": "Brief quote from Version A",
      "revised_text_snippet": "Brief quote from Version B",
      "change_type": "ADDITION or DELETION or MODIFICATION or REORDERING",
      "impact_severity": "HIGH or MEDIUM or LOW",
      "plain_explanation": "Plain-English explanation of what changed and why it matters",
      "who_benefits": "Party A, Party B, or Both/Neutral",
      "negotiation_note": "Suggested counter-position or acceptance rationale"
    }
  ],
  "unchanged_key_clauses": ["Important clauses that were NOT changed"],
  "executive_recommendation": "Overall recommendation — should the revised version be accepted, rejected, or negotiated?",
  "recommendations": ["Specific recommendation 1", "Specific recommendation 2"]
}

Return ONLY the JSON object above. No other text.

{memory_block}

=== GROUNDING CONTEXT — VERSION A (ORIGINAL CONTRACT) ===
{contract_text}

=== GROUNDING CONTEXT — VERSION B (REVISED CONTRACT) ===
{extra_context}
"""

# ═══════════════════════════════════════════════════════════════
# FEATURE 7: Multilingual Translation
# ═══════════════════════════════════════════════════════════════

MULTILINGUAL_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: MULTILINGUAL PLAIN-LANGUAGE TRANSLATION ===
Translate the contract into the TARGET LANGUAGE specified below, using plain everyday language
that a non-lawyer speaker of that language can easily understand.
Preserve the meaning and legal intent faithfully — do NOT simplify away important obligations.

=== TARGET LANGUAGE ===
{extra_context}

=== REQUIRED JSON OUTPUT SCHEMA ===
{
  "target_language": "{extra_context}",
  "quick_summary": "One-sentence overview of the contract in the target language",
  "sections": [
    {
      "section_number": <number>,
      "original_heading": "Original section heading (in source language)",
      "translated_heading": "Section heading in target language",
      "translated_text": "Full plain-language translation of this section in the target language",
      "key_obligation": "The single most important obligation from this section"
    }
  ],
  "critical_terms_glossary": [
    {
      "original_term": "Legal term in original language",
      "translated_term": "Term in target language",
      "plain_explanation": "What this term means in plain terms"
    }
  ],
  "translation_notes": ["Any note about terms that have no direct equivalent in the target language"],
  "recommendations": ["Recommendation 1"]
}

Return ONLY the JSON object above. No other text.

{memory_block}

=== GROUNDING CONTEXT (CONTRACT TEXT) ===
{contract_text}
"""

# ═══════════════════════════════════════════════════════════════
# FOLLOW-UP CHAT PROMPT
# ═══════════════════════════════════════════════════════════════

CHAT_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: FOLLOW-UP CONVERSATION ===
The user has already analyzed a contract and is now asking follow-up questions about it.
Answer their question using the contract text and conversation history as context.

=== REQUIRED JSON OUTPUT SCHEMA ===
{
  "answer": "Your detailed, plain-English answer to the user's question",
  "relevant_clauses": ["Brief reference to relevant clauses if applicable"],
  "confidence": "HIGH or MEDIUM or LOW",
  "follow_up_suggestions": ["Suggested follow-up question 1", "Suggested follow-up question 2"]
}

Return ONLY the JSON object above. No other text.

=== CONVERSATION MEMORY (last {turn_count} turns) ===
{memory_block}

=== GROUNDING CONTEXT (CONTRACT TEXT) ===
{contract_text}

=== USER'S CURRENT QUESTION ===
{user_question}
"""

# ═══════════════════════════════════════════════════════════════
# PROMPT REGISTRY
# ═══════════════════════════════════════════════════════════════

FEATURE_PROMPTS = {
    "summarize": CLAUSE_SUMMARIZATION_PROMPT,
    "translate": PLAIN_LANGUAGE_PROMPT,
    "risks": RISK_HIGHLIGHT_PROMPT,
    "tags": CLAUSE_TAGGING_PROMPT,
    "entities": ENTITY_EXTRACTION_PROMPT,
    "compare": CONTRACT_COMPARE_PROMPT,
    "multilingual": MULTILINGUAL_PROMPT,
}

FEATURE_LABELS = {
    "summarize": "Clause-Level Summarization",
    "translate": "Plain Language Translation",
    "risks": "Risk Highlight Generation",
    "tags": "Structured Clause Tagging",
    "entities": "Key Entity Extraction",
    "compare": "Contract Comparison",
    "multilingual": "Multilingual Translation",
}


# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def _build_memory_block(memory_turns):
    """Format conversation memory for injection into prompts."""
    if not memory_turns:
        return ""

    lines = ["=== CONVERSATION MEMORY (previous context) ==="]
    for i, turn in enumerate(memory_turns, 1):
        role_label = "USER" if turn["role"] == "user" else "ASSISTANT"
        content_preview = turn["content"][:500]
        lines.append(f"Turn {i} [{role_label}]: {content_preview}")

    return "\n".join(lines)


def _call_gemini(prompt_text):
    """
    Call Gemini API with retry logic for 503 errors.

    Args:
        prompt_text: The fully assembled prompt string.

    Returns:
        Parsed JSON dict, or error dict.
    """
    if not Config.GEMINI_API_KEY or Config.GEMINI_API_KEY == "your_gemini_api_key_here":
        return {"error": "Gemini API key is not configured. Please add your key to the .env file."}

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=Config.GEMINI_MODEL,
                contents=prompt_text,
                config=genai.types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=8192,
                ),
            )

            raw_text = response.text.strip()

            # Strip markdown code fences if the model wraps JSON in them
            if raw_text.startswith("```"):
                first_newline = raw_text.index("\n")
                last_fence = raw_text.rfind("```")
                raw_text = raw_text[first_newline + 1:last_fence].strip()

            return json.loads(raw_text)

        except json.JSONDecodeError:
            # If JSON parsing fails, return the raw text in an error wrapper
            return {
                "error": "Model returned invalid JSON. Showing raw output.",
                "raw_response": raw_text[:3000]
            }
        except Exception as e:
            error_msg = str(e)
            if "503" in error_msg or "UNAVAILABLE" in error_msg:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                    continue
                return {
                    "error": "The Gemini model is experiencing high demand. Please try again in a few seconds."
                }
            return {"error": f"API error: {error_msg}"}

    return {"error": "Failed after maximum retries."}


# ═══════════════════════════════════════════════════════════════
# PUBLIC API FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def analyze_contract(feature, contract_text, memory_turns=None, extra_context=""):
    """
    Run one of the analysis features on a contract.

    Args:
        feature: One of 'summarize', 'translate', 'risks', 'tags',
                 'entities', 'compare', 'multilingual'.
        contract_text: The full contract text to analyze (Version A for compare).
        memory_turns: List of previous conversation turns for context.
        extra_context: Secondary data required by some features:
                       - 'compare'      → Version B contract text
                       - 'multilingual' → Target language string (e.g. "Spanish")

    Returns:
        Parsed JSON response dict from Gemini.
    """
    if feature not in FEATURE_PROMPTS:
        return {"error": f"Unknown feature: {feature}"}

    if not contract_text or not contract_text.strip():
        return {"error": "No contract text provided. Please paste text or upload a file."}

    # Validate extra_context for features that require it
    if feature == "compare" and not (extra_context or "").strip():
        return {"error": "Contract Comparison requires a second (revised) contract text."}
    if feature == "multilingual" and not (extra_context or "").strip():
        return {"error": "Multilingual Translation requires a target language (e.g. 'Spanish')."}

    prompt_template = FEATURE_PROMPTS[feature]
    memory_block = _build_memory_block(memory_turns or [])

    prompt = (prompt_template
               .replace("{memory_block}", memory_block)
               .replace("{contract_text}", contract_text[:15000])
               .replace("{extra_context}", (extra_context or "")[:8000]))

    return _call_gemini(prompt)


def chat_followup(user_question, contract_text, memory_turns=None):
    """
    Handle a follow-up chat question about a previously analyzed contract.

    Args:
        user_question: The user's follow-up question.
        contract_text: The contract text for grounding.
        memory_turns: Last N conversation turns for memory.

    Returns:
        Parsed JSON response dict from Gemini.
    """
    if not user_question or not user_question.strip():
        return {"error": "No question provided."}

    turns = memory_turns or []
    memory_block = _build_memory_block(turns)

    prompt = (CHAT_PROMPT
               .replace("{turn_count}", str(len(turns)))
               .replace("{memory_block}", memory_block)
               .replace("{contract_text}", (contract_text or "No contract uploaded yet.")[:15000])
               .replace("{user_question}", user_question))

    return _call_gemini(prompt)
