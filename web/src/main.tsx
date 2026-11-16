import '@fontsource-variable/public-sans/wght.css';
import '@fontsource-variable/jetbrains-mono/wght.css';
import '@fontsource-variable/noto-sans-malayalam/wght.css';
import '@fontsource-variable/noto-sans-devanagari/wght.css';
import './styles/tokens.css';
import './styles/base.css';
import './styles/components.css';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';
import { ToastProvider } from './components/ui';
import { ApiError } from './lib/api';
import { AuthProvider } from './lib/auth';
import { applyTheme } from './lib/theme';

applyTheme();

const client = new QueryClient({
  defaultOptions: {
    queries: {
      // Realtime events invalidate queries; polling is only a backstop.
      staleTime: 15_000,
      refetchInterval: 60_000,
      refetchOnWindowFocus: true,
      // The API client already retries transient failures.
      retry: (count, error) => count < 1 && !(error instanceof ApiError && error.status < 500),
      // Keep showing the last data when the backend goes away; the shell labels its age.
      gcTime: 30 * 60_000,
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <AuthProvider>
        <ToastProvider>
          <App />
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
