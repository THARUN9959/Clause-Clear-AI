"""
ClauseClear AI — Main Flask Application.

Routes:
  GET  /                        → Landing page
  GET  /analyze                 → Analysis page
  GET  /history                 → Paginated history page (SQLite-backed)
  POST /api/upload              → Upload file, extract text, save to session
  POST /api/analyze             → Unified Gemini analysis
  POST /api/analyze/feature     → Legacy feature-specific analysis
  POST /api/chat                → Follow-up chat
  GET  /api/history/<id>        → Load a past analysis from DB
  DELETE /api/history/<id>      → Delete an analysis from DB
  GET  /api/export/<id>         → Download PDF report
  GET  /api/memory              → Current session memory state
  POST /api/clear-memory        → Clear in-memory session turns
"""

import os
import io
import json
import uuid
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

from flask import (
    Flask, render_template, request, jsonify,
    session, g, send_file, abort,
)
from werkzeug.utils import secure_filename

from config import Config
from db import (
    create_db, get_db_session, cleanup_old_sessions,
    get_or_create_session, save_analysis, get_session_analyses,
    delete_analysis, save_chat_message, get_chat_history,
    get_all_embeddings, AnalysisModel,
)
from services.memory_service import memory_manager
from services.document_service import extract_text, allowed_file
from services.gemini_service import (
    unified_analyze, analyze_contract, chat_followup, FEATURE_LABELS, run_checklist,
)
from services.playbooks import PLAYBOOKS, DEFAULT_STANDARD
from services.export_service import generate_pdf, _FPDF_AVAILABLE
from sqlmodel import select as _select

# ─── Logging setup ────────────────────────────────────────────────────────────

def _configure_logging():
    log_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(log_dir, exist_ok=True)
    handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)s | %(module)s | %(message)s"
    ))
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    root_logger.addHandler(logging.StreamHandler())


_configure_logging()
logger = logging.getLogger(__name__)

# ─── App init ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.config["SECRET_KEY"] = Config.SECRET_KEY
app.config["UPLOAD_FOLDER"] = Config.UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH

# Flask-WTF CSRF
try:
    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect(app)
    logger.info("CSRF protection enabled")
except ImportError:
    logger.warning("flask-wtf not installed — CSRF protection disabled. Run: pip install flask-wtf")
    csrf = None

# Flask-Limiter
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        storage_uri=Config.RATELIMIT_STORAGE_URI,
        default_limits=[],
    )
    logger.info("Rate limiting enabled")
except ImportError:
    logger.warning("flask-limiter not installed — rate limiting disabled. Run: pip install flask-limiter")
    limiter = None

Config.init_app()

# Create DB tables and run startup cleanup
create_db()
_startup_db = get_db_session()
try:
    cleanup_old_sessions(_startup_db, Config.UPLOAD_FOLDER)
finally:
    _startup_db.close()


# ─── DB session per request ───────────────────────────────────────────────────

@app.before_request
def open_db():
    g.db = get_db_session()


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ─── Session ID ───────────────────────────────────────────────────────────────

@app.before_request
def ensure_session_id():
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())


def _sid():
    return session["session_id"]


def _get_memory():
    return memory_manager.get_session(_sid())


# ─── MIME type validator ──────────────────────────────────────────────────────

def _validate_mime(filepath: str) -> bool:
    """Validate MIME type using python-magic-bin if available, else skip."""
    try:
        import magic
        mime = magic.from_file(filepath, mime=True)
        return mime in Config.ALLOWED_MIME_TYPES
    except ImportError:
        logger.debug("python-magic not available — skipping MIME validation")
        return True
    except Exception as exc:
        logger.warning("MIME check failed for %s: %s", filepath, exc)
        return True


# ─── Page Routes ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze")
def analyze():
    mem = _get_memory()
    return render_template(
        "analyze.html",
        contract_name=mem.get_contract_name(),
        has_contract=bool(mem.get_contract_text()),
        feature_labels=FEATURE_LABELS,
    )


@app.route("/tools")
def tools():
    return render_template("tools.html")


@app.route("/history")
def history():
    page = request.args.get("page", 1, type=int)
    rows, total = get_session_analyses(g.db, _sid(), page=page, per_page=10)
    total_pages = max(1, -(-total // 10))   # ceiling division

    analyses = []
    for row in rows:
        analyses.append({
            "id": row.id,
            "filename": row.filename,
            "contract_type": row.contract_type,
            "health_score": row.health_score,
            "created_at": row.created_at.strftime("%Y-%m-%d %H:%M"),
        })

    return render_template(
        "history.html",
        analyses=analyses,
        page=page,
        total_pages=total_pages,
        total=total,
    )


# ─── API: Upload ──────────────────────────────────────────────────────────────

def apply_limit(rate: str):
    """Decorator to apply rate limit if limiter is available."""
    def decorator(func):
        if limiter:
            return limiter.limit(rate)(func)
        return func
    return decorator


@app.route("/api/upload", methods=["POST"])
@apply_limit("10 per hour")
def api_upload():
    """Handle contract file upload — extract text and store in session memory."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided."}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "No file selected."}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type. Accepted: PDF, DOCX, TXT, PNG, JPG, JPEG."}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    text = ""
    try:
        if not _validate_mime(filepath):
            return jsonify({"error": "File MIME type does not match its extension."}), 400

        text = extract_text(filepath)
        if not text.strip():
            return jsonify({"error": "Could not extract text. The file may be empty or image-only."}), 400

    finally:
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError as exc:
                logger.warning("Could not remove upload file %s: %s", filepath, exc)

    mem = _get_memory()
    mem.set_contract(text, filename)
    logger.info("Upload success: session=%s file=%s chars=%d", _sid(), filename, len(text))

    return jsonify({
        "success": True,
        "filename": filename,
        "char_count": len(text),
        "preview": text[:800] + ("..." if len(text) > 800 else ""),
        "message": f"'{filename}' uploaded ({len(text):,} characters extracted).",
    })



# ─── API: Unified Analyze ─────────────────────────────────────────────────────

@app.route("/api/analyze", methods=["POST"])
@apply_limit("10 per hour")
def api_analyze():
    """Run unified contract analysis (classify + analyze + obligations + health score)."""
    data = request.get_json() or {}
    contract_text = data.get("contract_text", "").strip()

    mem = _get_memory()
    if not contract_text:
        contract_text = mem.get_contract_text()
    if not contract_text:
        return jsonify({"error": "No contract text available. Please paste or upload a contract first."}), 400

    if contract_text != mem.get_contract_text():
        mem.set_contract(contract_text, "Pasted Text")

    # Fetch past embeddings for RAG
    past_embeddings = get_all_embeddings(g.db, _sid())

    evaluation_standard = data.get("evaluation_standard", DEFAULT_STANDARD)
    if evaluation_standard not in PLAYBOOKS:
        evaluation_standard = DEFAULT_STANDARD

    result = unified_analyze(
        contract_text=contract_text,
        memory_turns=mem.get_turns(),
        past_embeddings=past_embeddings,
        session_id=_sid(),
        filename=mem.get_contract_name() or "Pasted Text",
        evaluation_standard=evaluation_standard,
    )

    if "error" in result:
        logger.error("Analysis error for session=%s: %s", _sid(), result["error"])
        # Return 429 if it's a quota/rate error, 503 if all providers unavailable, else 500
        err_lower = result["error"].lower()
        if "quota" in err_lower or "rate" in err_lower or "429" in result["error"]:
            status_code = 429
        elif "unavailable" in err_lower or "all ai providers" in err_lower:
            status_code = 503
        else:
            status_code = 500
        return jsonify(result), status_code

    # Persist to DB
    embedding = result.pop("_embedding", [])
    contract_type = result.pop("_contract_type", "UNKNOWN")
    result.pop("_duration_ms", None)

    analysis_row = save_analysis(
        db=g.db,
        session_id=_sid(),
        filename=mem.get_contract_name() or "Pasted Text",
        contract_type=contract_type,
        full_text=contract_text,
        analysis_json=result,
        health_score=result.get("health_score", 0),
        embedding=embedding,
    )

    # Store summary in in-memory session for chat context
    summary = result.get("summary", "Analysis completed.")
    mem.add_turn("user", "[Unified Contract Analysis]")
    mem.add_turn("assistant", summary)
    mem.add_analysis("unified", summary)

    return jsonify({
        "analysis_id": analysis_row.id,
        "feature": "unified",
        "feature_label": "Full Contract Analysis",
        "result": result,
    })



# ─── API: Legacy Feature Analyze ──────────────────────────────────────────────

@app.route("/api/analyze/feature", methods=["POST"])
@apply_limit("10 per hour")
def api_analyze_feature():
    """Run a legacy feature-specific analysis (summarize, translate, tags, etc.)."""
    data = request.get_json() or {}
    feature = data.get("feature", "")
    contract_text = data.get("contract_text", "").strip()
    extra_context = data.get("extra_context", "")

    mem = _get_memory()
    if not contract_text:
        contract_text = mem.get_contract_text()
    if not contract_text:
        return jsonify({"error": "No contract text available."}), 400

    evaluation_standard = data.get("evaluation_standard", DEFAULT_STANDARD)
    if evaluation_standard not in PLAYBOOKS:
        evaluation_standard = DEFAULT_STANDARD

    result = analyze_contract(feature, contract_text, mem.get_turns(), extra_context, evaluation_standard)

    if "error" in result:
        status_code = 429 if "quota" in result["error"].lower() or "rate" in result["error"].lower() else 500
        return jsonify({
            "feature": feature,
            "feature_label": FEATURE_LABELS.get(feature, feature),
            "result": result,
            "error": result["error"],
        }), status_code

    feature_label = FEATURE_LABELS.get(feature, feature)
    summary = result.get("quick_summary", "Analysis completed.")
    mem.add_turn("user", f"[{feature_label}]")
    mem.add_turn("assistant", summary)
    mem.add_analysis(feature, summary)

    return jsonify({
        "feature": feature,
        "feature_label": FEATURE_LABELS.get(feature, feature),
        "result": result,
    })


# ─── API: Chat ────────────────────────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
@apply_limit("30 per hour")
def api_chat():
    """Handle follow-up chat about the loaded contract."""
    data = request.get_json() or {}
    user_message = data.get("message", "").strip()
    analysis_id = data.get("analysis_id")

    if not user_message:
        return jsonify({"error": "Message cannot be empty."}), 400
    if len(user_message) > 2000:
        return jsonify({"error": "Message too long. Please keep it under 2000 characters."}), 400

    mem = _get_memory()
    contract_text = mem.get_contract_text()
    result = chat_followup(user_message, contract_text, mem.get_turns())

    # Always persist the user message
    save_chat_message(g.db, _sid(), analysis_id, "user", user_message)
    mem.add_turn("user", user_message)

    # Only persist / add assistant turn on success
    if "error" not in result:
        answer = result.get("answer", "")
        save_chat_message(g.db, _sid(), analysis_id, "assistant", answer)
        mem.add_turn("assistant", answer)
        return jsonify(result)

    # Return proper error status so the frontend's !resp.ok guard fires
    status_code = 429 if "quota" in result["error"].lower() or "rate" in result["error"].lower() else 500
    return jsonify(result), status_code


# ─── API: History ─────────────────────────────────────────────────────────────

@app.route("/api/history/<int:analysis_id>", methods=["GET"])
@apply_limit("60 per hour")
def api_get_history(analysis_id):
    """Load a past analysis from DB (no Gemini re-call)."""
    stmt = _select(AnalysisModel).where(
        AnalysisModel.id == analysis_id,
        AnalysisModel.session_id == _sid(),
    )
    row = g.db.exec(stmt).first()
    if not row:
        abort(404)

    try:
        result = json.loads(row.analysis_json)
    except (json.JSONDecodeError, TypeError):
        result = {}

    return jsonify({
        "analysis_id": row.id,
        "filename": row.filename,
        "contract_type": row.contract_type,
        "health_score": row.health_score,
        "created_at": row.created_at.isoformat(),
        "result": result,
    })


@app.route("/api/history/<int:analysis_id>", methods=["DELETE"])
def api_delete_history(analysis_id):
    """Cascade-delete an analysis and all linked data."""
    success = delete_analysis(g.db, analysis_id, _sid())
    if not success:
        return jsonify({"error": "Analysis not found or not yours."}), 404
    return jsonify({"success": True, "message": "Analysis deleted."})


# ─── API: Export ──────────────────────────────────────────────────────────────

@app.route("/api/export/<int:analysis_id>", methods=["GET"])
@apply_limit("30 per hour")
def api_export(analysis_id):
    """Generate and return a PDF report for a given analysis."""
    if not _FPDF_AVAILABLE:
        return jsonify({"error": "PDF export is not available. Please install fpdf2."}), 503

    stmt = _select(AnalysisModel).where(
        AnalysisModel.id == analysis_id,
        AnalysisModel.session_id == _sid(),
    )
    row = g.db.exec(stmt).first()
    if not row:
        abort(404)

    try:
        pdf_bytes = generate_pdf(row)
    except Exception as exc:
        logger.error("PDF export failed for analysis_id=%d: %s", analysis_id, exc, exc_info=True)
        return jsonify({"error": "PDF generation failed. Please try again."}), 500

    filename_stem = os.path.splitext(row.filename)[0]
    download_name = f"clauseclear_{filename_stem}_{row.id}.pdf"

    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_name,
    )


# ─── API: Memory ─────────────────────────────────────────────────────────────

@app.route("/api/memory", methods=["GET"])
def api_memory():
    return jsonify(_get_memory().get_memory_summary())


@app.route("/api/clear-memory", methods=["POST"])
def api_clear_memory():
    _get_memory().clear()
    return jsonify({"success": True, "message": "Session memory cleared."})


# ─── API: Tools — Checklist ──────────────────────────────────────────────────

@app.route("/api/tools/checklist", methods=["POST"])
@apply_limit("10 per hour")
def api_tools_checklist():
    """Run the contract compliance checklist."""
    data = request.get_json() or {}
    contract_text = data.get("contract_text", "").strip()

    mem = _get_memory()
    if not contract_text:
        contract_text = mem.get_contract_text()
    if not contract_text:
        return jsonify({"error": "No contract text provided."}), 400

    result = run_checklist(contract_text)
    if "error" in result:
        status_code = 429 if "quota" in result["error"].lower() or "rate" in result["error"].lower() else 500
        return jsonify(result), status_code
    return jsonify(result)


# ─── Error handlers ───────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "The requested resource was not found."}), 404


@app.errorhandler(413)
def too_large(e):
    return jsonify({"error": "File too large. Maximum upload size is 10 MB."}), 413


@app.errorhandler(429)
def rate_limited(e):
    logger.warning("Rate limit hit: session=%s path=%s", _sid(), request.path)
    return jsonify({"error": "Too many requests. Please wait a moment before trying again."}), 429


# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_DEBUG", "false").lower() == "true",
        port=5000,
    )
