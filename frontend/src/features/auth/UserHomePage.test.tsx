import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiClient } from "../../api/client";
import type { CurrentUser } from "../../api/types";
import { click, flush, mountWithAuth, mouseDown, type MountedView } from "../../test/renderTestApp";
import type { AuthContextValue } from "./authContextValue";
import { UserHomePage } from "./UserHomePage";

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
  logout: vi.fn(),
  changePassword: vi.fn(),
};
let view: MountedView | null = null;

afterEach(async () => {
  if (view) await view.unmount();
  view = null;
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("UserHomePage", () => {
  it("requires an explicit active business-system selection", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([
      {
        id: "20000000-0000-0000-0000-000000000001",
        code: "ESB",
        name: "企业服务总线",
        description: null,
        status: "ACTIVE",
        owners: [],
        created_at: "2026-08-02T10:00:00Z",
        updated_at: "2026-08-02T10:00:00Z",
      },
    ]);
    view = await mountWithAuth(<UserHomePage />, auth, "/app");
    await flush();

    expect(view.container.textContent).toContain("选择业务系统");
    expect(view.container.textContent).toContain("请选择要咨询的业务系统");
    await mouseDown(view.container.querySelector('[role="combobox"]')!);
    await flush();
    const option = [...document.querySelectorAll(".ant-select-item-option")].find((item) =>
      item.textContent?.includes("企业服务总线"),
    );
    (option as HTMLElement).click();
    await flush();
    expect(view.container.textContent).toContain("当前系统：企业服务总线");
  });

  it("shows empty and recoverable error states without inventing a selection", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([]);
    view = await mountWithAuth(<UserHomePage />, auth, "/app");
    await flush();
    expect(view.container.textContent).toContain("暂无可用业务系统");
    await view.unmount();
    view = null;

    vi.restoreAllMocks();
    const listSystems = vi
      .spyOn(apiClient, "listSystems")
      .mockRejectedValueOnce(
        new ApiError(503, {
          code: "DEPENDENCY_UNAVAILABLE",
          message: "服务暂时不可用",
          request_id: "request-id",
        }),
      )
      .mockResolvedValueOnce([]);
    view = await mountWithAuth(<UserHomePage />, auth, "/app");
    await flush();
    expect(view.container.textContent).toContain("服务暂时不可用");
    expect(view.container.textContent).toContain("request-id");
    await click(view.container.querySelector('[aria-label="重试加载业务系统"]')!);
    await flush();
    expect(listSystems).toHaveBeenCalledTimes(2);
    expect(view.container.textContent).toContain("暂无可用业务系统");
  });
});
