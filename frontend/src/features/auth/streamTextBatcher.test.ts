import { afterEach, describe, expect, it, vi } from "vitest";

import { createStreamTextBatcher } from "./streamTextBatcher";

afterEach(() => {
  vi.useRealTimers();
});

describe("createStreamTextBatcher", () => {
  it("coalesces rapid deltas into one render update", () => {
    vi.useFakeTimers();
    const updates: string[] = [];
    const batcher = createStreamTextBatcher((delta) => updates.push(delta), 50);

    batcher.append("第一");
    batcher.append("段");

    expect(updates).toEqual([]);
    vi.advanceTimersByTime(49);
    expect(updates).toEqual([]);
    vi.advanceTimersByTime(1);
    expect(updates).toEqual(["第一段"]);
  });

  it("flushes pending text before a terminal event and supports cancellation", () => {
    vi.useFakeTimers();
    const updates: string[] = [];
    const batcher = createStreamTextBatcher((delta) => updates.push(delta), 50);

    batcher.append("完整");
    batcher.flush();
    batcher.append("忽略");
    batcher.cancel();
    vi.runAllTimers();

    expect(updates).toEqual(["完整"]);
  });
});
