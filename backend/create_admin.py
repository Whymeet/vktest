#!/usr/bin/env python3
"""
Скрипт для создания администратора VK Ads Manager

Использование:
    python create_admin.py --username admin --password your_password
    python create_admin.py --username admin --password your_password --email admin@example.com
    python create_admin.py --interactive  # Интерактивный режим
"""
import argparse
import sys
from pathlib import Path
from getpass import getpass

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from database.database import SessionLocal, init_db
from database import crud
from auth.security import get_password_hash


def create_admin_user(username: str, password: str, email: str = None):
    """Создать пользователя-администратора"""
    
    # Initialize database if needed
    print("🔧 Инициализация базы данных...")
    init_db()
    
    db = SessionLocal()
    try:
        # Check if user already exists
        existing_user = crud.get_user_by_username(db, username)
        if existing_user:
            print(f"❌ Пользователь '{username}' уже существует!")
            print(f"   ID: {existing_user.id}")
            print(f"   Email: {existing_user.email}")
            print(f"   Создан: {existing_user.created_at}")
            return False
        
        # Check if email is taken
        if email:
            existing_email = crud.get_user_by_email(db, email)
            if existing_email:
                print(f"❌ Email '{email}' уже используется пользователем '{existing_email.username}'!")
                return False
        
        # Create admin user
        print(f"\n🔨 Создание администратора '{username}'...")
        password_hash = get_password_hash(password)
        
        user = crud.create_user(
            db,
            username=username,
            password_hash=password_hash,
            email=email,
            is_superuser=True
        )
        
        print(f"\n✅ Администратор успешно создан!")
        print(f"   ID: {user.id}")
        print(f"   Username: {user.username}")
        print(f"   Email: {user.email or '(не указан)'}")
        print(f"   Суперпользователь: {user.is_superuser}")
        print(f"   Активен: {user.is_active}")
        print(f"   Создан: {user.created_at}")
        print(f"\n🔐 Используйте эти данные для входа:")
        print(f"   Username: {user.username}")
        print(f"   Password: {'*' * len(password)}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Ошибка при создании пользователя: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def interactive_mode():
    """Интерактивный режим создания администратора"""
    print("="*60)
    print("  VK Ads Manager - Создание администратора")
    print("="*60)
    print()
    
    # Get username
    while True:
        username = input("Введите username (минимум 3 символа): ").strip()
        if len(username) >= 3:
            break
        print("❌ Username должен содержать минимум 3 символа!")
    
    # Get password
    while True:
        password = getpass("Введите пароль (минимум 6 символов): ").strip()
        if len(password) < 6:
            print("❌ Пароль должен содержать минимум 6 символов!")
            continue
        
        password_confirm = getpass("Подтвердите пароль: ").strip()
        if password != password_confirm:
            print("❌ Пароли не совпадают!")
            continue
        
        break
    
    # Get email (optional)
    email = input("Введите email (опционально, нажмите Enter чтобы пропустить): ").strip()
    if not email:
        email = None
    
    print()
    return create_admin_user(username, password, email)


def main():
    parser = argparse.ArgumentParser(
        description="Создать администратора VK Ads Manager"
    )
    
    parser.add_argument(
        "--username",
        type=str,
        help="Username администратора"
    )
    
    parser.add_argument(
        "--password",
        type=str,
        help="Пароль администратора"
    )
    
    parser.add_argument(
        "--email",
        type=str,
        help="Email администратора (опционально)"
    )
    
    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Интерактивный режим"
    )
    
    args = parser.parse_args()
    
    # Interactive mode
    if args.interactive or (not args.username and not args.password):
        success = interactive_mode()
    else:
        # Command-line mode
        if not args.username:
            print("❌ Укажите --username")
            sys.exit(1)
        
        if not args.password:
            print("❌ Укажите --password")
            sys.exit(1)
        
        if len(args.username) < 3:
            print("❌ Username должен содержать минимум 3 символа!")
            sys.exit(1)
        
        if len(args.password) < 6:
            print("❌ Пароль должен содержать минимум 6 символов!")
            sys.exit(1)
        
        success = create_admin_user(args.username, args.password, args.email)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

