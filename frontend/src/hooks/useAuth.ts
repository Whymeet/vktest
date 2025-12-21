import { useState, useEffect, useCallback } from 'react';
import { getCurrentUser, getUserFeatures, isAuthenticated as checkToken, logout as authLogout, getAccessToken } from '../api/auth';
import type { User } from '../api/auth';

export const useAuth = () => {
  const [user, setUser] = useState<User | null>(null);
  const [features, setFeatures] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [isAuth, setIsAuth] = useState(() => checkToken());

  const fetchUser = useCallback(async () => {
    const token = getAccessToken();

    if (!token) {
      setLoading(false);
      setIsAuth(false);
      setUser(null);
      setFeatures([]);
      return;
    }

    // Token exists - mark as authenticated immediately
    setIsAuth(true);

    try {
      const [userData, featuresData] = await Promise.all([
        getCurrentUser(),
        getUserFeatures()
      ]);
      setUser(userData);
      setFeatures(featuresData.features);
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
    setFeatures([]);
    setIsAuth(false);
  }, []);

  // Helper to check if user has a specific feature
  const hasFeature = useCallback((feature: string): boolean => {
    return features.includes(feature);
  }, [features]);

  return { user, features, hasFeature, loading, isAuthenticated: isAuth, logout, refetch: fetchUser };
};
