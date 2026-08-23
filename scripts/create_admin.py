import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.security import hash_password
from app.database import Base, SessionLocal, engine
from app.models.user import User, UserRole
import app.models  # noqa: F401


DEFAULT_EMAIL = "admin@elmshelf.com"
DEFAULT_PASSWORD = "ElmShelf#A9vR72!Qp"
DEFAULT_NAME = "System Administrator"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or reset a local admin user for the Furniture Store backend."
    )
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="Admin email address")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Admin password")
    parser.add_argument("--full-name", default=DEFAULT_NAME, help="Admin display name")
    parser.add_argument("--phone", default=None, help="Optional admin phone number")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        normalized_email = args.email.strip().lower()
        user = db.query(User).filter(User.email == normalized_email).first()

        if user is None:
            user = User(
                email=normalized_email,
                hashed_password=hash_password(args.password),
                full_name=args.full_name.strip(),
                phone=args.phone,
                role=UserRole.admin,
                is_active=True,
            )
            db.add(user)
            action = "created"
        else:
            user.hashed_password = hash_password(args.password)
            user.full_name = args.full_name.strip()
            user.phone = args.phone
            user.role = UserRole.admin
            user.is_active = True
            user.failed_login_attempts = 0
            user.lockout_until = None
            action = "updated"

        db.commit()
        db.refresh(user)
    finally:
        db.close()

    print(f"Admin user {action} successfully.")
    print(f"email={normalized_email}")
    print(f"password={args.password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
