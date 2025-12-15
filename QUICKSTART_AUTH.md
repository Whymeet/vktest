# Быстрый запуск с авторизацией

## 1. Запустить систему

```bash
docker-compose down
docker-compose up --build -d
```
 
## 2. Создать первого администратора

```bash
docker-compose exec backend python create_admin.py --interactive
```

Или:

```bash
docker-compose exec backend python create_admin.py --username admin --password admin123
```

## 3. Войти через API

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

Получите токены:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

## 4. Использовать токен

```bash
# Все запросы теперь требуют токен
curl http://localhost:8000/api/dashboard \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## 5. Создать других пользователей (как админ)

```bash
curl -X POST http://localhost:8000/api/auth/users \
  -H "Authorization: Bearer ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "user1",
    "password": "password123",
    "email": "user1@example.com"
  }'
```

## Фронтенд (UI готов!)

1. Откройте http://localhost:3000
2. Автоматически перенаправит на `/login`
3. Введите username и пароль
4. После входа увидите все свои данные
5. В сайдбаре внизу показан текущий пользователь и кнопка "Выйти"
6. Токены автоматически добавляются ко всем запросам

## UI Компоненты

Созданы следующие компоненты:

- ✅ `Login.tsx` - страница входа с формой
- ✅ `useAuth.ts` - хук для работы с авторизацией
- ✅ `ProtectedRoute.tsx` - защита роутов от неавторизованных
- ✅ `Layout.tsx` - обновлен (показ пользователя + кнопка выхода)
- ✅ `api/auth.ts` - функции авторизации
- ✅ `api/client.ts` - автодобавление токенов к запросам

## Как это работает

1. **Страница логина** - `/login` доступна без авторизации
2. **Все остальные страницы** - защищены, требуют токен
3. **Автоматическое перенаправление** - если не авторизован → на `/login`
4. **Показ пользователя** - в сайдбаре внизу (username + email)
5. **Кнопка выхода** - очищает токены и возвращает на логин
6. **Обновление токена** - автоматически при истечении

## Важно

- ✅ Каждый пользователь видит только свои данные
- ✅ Все процессы (scheduler, analysis) работают отдельно для каждого пользователя
- ✅ Логи разделены по пользователям: `user_1_scheduler_stdout.log`
- ✅ UI полностью готов - просто откройте браузер!

