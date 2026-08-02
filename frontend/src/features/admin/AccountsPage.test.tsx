import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiClient } from "../../api/client";
import type { AccountPage, AccountView } from "../../api/types";
import {
  click,
  flush,
  mountWithAuth,
  mouseDown,
  setInput,
  type MountedView,
} from "../../test/renderTestApp";
import type { AuthContextValue } from "../auth/authContextValue";
import { AccountsPage } from "./AccountsPage";

const accounts: AccountView[] = [
  {
    id: "10000000-0000-0000-0000-000000000001",
    username: "alice",
    display_name: "Alice",
    role: "USER",
    source: "LOCAL_IMPORT",
    status: "ACTIVE",
    must_change_password: true,
    credential_batch: "batch-1",
    external_provider: null,
    created_at: "2026-08-02T10:00:00Z",
    updated_at: "2026-08-02T10:00:00Z",
  },
  {
    id: "10000000-0000-0000-0000-000000000002",
    username: "owner",
    display_name: "Owner",
    role: "SYSTEM_OWNER",
    source: "SSO",
    status: "ACTIVE",
    must_change_password: false,
    credential_batch: null,
    external_provider: "company",
    created_at: "2026-08-02T10:00:00Z",
    updated_at: "2026-08-02T10:00:00Z",
  },
  {
    id: "10000000-0000-0000-0000-000000000003",
    username: "admin",
    display_name: "Admin",
    role: "ADMIN",
    source: "ADMIN_CREATED",
    status: "DISABLED",
    must_change_password: false,
    credential_batch: null,
    external_provider: null,
    created_at: "2026-08-02T10:00:00Z",
    updated_at: "2026-08-02T10:00:00Z",
  },
];

const page: AccountPage = { items: accounts, page: 1, page_size: 20, total: 45 };
const adminUser = {
  id: accounts[2]!.id,
  username: "admin",
  display_name: "Admin",
  role: "ADMIN" as const,
  status: "ACTIVE" as const,
  must_change_password: false,
  system_roles: [],
};
let views: MountedView[] = [];

afterEach(async () => {
  for (const view of views.reverse()) await view.unmount();
  views = [];
  document
    .querySelectorAll(".ant-drawer, .ant-select-dropdown, .ant-popover")
    .forEach((element) => element.remove());
  vi.restoreAllMocks();
});

function auth(): AuthContextValue {
  return {
    user: adminUser,
    loading: false,
    bootstrapError: null,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
  };
}

async function mountPage(): Promise<MountedView> {
  const view = await mountWithAuth(<AccountsPage />, auth(), "/admin/accounts");
  views.push(view);
  await flush();
  return view;
}

function findDocumentElement(selector: string, text: string): Element {
  const normalizedText = text.replaceAll(/\s/g, "");
  const element = [...document.querySelectorAll(selector)].find((candidate) =>
    candidate.textContent?.replaceAll(/\s/g, "").includes(normalizedText),
  );
  if (!element) {
    throw new Error(
      `Missing ${selector} containing ${text}; body=${document.body.textContent?.slice(0, 500)}`,
    );
  }
  return element;
}

describe("AccountsPage", () => {
  it("loads, filters, paginates, creates, and changes account status", async () => {
    const listAccounts = vi.spyOn(apiClient, "listAccounts").mockResolvedValue(page);
    const createAdmin = vi.spyOn(apiClient, "createAdmin").mockResolvedValue(accounts[2]!);
    const setStatus = vi.spyOn(apiClient, "setAccountStatus").mockResolvedValue(accounts[0]!);
    const view = await mountPage();

    expect(view.container.textContent).toContain("alice");
    expect(view.container.textContent).toContain("系统负责人");
    expect(view.container.textContent).toContain("批量导入");
    expect(view.container.textContent).toContain("SSO");
    expect(view.container.textContent).toContain("已禁用");

    const selects = view.container.querySelectorAll('[role="combobox"]');
    await mouseDown(selects[0] as Element);
    await flush();
    await click(findDocumentElement(".ant-select-item-option", "平台管理员"));
    await flush();
    expect(listAccounts).toHaveBeenLastCalledWith(
      expect.objectContaining({ page: 1, role: "ADMIN" }),
    );

    await mouseDown(selects[1] as Element);
    await flush();
    await click(findDocumentElement(".ant-select-item-option", "已启用"));
    await flush();
    expect(listAccounts).toHaveBeenLastCalledWith(
      expect.objectContaining({ role: "ADMIN", status: "ACTIVE" }),
    );

    const nextPage = view.container.querySelector(".ant-pagination-next button");
    if (nextPage) {
      await click(nextPage);
      await flush();
      expect(listAccounts).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
    }

    await click(view.container.querySelector('[aria-label="刷新账号列表"]') as Element);
    await flush();
    expect(listAccounts.mock.calls.length).toBeGreaterThan(3);

    await click(findDocumentElement("button", "新增管理员"));
    await flush();
    await setInput(document.querySelector("#username") as HTMLInputElement, "second.admin");
    await setInput(document.querySelector("#displayName") as HTMLInputElement, "Second Admin");
    await setInput(
      document.querySelector("#temporaryPassword") as HTMLInputElement,
      "Temporary22@",
    );
    await click(findDocumentElement("button", "创建"));
    await flush();
    expect(createAdmin).toHaveBeenCalledWith({
      username: "second.admin",
      display_name: "Second Admin",
      temporary_password: "Temporary22@",
    });

    const statusButton = view.container.querySelector(
      `[data-row-key="${accounts[0]!.id}"] [aria-label="切换账号状态"]`,
    );
    await click(statusButton as Element);
    await flush();
    await click(findDocumentElement("button", "确认"));
    await flush();
    expect(setStatus).toHaveBeenCalledWith(accounts[0]!.id, "DISABLED");
  });

  it("keeps the page usable when list and mutation requests fail", async () => {
    const listAccounts = vi
      .spyOn(apiClient, "listAccounts")
      .mockResolvedValueOnce(page)
      .mockRejectedValueOnce(
        new ApiError(503, {
          code: "DEPENDENCY_UNAVAILABLE",
          message: "服务暂时不可用",
          request_id: "request-id",
        }),
      );
    vi.spyOn(apiClient, "createAdmin").mockRejectedValue(new Error("network"));
    const setStatus = vi
      .spyOn(apiClient, "setAccountStatus")
      .mockRejectedValue(new Error("network"));
    const view = await mountPage();

    await click(view.container.querySelector('[aria-label="刷新账号列表"]') as Element);
    await flush();
    expect(listAccounts).toHaveBeenCalledTimes(2);

    await click(findDocumentElement("button", "新增管理员"));
    await flush();
    await setInput(document.querySelector("#username") as HTMLInputElement, "second.admin");
    await setInput(document.querySelector("#displayName") as HTMLInputElement, "Second Admin");
    await setInput(
      document.querySelector("#temporaryPassword") as HTMLInputElement,
      "Temporary22@",
    );
    await click(findDocumentElement("button", "创建"));
    await flush();

    const statusButton = view.container.querySelector(
      `[data-row-key="${accounts[0]!.id}"] [aria-label="切换账号状态"]`,
    );
    await click(statusButton as Element);
    await flush();
    await click(findDocumentElement("button", "确认"));
    await flush();
    expect(setStatus).toHaveBeenCalledWith(accounts[0]!.id, "DISABLED");
  });
});
