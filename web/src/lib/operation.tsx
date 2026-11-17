/** The operation (disaster) the operator is working in. Remembered per browser as a convenience only. */
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { useOperations } from './queries';
import type { Operation } from './types';

const KEY = 'raahat.operation';

interface OperationValue {
  operation: Operation | null;
  operations: Operation[];
  loading: boolean;
  error: unknown;
  select: (id: string) => void;
}

const OperationContext = createContext<OperationValue | null>(null);

function remembered(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function OperationProvider({ children }: { children: ReactNode }) {
  const query = useOperations();
  const [selectedId, setSelectedId] = useState<string | null>(remembered);
  const operations = useMemo(() => query.data ?? [], [query.data]);

  const operation = useMemo(() => {
    const chosen = operations.find((o) => o.id === selectedId);
    return chosen ?? operations.find((o) => o.status === 'active') ?? operations[0] ?? null;
  }, [operations, selectedId]);

  useEffect(() => {
    if (!operation) return;
    try {
      localStorage.setItem(KEY, operation.id);
    } catch {
      /* not essential */
    }
  }, [operation]);

  const value = useMemo<OperationValue>(
    () => ({ operation, operations, loading: query.isLoading, error: query.error, select: setSelectedId }),
    [operation, operations, query.isLoading, query.error],
  );
  return <OperationContext.Provider value={value}>{children}</OperationContext.Provider>;
}

export function useOperation(): OperationValue {
  const value = useContext(OperationContext);
  if (!value) throw new Error('useOperation outside OperationProvider');
  return value;
}
