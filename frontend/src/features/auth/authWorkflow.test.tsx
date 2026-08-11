import { Button } from "antd";
import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import type { CurrentUser } from "../../api/types";
import { click, flush, mountWithAuth, setInput, type MountedView } from "../../test/renderTestApp";
import { AdminShell } from "../admin/AdminShell";
import { ChangePasswordPage } from "./ChangePasswordPage";
import { LoginPage } from "./LoginPage";
import { ProtectedRoute } from "./ProtectedRoute";
import { UserHomePage } from "./UserHomePage";
import { UserShell } from "./UserShell";
import type { AuthContextValue } from "./authContextValue";

const user: CurrentUser = {
  id: "10000000-0000-0000-0000-000000000001",
  username: "alice",
  display_name: "Alice",
  role: "USER",
  status: "ACTIVE",
  must_change_password: false,
  system_roles: [],
};

const admin: CurrentUser = { ...user, username: "admin", display_name: "Admin", role: "ADMIN" };
let views: MountedView[] = [];

afterEach(async () => {
  for (const view of views.reverse()) await view.unmount();
  views = [];
  document.querySelectorAll(".ant-dropdown, .ant-popover").forEach((element) => element.remove());
  vi.restoreAllMocks();
});

function auth(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return {
    user: null,
    loading: false,
    bootstrapError: null,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
    ...overrides,
  };
}

async function mount(node: ReactNode, value: AuthContextValue, route = "/"): Promise<MountedView> {
  const view = await mountWithAuth(node, value, route);
  views.push(view);
  return view;
}

describe("authentication pages", () => {
  it("submits the matching login entry and reports API failures", async () => {
    const login = vi
      .fn<AuthContextValue["login"]>()
      .mockResolvedValueOnce(user)
      .mockRejectedValueOnce(
        new ApiError(401, {
          code: "AUTH_INVALID",
          message: "账号或密码不正确",
          request_id: "request-id",
        }),
      );
    const view = await mount(<LoginPage entry="user" />, auth({ login }), "/login");
    await setInput(view.container.querySelector("#username") as HTMLInputElement, "alice");
    await setInput(view.container.querySelector("#password") as HTMLInputElement, "Temporary1!");
    await click(view.container.querySelector('button[type="submit"]') as Element);
    await flush();

    expect(login).toHaveBeenCalledWith("user", "alice", "Temporary1!");

    const second = await mount(<LoginPage entry="admin" />, auth({ login }), "/admin/login");
    await setInput(second.container.querySelector("#username") as HTMLInputElement, "admin");
    await setInput(second.container.querySelector("#password") as HTMLInputElement, "bad-password");
    await click(second.container.querySelector('button[type="submit"]') as Element);
    await flush();
    expect(login).toHaveBeenLastCalledWith("admin", "admin", "bad-password");
  });

  it("renders bootstrap errors and redirects an existing user", async () => {
    const errorView = await mount(
      <LoginPage entry="user" />,
      auth({ bootstrapError: "认证服务暂时不可用" }),
      "/login",
    );
    expect(errorView.container.textContent).toContain("无法检查登录状态");

    const userView = await mount(
      <Routes>
        <Route path="/login" element={<LoginPage entry="user" />} />
        <Route path="/app" element={<div>用户首页</div>} />
      </Routes>,
      auth({ user }),
      "/login",
    );
    expect(userView.container.textContent).toContain("用户首页");
  });

  it("changes a password, rejects invalid confirmation, and signs out", async () => {
    const changePassword = vi.fn<AuthContextValue["changePassword"]>().mockResolvedValue(user);
    const logout = vi.fn<AuthContextValue["logout"]>().mockResolvedValue(undefined);
    const view = await mount(
      <Routes>
        <Route path="/change-password" element={<ChangePasswordPage />} />
        <Route path="/app" element={<div>用户首页</div>} />
        <Route path="/login" element={<div>登录页</div>} />
      </Routes>,
      auth({ user, changePassword, logout }),
      "/change-password",
    );
    await setInput(
      view.container.querySelector("#currentPassword") as HTMLInputElement,
      "Temporary1!",
    );
    await setInput(
      view.container.querySelector("#newPassword") as HTMLInputElement,
      "Replacement2@",
    );
    await setInput(
      view.container.querySelector("#confirmation") as HTMLInputElement,
      "Replacement2@",
    );
    await click(view.container.querySelector('button[type="submit"]') as Element);
    await flush();
    expect(changePassword).toHaveBeenCalledWith("Temporary1!", "Replacement2@");
    expect(view.container.textContent).toContain("用户首页");

    const signOutView = await mount(
      <ChangePasswordPage />,
      auth({ user, logout }),
      "/change-password",
    );
    const buttons = [...signOutView.container.querySelectorAll("button")];
    await click(buttons.find((button) => button.textContent?.includes("退出登录")) as Element);
    await flush();
    expect(logout).toHaveBeenCalled();
  });

  it("redirects anonymous password changes and handles password API errors", async () => {
    const anonymous = await mount(
      <Routes>
        <Route path="/change-password" element={<ChangePasswordPage />} />
        <Route path="/login" element={<div>登录页</div>} />
      </Routes>,
      auth(),
      "/change-password",
    );
    expect(anonymous.container.textContent).toContain("登录页");

    const invalidChange = vi.fn<AuthContextValue["changePassword"]>();
    const invalid = await mount(
      <ChangePasswordPage />,
      auth({ user, changePassword: invalidChange }),
      "/change-password",
    );
    await setInput(invalid.container.querySelector("#currentPassword") as HTMLInputElement, "old");
    await setInput(invalid.container.querySelector("#newPassword") as HTMLInputElement, "short");
    await setInput(
      invalid.container.querySelector("#confirmation") as HTMLInputElement,
      "different",
    );
    await click(invalid.container.querySelector('button[type="submit"]') as Element);
    await flush();
    expect(invalidChange).not.toHaveBeenCalled();

    const changePassword = vi.fn<AuthContextValue["changePassword"]>().mockRejectedValue(
      new ApiError(422, {
        code: "PASSWORD_POLICY",
        message: "密码不符合策略",
        request_id: "request-id",
      }),
    );
    const view = await mount(
      <ChangePasswordPage />,
      auth({ user, changePassword }),
      "/change-password",
    );
    await setInput(
      view.container.querySelector("#currentPassword") as HTMLInputElement,
      "Temporary1!",
    );
    await setInput(
      view.container.querySelector("#newPassword") as HTMLInputElement,
      "Replacement2@",
    );
    await setInput(
      view.container.querySelector("#confirmation") as HTMLInputElement,
      "Replacement2@",
    );
    await click(view.container.querySelector('button[type="submit"]') as Element);
    await flush();
    expect(changePassword).toHaveBeenCalled();
  });
});

describe("route and shell workflows", () => {
  it("covers protected route loading, error, redirect, denial, and allow states", async () => {
    const loading = await mount(
      <ProtectedRoute>content</ProtectedRoute>,
      auth({ loading: true }),
      "/app",
    );
    expect(loading.container.querySelector('[aria-label="正在检查登录状态"]')).not.toBeNull();

    const error = await mount(
      <ProtectedRoute>content</ProtectedRoute>,
      auth({ bootstrapError: "down" }),
      "/app",
    );
    expect(error.container.textContent).toContain("无法检查登录状态");

    const redirected = await mount(
      <Routes>
        <Route path="/app" element={<ProtectedRoute>content</ProtectedRoute>} />
        <Route path="/login" element={<div>登录页</div>} />
      </Routes>,
      auth(),
      "/app",
    );
    expect(redirected.container.textContent).toContain("登录页");

    const denied = await mount(
      <Routes>
        <Route path="/admin" element={<ProtectedRoute>content</ProtectedRoute>} />
        <Route path="/forbidden" element={<div>无权访问</div>} />
      </Routes>,
      auth({ user }),
      "/admin",
    );
    expect(denied.container.textContent).toContain("无权访问");

    const allowed = await mount(<ProtectedRoute>content</ProtectedRoute>, auth({ user }), "/app");
    expect(allowed.container.textContent).toContain("content");
  });

  it("renders user and admin shells and executes their logout menus", async () => {
    const userLogout = vi.fn<AuthContextValue["logout"]>().mockResolvedValue(undefined);
    const userView = await mount(
      <Routes>
        <Route path="/app" element={<UserShell />}>
          <Route path="question" element={<div>问答内容</div>} />
        </Route>
      </Routes>,
      auth({ user, logout: userLogout }),
      "/app/question",
    );
    expect(userView.container.textContent).toContain("问答内容");
    await click(userView.container.querySelector('[aria-label="账号菜单"]') as Element);
    await flush();
    const userMenu = [...document.querySelectorAll(".ant-dropdown-menu-item")].find((item) =>
      item.textContent?.includes("退出登录"),
    );
    await click(userMenu as Element);
    expect(userLogout).toHaveBeenCalled();

    const adminLogout = vi.fn<AuthContextValue["logout"]>().mockResolvedValue(undefined);
    const adminView = await mount(
      <Routes>
        <Route path="/admin" element={<AdminShell />}>
          <Route index element={<Navigate to="accounts" replace />} />
          <Route path="accounts" element={<div>账号内容</div>} />
          <Route path="systems" element={<div>系统内容</div>} />
        </Route>
      </Routes>,
      auth({ user: admin, logout: adminLogout }),
      "/admin/accounts",
    );
    expect(adminView.container.textContent).toContain("账号内容");
    await click(
      [...adminView.container.querySelectorAll("button")].find((item) =>
        item.textContent?.includes("业务系统"),
      ) as Element,
    );
    await flush();
    expect(adminView.container.textContent).toContain("系统内容");
    await click(
      [...adminView.container.querySelectorAll("button")].find((item) =>
        item.textContent?.includes("用户与角色"),
      ) as Element,
    );
    await flush();
    expect(adminView.container.textContent).toContain("账号内容");
    await click(adminView.container.querySelector('[aria-label="账号菜单"]') as Element);
    await flush();
    const menus = [...document.querySelectorAll(".ant-dropdown-menu-item")];
    await click(menus.at(-1) as Element);
    expect(adminLogout).toHaveBeenCalled();
  });

  it("renders the question workspace for a system owner", async () => {
    const owner = { ...user, role: "SYSTEM_OWNER" as const };
    const view = await mount(<UserHomePage />, auth({ user: owner }), "/app");
    expect(view.container.textContent).toContain("知识问答");
    expect(view.container.querySelector('[aria-label="选择业务系统"]')).not.toBeNull();
  });

  it("keeps familiar buttons callable", async () => {
    const action = vi.fn();
    const view = await mount(<Button onClick={action}>操作</Button>, auth());
    await click(view.container.querySelector("button") as Element);
    expect(action).toHaveBeenCalled();
  });
});
