// Auth utilities for API client

// Базовый URL API из окружения (в проде через nginx это '/api')
const API_URL = import.meta.env.VITE_API_URL || '/api';

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface User {
  id: number;
  username: string;
  email: string | null;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
  last_login: string | null;
}

/**
 * Get stored access token
 */
export const getAccessToken = (): string | null => {
  return localStorage.getItem('access_token');
};

/**
 * Get stored refresh token
 */
export const getRefreshToken = (): string | null => {
  return localStorage.getItem('refresh_token');
};

/**
 * Save tokens to localStorage
 */
export const saveTokens = (tokens: AuthTokens): void => {
  localStorage.setItem('access_token', tokens.access_token);
  localStorage.setItem('refresh_token', tokens.refresh_token);
};

/**
 * Clear stored tokens
 */
export const clearTokens = (): void => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
};

/**
 * Check if user is authenticated
 */
export const isAuthenticated = (): boolean => {
  return getAccessToken() !== null;
};

/**
 * Login with username and password
 */
export const login = async (username: string, password: string): Promise<AuthTokens> => {
  const response = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ username, password }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Login failed');
  }

  const tokens: AuthTokens = await response.json();
  saveTokens(tokens);
  return tokens;
};

/**
 * Logout - revoke current session and clear tokens
 */
export const logout = async (): Promise<void> => {
  const token = getAccessToken();
  const refreshToken = getRefreshToken();

  // Try to revoke refresh token on server
  if (token && refreshToken) {
    try {
      await fetch(`${API_URL}/auth/logout`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch (error) {
      // Continue with local logout even if server request fails
      console.error('Logout error:', error);
    }
  }

  // Clear tokens locally
  clearTokens();
  window.location.href = '/login';
};

/**
 * Logout from all devices - revoke all sessions
 */
export const logoutAll = async (): Promise<number> => {
  const token = getAccessToken();

  if (!token) {
    throw new Error('Not authenticated');
  }

  const response = await fetch(`${API_URL}/auth/logout-all`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    throw new Error('Failed to logout from all devices');
  }

  const data = await response.json();

  // Clear local tokens
  clearTokens();
  window.location.href = '/login';

  return data.revoked_tokens_count;
};

/**
 * Refresh access token using refresh token
 */
export const refreshAccessToken = async (): Promise<AuthTokens> => {
  const refreshToken = getRefreshToken();
  
  if (!refreshToken) {
    throw new Error('No refresh token available');
  }

  const response = await fetch(`${API_URL}/auth/refresh`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });

  if (!response.ok) {
    // Refresh token expired or invalid - logout
    logout();
    throw new Error('Session expired. Please login again.');
  }

  const tokens: AuthTokens = await response.json();
  saveTokens(tokens);
  return tokens;
};

/**
 * Get current user info
 */
export const getCurrentUser = async (): Promise<User> => {
  const token = getAccessToken();
  
  if (!token) {
    throw new Error('Not authenticated');
  }

  const response = await fetch(`${API_URL}/auth/me`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (response.status === 401) {
    // Try to refresh token
    try {
      await refreshAccessToken();
      // Retry with new token
      return getCurrentUser();
    } catch {
      logout();
      throw new Error('Session expired');
    }
  }

  if (!response.ok) {
    throw new Error('Failed to get user info');
  }

  return await response.json();
};

/**
 * Change password
 */
export const changePassword = async (currentPassword: string, newPassword: string): Promise<void> => {
  const token = getAccessToken();

  if (!token) {
    throw new Error('Not authenticated');
  }

  const response = await fetch(`${API_URL}/auth/change-password`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to change password');
  }

  const data = await response.json();

  // Password changed, all sessions revoked - need to re-login
  clearTokens();
  return data;
};

export interface Session {
  id: number;
  device_name: string | null;
  user_agent: string | null;
  ip_address: string | null;
  created_at: string;
  last_used_at: string;
  expires_at: string;
}

/**
 * Get list of active sessions
 */
export const getActiveSessions = async (): Promise<Session[]> => {
  const token = getAccessToken();

  if (!token) {
    throw new Error('Not authenticated');
  }

  const response = await fetch(`${API_URL}/auth/sessions`, {
    headers: {
      'Authorization': `Bearer ${token}`,
    },
  });

  if (response.status === 401) {
    // Try to refresh token
    try {
      await refreshAccessToken();
      // Retry with new token
      return getActiveSessions();
    } catch {
      logout();
      throw new Error('Session expired');
    }
  }

  if (!response.ok) {
    throw new Error('Failed to get active sessions');
  }

  const data = await response.json();
  return data.sessions;
};

