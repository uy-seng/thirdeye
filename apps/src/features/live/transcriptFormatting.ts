export function formatTimestamp(seconds?: number) {
  if (typeof seconds !== "number" || Number.isNaN(seconds)) {
    return "";
  }
  const value = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
}

export function formatRange(start?: number, current?: number) {
  const startLabel = formatTimestamp(start);
  const currentLabel = formatTimestamp(current);

  if (startLabel && currentLabel && startLabel !== currentLabel) {
    return `${startLabel} - ${currentLabel}`;
  }

  return startLabel || currentLabel;
}

export function isNearBottom(element: HTMLDivElement | null) {
  if (!element) {
    return true;
  }
  return element.scrollHeight - element.scrollTop - element.clientHeight < 80;
}
