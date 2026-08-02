import { describe, expect, it } from "vitest";

import { ApiError } from "../api/client";
import { toUiError } from "./uiError";

describe("toUiError", () => {
  it("keeps a safe API message and request id", () => {
    expect(
      toUiError(
        new ApiError(503, {
          code: "DEPENDENCY_UNAVAILABLE",
          message: "服务暂时不可用",
          request_id: "request-id",
        }),
        "加载失败",
      ),
    ).toEqual({ message: "服务暂时不可用", requestId: "request-id" });
  });

  it("uses the contextual fallback for unknown errors", () => {
    expect(toUiError(new Error("socket details"), "加载失败")).toEqual({
      message: "加载失败",
      requestId: null,
    });
  });
});
