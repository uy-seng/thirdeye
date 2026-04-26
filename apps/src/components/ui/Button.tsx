import type { ButtonHTMLAttributes } from "react";

import { joinClasses } from "./classes";

export function Button({
  className,
  variant = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "quiet" | "danger" }) {
  return <button className={joinClasses("button", `button-${variant}`, className)} {...props} />;
}
