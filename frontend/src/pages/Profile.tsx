import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { api } from '../api/client';
import { getActiveSessions, logoutAll, type Session } from '../api/auth';
import { User, Key, Monitor, RefreshCw, LogOut, Shield, Clock } from 'lucide-react';

export const Profile = () => {
  const { user, refetch } = useAuth();

  // Profile form state
  const [username, setUsername] = useState(user?.username || '');
  const [email, setEmail] = useState(user?.email || '');
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState('');
  const [profileSuccess, setProfileSuccess] = useState('');

  // Password form state
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordError, setPasswordError] = useState('');
  const [passwordSuccess, setPasswordSuccess] = useState('');

  // Sessions state
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [sessionsError, setSessionsError] = useState('');

  // Load sessions on mount
  useEffect(() => {
    loadSessions();
  }, []);

  const loadSessions = async () => {
    setSessionsLoading(true);
    setSessionsError('');
    try {
      const data = await getActiveSessions();
      setSessions(data);
    } catch (err: any) {
      setSessionsError(err.message || 'Ошибка загрузки сессий');
    } finally {
      setSessionsLoading(false);
    }
  };

  const handleLogoutAll = async () => {
    if (!confirm('Вы уверены? Все активные сессии будут завершены, включая текущую.')) {
      return;
    }

    try {
      await logoutAll();
    } catch (err: any) {
      alert('Ошибка: ' + (err.message || 'Не удалось выйти из всех сессий'));
    }
  };

  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileError('');
    setProfileSuccess('');
    setProfileLoading(true);

    try {
      await api.put('/auth/me', { username, email: email || null });
      setProfileSuccess('Профиль успешно обновлён');
      refetch?.();
    } catch (err: any) {
      setProfileError(err.response?.data?.detail || 'Ошибка обновления профиля');
    } finally {
      setProfileLoading(false);
    }
  };

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError('');
    setPasswordSuccess('');

    // Validate passwords match
    if (newPassword !== confirmPassword) {
      setPasswordError('Пароли не совпадают');
      return;
    }

    // Validate password length
    if (newPassword.length < 6) {
      setPasswordError('Пароль должен быть не менее 6 символов');
      return;
    }

    setPasswordLoading(true);

    try {
      await api.post('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword
      });
      setPasswordSuccess('Пароль успешно изменён');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: any) {
      setPasswordError(err.response?.data?.detail || 'Ошибка смены пароля');
    } finally {
      setPasswordLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-12 h-12 bg-blue-600 rounded-xl flex items-center justify-center">
          <User className="w-6 h-6 text-white" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-white">Личный кабинет</h1>
          <p className="text-zinc-400 text-sm">Управление профилем и безопасностью</p>
        </div>
      </div>

      {/* Profile Section */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <User className="w-5 h-5 text-blue-400" />
          <h2 className="text-lg font-semibold text-white">Данные профиля</h2>
        </div>

        <form onSubmit={handleProfileSubmit} className="space-y-4">
          <div>
            <label htmlFor="username" className="label">
              Логин
            </label>
            <input
              type="text"
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="input"
              required
              minLength={3}
            />
          </div>

          <div>
            <label htmlFor="email" className="label">
              Email (необязательно)
            </label>
            <input
              type="email"
              id="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input"
              placeholder="example@mail.com"
            />
          </div>

          {profileError && (
            <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
              {profileError}
            </div>
          )}

          {profileSuccess && (
            <div className="p-3 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400 text-sm">
              {profileSuccess}
            </div>
          )}

          <button
            type="submit"
            disabled={profileLoading}
            className="btn btn-primary w-full justify-center"
          >
            {profileLoading ? 'Сохранение...' : 'Сохранить изменения'}
          </button>
        </form>
      </div>

      {/* Password Section */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Key className="w-5 h-5 text-orange-400" />
          <h2 className="text-lg font-semibold text-white">Смена пароля</h2>
        </div>

        <form onSubmit={handlePasswordSubmit} className="space-y-4">
          <div>
            <label htmlFor="currentPassword" className="label">
              Текущий пароль
            </label>
            <input
              type="password"
              id="currentPassword"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="input"
              required
            />
          </div>

          <div>
            <label htmlFor="newPassword" className="label">
              Новый пароль
            </label>
            <input
              type="password"
              id="newPassword"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="input"
              required
              minLength={6}
              placeholder="Минимум 6 символов"
            />
          </div>

          <div>
            <label htmlFor="confirmPassword" className="label">
              Подтвердите новый пароль
            </label>
            <input
              type="password"
              id="confirmPassword"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className={`input ${
                confirmPassword && newPassword !== confirmPassword
                  ? 'border-red-500 bg-red-500/10'
                  : ''
              }`}
              required
              minLength={6}
              placeholder="Повторите новый пароль"
            />
            {confirmPassword && newPassword !== confirmPassword && (
              <p className="mt-1 text-sm text-red-400">Пароли не совпадают</p>
            )}
          </div>

          {passwordError && (
            <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
              {passwordError}
            </div>
          )}

          {passwordSuccess && (
            <div className="p-3 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400 text-sm">
              {passwordSuccess}
            </div>
          )}

          <button
            type="submit"
            disabled={passwordLoading || (confirmPassword !== '' && newPassword !== confirmPassword)}
            className="btn btn-warning w-full justify-center"
          >
            {passwordLoading ? 'Смена пароля...' : 'Сменить пароль'}
          </button>
        </form>
      </div>

      {/* Active Sessions */}
      <div className="card">
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-2">
            <Monitor className="w-5 h-5 text-purple-400" />
            <h2 className="text-lg font-semibold text-white">Активные сессии</h2>
          </div>
          <button
            onClick={loadSessions}
            disabled={sessionsLoading}
            className="btn btn-secondary text-sm"
          >
            <RefreshCw className={`w-4 h-4 ${sessionsLoading ? 'animate-spin' : ''}`} />
            {sessionsLoading ? 'Загрузка...' : 'Обновить'}
          </button>
        </div>

        {sessionsError && (
          <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm mb-4">
            {sessionsError}
          </div>
        )}

        {sessionsLoading && sessions.length === 0 ? (
          <p className="text-zinc-400 text-center py-4">Загрузка сессий...</p>
        ) : sessions.length === 0 ? (
          <p className="text-zinc-400 text-center py-4">Нет активных сессий</p>
        ) : (
          <div className="space-y-3">
            {sessions.map((session) => (
              <div key={session.id} className="p-4 bg-zinc-800 rounded-lg border border-zinc-700">
                <div className="flex justify-between items-start">
                  <div className="space-y-2 text-sm flex-1">
                    <p className="text-zinc-300">
                      <span className="text-zinc-500">IP:</span> {session.ip_address || 'Неизвестно'}
                    </p>
                    {session.user_agent && (
                      <p className="text-zinc-400 truncate max-w-md" title={session.user_agent}>
                        <span className="text-zinc-500">Устройство:</span> {session.user_agent}
                      </p>
                    )}
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-zinc-400">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        Создана: {new Date(session.created_at).toLocaleString('ru-RU')}
                      </span>
                      <span>
                        Активность: {new Date(session.last_used_at).toLocaleString('ru-RU')}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ))}

            {sessions.length > 1 && (
              <button
                onClick={handleLogoutAll}
                className="btn btn-danger w-full justify-center mt-4"
              >
                <LogOut className="w-4 h-4" />
                Выйти из всех устройств ({sessions.length})
              </button>
            )}
          </div>
        )}
      </div>

      {/* Account Info */}
      <div className="card bg-zinc-800/50">
        <div className="flex items-center gap-2 mb-3">
          <Shield className="w-5 h-5 text-zinc-400" />
          <h3 className="text-sm font-medium text-zinc-400">Информация об аккаунте</h3>
        </div>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <p className="text-zinc-500">ID:</p>
          <p className="text-zinc-300">{user?.id}</p>

          <p className="text-zinc-500">Статус:</p>
          <p className={user?.is_active ? 'text-green-400' : 'text-red-400'}>
            {user?.is_active ? 'Активен' : 'Неактивен'}
          </p>

          <p className="text-zinc-500">Роль:</p>
          <p className={user?.is_superuser ? 'text-yellow-400' : 'text-zinc-300'}>
            {user?.is_superuser ? 'Администратор' : 'Пользователь'}
          </p>

          {user?.last_login && (
            <>
              <p className="text-zinc-500">Последний вход:</p>
              <p className="text-zinc-300">{new Date(user.last_login).toLocaleString('ru-RU')}</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
