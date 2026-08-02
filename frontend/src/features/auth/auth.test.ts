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
  it("accepts a password with all required character classes", () => {
    expect(passwordViolations("Replacement2@")).toEqual([]);
  });

  it("reports every missing rule", () => {
    expect(passwordViolations("short")).toEqual([
      "至少 12 个字符",
      "包含大写字母",
      "包含数字",
      "包含特殊字符",
    ]);
  });
});
