import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppErrorBoundary } from "./AppErrorBoundary";

function BrokenView(): never {
  throw new Error("render details");
}

afterEach(() => {
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("AppErrorBoundary", () => {
  it("replaces render failures with safe recovery commands", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);

    act(() => {
      root.render(
        <AppErrorBoundary>
          <BrokenView />
        </AppErrorBoundary>,
      );
    });

    expect(container.textContent).toContain("页面加载失败");
    expect(container.textContent).toContain("重新加载");
    expect(container.textContent).not.toContain("render details");
    act(() => root.unmount());
  });
});
