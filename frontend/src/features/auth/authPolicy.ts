import type { AccountRole } from "../../api/types";

export function resolvePostLoginPath(role: AccountRole, mustChangePassword: boolean): string {
  if (mustChangePassword) return "/change-password";
  return role === "ADMIN" ? "/admin/accounts" : "/app";
}

export function passwordViolations(password: string): string[] {
  const checks: Array<[boolean, string]> = [
    [password.length >= 8, "至少 8 个字符"],
    [/[A-Za-z]/.test(password), "包含字母"],
    [/\d/.test(password), "包含数字"],
  ];
  return checks.filter(([valid]) => !valid).map(([, message]) => message);
}
