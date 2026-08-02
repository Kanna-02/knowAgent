import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiClient } from "../../api/client";
import type { AccountPage, BusinessSystemView } from "../../api/types";
import {
  click,
  flush,
  mountWithAuth,
  mouseDown,
  setInput,
  type MountedView,
} from "../../test/renderTestApp";
import type { AuthContextValue } from "../auth/authContextValue";
import { SystemsPage } from "./SystemsPage";

const system: BusinessSystemView = {
  id: "20000000-0000-0000-0000-000000000001",
  code: "ESB",
  name: "企业服务总线",
  description: "集成服务",
  status: "ACTIVE",
  owners: [],
  created_at: "2026-08-02T10:00:00Z",
  updated_at: "2026-08-02T10:00:00Z",
};
const disabledSystem: BusinessSystemView = {
  ...system,
  status: "DISABLED",
  owners: [
    {
      account_id: "10000000-0000-0000-0000-000000000002",
      username: "owner",
      display_name: "Owner",
    },
  ],
};
const owner = {
  id: "10000000-0000-0000-0000-000000000002",
  username: "owner",
  display_name: "Owner",
  role: "SYSTEM_OWNER" as const,
  source: "LOCAL_IMPORT" as const,
  status: "ACTIVE" as const,
  must_change_password: false,
  credential_batch: null,
  external_provider: null,
  created_at: "2026-08-02T10:00:00Z",
  updated_at: "2026-08-02T10:00:00Z",
};
const ownerPage: AccountPage = {
  items: [owner],
  page: 1,
  page_size: 100,
  total: 1,
};
const systemPage = {
  items: [system],
  page: 1,
  page_size: 20,
  total: 1,
};
const auth: AuthContextValue = {
  user: { ...owner, role: "ADMIN", system_roles: [] },
  loading: false,
  bootstrapError: null,
  login: vi.fn(),
  logout: vi.fn(),
  changePassword: vi.fn(),
};
let views: MountedView[] = [];

afterEach(async () => {
  for (const view of views.reverse()) await view.unmount();
  views = [];
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("SystemsPage", () => {
  it("creates, disables, and configures owners", async () => {
    vi.spyOn(apiClient, "listAdminSystems").mockResolvedValue(systemPage);
    vi.spyOn(apiClient, "listAccounts").mockResolvedValue(ownerPage);
    const createSystem = vi.spyOn(apiClient, "createSystem").mockResolvedValue(system);
    const updateSystem = vi.spyOn(apiClient, "updateSystem").mockResolvedValue({
      ...system,
      status: "DISABLED",
    });
    const assignOwners = vi
      .spyOn(apiClient, "assignSystemOwners")
      .mockResolvedValue([
        { account_id: owner.id, username: owner.username, display_name: owner.display_name },
      ]);
    const view = await mountWithAuth(<SystemsPage />, auth, "/admin/systems");
    views.push(view);
    await flush();

    expect(view.container.textContent).toContain("企业服务总线");
    await click(view.container.querySelector('[aria-label="新增业务系统"]')!);
    await flush();
    await setInput(document.querySelector("#code") as HTMLInputElement, "crm");
    await setInput(document.querySelector("#name") as HTMLInputElement, "客户关系管理");
    await click(document.querySelector('[aria-label="创建业务系统"]')!);
    await flush();
    expect(createSystem).toHaveBeenCalledWith(
      expect.objectContaining({ code: "crm", name: "客户关系管理" }),
    );

    await click(view.container.querySelector('[aria-label="配置系统负责人"]')!);
    await flush();
    const ownerSelect = document.querySelector('[aria-label="系统负责人"]') as HTMLInputElement;
    await mouseDown(ownerSelect);
    await flush();
    const option = [...document.querySelectorAll(".ant-select-item-option")].find((item) =>
      item.textContent?.includes("Owner"),
    );
    await click(option!);
    await click(document.querySelector('[aria-label="保存系统负责人"]')!);
    await flush();
    expect(assignOwners).toHaveBeenCalledWith(system.id, [owner.id], true);

    await click(view.container.querySelector('[aria-label="切换系统状态"]')!);
    await flush();
    await click(document.querySelector(".ant-popconfirm-buttons .ant-btn-primary")!);
    await flush();
    expect(updateSystem).toHaveBeenCalledWith(system.id, { status: "DISABLED" });
  });

  it("edits and enables an existing disabled system", async () => {
    vi.spyOn(apiClient, "listAdminSystems").mockResolvedValue({
      ...systemPage,
      items: [disabledSystem],
    });
    vi.spyOn(apiClient, "listAccounts").mockResolvedValue(ownerPage);
    const updateSystem = vi.spyOn(apiClient, "updateSystem").mockResolvedValue({
      ...disabledSystem,
      name: "ESB 集成平台",
      status: "ACTIVE",
    });
    const view = await mountWithAuth(<SystemsPage />, auth, "/admin/systems");
    views.push(view);
    await flush();

    expect(view.container.textContent).toContain("Owner");
    expect(view.container.textContent).toContain("已停用");
    await click(view.container.querySelector('[aria-label="编辑业务系统"]')!);
    await flush();
    await setInput(document.querySelector("#name") as HTMLInputElement, "ESB 集成平台");
    await click(document.querySelector('[aria-label="保存业务系统"]')!);
    await flush();
    expect(updateSystem).toHaveBeenCalledWith(system.id, {
      name: "ESB 集成平台",
      description: "集成服务",
    });

    await click(view.container.querySelector('[aria-label="切换系统状态"]')!);
    await flush();
    await click(document.querySelector(".ant-popconfirm-buttons .ant-btn-primary")!);
    await flush();
    expect(updateSystem).toHaveBeenLastCalledWith(system.id, { status: "ACTIVE" });
  });

  it("keeps controls available when system mutations fail", async () => {
    const listSystems = vi.spyOn(apiClient, "listAdminSystems").mockResolvedValue(systemPage);
    vi.spyOn(apiClient, "listAccounts").mockResolvedValue(ownerPage);
    const createSystem = vi.spyOn(apiClient, "createSystem").mockRejectedValue(
      new ApiError(409, {
        code: "SYSTEM_EXISTS",
        message: "系统标识已存在",
        request_id: "request-id",
      }),
    );
    const updateSystem = vi
      .spyOn(apiClient, "updateSystem")
      .mockRejectedValue(new Error("network"));
    const assignOwners = vi
      .spyOn(apiClient, "assignSystemOwners")
      .mockRejectedValue(new Error("network"));
    const view = await mountWithAuth(<SystemsPage />, auth, "/admin/systems");
    views.push(view);
    await flush();

    await click(view.container.querySelector('[aria-label="新增业务系统"]')!);
    await flush();
    await setInput(document.querySelector("#code") as HTMLInputElement, "esb");
    await setInput(document.querySelector("#name") as HTMLInputElement, "重复系统");
    await click(document.querySelector('[aria-label="创建业务系统"]')!);
    await flush();
    expect(createSystem).toHaveBeenCalled();
    await click(document.querySelector(".ant-drawer-close")!);
    await flush();

    await click(view.container.querySelector('[aria-label="配置系统负责人"]')!);
    await flush();
    await click(document.querySelector('[aria-label="保存系统负责人"]')!);
    await flush();
    expect(assignOwners).toHaveBeenCalledWith(system.id, [], true);
    await click(document.querySelector(".ant-drawer-close")!);
    await flush();

    await click(view.container.querySelector('[aria-label="切换系统状态"]')!);
    await flush();
    await click(document.querySelector(".ant-popconfirm-buttons .ant-btn-primary")!);
    await flush();
    expect(updateSystem).toHaveBeenCalledWith(system.id, { status: "DISABLED" });

    listSystems.mockRejectedValueOnce(
      new ApiError(503, {
        code: "DEPENDENCY_UNAVAILABLE",
        message: "服务暂时不可用",
        request_id: "request-id",
      }),
    );
    await click(view.container.querySelector('[aria-label="刷新业务系统列表"]')!);
    await flush();
    expect(listSystems).toHaveBeenCalledTimes(2);
  });

  it("keeps systems visible and retries owner candidates independently", async () => {
    vi.spyOn(apiClient, "listAdminSystems").mockResolvedValue(systemPage);
    const listAccounts = vi
      .spyOn(apiClient, "listAccounts")
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValue(ownerPage);
    const view = await mountWithAuth(<SystemsPage />, auth, "/admin/systems");
    views.push(view);
    await flush();

    expect(view.container.textContent).toContain("企业服务总线");
    await click(view.container.querySelector('[aria-label="配置系统负责人"]')!);
    await flush();
    expect(document.body.textContent).toContain("负责人候选加载失败");
    await click(document.querySelector('[aria-label="重试加载负责人候选"]')!);
    await flush();
    expect(listAccounts).toHaveBeenCalledTimes(2);
    expect(document.body.textContent).not.toContain("负责人候选加载失败");
  });

  it("clears a preserved description before editing another system", async () => {
    const withoutDescription: BusinessSystemView = {
      ...system,
      id: "20000000-0000-0000-0000-000000000002",
      code: "CRM",
      name: "客户关系管理",
      description: null,
    };
    vi.spyOn(apiClient, "listAdminSystems").mockResolvedValue({
      ...systemPage,
      items: [system, withoutDescription],
      total: 2,
    });
    vi.spyOn(apiClient, "listAccounts").mockResolvedValue(ownerPage);
    const updateSystem = vi.spyOn(apiClient, "updateSystem").mockResolvedValue(withoutDescription);
    const view = await mountWithAuth(<SystemsPage />, auth, "/admin/systems");
    views.push(view);
    await flush();

    const editButtons = view.container.querySelectorAll('[aria-label="编辑业务系统"]');
    await click(editButtons[0]!);
    await flush();
    expect((document.querySelector("#description") as HTMLTextAreaElement).value).toBe("集成服务");
    await click(document.querySelector(".ant-drawer-close")!);
    await flush();
    await click(editButtons[1]!);
    await flush();
    expect((document.querySelector("#description") as HTMLTextAreaElement).value).toBe("");
    await click(document.querySelector('[aria-label="保存业务系统"]')!);
    await flush();
    expect(updateSystem).toHaveBeenCalledWith(withoutDescription.id, {
      name: withoutDescription.name,
      description: null,
    });
  });
});
