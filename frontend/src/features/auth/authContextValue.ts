import { createContext, useContext } from "react";

import type { CurrentUser } from "../../api/types";

export interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  bootstrapError: string | null;
  login: (entry: "user" | "admin", username: string, password: string) => Promise<CurrentUser>;
  logout: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<CurrentUser>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
