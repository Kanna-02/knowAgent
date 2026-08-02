import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, apiClient, AUTH_UNAUTHORIZED_EVENT } from "../../api/client";
import type { CurrentUser } from "../../api/types";
import { AuthContext, type AuthContextValue } from "./authContextValue";

export function AuthProvider({ children }: { children: ReactNode }): ReactNode {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);

  const refresh = useCallback(async (): Promise<CurrentUser> => {
    const current = await apiClient.me();
    setUser(current);
    setBootstrapError(null);
    return current;
  }, []);

  useEffect(() => {
    const clearUnauthorizedSession = (): void => {
      setUser(null);
      setBootstrapError(null);
    };
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, clearUnauthorizedSession);
    return () => window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, clearUnauthorizedSession);
  }, []);

  useEffect(() => {
    let active = true;
    apiClient
      .me()
      .then((current) => {
        if (active) setUser(current);
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          setUser(null);
          return;
        }
        setBootstrapError(error instanceof Error ? error.message : "认证服务暂时不可用");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (entry: "user" | "admin", username: string, password: string) => {
    const session = await apiClient.login(entry, username, password);
    setUser(session.user);
    setBootstrapError(null);
    return session.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiClient.logout();
    } finally {
      setUser(null);
      setBootstrapError(null);
    }
  }, []);

  const changePassword = useCallback(
    async (currentPassword: string, newPassword: string) => {
      await apiClient.changePassword(currentPassword, newPassword);
      return refresh();
    },
    [refresh],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, bootstrapError, login, logout, changePassword }),
    [user, loading, bootstrapError, login, logout, changePassword],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
