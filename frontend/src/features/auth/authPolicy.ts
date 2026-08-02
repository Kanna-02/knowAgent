import type { AccountRole } from "../../api/types";

export function resolvePostLoginPath(role: AccountRole, mustChangePassword: boolean): string {
  if (mustChangePassword) return "/change-password";
  return role === "ADMIN" ? "/admin/accounts" : "/app";
}

export function passwordViolations(password: string): string[] {
  const checks: Array<[boolean, string]> = [
    [password.length >= 12, "至少 12 个字符"],
    [/[a-z]/.test(password), "包含小写字母"],
    [/[A-Z]/.test(password), "包含大写字母"],
    [/\d/.test(password), "包含数字"],
    [/[^A-Za-z0-9]/.test(password), "包含特殊字符"],
  ];
  return checks.filter(([valid]) => !valid).map(([, message]) => message);
}
