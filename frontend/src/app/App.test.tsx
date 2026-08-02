import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiClient } from "../api/client";
import { App } from "./App";
import { theme } from "./theme";

afterEach(() => {
  document.body.innerHTML = "";
  window.history.replaceState({}, "", "/");
  vi.restoreAllMocks();
});

describe("App", () => {
  it("renders the routed login application with the configured theme", async () => {
    vi.spyOn(apiClient, "me").mockRejectedValue(
      new ApiError(401, {
        code: "SESSION_REQUIRED",
        message: "请先登录",
        request_id: "request-id",
      }),
    );
    window.history.replaceState({}, "", "/login");
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(<App />);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(container.textContent).toContain("登录 KnowAgent");
    expect(theme.token?.colorPrimary).toBe("#0F766E");
    act(() => root.unmount());
  });
});
