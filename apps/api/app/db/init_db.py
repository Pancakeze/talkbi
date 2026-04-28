from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models import User


def seed_data(db: Session) -> None:
    exists = db.query(User).filter(User.username == "admin").first()
    if exists:
        return
    admin = User(
        username="admin",
        full_name="系统管理员",
        role="admin",
        hashed_password=get_password_hash("admin123"),
    )
    analyst = User(
        username="analyst",
        full_name="业务分析员",
        role="business",
        hashed_password=get_password_hash("analyst123"),
    )
    db.add_all([admin, analyst])
    db.commit()
