"""
ClauseClear AI — AI Provider Layer.

Handles all direct API calls to Gemini, DeepSeek, OpenAI, and Claude.
Exposes a single _call_ai() dispatcher that tries providers in order
and returns the first successful parsed-JSON response.

Also contains shared helpers and lightweight embedding utilities.
"""

import json
import math
import re
import time
import logging

from config import Config
from services.prompts import MAX_RETRIES, RETRY_DELAY_SECONDS

logger = logging.getLogger(__name__)


# --- Shared helpers ----------------------------------------------------------

def _build_memory_block(memory_turns: list) -> str:
    """Format conversation turns into a prompt-ready block."""
    if not memory_turns:
        return ""
    lines = ["=== CONVERSATION MEMORY ==="]
    for i, turn in enumerate(memory_turns, 1):
        label = "USER" if turn["role"] == "user" else "ASSISTANT"
        lines.append(f"Turn {i} [{label}]: {turn['content'][:500]}")
    return "\n".join(lines)


def _parse_json_response(raw: str) -> dict:
    """Strip markdown fences and parse JSON. Raises json.JSONDecodeError on failure."""
    raw = raw.strip()
    # Strip leading ``` code fences (e.g. ```json\n{...}\n```)
    if raw.startswith("```"):
        # Remove opening fence line
        newline_idx = raw.find("\n")
        if newline_idx != -1:
            raw = raw[newline_idx + 1:]
        # Remove closing fence
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()
    return json.loads(raw)


# --- Provider 1: Gemini (primary) -------------------------------------------

_gemini_client = None  # module-level singleton


def _get_gemini_client():
    """Return the cached Gemini client, initialising it on first call."""
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client
    if not Config.GEMINI_API_KEY:
        return None
    try:
        from google import genai
        _gemini_client = genai.Client(api_key=Config.GEMINI_API_KEY)
        return _gemini_client
    except Exception as exc:
        logger.error("Failed to init Gemini client: %s", exc)
        return None


def _call_gemini(prompt_text: str, temperature: float = 0.3) -> dict:
    if not Config.GEMINI_API_KEY:
        return {"error": "NO_KEY:GEMINI"}
    client = _get_gemini_client()
    if client is None:
        return {"error": "INIT_ERROR:GEMINI"}
    try:
        from google import genai as _genai
        _GCConfig = _genai.types.GenerateContentConfig
    except Exception:
        return {"error": "INIT_ERROR:GEMINI"}

    for attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=Config.GEMINI_MODEL,
                contents=prompt_text,
                config=_GCConfig(temperature=temperature, max_output_tokens=8192),
            )
            return _parse_json_response(response.text)
        except json.JSONDecodeError:
            logger.error("Gemini bad JSON (attempt %d/%d)", attempt + 1, MAX_RETRIES)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            return {"error": "BAD_JSON:GEMINI"}
        except Exception as exc:
            err = str(exc)
            err_up = err.upper()
            is_quota = (
                "429" in err or "RESOURCE_EXHAUSTED" in err_up
                or "QUOTA" in err_up or "RATE_LIMIT" in err_up
                or "rate limit" in err.lower() or "quota" in err.lower()
                or "too many requests" in err.lower()
            )
            if is_quota:
                delay = RETRY_DELAY_SECONDS * (2 ** attempt)
                try:
                    m = re.search(r"retryDelay.*?(\d+)s", err)
                    if m:
                        delay = min(int(m.group(1)), 60)
                except Exception:
                    pass
                if attempt < MAX_RETRIES - 1:
                    logger.warning("Gemini quota (attempt %d/%d). Retrying in %ds.", attempt + 1, MAX_RETRIES, delay)
                    time.sleep(delay)
                    continue
                logger.warning("Gemini quota exhausted -- falling back.")
                return {"error": "QUOTA:GEMINI"}
            if "503" in err or "UNAVAILABLE" in err_up:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                    continue
                return {"error": "UNAVAILABLE:GEMINI"}
            if "404" in err or "NOT_FOUND" in err_up or "not found" in err.lower():
                logger.error("Gemini model not found (%s). check GEMINI_MODEL in config.py or .env", Config.GEMINI_MODEL)
                return {"error": f"NOT_FOUND:GEMINI:{Config.GEMINI_MODEL}"}
            logger.error("Gemini error: %s", err)
            return {"error": f"ERROR:GEMINI:{err[:120]}"}
    return {"error": "MAX_RETRIES:GEMINI"}


# --- Provider 2: DeepSeek (first fallback) ----------------------------------

def _call_deepseek(prompt_text: str, temperature: float = 0.3) -> dict:
    """
    Call DeepSeek via its OpenAI-compatible REST API.
    DeepSeek's chat endpoint is a drop-in for the OpenAI client --
    just point base_url to https://api.deepseek.com.

    Models:
      deepseek-chat      -- DeepSeek-V3 (fast, cheap, great for JSON tasks)
      deepseek-reasoner  -- DeepSeek-R1 (slower but stronger reasoning)
    """
    if not Config.DEEPSEEK_API_KEY or not Config.DEEPSEEK_API_KEY.strip():
        return {"error": "NO_KEY:DEEPSEEK"}
    try:
        import openai as _openai
        client = _openai.OpenAI(
            api_key=Config.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com",
        )
    except ImportError:
        logger.error("openai package not installed -- required for DeepSeek.")
        return {"error": "NOT_INSTALLED:DEEPSEEK"}
    except Exception as exc:
        logger.error("Failed to init DeepSeek client: %s", exc)
        return {"error": "INIT_ERROR:DEEPSEEK"}

    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=Config.DEEPSEEK_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a legal contract analysis assistant. Always return valid JSON only.",
                    },
                    {"role": "user", "content": prompt_text},
                ],
                temperature=temperature,
                max_tokens=8192,
                response_format={"type": "json_object"},
            )
            return _parse_json_response(response.choices[0].message.content)
        except json.JSONDecodeError:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            return {"error": "BAD_JSON:DEEPSEEK"}
        except Exception as exc:
            err = str(exc)
            err_lower = err.lower()
            if "rate" in err_lower or "429" in err or "quota" in err_lower or "too many" in err_lower:
                delay = RETRY_DELAY_SECONDS * (2 ** attempt)
                if attempt < MAX_RETRIES - 1:
                    logger.warning(
                        "DeepSeek rate-limit (attempt %d/%d). Retrying in %ds.",
                        attempt + 1, MAX_RETRIES, delay,
                    )
                    time.sleep(delay)
                    continue
                return {"error": "QUOTA:DEEPSEEK"}
            if "503" in err or "unavailable" in err_lower:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                    continue
                return {"error": "UNAVAILABLE:DEEPSEEK"}
            if "401" in err or "403" in err or "authentication" in err_lower or "invalid api key" in err_lower:
                logger.error("DeepSeek auth failed -- check DEEPSEEK_API_KEY.")
                return {"error": "AUTH:DEEPSEEK"}
            if "400" in err or "invalid" in err_lower:
                logger.error("DeepSeek bad request: %s", err)
                return {"error": f"BAD_REQUEST:DEEPSEEK:{err[:80]}"}
            logger.error("DeepSeek error: %s", err)
            return {"error": f"ERROR:DEEPSEEK:{err[:120]}"}
    return {"error": "MAX_RETRIES:DEEPSEEK"}


# --- Provider 3: OpenAI (second fallback) -----------------------------------

def _call_openai(prompt_text: str, temperature: float = 0.3) -> dict:
    if not Config.OPENAI_API_KEY or Config.OPENAI_API_KEY.startswith("your-") or Config.OPENAI_API_KEY.startswith("sk-proj-your"):
        return {"error": "NO_KEY:OPENAI"}
    try:
        import openai as _openai
        client = _openai.OpenAI(api_key=Config.OPENAI_API_KEY)
    except ImportError:
        logger.error("openai package not installed.")
        return {"error": "NOT_INSTALLED:OPENAI"}
    except Exception as exc:
        logger.error("Failed to init OpenAI client: %s", exc)
        return {"error": "INIT_ERROR:OPENAI"}

    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=Config.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a legal contract analysis assistant. Always return valid JSON only."},
                    {"role": "user", "content": prompt_text},
                ],
                temperature=temperature,
                max_tokens=8192,
                response_format={"type": "json_object"},
            )
            return _parse_json_response(response.choices[0].message.content)
        except json.JSONDecodeError:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            return {"error": "BAD_JSON:OPENAI"}
        except Exception as exc:
            err = str(exc)
            err_lower = err.lower()
            if "rate" in err_lower or "429" in err or "quota" in err_lower:
                delay = RETRY_DELAY_SECONDS * (2 ** attempt)
                if attempt < MAX_RETRIES - 1:
                    logger.warning("OpenAI rate-limit (attempt %d/%d). Retrying in %ds.", attempt + 1, MAX_RETRIES, delay)
                    time.sleep(delay)
                    continue
                return {"error": "QUOTA:OPENAI"}
            if "503" in err or "unavailable" in err_lower:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                    continue
                return {"error": "UNAVAILABLE:OPENAI"}
            if "401" in err or "403" in err or "authentication" in err_lower or "incorrect api key" in err_lower:
                logger.error("OpenAI auth failed -- check OPENAI_API_KEY.")
                return {"error": "AUTH:OPENAI"}
            if "400" in err or "invalid" in err_lower:
                logger.error("OpenAI bad request: %s", err)
                return {"error": f"BAD_REQUEST:OPENAI:{err[:80]}"}
            logger.error("OpenAI error: %s", err)
            return {"error": f"ERROR:OPENAI:{err[:120]}"}
    return {"error": "MAX_RETRIES:OPENAI"}


# --- Provider 4: Claude (last resort) ---------------------------------------

def _call_claude(prompt_text: str, temperature: float = 0.3) -> dict:
    if not Config.ANTHROPIC_API_KEY or not Config.ANTHROPIC_API_KEY.strip() or Config.ANTHROPIC_API_KEY.startswith("your-"):
        logger.warning("No Anthropic API key -- Claude provider skipped.")
        return {"error": "All AI providers are unavailable. Check your API keys in .env."}
    try:
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    except ImportError:
        logger.error("anthropic package not installed.")
        return {"error": "All AI providers failed. Please try again later."}
    except Exception as exc:
        logger.error("Failed to init Claude client: %s", exc)
        return {"error": "All AI providers failed. Please try again later."}

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=Config.CLAUDE_MODEL,
                max_tokens=8192,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt_text}],
            )
            return _parse_json_response(response.content[0].text)
        except json.JSONDecodeError:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS)
                continue
            return {"error": "The AI returned an unexpected format. Please try again."}
        except Exception as exc:
            err = str(exc)
            err_lower = err.lower()
            if "rate" in err_lower or "429" in err or "overloaded" in err_lower:
                delay = RETRY_DELAY_SECONDS * (2 ** attempt)
                if attempt < MAX_RETRIES - 1:
                    logger.warning("Claude rate-limit (attempt %d/%d). Waiting %ds.", attempt + 1, MAX_RETRIES, delay)
                    time.sleep(delay)
                    continue
                return {"error": "All AI providers have hit rate limits. Please wait and try again."}
            if "401" in err or "403" in err or "authentication" in err_lower or "invalid x-api-key" in err_lower:
                logger.error("Claude auth failed -- check ANTHROPIC_API_KEY.")
                return {"error": "Invalid Anthropic API key. Please check your .env file."}
            logger.error("Claude error: %s", err, exc_info=True)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
                continue
            return {"error": "All AI providers are temporarily unavailable. Please try again shortly."}
    return {"error": "All AI providers failed after maximum retries."}


# --- Primary dispatcher: Gemini -> DeepSeek -> OpenAI -> Claude -------------

def _call_ai(prompt_text: str, temperature: float = 0.3) -> dict:
    """
    Try each provider in order, return the first successful JSON response.
      1. Gemini   (primary -- free tier, fast)
      2. DeepSeek (first fallback)
      3. OpenAI   (second fallback)
      4. Claude   (last resort)
    """
    # --- 1. Gemini ---
    gemini_result = _call_gemini(prompt_text, temperature)
    if "error" not in gemini_result:
        return gemini_result
    logger.warning("Gemini failed (%s) -- trying DeepSeek.", gemini_result.get("error"))

    # --- 2. DeepSeek ---
    deepseek_result = _call_deepseek(prompt_text, temperature)
    if "error" not in deepseek_result:
        logger.info("DeepSeek fallback succeeded.")
        return deepseek_result
    logger.warning("DeepSeek failed (%s) -- trying OpenAI.", deepseek_result.get("error"))

    # --- 3. OpenAI ---
    openai_result = _call_openai(prompt_text, temperature)
    if "error" not in openai_result:
        logger.info("OpenAI fallback succeeded.")
        return openai_result
    logger.warning("OpenAI failed (%s) -- trying Claude.", openai_result.get("error"))

    # --- 4. Claude ---
    claude_result = _call_claude(prompt_text, temperature)
    if "error" not in claude_result:
        logger.info("Claude fallback succeeded.")
        return claude_result

    # All providers failed -- return the most "actionable" error.
    # Prioritize: AUTH > NO_KEY > NOT_FOUND > QUOTA > Generic ERROR
    all_results = [gemini_result, deepseek_result, openai_result, claude_result]
    
    # 1. Check for Auth/Key errors (Configuration issues)
    for res in all_results:
        err = res.get("error", "")
        if any(x in err for x in ["AUTH", "NO_KEY", "INVALID_KEY", "NOT_FOUND"]):
            logger.error("AI Dispatcher: Configuration issue detected: %s", err)
            return res
            
    # 2. Check for Quota/Rate errors
    for res in all_results:
        err = res.get("error", "").lower()
        if "quota" in err or "rate" in err or "429" in err:
            logger.error("AI Dispatcher: All configured providers hit quota limits.")
            return res

    # 3. Fallback to the very last error
    logger.error("All 4 providers failed. Final error: %s", claude_result.get("error"))
    return claude_result


# --- Embedding & RAG (no external API needed) --------------------------------

def generate_embedding(text: str) -> list:
    """Simple TF-IDF-style keyword vector -- no external API required."""
    try:
        words = re.findall(r'\b[a-z]{3,}\b', text.lower()[:8000])
        freq = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        total = sum(freq.values()) or 1
        top_words = sorted(freq.items(), key=lambda x: -x[1])[:300]
        vec = [v / total for _, v in top_words]
        return vec[:300] + [0.0] * (300 - len(vec))
    except Exception as exc:
        logger.error("Embedding generation failed: %s", exc)
        return []


def cosine_similarity(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    return 0.0 if mag_a == 0 or mag_b == 0 else dot / (mag_a * mag_b)


def find_similar_analysis(new_embedding: list, past_embeddings: list):
    """Return the most similar past analysis if cosine similarity > 0.75, else None."""
    if not new_embedding or not past_embeddings:
        return None
    best_score, best_match = 0.0, None
    for entry in past_embeddings:
        score = cosine_similarity(new_embedding, entry.get("embedding", []))
        if score > best_score:
            best_score, best_match = score, entry
    return best_match if best_match and best_score > 0.75 else None
