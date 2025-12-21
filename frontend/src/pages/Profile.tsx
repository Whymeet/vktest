import { useState, useEffect } from 'react';
import { useAuth } from '../hooks/useAuth';
import { api } from '../api/client';
import { getActiveSessions, logoutAll, type Session } from '../api/auth';

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
    <div className="max-w-2xl mx-auto space-y-8">
      <h1 className="text-2xl font-bold text-gray-900">Личный кабинет</h1>

      {/* Profile Section */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Данные профиля</h2>
        
        <form onSubmit={handleProfileSubmit} className="space-y-4">
          <div>
            <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-1">
              Логин
            </label>
            <input
              type="text"
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
              required
              minLength={3}
            />
          </div>

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
              Email (необязательно)
            </label>
            <input
              type="email"
              id="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
              placeholder="example@mail.com"
            />
          </div>

          {profileError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {profileError}
            </div>
          )}

          {profileSuccess && (
            <div className="p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
              {profileSuccess}
            </div>
          )}

          <button
            type="submit"
            disabled={profileLoading}
            className="w-full py-2 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-medium rounded-lg transition duration-200"
          >
            {profileLoading ? 'Сохранение...' : 'Сохранить изменения'}
          </button>
        </form>
      </div>

      {/* Password Section */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Смена пароля</h2>
        
        <form onSubmit={handlePasswordSubmit} className="space-y-4">
          <div>
            <label htmlFor="currentPassword" className="block text-sm font-medium text-gray-700 mb-1">
              Текущий пароль
            </label>
            <input
              type="password"
              id="currentPassword"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
              required
            />
          </div>

          <div>
            <label htmlFor="newPassword" className="block text-sm font-medium text-gray-700 mb-1">
              Новый пароль
            </label>
            <input
              type="password"
              id="newPassword"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
              required
              minLength={6}
              placeholder="Минимум 6 символов"
            />
          </div>

          <div>
            <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 mb-1">
              Подтвердите новый пароль
            </label>
            <input
              type="password"
              id="confirmPassword"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className={`w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition ${
                confirmPassword && newPassword !== confirmPassword 
                  ? 'border-red-300 bg-red-50' 
                  : 'border-gray-300'
              }`}
              required
              minLength={6}
              placeholder="Повторите новый пароль"
            />
            {confirmPassword && newPassword !== confirmPassword && (
              <p className="mt-1 text-sm text-red-600">Пароли не совпадают</p>
            )}
          </div>

          {passwordError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {passwordError}
            </div>
          )}

          {passwordSuccess && (
            <div className="p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
              {passwordSuccess}
            </div>
          )}

          <button
            type="submit"
            disabled={passwordLoading || (confirmPassword !== '' && newPassword !== confirmPassword)}
            className="w-full py-2 px-4 bg-orange-600 hover:bg-orange-700 disabled:bg-orange-400 text-white font-medium rounded-lg transition duration-200"
          >
            {passwordLoading ? 'Смена пароля...' : 'Сменить пароль'}
          </button>
        </form>
      </div>

      {/* Active Sessions */}
      <div className="bg-white rounded-lg shadow-md p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-gray-800">Активные сессии</h2>
          <button
            onClick={loadSessions}
            disabled={sessionsLoading}
            className="px-3 py-1 text-sm text-blue-600 hover:text-blue-700 disabled:text-gray-400"
          >
            {sessionsLoading ? 'Загрузка...' : 'Обновить'}
          </button>
        </div>

        {sessionsError && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm mb-4">
            {sessionsError}
          </div>
        )}

        {sessionsLoading && sessions.length === 0 ? (
          <p className="text-gray-500 text-center py-4">Загрузка сессий...</p>
        ) : sessions.length === 0 ? (
          <p className="text-gray-500 text-center py-4">Нет активных сессий</p>
        ) : (
          <div className="space-y-3">
            {sessions.map((session) => (
              <div key={session.id} className="p-4 bg-gray-50 rounded-lg border border-gray-200">
                <div className="flex justify-between items-start">
                  <div className="space-y-1 text-sm flex-1">
                    <p className="text-gray-700">
                      <strong>IP:</strong> {session.ip_address || 'Неизвестно'}
                    </p>
                    {session.user_agent && (
                      <p className="text-gray-600 truncate max-w-md" title={session.user_agent}>
                        <strong>Устройство:</strong> {session.user_agent}
                      </p>
                    )}
                    <p className="text-gray-600">
                      <strong>Создана:</strong> {new Date(session.created_at).toLocaleString('ru-RU')}
                    </p>
                    <p className="text-gray-600">
                      <strong>Последняя активность:</strong> {new Date(session.last_used_at).toLocaleString('ru-RU')}
                    </p>
                    <p className="text-gray-600">
                      <strong>Истекает:</strong> {new Date(session.expires_at).toLocaleString('ru-RU')}
                    </p>
                  </div>
                </div>
              </div>
            ))}

            {sessions.length > 1 && (
              <button
                onClick={handleLogoutAll}
                className="w-full mt-4 py-2 px-4 bg-red-600 hover:bg-red-700 text-white font-medium rounded-lg transition duration-200"
              >
                Выйти из всех устройств ({sessions.length})
              </button>
            )}
          </div>
        )}
      </div>

      {/* Account Info */}
      <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-600">
        <p><strong>ID:</strong> {user?.id}</p>
        <p><strong>Статус:</strong> {user?.is_active ? 'Активен' : 'Неактивен'}</p>
        <p><strong>Роль:</strong> {user?.is_superuser ? 'Администратор' : 'Пользователь'}</p>
        {user?.last_login && (
          <p><strong>Последний вход:</strong> {new Date(user.last_login).toLocaleString('ru-RU')}</p>
        )}
      </div>
    </div>
  );
};

