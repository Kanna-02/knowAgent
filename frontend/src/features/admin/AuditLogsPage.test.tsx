import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiClient } from "../../api/client";
import type { AuditLogPage, AuditLogView } from "../../api/types";
import {
  click,
  flush,
  mountWithAuth,
  mouseDown,
  setInput,
  type MountedView,
} from "../../test/renderTestApp";
import type { AuthContextValue } from "../auth/authContextValue";
import { AuditLogsPage } from "./AuditLogsPage";

const log: AuditLogView = {
  id: "50000000-0000-0000-0000-000000000001",
  actor_id: "10000000-0000-0000-0000-0000000000aa",
  action: "document.publish",
  object_type: "document_version",
  object_id: "40000000-0000-0000-0000-000000000001",
  result: "success",
  request_id: "req-xyz-12345678",
  context_data: { system_id: "test" },
  created_at: "2026-08-07T12:00:00Z",
  detail: "Published v1",
};

const logPage: AuditLogPage = {
  items: [log],
  page: 1,
  page_size: 20,
  total: 1,
};

const auth: AuthContextValue = {
  user: {
    id: "10000000-0000-0000-0000-000000000001",
    username: "admin",
    display_name: "Admin",
    role: "ADMIN",
    status: "ACTIVE",
    must_change_password: false,
    system_roles: [],
  },
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

describe("AuditLogsPage", () => {
  it("loads and displays audit logs with action and result columns", async () => {
    vi.spyOn(apiClient, "listAuditLogs").mockResolvedValue(logPage);

    const view = await mountWithAuth(<AuditLogsPage />, auth, "/admin/audit-logs");
    views.push(view);
    await flush();

    expect(view.container.textContent).toContain("document.publish");
    expect(view.container.textContent).toContain("Published v1");
    expect(view.container.textContent).toContain("成功");
  });

  it("shows error and keeps retry when load fails", async () => {
    const listAuditLogs = vi
      .spyOn(apiClient, "listAuditLogs")
      .mockRejectedValueOnce(
        new ApiError(503, {
          code: "DEPENDENCY_UNAVAILABLE",
          message: "服务暂时不可用",
          request_id: "audit-err",
        }),
      )
      .mockResolvedValue(logPage);

    const view = await mountWithAuth(<AuditLogsPage />, auth, "/admin/audit-log");
    views.push(view);
    await flush();

    expect(view.container.textContent).toContain("audit-err");

    await click(view.container.querySelector('[aria-label="重试加载审计日志"]')!);
    await flush();
    expect(listAuditLogs).toHaveBeenCalledTimes(2);
    await flush();
    expect(view.container.textContent).toContain("document.publish");
  });

  it("refreshes audit logs on button click", async () => {
    const listAuditLogs = vi.spyOn(apiClient, "listAuditLogs").mockResolvedValue(logPage);

    const view = await mountWithAuth(<AuditLogsPage />, auth, "/admin/audit-log");
    views.push(view);
    await flush();

    await click(view.container.querySelector('[aria-label="刷新审计日志"]')!);
    await flush();

    expect(listAuditLogs).toHaveBeenCalledTimes(2);
  });

  it("filters by action and resets to page 1", async () => {
    const listAuditLogs = vi.spyOn(apiClient, "listAuditLogs").mockResolvedValue(logPage);

    const view = await mountWithAuth(<AuditLogsPage />, auth, "/admin/audit-log");
    views.push(view);
    await flush();

    const actionInput = view.container.querySelector(
      '[aria-label="筛选操作类型"]',
    ) as HTMLInputElement;
    await setInput(actionInput, "document");
    await setInput(
      view.container.querySelector('[aria-label="筛选对象类型"]') as HTMLInputElement,
      "document_version",
    );
    await mouseDown(view.container.querySelector('[aria-label="筛选结果"]')!);
    const failureOption = [...document.body.querySelectorAll(".ant-select-item-option")].find(
      (option) => option.textContent === "失败",
    );
    if (!failureOption) throw new Error("Failure result option not found");
    await click(failureOption);
    await click(view.container.querySelector('[aria-label="应用筛选"]')!);
    await flush();

    expect(listAuditLogs).toHaveBeenLastCalledWith(
      expect.objectContaining({
        action: "document",
        object_type: "document_version",
        result: "failure",
        page: 1,
      }),
    );
  });

  it("renders null identifiers, context details, failures, and custom results", async () => {
    vi.spyOn(apiClient, "listAuditLogs").mockResolvedValue({
      items: [
        {
          ...log,
          id: "50000000-0000-0000-0000-000000000002",
          actor_id: null,
          object_type: null,
          result: "failure",
          request_id: null,
          detail: null,
          context_data: { reason: "denied" },
        },
        {
          ...log,
          id: "50000000-0000-0000-0000-000000000003",
          result: "skipped",
          detail: null,
          context_data: null,
        },
      ],
      page: 1,
      page_size: 20,
      total: 2,
    });

    const view = await mountWithAuth(<AuditLogsPage />, auth, "/admin/audit-logs");
    views.push(view);
    await flush();

    expect(view.container.textContent).toContain("失败");
    expect(view.container.textContent).toContain("skipped");
    expect(view.container.textContent).toContain('{"reason":"denied"}');
  });
});
