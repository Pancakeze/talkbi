from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.db.session import engine
from app.models import DataSource, User
from app.schemas.data_source import DataSourceCreate, DataSourceOut
from app.services.excel_service import MAX_UPLOAD_BYTES, materialize_excel_staging

router = APIRouter(prefix="/data-sources", tags=["data-sources"])

_ALLOWED_SUFFIX = (".xlsx", ".xls", ".csv")


def _read_bounded_upload(file: UploadFile) -> bytes:
    raw = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds upload limit.",
        )
    return raw


def _get_owned_source(db: Session, source_id: int, user: User) -> DataSource:
    ds = (
        db.query(DataSource)
        .filter(DataSource.id == source_id, DataSource.owner_id == user.id)
        .first()
    )
    if not ds:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")
    return ds


@router.get("", response_model=list[DataSourceOut])
def list_data_sources(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(DataSource).filter(DataSource.owner_id == current_user.id).all()


@router.get("/{source_id}", response_model=DataSourceOut)
def get_data_source(
    source_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_owned_source(db, source_id, current_user)


@router.post("", response_model=DataSourceOut)
def create_data_source(
    payload: DataSourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = DataSource(
        name=payload.name,
        source_type=payload.source_type,
        connection_info=payload.connection_info,
        owner_id=current_user.id,
        status="active",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/excel/upload", response_model=DataSourceOut)
def upload_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filename = file.filename or "upload.xlsx"
    lower = filename.lower()
    if not any(lower.endswith(s) for s in _ALLOWED_SUFFIX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .xlsx, .xls, or .csv files are accepted.",
        )

    raw = _read_bounded_upload(file)

    item = DataSource(
        name=filename,
        source_type="excel",
        connection_info={"status": "staging"},
        owner_id=current_user.id,
        status="staging",
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    try:
        info = materialize_excel_staging(engine, item.id, raw, filename)
    except ValueError as exc:
        item.status = "failed"
        item.connection_info = {"error": str(exc)}
        db.add(item)
        db.commit()
        db.refresh(item)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    item.connection_info = info
    item.status = "active"
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
