"""ClauseClear AI — Main Flask Application.

Routes:
  GET  /              → Landing page
  GET  /analyze       → Analysis page (split layout)
  GET  /history       → Session history page
  POST /api/upload    → Upload PDF/TXT, extract text, store in session
  POST /api/analyze   → Run one of 4 analysis features
  POST /api/chat      → Follow-up chat with session memory
  GET  /api/memory    → Get current session memory state
  POST /api/clear-memory → Clear session memory
"""

import os
import uuid
from flask import (
    Flask, render_template, request, jsonify, session
)
from werkzeug.utils import secure_filename
from config import Config
from services.memory_service import memory_manager
from services.document_service import extract_text, allowed_file
from services.gemini_service import analyze_contract, chat_followup, FEATURE_LABELS

# Initialize Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = Config.SECRET_KEY
app.config["UPLOAD_FOLDER"] = Config.UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH

# Ensure required directories exist
Config.init_app()


@app.before_request
def ensure_session_id():
    """Assign a unique session ID if not present."""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())


def _get_memory():
    """Get the SessionMemory instance for the current user."""
    return memory_manager.get_session(session["session_id"])


# ─────────────────────────────────────────────
# Page Routes
# ─────────────────────────────────────────────

@app.route("/")
def index():
    """Landing page."""
    return render_template("index.html")


@app.route("/analyze")
def analyze():
    """Analysis page with split layout."""
    mem = _get_memory()
    return render_template(
        "analyze.html",
        contract_name=mem.get_contract_name(),
        has_contract=bool(mem.get_contract_text()),
        feature_labels=FEATURE_LABELS,
    )


@app.route("/history")
def history():
    """Session history page."""
    mem = _get_memory()
    return render_template(
        "history.html",
        memory_summary=mem.get_memory_summary(),
        analysis_history=mem.get_analysis_history(),
    )


# ─────────────────────────────────────────────
# API: Upload
# ─────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Handle contract file upload — extract text and store in session."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided."}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type. Accepted formats: PDF, TXT, DOCX, PNG, JPG, JPEG."}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    # Extract text
    text = extract_text(filepath)
    if not text.strip():
        return jsonify({"error": "Could not extract text from the file. The file might be empty or image-based."}), 400

    # Store in session memory
    mem = _get_memory()
    mem.set_contract(text, filename)

    return jsonify({
        "success": True,
        "filename": filename,
        "char_count": len(text),
        "preview": text[:800] + ("..." if len(text) > 800 else ""),
        "message": f"Contract '{filename}' uploaded successfully ({len(text):,} characters extracted).",
    })


# ─────────────────────────────────────────────
# API: Analyze
# ─────────────────────────────────────────────

@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Run one of the 4 analysis features on the loaded contract."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No request body."}), 400

    feature = data.get("feature", "")
    contract_text = data.get("contract_text", "")
    extra_context = data.get("extra_context", "")

    mem = _get_memory()

    # Use pasted text if provided, otherwise use uploaded contract
    if not contract_text.strip():
        contract_text = mem.get_contract_text()

    if not contract_text.strip():
        return jsonify({"error": "No contract text available. Please paste text or upload a file first."}), 400

    # If user pasted new text (not from upload), store it
    if contract_text != mem.get_contract_text():
        mem.set_contract(contract_text, "Pasted Text")

    # Get conversation memory for context injection
    memory_turns = mem.get_turns()

    # Call Gemini with full context engineering
    result = analyze_contract(feature, contract_text, memory_turns, extra_context)

    # Store the analysis in memory
    feature_label = FEATURE_LABELS.get(feature, feature)
    if "error" not in result:
        summary = result.get("quick_summary", "Analysis completed.")
        mem.add_turn("user", f"[Analysis: {feature_label}]")
        mem.add_turn("assistant", summary)
        mem.add_analysis(feature, summary)

    return jsonify({
        "feature": feature,
        "feature_label": feature_label,
        "result": result,
    })


# ─────────────────────────────────────────────
# API: Chat
# ─────────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Handle follow-up chat questions about the contract."""
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "No message provided."}), 400

    user_message = data["message"].strip()
    if not user_message:
        return jsonify({"error": "Message cannot be empty."}), 400

    mem = _get_memory()
    contract_text = mem.get_contract_text()
    memory_turns = mem.get_turns()

    # Call Gemini with memory + contract context
    result = chat_followup(user_message, contract_text, memory_turns)

    # Store in conversation memory
    mem.add_turn("user", user_message)
    if "error" not in result:
        mem.add_turn("assistant", result.get("answer", ""))
    else:
        mem.add_turn("assistant", result.get("error", "Error occurred."))

    return jsonify(result)


# ─────────────────────────────────────────────
# API: Memory
# ─────────────────────────────────────────────

@app.route("/api/memory", methods=["GET"])
def api_memory():
    """Return current session memory state."""
    mem = _get_memory()
    return jsonify(mem.get_memory_summary())


@app.route("/api/clear-memory", methods=["POST"])
def api_clear_memory():
    """Clear all session memory."""
    mem = _get_memory()
    mem.clear()
    return jsonify({"success": True, "message": "Session memory cleared."})


# ─────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
