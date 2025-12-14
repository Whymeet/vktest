import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './components/Layout';
import { ProtectedRoute } from './components/ProtectedRoute';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { Accounts } from './pages/Accounts';
import { Settings } from './pages/Settings';
import { Control } from './pages/Control';
import { Logs } from './pages/Logs';
import { Whitelist } from './pages/Whitelist';
import { Statistics } from './pages/Statistics';
import { ProfitableAds } from './pages/ProfitableAds';
import { Scaling } from './pages/Scaling';
import { DisableRules } from './pages/DisableRules';
import { Profile } from './pages/Profile';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* Login page - not protected */}
          <Route path="/login" element={<Login />} />

          {/* Protected routes */}
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route index element={<Dashboard />} />
            <Route path="accounts" element={<Accounts />} />
            <Route path="statistics" element={<Statistics />} />
            <Route path="profitable-ads" element={<ProfitableAds />} />
            <Route path="scaling" element={<Scaling />} />
            <Route path="disable-rules" element={<DisableRules />} />
            <Route path="settings" element={<Settings />} />
            <Route path="control" element={<Control />} />
            <Route path="logs" element={<Logs />} />
            <Route path="whitelist" element={<Whitelist />} />
            <Route path="profile" element={<Profile />} />
          </Route>

          {/* Catch all - redirect to home or login */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
