"""
ClauseClear AI — Prompt Templates & Constants.

All AI prompt strings and associated constants live here so they can be
edited without touching provider logic or high-level analysis functions.

Injection convention: use PLACEHOLDER tokens with safe .replace() calls —
never .format() — because contract text may contain { } braces.
"""

# ─── Retry / self-critique knobs ─────────────────────────────────────────────

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2

# Disable self-critique to save API quota on free tiers.
# Set True on paid plans for higher accuracy.
ENABLE_SELF_CRITIQUE = False

# ─── Contract type list ───────────────────────────────────────────────────────

CONTRACT_TYPES = [
    "NDA", "EMPLOYMENT", "SAAS_TOS", "FREELANCE",
    "RENTAL", "LOAN", "PARTNERSHIP", "UNKNOWN",
]

# ─── Classification prompt ────────────────────────────────────────────────────

CLASSIFY_ONLY_PROMPT = """You are a contract classifier. Read the contract text below and return ONLY a single JSON object:
{"contract_type": "<TYPE>"}
Where <TYPE> is exactly one of: NDA, EMPLOYMENT, SAAS_TOS, FREELANCE, RENTAL, LOAN, PARTNERSHIP, UNKNOWN
No other output. No markdown. No explanation.

CONTRACT TEXT:
TEXT_PLACEHOLDER
"""

# ─── Shared system prompt ─────────────────────────────────────────────────────

BASE_SYSTEM_PROMPT = """You are a senior legal contract analyst at ClauseClear AI. You provide structured, actionable analysis.

ABSOLUTE RULES:
1. Return ONLY valid JSON — no markdown, no preamble, no text outside the JSON object.
2. NEVER fabricate clauses not present in the contract text.
3. NEVER provide binding legal advice.
4. If uncertain about a clause, flag it explicitly in the explanation.
5. All risk explanations MUST reference the market benchmark standards provided.
"""

# ─── Unified analysis template ────────────────────────────────────────────────

_UNIFIED_TEMPLATE = """SYSTEM_PROMPT_PLACEHOLDER

BENCHMARK_PLACEHOLDER
PLAYBOOK_PLACEHOLDER

HISTORICAL_PLACEHOLDER

=== TASK: FULL CONTRACT ANALYSIS ===
Analyze the contract below. Return this EXACT JSON schema (all fields required):

{
  "contract_type": "CONTRACT_TYPE_PLACEHOLDER",
  "health_score": <integer 0-100>,
  "health_grade": "<A|B|C|D|F>",
  "health_verdict": "<one sentence plain English verdict>",
  "risks": [
    {
      "clause": "<clause name>",
      "severity": "<HIGH|MEDIUM|LOW>",
      "explanation": "<plain English explanation WITH explicit market benchmark comparison>",
      "standard_justification": "<cite the exact Indian statute and section that makes this HIGH_RISK — empty string for LOW/MEDIUM>",
      "suggested_redline": "<one or two sentence proposed rewrite>"
    }
  ],
  "obligations": [
    {
      "obligation": "<obligation description>",
      "deadline_description": "<timing or deadline>",
      "party": "<responsible party>",
      "section": "<contract section reference>"
    }
  ],
  "summary": "<3-5 sentence plain language summary of the whole contract>",
  "key_entities": {
    "parties": ["<party name>"],
    "effective_date": "<date or empty string>",
    "governing_law": "<jurisdiction or empty string>",
    "termination_notice": "<notice period or empty string>"
  }
}

Health score guide: 90-100=A (excellent), 80-89=B (good), 70-79=C (acceptable), 60-69=D (concerning), 0-59=F (dangerous).

MEMORY_PLACEHOLDER

=== CONTRACT TEXT ===
CONTRACT_TEXT_PLACEHOLDER
"""

# ─── Contract-type focus addenda ──────────────────────────────────────────────

_NDA_ADDENDUM        = "NDA FOCUS AREAS: Analyze mutual vs one-sided scope, IP assignment breadth, residuals clauses, duration against 2-3 year market standard, jurisdiction, and definition of Confidential Information."
_EMPLOYMENT_ADDENDUM = "EMPLOYMENT FOCUS AREAS: At-will provisions, non-compete duration+geography vs 6-12 month standard, equity vesting cliff+acceleration (standard: 4yr/1yr cliff), IP ownership of side projects, arbitration waivers, and severance terms."
_SAAS_ADDENDUM       = "SAAS_TOS FOCUS AREAS: Auto-renewal + cancellation notice windows (standard: 30-60 days), data ownership clauses, liability caps vs 12-month fees standard, SLA definitions, unilateral modification rights, and data retention on termination."
_FREELANCE_ADDENDUM  = "FREELANCE FOCUS AREAS: Payment terms + kill fees (standard: Net-30, 25-50% kill fee), IP transfer timing (should transfer only on full payment), revision limits, non-solicit clauses, and one-sided indemnification."
_RENTAL_ADDENDUM     = "RENTAL FOCUS AREAS: Security deposit vs 1-2 months standard, early termination penalties, maintenance responsibility allocation, subletting rights, notice periods (standard: 30 days), and rent increase mechanisms."
_LOAN_ADDENDUM       = "LOAN FOCUS AREAS: Interest rate vs market standard (6-12% APR for personal loans), prepayment penalties, default cure periods (standard: 10-30 days), collateral scope, and acceleration clauses."
_PARTNERSHIP_ADDENDUM= "PARTNERSHIP FOCUS AREAS: Profit distribution fairness, deadlock resolution mechanisms, dissolution and exit provisions, post-dissolution non-compete scope, IP ownership assignment, and fiduciary duty language."
_UNKNOWN_ADDENDUM    = "GENERAL FOCUS: Apply balanced general legal analysis. Identify all liability, termination, payment, IP, and dispute resolution clauses."

PROMPT_TEMPLATES = {
    "NDA":         _NDA_ADDENDUM,
    "EMPLOYMENT":  _EMPLOYMENT_ADDENDUM,
    "SAAS_TOS":    _SAAS_ADDENDUM,
    "FREELANCE":   _FREELANCE_ADDENDUM,
    "RENTAL":      _RENTAL_ADDENDUM,
    "LOAN":        _LOAN_ADDENDUM,
    "PARTNERSHIP": _PARTNERSHIP_ADDENDUM,
    "UNKNOWN":     _UNKNOWN_ADDENDUM,
}

# ─── Self-critique template ───────────────────────────────────────────────────

SELF_CRITIQUE_PROMPT_TEMPLATE = """You are a senior legal QA reviewer at ClauseClear AI.

Review the original contract text and the generated analysis JSON below.
Check for: overstated/understated risks, missed obligations, wrong health score,
impractical redlines, and vague statute citations.

Return the corrected JSON in the EXACT same schema. Return ONLY the JSON object.

=== ORIGINAL CONTRACT TEXT ===
ORIGINAL_TEXT_PLACEHOLDER

=== GENERATED ANALYSIS JSON TO REVIEW ===
ANALYSIS_JSON_PLACEHOLDER
"""

# ─── Feature prompt templates ─────────────────────────────────────────────────

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

MEMORY_PLACEHOLDER

=== CONTRACT TEXT ===
CONTRACT_TEXT_PLACEHOLDER
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

MEMORY_PLACEHOLDER

=== CONTRACT TEXT ===
CONTRACT_TEXT_PLACEHOLDER
"""

CLAUSE_TAGGING_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: STRUCTURED CLAUSE TAGGING ===
Tag every clause. Categories: Payment, Termination, Liability, Confidentiality,
Governing Law, Dispute Resolution, Warranties, Non-Compete, Data Privacy, IP Rights,
Force Majeure, Indemnification, Representations, Amendments, Assignment, Notices,
Severability, Entire Agreement, Other.

Return ONLY this JSON schema:
{
  "quick_summary": "One-liner overview",
  "total_clauses": <number>,
  "category_frequency": {"Payment": <n>},
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
  "missing_categories": ["Categories commonly expected but not found"],
  "recommendations": ["Recommendation 1"]
}

MEMORY_PLACEHOLDER

=== CONTRACT TEXT ===
CONTRACT_TEXT_PLACEHOLDER
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

MEMORY_PLACEHOLDER

=== CONTRACT TEXT ===
CONTRACT_TEXT_PLACEHOLDER
"""

CONTRACT_COMPARE_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: CONTRACT COMPARISON & SEMANTIC REDLINING ===
Compare Version A (original) and Version B (revised).

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

MEMORY_PLACEHOLDER

=== CONTRACT TEXT - VERSION A (ORIGINAL) ===
CONTRACT_TEXT_PLACEHOLDER

=== CONTRACT TEXT - VERSION B (REVISED) ===
EXTRA_CONTEXT_PLACEHOLDER
"""

MULTILINGUAL_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: MULTILINGUAL PLAIN-LANGUAGE TRANSLATION ===
Translate the contract into the TARGET LANGUAGE below in plain everyday language.

=== TARGET LANGUAGE ===
EXTRA_CONTEXT_PLACEHOLDER

Return ONLY this JSON schema:
{
  "target_language": "EXTRA_CONTEXT_PLACEHOLDER",
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

MEMORY_PLACEHOLDER

=== CONTRACT TEXT ===
CONTRACT_TEXT_PLACEHOLDER
"""

CHAT_PROMPT = BASE_SYSTEM_PROMPT + """
=== TASK: FOLLOW-UP CONVERSATION ===
Answer the user question about the contract using contract text and conversation history.

Return ONLY this JSON schema:
{
  "answer": "Detailed plain-English answer",
  "relevant_clauses": ["Brief clause reference"],
  "confidence": "HIGH or MEDIUM or LOW",
  "follow_up_suggestions": ["Suggested follow-up 1", "Suggested follow-up 2"]
}

=== CONVERSATION MEMORY ===
MEMORY_PLACEHOLDER

=== CONTRACT TEXT ===
CONTRACT_TEXT_PLACEHOLDER

=== USER QUESTION ===
QUESTION_PLACEHOLDER
"""

HIGHLIGHT_PROMPT = """
PLAYBOOK_PLACEHOLDER
You are a senior legal risk analyst. Classify every clause into one of:
- HIGH_RISK, RISK, NEUTRAL, POSITIVE

Return ONLY valid JSON:
{
  "quick_summary": "<one sentence overall risk assessment>",
  "highlighted_clauses": [
    {
      "text": "<exact clause or sentence from contract>",
      "classification": "HIGH_RISK|RISK|NEUTRAL|POSITIVE",
      "reason": "<one sentence explaining why>",
      "standard_justification": "<cite exact Indian statute/section if HIGH_RISK>",
      "negotiation_tip": "<one sentence actionable tip or empty string>"
    }
  ],
  "high_risk_count": <int>,
  "risk_count": <int>,
  "neutral_count": <int>,
  "positive_count": <int>
}

MEMORY_PLACEHOLDER

CONTRACT:
CONTRACT_TEXT_PLACEHOLDER
"""

_CHECKLIST_PROMPT = """
You are a contract compliance expert. Analyze the contract and check for 10 essential clauses.

Return ONLY valid JSON — no markdown, no text outside JSON:
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

Check EXACTLY these 10 items in order:
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
CONTRACT_TEXT_PLACEHOLDER
"""

# ─── Feature routing maps ─────────────────────────────────────────────────────

FEATURE_PROMPTS = {
    "summarize":  CLAUSE_SUMMARIZATION_PROMPT,
    "translate":  PLAIN_LANGUAGE_PROMPT,
    "tags":       CLAUSE_TAGGING_PROMPT,
    "entities":   ENTITY_EXTRACTION_PROMPT,
    "compare":    CONTRACT_COMPARE_PROMPT,
    "multilingual": MULTILINGUAL_PROMPT,
    "highlight":  HIGHLIGHT_PROMPT,
}

FEATURE_LABELS = {
    "unified":      "Full Contract Analysis",
    "summarize":    "Clause Summarization",
    "translate":    "Plain Language",
    "summary_plain":"Summary & Plain Language",
    "risks":        "Risk Highlight",
    "tags":         "Tag Clauses",
    "highlight":    "HIGH_RISK Clause Highlighter",
    "entities":     "Extract Entities",
    "compare":      "Compare Contracts",
    "multilingual": "Translate Language",
    "checklist":    "Contract Checklist",
}
