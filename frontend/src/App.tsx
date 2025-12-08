import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { Accounts } from './pages/Accounts';
import { Settings } from './pages/Settings';
import { Control } from './pages/Control';
import { Logs } from './pages/Logs';
import { Whitelist } from './pages/Whitelist';
import { Statistics } from './pages/Statistics';
import { ProfitableAds } from './pages/ProfitableAds';
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
          <Route path="/" element={<Layout />}>
            <Route index element={<Dashboard />} />
            <Route path="accounts" element={<Accounts />} />
            <Route path="statistics" element={<Statistics />} />
            <Route path="profitable-ads" element={<ProfitableAds />} />
            <Route path="settings" element={<Settings />} />
            <Route path="control" element={<Control />} />
            <Route path="logs" element={<Logs />} />
            <Route path="whitelist" element={<Whitelist />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
