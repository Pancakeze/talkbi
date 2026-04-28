from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import DataSource, ThemeField, ThemeJoin, ThemeLibrary, User
from app.schemas.theme import (
    ThemeCreate,
    ThemeFieldCreate,
    ThemeFieldOut,
    ThemeFieldPatch,
    ThemeJoinCreate,
    ThemeJoinOut,
    ThemeOut,
)

router = APIRouter(prefix="/theme-libraries", tags=["theme-libraries"])


def _get_owned_theme(db: Session, theme_id: int, user: User) -> ThemeLibrary:
    theme = (
        db.query(ThemeLibrary)
        .filter(ThemeLibrary.id == theme_id, ThemeLibrary.owner_id == user.id)
        .first()
    )
    if not theme:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Theme not found")
    return theme


def _assert_owned_data_source(db: Session, data_source_id: Optional[int], user: User) -> None:
    if data_source_id is None:
        return
    ds = (
        db.query(DataSource)
        .filter(DataSource.id == data_source_id, DataSource.owner_id == user.id)
        .first()
    )
    if not ds:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="data_source_id not found or not owned by current user",
        )


@router.get("", response_model=list[ThemeOut])
def list_themes(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    return db.query(ThemeLibrary).filter(ThemeLibrary.owner_id == current_user.id).all()


@router.get("/{theme_id}", response_model=ThemeOut)
def get_theme(
    theme_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_owned_theme(db, theme_id, current_user)


@router.post("", response_model=ThemeOut)
def create_theme(
    payload: ThemeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _assert_owned_data_source(db, payload.data_source_id, current_user)
    item = ThemeLibrary(
        name=payload.name,
        description=payload.description,
        owner_id=current_user.id,
        status="published",
        data_source_id=payload.data_source_id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{theme_id}/fields", response_model=ThemeFieldOut)
def add_theme_field(
    theme_id: int,
    payload: ThemeFieldCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_theme(db, theme_id, current_user)
    field = ThemeField(theme_id=theme_id, **payload.model_dump())
    db.add(field)
    db.commit()
    db.refresh(field)
    return field


@router.patch("/{theme_id}/fields/{field_id}", response_model=ThemeFieldOut)
def patch_theme_field(
    theme_id: int,
    field_id: int,
    payload: ThemeFieldPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_theme(db, theme_id, current_user)
    field = (
        db.query(ThemeField)
        .filter(ThemeField.id == field_id, ThemeField.theme_id == theme_id)
        .first()
    )
    if not field:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(field, k, v)
    db.add(field)
    db.commit()
    db.refresh(field)
    return field


@router.get("/{theme_id}/fields", response_model=list[ThemeFieldOut])
def list_theme_fields(
    theme_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_theme(db, theme_id, current_user)
    return db.query(ThemeField).filter(ThemeField.theme_id == theme_id).all()


@router.post("/{theme_id}/joins", response_model=ThemeJoinOut)
def add_theme_join(
    theme_id: int,
    payload: ThemeJoinCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_theme(db, theme_id, current_user)
    row = ThemeJoin(
        theme_id=theme_id,
        left_table=payload.left_table,
        right_table=payload.right_table,
        left_column=payload.left_column,
        right_column=payload.right_column,
        join_type=payload.join_type,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/{theme_id}/joins", response_model=list[ThemeJoinOut])
def list_theme_joins(
    theme_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_theme(db, theme_id, current_user)
    return db.query(ThemeJoin).filter(ThemeJoin.theme_id == theme_id).all()
