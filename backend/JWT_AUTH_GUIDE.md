# JWT Authentication System Guide

## Обзор

Система JWT аутентификации построена на следующих принципах:

- **Двойная токенизация**: Access Token (короткоживущий) + Refresh Token (долгоживущий)
- **Token Rotation**: Автоматическая ротация refresh токенов при обновлении
- **Database Storage**: Все refresh токены хранятся в БД для отслеживания и отзыва
- **Session Tracking**: Отслеживание устройств, IP-адресов и User-Agent
- **Security**: Автоматический отзыв токенов при смене пароля
- **Rate Limiting**: Защита от brute-force атак

---

## Архитектура

### 1. Access Token
- **Срок действия**: 24 часа (настраивается через `ACCESS_TOKEN_EXPIRE_MINUTES`)
- **Хранение**: Только на клиенте (localStorage/memory)
- **Использование**: Отправляется с каждым запросом в заголовке `Authorization: Bearer <token>`
- **Отзыв**: Невозможен (действует до истечения срока)

### 2. Refresh Token
- **Срок действия**: 7 дней (настраивается через `REFRESH_TOKEN_EXPIRE_DAYS`)
- **Хранение**: В базе данных + на клиенте
- **Использование**: Для получения нового Access Token
- **Отзыв**: Возможен в любой момент

### 3. Database Schema

```sql
CREATE TABLE refresh_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Token identification
    token_hash VARCHAR(255) NOT NULL UNIQUE,  -- SHA256 hash
    jti VARCHAR(36) NOT NULL UNIQUE,           -- JWT ID (UUID)

    -- Device/Session info
    user_agent VARCHAR(500),
    ip_address VARCHAR(45),
    device_name VARCHAR(255),

    -- Token validity
    expires_at TIMESTAMP NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at TIMESTAMP,

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

## API Endpoints

### 1. Login - `/api/auth/login`
**POST** - Вход в систему

**Request:**
```json
{
  "username": "admin",
  "password": "password123"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**Features:**
- ✅ Проверка пароля через bcrypt
- ✅ Сохранение refresh token в БД
- ✅ Отслеживание IP и User-Agent
- ✅ Rate limiting (60 req/min по умолчанию)

---

### 2. Refresh Token - `/api/auth/refresh`
**POST** - Обновление access token

**Request:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**Features:**
- ✅ Проверка токена в БД
- ✅ Автоматическая ротация (старый токен отзывается)
- ✅ Новый refresh token создается при каждом обновлении
- ✅ Защита от переиспользования токенов

---

### 3. Logout - `/api/auth/logout`
**POST** - Выход из текущей сессии

**Request:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Response:**
```json
{
  "message": "Logged out successfully"
}
```

**Features:**
- ✅ Отзыв конкретного refresh token
- ✅ Access token продолжает работать до истечения

---

### 4. Logout All - `/api/auth/logout-all`
**POST** - Выход со всех устройств

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "message": "Logged out from all devices successfully",
  "revoked_tokens_count": 5
}
```

**Features:**
- ✅ Отзыв всех refresh токенов пользователя
- ✅ Требует валидный access token
- ✅ Полезно при компрометации учетной записи

---

### 5. Active Sessions - `/api/auth/sessions`
**GET** - Список активных сессий

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "sessions": [
    {
      "id": 1,
      "device_name": null,
      "user_agent": "Mozilla/5.0...",
      "ip_address": "192.168.1.1",
      "created_at": "2025-12-21T10:00:00",
      "last_used_at": "2025-12-21T12:30:00",
      "expires_at": "2025-12-28T10:00:00"
    }
  ],
  "total": 1
}
```

---

### 6. Change Password - `/api/auth/change-password`
**POST** - Смена пароля

**Headers:**
```
Authorization: Bearer <access_token>
```

**Request:**
```json
{
  "current_password": "oldpass123",
  "new_password": "newpass456"
}
```

**Response:**
```json
{
  "message": "Password changed successfully. All sessions have been logged out.",
  "revoked_sessions": 3
}
```

**Features:**
- ✅ Автоматический отзыв всех refresh токенов
- ✅ Принудительный logout со всех устройств
- ✅ Защита от компрометации

---

## Frontend Integration

### 1. Хранение токенов

```typescript
// НЕ РЕКОМЕНДУЕТСЯ: localStorage (уязвимо к XSS)
localStorage.setItem('access_token', token);

// РЕКОМЕНДУЕТСЯ: В памяти + HttpOnly cookies для refresh token
let accessToken: string | null = null;
```

### 2. Axios Interceptor

```typescript
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000'
});

// Request interceptor - добавляем access token
api.interceptors.request.use(config => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor - обновляем токен при 401
api.interceptors.response.use(
  response => response,
  async error => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        const refreshToken = getRefreshToken();
        const { data } = await axios.post('/api/auth/refresh', {
          refresh_token: refreshToken
        });

        setAccessToken(data.access_token);
        setRefreshToken(data.refresh_token);

        originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
        return api(originalRequest);
      } catch (refreshError) {
        // Refresh token недействителен - redirect to login
        logout();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);
```

### 3. Login Flow

```typescript
async function login(username: string, password: string) {
  try {
    const { data } = await api.post('/api/auth/login', {
      username,
      password
    });

    setAccessToken(data.access_token);
    setRefreshToken(data.refresh_token);

    // Redirect to dashboard
    navigate('/dashboard');
  } catch (error) {
    console.error('Login failed:', error);
  }
}
```

### 4. Logout Flow

```typescript
async function logout() {
  try {
    const refreshToken = getRefreshToken();
    await api.post('/api/auth/logout', {
      refresh_token: refreshToken
    });
  } catch (error) {
    console.error('Logout failed:', error);
  } finally {
    // Clear tokens даже если запрос провалился
    clearAccessToken();
    clearRefreshToken();
    navigate('/login');
  }
}
```

---

## Security Best Practices

### 1. Переменные окружения

```bash
# .env или docker-compose.yml
JWT_SECRET_KEY=your-super-secret-key-min-32-characters
ACCESS_TOKEN_EXPIRE_MINUTES=1440  # 24 hours
REFRESH_TOKEN_EXPIRE_DAYS=7       # 7 days
RATE_LIMIT_PER_MINUTE=60          # login rate limit
```

### 2. Production Checklist

- [ ] Использовать сильный `JWT_SECRET_KEY` (min 32 символа)
- [ ] Включить HTTPS для всех API запросов
- [ ] Настроить CORS правильно
- [ ] Использовать rate limiting
- [ ] Регулярно чистить истекшие токены из БД
- [ ] Мониторить подозрительную активность

### 3. Cleanup Tasks

Добавьте cron job для очистки истекших токенов:

```python
# cleanup_tokens.py
from database import crud, SessionLocal

def cleanup_old_tokens():
    db = SessionLocal()
    try:
        # Delete expired tokens
        expired_count = crud.delete_expired_tokens(db)
        print(f"Deleted {expired_count} expired tokens")

        # Delete revoked tokens older than 30 days
        revoked_count = crud.delete_revoked_tokens(db, older_than_days=30)
        print(f"Deleted {revoked_count} old revoked tokens")
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_old_tokens()
```

---

## Troubleshooting

### Проблема: "Invalid or expired refresh token"

**Причины:**
- Токен был отозван (logout, смена пароля)
- Токен истек (> 7 дней)
- Токен не найден в БД

**Решение:** Перелогиниться

---

### Проблема: "Could not validate credentials"

**Причины:**
- Access token истек
- Access token поврежден
- Неправильный формат Authorization header

**Решение:** Использовать refresh token для получения нового access token

---

### Проблема: Rate limit exceeded

**Причины:**
- Слишком много попыток входа с одного IP

**Решение:** Подождать 1 минуту или увеличить `RATE_LIMIT_PER_MINUTE`

---

## Миграция БД

Выполните SQL скрипт для создания таблицы:

```bash
# В DBeaver или psql
psql -U vkads -d vkads -f backend/migrations/create_refresh_tokens_table.sql
```

Или вручную выполните содержимое файла:
`backend/migrations/create_refresh_tokens_table.sql`

---

## Testing

### 1. Test Login

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

### 2. Test Protected Endpoint

```bash
curl -X GET http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer <access_token>"
```

### 3. Test Refresh

```bash
curl -X POST http://localhost:8000/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'
```

### 4. Test Logout

```bash
curl -X POST http://localhost:8000/api/auth/logout \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'
```

---

## Заключение

Система JWT готова к использованию! Все endpoints защищены, токены отслеживаются в БД, а безопасность обеспечена через:

- ✅ Token rotation
- ✅ Automatic revocation on password change
- ✅ Session tracking
- ✅ Rate limiting
- ✅ Secure password hashing (bcrypt)

Для вопросов и багов см. issue tracker проекта.
