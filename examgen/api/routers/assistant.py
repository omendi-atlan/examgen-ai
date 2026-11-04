"""Subject assistant endpoints — a grounded chatbot scoped to one workspace.

Every route resolves the workspace through :func:`require_workspace`, so the
assistant can only ever read material the requesting student owns. Sessions and
messages are persisted, so a conversation survives a page refresh.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_db
from ...models import ChatMessage, ChatSession, SubjectWorkspace, User
from ...schemas import (
    ChatAskRequest,
    ChatAskResponse,
    ChatMessageOut,
    ChatSessionDetail,
    ChatSessionOut,
)
from ...security import get_current_user, require_workspace
from ...services import assistant as assistant_service
from ...services import workspace as ws

router = APIRouter(prefix="/api/workspaces/{workspace_id}/assistant", tags=["assistant"])
global_router = APIRouter(prefix="/api/assistant", tags=["assistant"])

GREETING = (
    "Hello — I am your subject assistant. I answer only from the coursework you "
    "uploaded for this subject, and I cite the exact document and section I used. "
    "Ask me to explain a concept, list the topics and gaps, or tell you how you are "
    "performing."
)

SUGGESTED_PROMPTS = [
    "What topics does this subject cover?",
    "What is missing from my coursework?",
    "Which topics need diagrams?",
    "What learning outcomes should I meet?",
    "How should I prepare for the examination?",
    "How am I performing in this subject?",
]


def _session_or_404(db: Session, workspace_id: str, session_id: str) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if session is None or session.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found in this workspace")
    return session


@global_router.get("/prompts")
def suggested_prompts() -> dict:
    """Starter prompts the chat panel offers before a subject is even open.

    Deliberately unauthenticated: it exposes only static UI copy, never any
    workspace content, so it cannot leak academic material.
    """
    return {"greeting": GREETING, "prompts": SUGGESTED_PROMPTS}


@router.get("/sessions", response_model=list[ChatSessionOut])
def list_sessions(workspace: SubjectWorkspace = Depends(require_workspace),
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> list[ChatSession]:
    return list(db.scalars(select(ChatSession).where(
        ChatSession.workspace_id == workspace.id,
        ChatSession.user_id == user.id,
    ).order_by(ChatSession.updated_at.desc())))


@router.post("/sessions", response_model=ChatSessionDetail,
             status_code=status.HTTP_201_CREATED)
def create_session(workspace: SubjectWorkspace = Depends(require_workspace),
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> dict:
    session = ChatSession(workspace_id=workspace.id, user_id=user.id,
                          title="New conversation")
    db.add(session)
    db.flush()
    greeting = ChatMessage(session_id=session.id, workspace_id=workspace.id,
                           role="assistant", content=GREETING, intent="greeting",
                           grounded=False, suggestions=SUGGESTED_PROMPTS)
    db.add(greeting)
    ws.audit(db, workspace.id, user.id, "assistant.session_created", "chat_session",
             session.id, {"title": session.title})
    db.commit()
    db.refresh(session)
    return _detail(db, session)


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_session(session_id: str,
                workspace: SubjectWorkspace = Depends(require_workspace),
                db: Session = Depends(get_db)) -> dict:
    return _detail(db, _session_or_404(db, workspace.id, session_id))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str,
                   workspace: SubjectWorkspace = Depends(require_workspace),
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)) -> None:
    session = _session_or_404(db, workspace.id, session_id)
    ws.audit(db, workspace.id, user.id, "assistant.session_deleted", "chat_session",
             session.id, {"title": session.title})
    db.delete(session)
    db.commit()


@router.post("/ask", response_model=ChatAskResponse, status_code=status.HTTP_201_CREATED)
def ask(payload: ChatAskRequest,
        workspace: SubjectWorkspace = Depends(require_workspace),
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db)) -> dict:
    """Record a student message and return a grounded assistant reply."""
    if payload.session_id:
        session = _session_or_404(db, workspace.id, payload.session_id)
    else:
        session = ChatSession(workspace_id=workspace.id, user_id=user.id,
                              title=assistant_service.title_for(payload.message))
        db.add(session)
        db.flush()

    question = payload.message.strip()
    db.add(ChatMessage(session_id=session.id, workspace_id=workspace.id,
                       role="user", content=question, grounded=False))
    db.flush()

    reply = assistant_service.answer(db, workspace, question)
    message = ChatMessage(
        session_id=session.id, workspace_id=workspace.id, role="assistant",
        content=reply.content, intent=reply.intent, grounded=reply.grounded,
        citations=reply.citations, suggestions=reply.suggestions)
    db.add(message)

    # Keep the sidebar title meaningful without renaming an established thread.
    if session.title in {"", "New conversation"}:
        session.title = assistant_service.title_for(question)

    ws.audit(db, workspace.id, user.id, "assistant.question", "chat_session", session.id,
             {"intent": reply.intent, "grounded": reply.grounded,
              "citations": len(reply.citations)})
    db.commit()
    db.refresh(session)
    db.refresh(message)
    return {"session": session, "message": message}


def _detail(db: Session, session: ChatSession) -> dict:
    messages = list(db.scalars(select(ChatMessage).where(
        ChatMessage.session_id == session.id).order_by(ChatMessage.created_at.asc())))
    return {
        "id": session.id, "workspace_id": session.workspace_id, "title": session.title,
        "created_at": session.created_at, "updated_at": session.updated_at,
        "messages": [ChatMessageOut.model_validate(m) for m in messages],
    }
