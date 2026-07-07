"""Notebook API — full management for the notes-first redesign. Auth-scoped to the caller.

Notebooks organize notes (Evernote-style). Every note belongs to a notebook; deleting a
notebook re-homes its notes to the user's default notebook (never deletes notes).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.notebook import Notebook
from app.models.quick_note import QuickNote
from app.models.user import User
from app.schemas.dashboard import Message
from app.schemas.notebook import NotebookCreate, NotebookOut, NotebookUpdate

router = APIRouter(prefix="/api/notebooks", tags=["notebooks"])


def _counts(db: Session, user_id: int) -> dict[int, int]:
    rows = (db.query(QuickNote.notebook_id, func.count(QuickNote.id))
            .filter(QuickNote.user_id == user_id, QuickNote.deleted.is_(False))
            .group_by(QuickNote.notebook_id).all())
    return {nb_id: n for nb_id, n in rows}


def _out(nb: Notebook, counts: dict[int, int]) -> NotebookOut:
    o = NotebookOut.model_validate(nb)
    o.note_count = counts.get(nb.id, 0)
    return o


def _default_notebook(db: Session, user_id: int) -> Notebook:
    nb = db.query(Notebook).filter(Notebook.user_id == user_id, Notebook.is_default.is_(True)).first()
    if not nb:
        nb = Notebook(user_id=user_id, name="Personal", icon="📓", is_default=True)
        db.add(nb)
        db.commit()
        db.refresh(nb)
    return nb


@router.get("", response_model=list[NotebookOut])
def list_notebooks(include_archived: bool = False,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Notebook).filter(Notebook.user_id == user.id)
    if not include_archived:
        q = q.filter(Notebook.is_archived.is_(False))
    nbs = q.order_by(Notebook.is_default.desc(), Notebook.is_favorite.desc(), Notebook.name).all()
    counts = _counts(db, user.id)
    return [_out(nb, counts) for nb in nbs]


@router.post("", response_model=NotebookOut, status_code=201)
def create_notebook(body: NotebookCreate, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    nb = Notebook(user_id=user.id, **body.model_dump())
    db.add(nb)
    db.commit()
    db.refresh(nb)
    return _out(nb, {})


def _owned(db: Session, user: User, notebook_id: int) -> Notebook:
    nb = db.get(Notebook, notebook_id)
    if not nb or nb.user_id != user.id:
        raise HTTPException(status_code=404, detail="notebook not found")
    return nb


@router.get("/{notebook_id}", response_model=NotebookOut)
def get_notebook(notebook_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(_owned(db, user, notebook_id), _counts(db, user.id))


@router.put("/{notebook_id}", response_model=NotebookOut)
def update_notebook(notebook_id: int, body: NotebookUpdate,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    nb = _owned(db, user, notebook_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(nb, k, v)
    db.commit()
    db.refresh(nb)
    return _out(nb, _counts(db, user.id))


@router.delete("/{notebook_id}", response_model=Message)
def delete_notebook(notebook_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    nb = _owned(db, user, notebook_id)
    if nb.is_default:
        raise HTTPException(status_code=400, detail="cannot delete the default notebook")
    dest = _default_notebook(db, user.id)
    (db.query(QuickNote).filter(QuickNote.user_id == user.id, QuickNote.notebook_id == notebook_id)
     .update({QuickNote.notebook_id: dest.id}, synchronize_session=False))
    db.delete(nb)
    db.commit()
    return Message(detail="notebook deleted; its notes moved to the default notebook")
