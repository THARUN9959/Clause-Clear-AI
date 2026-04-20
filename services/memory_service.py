"""Session memory service for ClauseClear AI — Memento pattern for conversation history."""

import copy
from datetime import datetime
from config import Config


class SessionMemory:
    """
    Manages conversation memory for a single user session.
    Stores the last MAX_MEMORY_TURNS conversation turns and the active contract text.
    Implements Memento pattern for state snapshot/restore.
    """

    def __init__(self):
        self.turns = []            # List of {"role": "user"|"assistant", "content": "...", "timestamp": "..."}
        self.contract_text = ""    # Currently loaded contract text
        self.contract_name = ""    # Filename of the uploaded contract
        self.analysis_history = [] # History of analyses performed

    def add_turn(self, role, content):
        """
        Add a conversation turn (user query or assistant response).
        Automatically trims to the last MAX_MEMORY_TURNS turns.
        """
        self.turns.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })

        # Keep only the last N turns
        max_turns = Config.MAX_MEMORY_TURNS
        if len(self.turns) > max_turns:
            self.turns = self.turns[-max_turns:]

    def add_analysis(self, feature, result_summary):
        """Record an analysis event in the session history."""
        self.analysis_history.append({
            "feature": feature,
            "summary": result_summary,
            "timestamp": datetime.now().isoformat(),
            "contract_name": self.contract_name,
        })

    def set_contract(self, text, name=""):
        """Set the active contract text and filename."""
        self.contract_text = text
        self.contract_name = name

    def get_turns(self):
        """Get conversation turns for memory injection."""
        return copy.deepcopy(self.turns)

    def get_contract_text(self):
        """Get the active contract text for RAG-style injection."""
        return self.contract_text

    def get_contract_name(self):
        """Get the active contract filename."""
        return self.contract_name

    def get_analysis_history(self):
        """Get the full analysis history for this session."""
        return copy.deepcopy(self.analysis_history)

    def get_memory_summary(self):
        """Get a summary of current memory state for the API."""
        return {
            "turn_count": len(self.turns),
            "max_turns": Config.MAX_MEMORY_TURNS,
            "has_contract": bool(self.contract_text),
            "contract_name": self.contract_name,
            "analysis_count": len(self.analysis_history),
            "turns": [
                {
                    "role": t["role"],
                    "content": t["content"][:200] + ("..." if len(t["content"]) > 200 else ""),
                    "timestamp": t["timestamp"],
                }
                for t in self.turns
            ],
        }

    def clear(self):
        """Clear all memory — conversation turns, contract, and history."""
        self.turns.clear()
        self.contract_text = ""
        self.contract_name = ""
        self.analysis_history.clear()

    def clear_conversation(self):
        """Clear only conversation turns, keep contract and history."""
        self.turns.clear()

    # ─── Memento pattern ───

    def save_snapshot(self):
        """Create an immutable snapshot (Memento) of current state."""
        return {
            "turns": copy.deepcopy(self.turns),
            "contract_text": self.contract_text,
            "contract_name": self.contract_name,
            "analysis_history": copy.deepcopy(self.analysis_history),
            "timestamp": datetime.now().isoformat(),
        }

    def restore_snapshot(self, snapshot):
        """Restore state from a saved snapshot."""
        self.turns = copy.deepcopy(snapshot.get("turns", []))
        self.contract_text = snapshot.get("contract_text", "")
        self.contract_name = snapshot.get("contract_name", "")
        self.analysis_history = copy.deepcopy(snapshot.get("analysis_history", []))


class MemoryManager:
    """
    Caretaker — manages SessionMemory instances per Flask session ID.
    """

    def __init__(self):
        self._sessions = {}

    def get_session(self, session_id):
        """Get or create a SessionMemory for the given session ID."""
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionMemory()
        return self._sessions[session_id]

    def remove_session(self, session_id):
        """Delete a session entirely."""
        self._sessions.pop(session_id, None)


# Global singleton
memory_manager = MemoryManager()
