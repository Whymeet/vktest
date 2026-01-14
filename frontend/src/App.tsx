import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './components/Layout';
import { ProtectedRoute } from './components/ProtectedRoute';
import { FeatureRoute } from './components/FeatureRoute';
import { ToastProvider } from './components/Toast';
import { PageLoader } from './components/PageLoader';
import './index.css';

// Lazy load all pages for code splitting
const Login = lazy(() => import('./pages/Login').then(m => ({ default: m.Login })));
const Dashboard = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.Dashboard })));
const Accounts = lazy(() => import('./pages/Accounts').then(m => ({ default: m.Accounts })));
const Settings = lazy(() => import('./pages/Settings').then(m => ({ default: m.Settings })));
const Control = lazy(() => import('./pages/Control').then(m => ({ default: m.Control })));
const Logs = lazy(() => import('./pages/Logs').then(m => ({ default: m.Logs })));
const Whitelist = lazy(() => import('./pages/Whitelist').then(m => ({ default: m.Whitelist })));
const Statistics = lazy(() => import('./pages/Statistics').then(m => ({ default: m.Statistics })));
const ProfitableAds = lazy(() => import('./pages/ProfitableAds').then(m => ({ default: m.ProfitableAds })));
const Scaling = lazy(() => import('./pages/Scaling').then(m => ({ default: m.Scaling })));
const ScalingTaskDetail = lazy(() => import('./pages/ScalingTaskDetail').then(m => ({ default: m.ScalingTaskDetail })));
const DisableRules = lazy(() => import('./pages/DisableRules').then(m => ({ default: m.DisableRules })));
const BudgetRules = lazy(() => import('./pages/BudgetRules').then(m => ({ default: m.BudgetRules })));
const Profile = lazy(() => import('./pages/Profile').then(m => ({ default: m.Profile })));
const NotFound = lazy(() => import('./pages/NotFound').then(m => ({ default: m.NotFound })));

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
      <ToastProvider>
        <BrowserRouter>
          <Suspense fallback={<PageLoader />}>
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
                <Route path="scaling/task/:taskId" element={<FeatureRoute feature="scaling"><ScalingTaskDetail /></FeatureRoute>} />
                <Route path="disable-rules" element={<FeatureRoute feature="auto_disable"><DisableRules /></FeatureRoute>} />
                <Route path="budget-rules" element={<FeatureRoute feature="auto_disable"><BudgetRules /></FeatureRoute>} />
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
          </Suspense>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

export default App;
