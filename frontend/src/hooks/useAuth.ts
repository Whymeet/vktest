import { useState, useEffect, useCallback } from 'react';
import { getCurrentUser, isAuthenticated as checkToken, logout as authLogout, getAccessToken } from '../api/auth';
import type { User } from '../api/auth';

export const useAuth = () => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [isAuth, setIsAuth] = useState(() => checkToken());

  const fetchUser = useCallback(async () => {
    const token = getAccessToken();
    
    if (!token) {
      setLoading(false);
      setIsAuth(false);
      setUser(null);
      return;
    }

    // Token exists - mark as authenticated immediately
    setIsAuth(true);

    try {
      const userData = await getCurrentUser();
      setUser(userData);
    } catch (error) {
      console.error('Failed to fetch user:', error);
      // Token might be invalid - but don't logout automatically
      // Let the API interceptor handle 401 errors
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  const logout = useCallback(() => {
    authLogout();
    setUser(null);
    setIsAuth(false);
  }, []);

  return { user, loading, isAuthenticated: isAuth, logout, refetch: fetchUser };
};

