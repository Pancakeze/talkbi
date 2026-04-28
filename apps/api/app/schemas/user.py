from app.schemas.common import Timestamped


class UserOut(Timestamped):
    username: str
    full_name: str
    role: str
