import { Button, Result, Spin } from "antd";
import { RefreshCw } from "lucide-react";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "./authContextValue";
import { evaluateRouteAccess } from "./routeAccess";

export function ProtectedRoute({ children }: { children: ReactNode }): ReactNode {
  const { user, loading, bootstrapError } = useAuth();
  const location = useLocation();
  if (loading) {
    return (
      <div className="center-state" aria-label="正在检查登录状态">
        <Spin size="large" />
      </div>
    );
  }
  if (bootstrapError) {
    return (
      <Result
        status="error"
        title="无法检查登录状态"
        subTitle={bootstrapError}
        extra={
          <Button icon={<RefreshCw size={16} />} onClick={() => window.location.reload()}>
            重试
          </Button>
        }
      />
    );
  }
  const decision = evaluateRouteAccess(
    user ? { role: user.role, mustChangePassword: user.must_change_password } : null,
    location.pathname,
  );
  if (decision.kind === "redirect") {
    return <Navigate replace to={decision.to} state={{ from: location.pathname }} />;
  }
  if (decision.kind === "denied") return <Navigate replace to="/forbidden" />;
  return children;
}
