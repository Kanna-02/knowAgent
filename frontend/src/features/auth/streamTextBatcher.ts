export interface StreamTextBatcher {
  append: (delta: string) => void;
  flush: () => void;
  cancel: () => void;
}

export function createStreamTextBatcher(
  onFlush: (delta: string) => void,
  intervalMs: number,
): StreamTextBatcher {
  let pending = "";
  let timer: number | null = null;

  const flush = (): void => {
    if (timer !== null) window.clearTimeout(timer);
    timer = null;
    if (!pending) return;
    const delta = pending;
    pending = "";
    onFlush(delta);
  };

  return {
    append(delta: string): void {
      pending += delta;
      if (timer === null) timer = window.setTimeout(flush, intervalMs);
    },
    flush,
    cancel(): void {
      if (timer !== null) window.clearTimeout(timer);
      timer = null;
      pending = "";
    },
  };
}
