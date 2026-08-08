import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../api/client";
import type { NotificationDeliveryPage, NotificationDeliveryView } from "../../api/types";
import { click, flush, mountWithAuth, mouseDown, type MountedView } from "../../test/renderTestApp";
import type { AuthContextValue } from "../auth/authContextValue";
import { NotificationDeliveriesPage } from "./NotificationDeliveriesPage";

const delivery: NotificationDeliveryView = {
  id: "80000000-0000-0000-0000-000000000001",
  outbox_id: "81000000-0000-0000-0000-000000000001",
  event_type: "ticket_created",
  recipient_id: "10000000-0000-0000-0000-000000000002",
  recipient_address: "owner.one",
  status: "PERMANENT_FAILURE",
  idempotency_key: "ticket:1:created:owner.one",
  attempt_count: 3,
  cycle_attempt: 3,
  next_attempt_at: null,
  last_status_code: 401,
  last_error_code: "PROVIDER_REJECTED",
  last_error_message: "notification provider rejected the request",
  provider_message_id: null,
  response_summary: null,
  delivered_at: null,
  created_at: "2026-08-08T00:00:00Z",
  updated_at: "2026-08-08T00:01:00Z",
};

const page: NotificationDeliveryPage = {
  items: [delivery],
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

let view: MountedView | null = null;

afterEach(async () => {
  if (view) await view.unmount();
  view = null;
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

describe("NotificationDeliveriesPage", () => {
  it("shows recipient, attempts and permanent failure reason", async () => {
    vi.spyOn(apiClient, "listNotificationDeliveries").mockResolvedValue(page);
    view = await mountWithAuth(<NotificationDeliveriesPage />, auth, "/admin/notifications");
    await flush();

    expect(view.container.textContent).toContain("owner.one");
    expect(view.container.textContent).toContain("永久失败");
    expect(view.container.textContent).toContain("PROVIDER_REJECTED");
    expect(view.container.textContent).toContain("3");
  });

  it("allows manual retry only for permanent failures", async () => {
    vi.spyOn(apiClient, "listNotificationDeliveries").mockResolvedValue(page);
    const retry = vi
      .spyOn(apiClient, "retryNotificationDelivery")
      .mockResolvedValue({ ...delivery, status: "PENDING", cycle_attempt: 0 });
    view = await mountWithAuth(<NotificationDeliveriesPage />, auth, "/admin/notifications");
    await flush();

    await click(
      [...view.container.querySelectorAll("button")].find(
        (button) => button.textContent?.trim() === "重试",
      )!,
    );
    await flush();
    await click(document.body.querySelector(".ant-popconfirm-buttons .ant-btn-primary")!);
    await flush();

    expect(retry).toHaveBeenCalledWith(delivery.id);
  });

  it("recovers after a delivery list error", async () => {
    const load = vi
      .spyOn(apiClient, "listNotificationDeliveries")
      .mockRejectedValueOnce(new Error("unavailable"))
      .mockResolvedValueOnce(page);
    view = await mountWithAuth(<NotificationDeliveriesPage />, auth, "/admin/notifications");
    await flush();

    await click(view.container.querySelector('[aria-label="重试加载通知记录"]')!);
    await flush();
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("renders every delivery state and optional provider fields", async () => {
    const statuses: NotificationDeliveryView["status"][] = [
      "PENDING",
      "QUEUED",
      "DELIVERING",
      "RETRY_SCHEDULED",
      "DELIVERED",
      "SKIPPED",
    ];
    vi.spyOn(apiClient, "listNotificationDeliveries").mockResolvedValue({
      items: statuses.map((status, index) => ({
        ...delivery,
        id: `80000000-0000-0000-0000-0000000000${index + 10}`,
        event_type: "ticket_replied",
        status,
        next_attempt_at: index === 3 ? "2026-08-08T00:05:00Z" : null,
        last_error_code: null,
        last_error_message: null,
        provider_message_id: index === 4 ? "provider-delivered" : null,
      })),
      page: 1,
      page_size: 20,
      total: statuses.length,
    });

    view = await mountWithAuth(<NotificationDeliveriesPage />, auth, "/admin/notifications");
    await flush();

    expect(view.container.textContent).toContain("待投递");
    expect(view.container.textContent).toContain("已入队");
    expect(view.container.textContent).toContain("投递中");
    expect(view.container.textContent).toContain("等待重试");
    expect(view.container.textContent).toContain("已送达");
    expect(view.container.textContent).toContain("已跳过");
    expect(view.container.textContent).toContain("负责人回复");
    expect(view.container.textContent).toContain("provider-delivered");
  });

  it("applies status and event filters", async () => {
    const load = vi.spyOn(apiClient, "listNotificationDeliveries").mockResolvedValue(page);
    view = await mountWithAuth(<NotificationDeliveriesPage />, auth, "/admin/notifications");
    await flush();

    await mouseDown(view.container.querySelector('[aria-label="筛选通知状态"]')!);
    const statusOption = [...document.body.querySelectorAll(".ant-select-item-option")].find(
      (option) => option.textContent === "永久失败",
    );
    if (!statusOption) throw new Error("Permanent failure option not found");
    await click(statusOption);
    await flush();

    await mouseDown(view.container.querySelector('[aria-label="筛选通知事件"]')!);
    const eventOption = [...document.body.querySelectorAll(".ant-select-item-option")].find(
      (option) => option.textContent === "负责人回复",
    );
    if (!eventOption) throw new Error("Ticket replied option not found");
    await click(eventOption);
    await flush();

    expect(load).toHaveBeenLastCalledWith({
      page: 1,
      pageSize: 20,
      status: "PERMANENT_FAILURE",
      eventType: "ticket_replied",
    });
  });

  it("reports a manual retry failure", async () => {
    vi.spyOn(apiClient, "listNotificationDeliveries").mockResolvedValue(page);
    const retry = vi
      .spyOn(apiClient, "retryNotificationDelivery")
      .mockRejectedValue(new Error("retry unavailable"));
    view = await mountWithAuth(<NotificationDeliveriesPage />, auth, "/admin/notifications");
    await flush();

    await click(
      [...view.container.querySelectorAll("button")].find(
        (button) => button.textContent?.trim() === "重试",
      )!,
    );
    await flush();
    await click(document.body.querySelector(".ant-popconfirm-buttons .ant-btn-primary")!);
    await flush();

    expect(retry).toHaveBeenCalledWith(delivery.id);
    expect(document.body.textContent).toContain("通知重试失败");
  });
});
