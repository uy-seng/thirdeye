import type { HTMLAttributes } from "react";

import { joinClasses } from "./classes";

export function Badge({
  tone = "neutral",
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: "neutral" | "good" | "warn" | "bad" | "info" }) {
  return <span className={joinClasses("badge", `badge-${tone}`, className)} {...props} />;
}
