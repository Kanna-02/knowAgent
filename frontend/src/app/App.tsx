import { App as AntApp, ConfigProvider, Result } from "antd";
import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "../features/auth/AuthContext";
import { LoginPage } from "../features/auth/LoginPage";
import { ProtectedRoute } from "../features/auth/ProtectedRoute";
import { AppErrorBoundary } from "./AppErrorBoundary";
import { theme } from "./theme";

const AccountsPage = lazy(() =>
  import("../features/admin/AccountsPage").then(({ AccountsPage: component }) => ({
    default: component,
  })),
);
const AdminShell = lazy(() =>
  import("../features/admin/AdminShell").then(({ AdminShell: component }) => ({
    default: component,
  })),
);
const SystemsPage = lazy(() =>
  import("../features/admin/SystemsPage").then(({ SystemsPage: component }) => ({
    default: component,
  })),
);
const TicketsPage = lazy(() =>
  import("../features/tickets/TicketsPage").then(({ TicketsPage: component }) => ({
    default: component,
  })),
);
const ChangePasswordPage = lazy(() =>
  import("../features/auth/ChangePasswordPage").then(({ ChangePasswordPage: component }) => ({
    default: component,
  })),
);
const UserHomePage = lazy(() =>
  import("../features/auth/UserHomePage").then(({ UserHomePage: component }) => ({
    default: component,
  })),
);
const UserShell = lazy(() =>
  import("../features/auth/UserShell").then(({ UserShell: component }) => ({
    default: component,
  })),
);

export function App(): ReactNode {
  return (
    <ConfigProvider theme={theme}>
      <AntApp>
        <AppErrorBoundary>
          <BrowserRouter>
            <AuthProvider>
              <Suspense fallback={<div className="route-loading" aria-label="正在加载页面" />}>
                <Routes>
                  <Route path="/login" element={<LoginPage entry="user" />} />
                  <Route path="/admin/login" element={<LoginPage entry="admin" />} />
                  <Route
                    path="/change-password"
                    element={
                      <ProtectedRoute>
                        <ChangePasswordPage />
                      </ProtectedRoute>
                    }
                  />
                  <Route
                    path="/app"
                    element={
                      <ProtectedRoute>
                        <UserShell />
                      </ProtectedRoute>
                    }
                  >
                    <Route index element={<Navigate replace to="question" />} />
                  <Route path="question" element={<UserHomePage />} />
                  <Route path="tickets" element={<TicketsPage />} />
                </Route>
                  <Route
                    path="/admin"
                    element={
                      <ProtectedRoute>
                        <AdminShell />
                      </ProtectedRoute>
                    }
                  >
                    <Route index element={<Navigate replace to="accounts" />} />
                    <Route path="accounts" element={<AccountsPage />} />
                    <Route path="systems" element={<SystemsPage />} />
                  </Route>
                  <Route
                    path="/forbidden"
                    element={
                      <Result
                        status="403"
                        title="无权访问"
                        subTitle="当前账号不能进入此区域，请返回对应入口。"
                      />
                    }
                  />
                  <Route path="/" element={<Navigate replace to="/login" />} />
                  <Route
                    path="*"
                    element={
                      <Result
                        status="404"
                        title="页面不存在"
                        subTitle="请检查地址，或返回应用入口。"
                      />
                    }
                  />
                </Routes>
              </Suspense>
            </AuthProvider>
          </BrowserRouter>
        </AppErrorBoundary>
      </AntApp>
    </ConfigProvider>
  );
}
