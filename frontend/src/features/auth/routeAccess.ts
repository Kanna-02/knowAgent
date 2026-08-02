import type { AccountRole } from "../../api/types";

interface RouteUser {
  role: AccountRole;
  mustChangePassword: boolean;
}

type RouteDecision = { kind: "allow" } | { kind: "denied" } | { kind: "redirect"; to: string };

export function evaluateRouteAccess(user: RouteUser | null, path: string): RouteDecision {
  if (!user) {
    return { kind: "redirect", to: path.startsWith("/admin") ? "/admin/login" : "/login" };
  }
  if (user.mustChangePassword && path !== "/change-password") {
    return { kind: "redirect", to: "/change-password" };
  }
  if (path.startsWith("/admin") && user.role !== "ADMIN") return { kind: "denied" };
  if (path.startsWith("/app") && user.role === "ADMIN") return { kind: "denied" };
  return { kind: "allow" };
}
