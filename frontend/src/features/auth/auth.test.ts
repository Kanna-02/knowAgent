import { describe, expect, it } from "vitest";

import { passwordViolations, resolvePostLoginPath } from "./authPolicy";

describe("resolvePostLoginPath", () => {
  it("forces every role through password change when required", () => {
    expect(resolvePostLoginPath("ADMIN", true)).toBe("/change-password");
    expect(resolvePostLoginPath("USER", true)).toBe("/change-password");
  });

  it("routes admins to the management app", () => {
    expect(resolvePostLoginPath("ADMIN", false)).toBe("/admin/accounts");
  });

  it("routes users and system owners to the user app", () => {
    expect(resolvePostLoginPath("USER", false)).toBe("/app");
    expect(resolvePostLoginPath("SYSTEM_OWNER", false)).toBe("/app");
  });
});

describe("passwordViolations", () => {
  it("accepts an eight character password containing letters and numbers", () => {
    expect(passwordViolations("welcome1")).toEqual([]);
  });

  it("reports every missing rule", () => {
    expect(passwordViolations("short")).toEqual(["至少 8 个字符", "包含数字"]);
    expect(passwordViolations("12345678")).toEqual(["包含字母"]);
  });
});
