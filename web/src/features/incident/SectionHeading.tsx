import { createContext, useContext, type ReactNode } from 'react';

export const SectionLevel = createContext<2 | 3>(3);

export function SectionHeading({ id, children }: { id: string; children: ReactNode }) {
  const level = useContext(SectionLevel);
  const Tag = level === 2 ? 'h2' : 'h3';
  return <Tag id={id} className="section-title">{children}</Tag>;
}
