---
name: Frontend Performance Optimization
overview: "План оптимизации фронтенда включает: внедрение lazy loading для страниц, оптимизацию React Query кэширования, уменьшение частоты polling, оптимизацию бандла Vite, и исправление паттернов рендеринга."
todos:
  - id: lazy-loading
    content: Добавить React.lazy() и Suspense для всех страниц в App.tsx
    status: pending
  - id: query-stale
    content: Настроить staleTime и gcTime в QueryClient
    status: pending
  - id: reduce-polling
    content: Уменьшить refetchInterval на всех страницах (Dashboard, Statistics, ProfitableAds, Scaling)
    status: pending
  - id: vite-chunks
    content: Добавить manualChunks в vite.config.ts для оптимизации бандла
    status: pending
  - id: virtualize-stats
    content: Добавить виртуализацию таблицы в Statistics.tsx
    status: pending
  - id: loading-skeleton
    content: Добавить Suspense fallback с skeleton UI вместо спиннера
    status: pending
---

# Оптимизация производительности фронтенда

## Выявленные проблемы

### 1. Отсутствие Code Splitting (Критично)

В [App.tsx](frontend/src/App.tsx) все страницы импортируются синхронно:

```1:19:frontend/src/App.tsx
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
```

Это приводит к загрузке **всего кода** при первом посещении. Крупные страницы:

- `ProfitableAds.tsx` - 1538 строк
- `Scaling.tsx` - 1245 строк  
- `DisableRules.tsx` - 768 строк
- `Statistics.tsx` - 500 строк

### 2. Агрессивный Polling (Критично)

Множество запросов с очень частым `refetchInterval`:

| Страница | Запрос | Интервал |

|----------|--------|----------|

| Dashboard | dashboard | 5 сек |

| Dashboard | processStatus | 3 сек |

| Statistics | disabledBanners | 5 сек |

| ProfitableAds | analysisResults | 5 сек |

| ProfitableAds | analysisStatus | 3 сек |

Это создает постоянную нагрузку даже когда пользователь не взаимодействует.

### 3. Отсутствие staleTime в React Query (Критично)

```22:29:frontend/src/App.tsx
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
```

Без `staleTime` каждый mount компонента вызывает новый запрос, даже если данные только что получены.

### 4. Блокирующая аутентификация

В [useAuth.ts](frontend/src/hooks/useAuth.ts) хук делает 2 запроса при старте и блокирует рендеринг:

```25:29:frontend/src/hooks/useAuth.ts
      const [userData, featuresData] = await Promise.all([
        getCurrentUser(),
        getUserFeatures()
      ]);
```

### 5. Нет оптимизации бандла Vite

[vite.config.ts](frontend/vite.config.ts) содержит только базовую конфигурацию без chunk splitting.

### 6. Тяжелые таблицы без виртуализации

`Statistics.tsx` рендерит до 500 строк напрямую в DOM (хотя `ProfitableAds.tsx` уже использует `@tanstack/react-virtual`).

---

## Решения

### 1. Добавить Lazy Loading для страниц

Заменить статические импорты на динамические с `React.lazy()` и `Suspense`:

```typescript
import { lazy, Suspense } from 'react';

// Lazy load тяжелых страниц
const Dashboard = lazy(() => import('./pages/Dashboard').then(m => ({ default: m.Dashboard })));
const Statistics = lazy(() => import('./pages/Statistics').then(m => ({ default: m.Statistics })));
const ProfitableAds = lazy(() => import('./pages/ProfitableAds').then(m => ({ default: m.ProfitableAds })));
const Scaling = lazy(() => import('./pages/Scaling').then(m => ({ default: m.Scaling })));
const DisableRules = lazy(() => import('./pages/DisableRules').then(m => ({ default: m.DisableRules })));
// ... остальные
```

### 2. Оптимизировать React Query

```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30 * 1000,        // Данные свежие 30 сек
      gcTime: 5 * 60 * 1000,       // Кэш 5 минут
      refetchOnMount: 'always',    // Но обновлять при mount
    },
  },
});
```

### 3. Уменьшить частоту polling

- Dashboard: 5 сек -> 15 сек
- Process status: 3 сек -> 10 сек  
- Analysis results: 5 сек -> 30 сек (или отключить и добавить кнопку обновления)
- Analysis status: только когда running

### 4. Оптимизировать Vite build

```typescript
// vite.config.ts
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          'vendor': ['react', 'react-dom', 'react-router-dom'],
          'query': ['@tanstack/react-query'],
          'ui': ['lucide-react'],
        },
      },
    },
    chunkSizeWarningLimit: 500,
  },
  // ...
});
```

### 5. Добавить виртуализацию в Statistics.tsx

Использовать `@tanstack/react-virtual` как в `ProfitableAds.tsx`.

### 6. Кэшировать auth данные

Добавить `staleTime` для auth запросов или хранить features в localStorage.

### 7. Добавить Loading Skeleton

Заменить простой спиннер на skeleton UI для лучшего UX.

---

## Оценка влияния

| Оптимизация | Влияние на загрузку | Сложность |

|-------------|---------------------|-----------|

| Lazy loading | Высокое (уменьшит начальный бандл на 50-70%) | Низкая |

| staleTime | Среднее (меньше запросов при навигации) | Низкая |

| Уменьшение polling | Среднее (снижение нагрузки на API/рендеринг) | Низкая |

| Vite chunks | Среднее (лучшее кэширование) | Низкая |

| Виртуализация таблиц | Высокое для Statistics | Средняя |