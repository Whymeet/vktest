"""
Скрипт для добавления user_id к существующим записям scaling_configs и scaling_logs
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from database import SessionLocal
from database.models import ScalingConfig, ScalingLog, User

def fix_user_ids():
    db = SessionLocal()

    try:
        # Получаем первого пользователя (или создаём, если нет)
        user = db.query(User).first()
        if not user:
            print("❌ Нет пользователей в базе данных")
            return

        print(f"✅ Используем пользователя: {user.username} (ID: {user.id})")

        # Обновляем scaling_configs без user_id
        configs = db.query(ScalingConfig).filter(ScalingConfig.user_id == None).all()
        if configs:
            print(f"📝 Найдено {len(configs)} конфигураций без user_id")
            for config in configs:
                config.user_id = user.id
                print(f"   ✅ Обновлена конфигурация: {config.name} (ID: {config.id})")
        else:
            print("✅ Все конфигурации уже имеют user_id")

        # Обновляем scaling_logs без user_id
        logs = db.query(ScalingLog).filter(ScalingLog.user_id == None).all()
        if logs:
            print(f"📝 Найдено {len(logs)} логов без user_id")
            for log in logs:
                log.user_id = user.id
            print(f"   ✅ Обновлено {len(logs)} логов")
        else:
            print("✅ Все логи уже имеют user_id")

        db.commit()
        print("\n🎉 Готово!")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_user_ids()
