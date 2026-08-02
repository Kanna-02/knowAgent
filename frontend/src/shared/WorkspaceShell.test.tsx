import { Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CurrentUser } from "../api/types";
import { click, flush, mountWithAuth, type MountedView } from "../test/renderTestApp";
import type { AuthContextValue } from "../features/auth/authContextValue";
import { WorkspaceShell } from "./WorkspaceShell";

const user: CurrentUser = {
  id: "10000000-0000-0000-0000-000000000001",
  username: "alice",
  display_name: "Alice",
  role: "USER",
  status: "ACTIVE",
  must_change_password: false,
  system_roles: [],
};
const auth: AuthContextValue = {
  user,
  loading: false,
  bootstrapError: null,
  login: vi.fn(),
  logout: vi.fn().mockResolvedValue(undefined),
  changePassword: vi.fn(),
};
let view: MountedView | null = null;

afterEach(async () => {
  if (view) await view.unmount();
  view = null;
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("WorkspaceShell", () => {
  it("renders active navigation and opens the mobile navigation", async () => {
    view = await mountWithAuth(
      <Routes>
        <Route
          path="/app"
          element={
            <WorkspaceShell
              brand="KnowAgent"
              navigationLabel="用户导航"
              loginPath="/login"
              items={[
                { path: "/app/question", label: "问答", icon: <span>Q</span> },
                { path: "/app/tickets", label: "我的工单", icon: <span>T</span> },
              ]}
            />
          }
        >
          <Route path="question" element={<div>问答内容</div>} />
          <Route path="tickets" element={<div>工单内容</div>} />
        </Route>
      </Routes>,
      auth,
      "/app/question",
    );

    expect(view.container.textContent).toContain("问答内容");
    expect(view.container.textContent).toContain("问答");
    expect(view.container.querySelector('[aria-current="page"]')?.textContent).toContain("问答");
    expect(view.container.textContent).toContain("Alice");

    await click(view.container.querySelector('[aria-label="打开用户导航"]')!);
    await flush();
    expect(document.body.textContent).toContain("我的工单");
  });
});
