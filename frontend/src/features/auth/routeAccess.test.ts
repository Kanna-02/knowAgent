import { describe, expect, it } from "vitest";

import { evaluateRouteAccess } from "./routeAccess";

describe("evaluateRouteAccess", () => {
  it("redirects anonymous visitors to the route-specific login", () => {
    expect(evaluateRouteAccess(null, "/admin/accounts")).toEqual({
      kind: "redirect",
      to: "/admin/login",
    });
    expect(evaluateRouteAccess(null, "/app")).toEqual({ kind: "redirect", to: "/login" });
  });

  it("forces restricted sessions to the password page", () => {
    expect(evaluateRouteAccess({ role: "USER", mustChangePassword: true }, "/app")).toEqual({
      kind: "redirect",
      to: "/change-password",
    });
  });

  it("denies users and system owners access to admin routes", () => {
    expect(
      evaluateRouteAccess({ role: "SYSTEM_OWNER", mustChangePassword: false }, "/admin/accounts"),
    ).toEqual({ kind: "denied" });
  });

  it("allows the matching role into its application", () => {
    expect(
      evaluateRouteAccess({ role: "ADMIN", mustChangePassword: false }, "/admin/accounts"),
    ).toEqual({ kind: "allow" });
    expect(evaluateRouteAccess({ role: "USER", mustChangePassword: false }, "/app")).toEqual({
      kind: "allow",
    });
  });
});
