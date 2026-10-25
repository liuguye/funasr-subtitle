import type { ReactNode } from "react";

export function SectionLabel({ en, children }: { en: string; children?: ReactNode }) {
  return (
    <div className="label-cap" style={{ marginBottom: 10 }}>
      {en}
      {children ? <> · <span className="cap-cn">{children}</span></> : null}
    </div>
  );
}
