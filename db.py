"""
ClauseClear AI — SQLite Persistence Layer via SQLModel.

Tables:
  Session     — One row per browser session
  Analysis    — One row per contract analysis (stores full JSON + embedding)
  ChatHistory — One row per chat message linked to an analysis
  Obligation  — One row per extracted obligation linked to an analysis

Thread safety: create_engine with check_same_thread=False.
Sessions managed via Flask g object (g.db) — never a global connection.
"""

import os
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from sqlmodel import Field, SQLModel, create_engine, Session, select, Relationship, func

logger = logging.getLogger(__name__)

# ─── Database file path ───────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clauseclear.sqlite")
_ENGINE = None


def get_engine():
    """Return the singleton SQLAlchemy engine."""
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(
            f"sqlite:///{DB_PATH}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
    return _ENGINE


# ─── SQLModel Table Definitions ───────────────────────────────────────────────


class SessionModel(SQLModel, table=True):
    """One row per browser session."""
    __tablename__ = "sessions"

    session_id: str = Field(primary_key=True, max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    analyses: List["AnalysisModel"] = Relationship(back_populates="session")


class AnalysisModel(SQLModel, table=True):
    """One row per contract analysis run."""
    __tablename__ = "analyses"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.session_id", index=True)
    filename: str = Field(max_length=255)
    contract_type: str = Field(default="UNKNOWN", max_length=64)
    full_text: str = Field(default="")
    analysis_json: str = Field(default="{}")   # serialised JSON string
    health_score: int = Field(default=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    embedding: str = Field(default="")         # JSON-encoded float list

    session: Optional[SessionModel] = Relationship(back_populates="analyses")
    chat_history: List["ChatHistoryModel"] = Relationship(back_populates="analysis")
    obligations: List["ObligationModel"] = Relationship(back_populates="analysis")


class ChatHistoryModel(SQLModel, table=True):
    """One chat message per row."""
    __tablename__ = "chat_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="sessions.session_id", index=True)
    analysis_id: Optional[int] = Field(default=None, foreign_key="analyses.id")
    role: str = Field(max_length=16)           # "user" | "assistant"
    content: str = Field(default="")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    analysis: Optional[AnalysisModel] = Relationship(back_populates="chat_history")


class ObligationModel(SQLModel, table=True):
    """One extracted obligation per row."""
    __tablename__ = "obligations"

    id: Optional[int] = Field(default=None, primary_key=True)
    analysis_id: int = Field(foreign_key="analyses.id", index=True)
    obligation: str = Field(default="")
    deadline_description: str = Field(default="")
    party: str = Field(default="")
    section: str = Field(default="")

    analysis: Optional[AnalysisModel] = Relationship(back_populates="obligations")


# ─── Database Lifecycle ───────────────────────────────────────────────────────


def create_db():
    """Create all tables (idempotent — safe to call on every startup)."""
    SQLModel.metadata.create_all(get_engine())
    logger.info("Database tables created/verified at %s", DB_PATH)


def get_db_session() -> Session:
    """Return a new SQLModel Session bound to the app engine."""
    return Session(get_engine())


# ─── Session Management ───────────────────────────────────────────────────────


def get_or_create_session(db: Session, session_id: str) -> SessionModel:
    """Get an existing session row or create a new one."""
    stmt = select(SessionModel).where(SessionModel.session_id == session_id)
    sess = db.exec(stmt).first()
    if sess is None:
        sess = SessionModel(session_id=session_id)
        db.add(sess)
        db.commit()
        db.refresh(sess)
    else:
        sess.last_accessed = datetime.now(timezone.utc)
        db.add(sess)
        db.commit()
    return sess


def save_analysis(
    db: Session,
    session_id: str,
    filename: str,
    contract_type: str,
    full_text: str,
    analysis_json: dict,
    health_score: int,
    embedding: Optional[list] = None,
) -> AnalysisModel:
    """Persist a completed analysis and its obligations to the database."""
    get_or_create_session(db, session_id)

    analysis = AnalysisModel(
        session_id=session_id,
        filename=filename,
        contract_type=contract_type,
        full_text=full_text[:50000],   # guard against huge contracts
        analysis_json=json.dumps(analysis_json),
        health_score=health_score,
        embedding=json.dumps(embedding or []),
    )
    db.add(analysis)
    db.commit()
    db.refresh(analysis)

    # Persist obligations as individual rows for fast querying
    obligations = analysis_json.get("obligations", [])
    for obl in obligations:
        obl_row = ObligationModel(
            analysis_id=analysis.id,
            obligation=obl.get("obligation", ""),
            deadline_description=obl.get("deadline_description", ""),
            party=obl.get("party", ""),
            section=obl.get("section", ""),
        )
        db.add(obl_row)

    db.commit()
    return analysis


def get_session_analyses(db: Session, session_id: str, page: int = 1, per_page: int = 10):
    """Return paginated analyses for a session, newest first."""
    offset = (page - 1) * per_page
    stmt = (
        select(AnalysisModel)
        .where(AnalysisModel.session_id == session_id)
        .order_by(AnalysisModel.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    rows = db.exec(stmt).all()

    # Use COUNT(*) — avoids fetching all rows just to count them
    count_stmt = select(func.count()).select_from(AnalysisModel).where(
        AnalysisModel.session_id == session_id
    )
    total = db.exec(count_stmt).one()
    return rows, total


def delete_analysis(db: Session, analysis_id: int, session_id: str) -> bool:
    """Cascade-delete an analysis and all linked chat history + obligations."""
    stmt = select(AnalysisModel).where(
        AnalysisModel.id == analysis_id,
        AnalysisModel.session_id == session_id,
    )
    analysis = db.exec(stmt).first()
    if not analysis:
        return False

    # Delete linked rows first (SQLite doesn't enforce FK cascade by default)
    for ch in db.exec(select(ChatHistoryModel).where(ChatHistoryModel.analysis_id == analysis_id)).all():
        db.delete(ch)
    for obl in db.exec(select(ObligationModel).where(ObligationModel.analysis_id == analysis_id)).all():
        db.delete(obl)

    db.delete(analysis)
    db.commit()
    return True


def save_chat_message(db: Session, session_id: str, analysis_id: Optional[int], role: str, content: str):
    """Persist a single chat message."""
    msg = ChatHistoryModel(
        session_id=session_id,
        analysis_id=analysis_id,
        role=role,
        content=content,
    )
    db.add(msg)
    db.commit()


def get_chat_history(db: Session, analysis_id: int, limit: int = 10) -> List[ChatHistoryModel]:
    """Get the last N chat messages for an analysis."""
    stmt = (
        select(ChatHistoryModel)
        .where(ChatHistoryModel.analysis_id == analysis_id)
        .order_by(ChatHistoryModel.timestamp.desc())
        .limit(limit)
    )
    return list(reversed(db.exec(stmt).all()))


# ─── Maintenance / Startup Cleanup ────────────────────────────────────────────


def cleanup_old_sessions(db: Session, upload_folder: str, days: int = 7):
    """
    Delete sessions older than `days` days and remove any orphaned upload files.
    Safe to call on every app startup — idempotent.
    """
    # Use timezone-aware UTC datetime to match how datetimes are stored in the DB
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    old_sessions = db.exec(
        select(SessionModel).where(SessionModel.last_accessed < cutoff)
    ).all()

    for sess in old_sessions:
        logger.info("Cleaning up expired session: %s", sess.session_id)
        # Cascade delete analyses, chat history, obligations
        analyses = db.exec(
            select(AnalysisModel).where(AnalysisModel.session_id == sess.session_id)
        ).all()
        for analysis in analyses:
            for ch in db.exec(select(ChatHistoryModel).where(ChatHistoryModel.analysis_id == analysis.id)).all():
                db.delete(ch)
            for obl in db.exec(select(ObligationModel).where(ObligationModel.analysis_id == analysis.id)).all():
                db.delete(obl)
            db.delete(analysis)
        db.delete(sess)

    db.commit()

    # Remove orphaned files in uploads/
    if os.path.isdir(upload_folder):
        for fname in os.listdir(upload_folder):
            if fname == ".gitkeep":
                continue
            fpath = os.path.join(upload_folder, fname)
            try:
                os.remove(fpath)
                logger.info("Removed orphaned upload file: %s", fpath)
            except OSError as exc:
                logger.warning("Could not remove upload file %s: %s", fpath, exc)


def get_all_embeddings(db: Session, session_id: str) -> List[dict]:
    """Fetch all stored embeddings for RAG similarity search."""
    stmt = select(AnalysisModel).where(
        AnalysisModel.session_id == session_id,
        AnalysisModel.embedding != "",
        AnalysisModel.embedding != "[]",
    )
    rows = db.exec(stmt).all()
    result = []
    for row in rows:
        try:
            vec = json.loads(row.embedding)
            if vec:
                result.append({
                    "analysis_id": row.id,
                    "health_score": row.health_score,
                    "contract_type": row.contract_type,
                    "filename": row.filename,
                    "embedding": vec,
                })
        except (json.JSONDecodeError, TypeError):
            pass
    return result
