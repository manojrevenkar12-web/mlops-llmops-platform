import type { ReactNode } from "react";

export function Section({ id, title, lede, children }: { id: string; title: string; lede?: ReactNode; children: ReactNode }) {
  return (
    <section className="section" aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`}>{title}</h2>
      {lede && <p className="ink2 measure">{lede}</p>}
      {children}
    </section>
  );
}
