import getpass
import sys

from .auth import hash_password
from .database import SessionLocal, init_db
from .models import User


def main():
    init_db()
    db = SessionLocal()

    username = sys.argv[1] if len(sys.argv) > 1 else input("Логин администратора: ").strip()
    if not username:
        print("Логин не указан")
        return

    user = db.query(User).filter(User.username == username).first()
    if not user:
        print(f"Пользователь «{username}» не найден")
        print("Доступные пользователи:")
        for u in db.query(User).all():
            print(f"  {u.username}")
        return

    if len(sys.argv) > 2:
        password = sys.argv[2]
    else:
        password = getpass.getpass("Новый пароль: ")
        confirm = getpass.getpass("Повторите пароль: ")
        if password != confirm:
            print("Пароли не совпадают")
            return

    user.password_hash = hash_password(password)
    db.commit()
    print(f"Пароль пользователя «{username}» изменён.")
    db.close()


if __name__ == "__main__":
    main()