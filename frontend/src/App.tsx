import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './components/Layout';
import { ProtectedRoute } from './components/ProtectedRoute';
import { FeatureRoute } from './components/FeatureRoute';
import { ToastProvider } from './components/Toast';
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
import { NotFound } from './pages/NotFound';
import { DEFAULT_QUERY_OPTIONS } from './api/queryConfig';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: DEFAULT_QUERY_OPTIONS,
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
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
            <Route path="profitable-ads" element={<FeatureRoute feature="leadstech"><ProfitableAds /></FeatureRoute>} />
            <Route path="scaling" element={<FeatureRoute feature="scaling"><Scaling /></FeatureRoute>} />
            <Route path="disable-rules" element={<FeatureRoute feature="auto_disable"><DisableRules /></FeatureRoute>} />
            <Route path="settings" element={<Settings />} />
            <Route path="control" element={<Control />} />
            <Route path="logs" element={<FeatureRoute feature="logs"><Logs /></FeatureRoute>} />
            <Route path="whitelist" element={<FeatureRoute feature="auto_disable"><Whitelist /></FeatureRoute>} />
            <Route path="profile" element={<Profile />} />
          </Route>

          {/* 404 page */}
          <Route path="/404" element={<NotFound />} />

          {/* Catch all - redirect to home or login */}
          <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

export default App;
