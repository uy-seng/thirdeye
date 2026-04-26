import type { HTMLAttributes } from "react";

import { joinClasses } from "./classes";

export function Card({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <section className={joinClasses("card", className)} {...props} />;
}
