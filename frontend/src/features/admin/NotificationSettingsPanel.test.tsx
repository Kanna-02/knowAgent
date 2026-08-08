import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../api/client";
import type { NotificationConfigurationView } from "../../api/types";
import { click, flush, mountWithAuth, setInput, type MountedView } from "../../test/renderTestApp";
import type { AuthContextValue } from "../auth/authContextValue";
import { NotificationSettingsPanel } from "./NotificationSettingsPanel";

const configuration: NotificationConfigurationView = {
  id: "70000000-0000-0000-0000-000000000001",
  enabled: true,
  endpoint_url: "https://notify.company.internal/api/messages",
  auth_type: "BEARER",
  auth_header_name: "Authorization",
  secret_reference: "KNOWAGENT_NOTIFICATION_TOKEN",
  ticket_created_template: '{"receiver":"${recipient}","ticket":"${ticket_id}"}',
  ticket_replied_template: '{"receiver":"${recipient}","content":"${reply_body}"}',
  success_status_codes: [200, 201, 202],
  timeout_seconds: 5,
  max_attempts: 3,
  retry_base_seconds: 30,
  updated_by: "10000000-0000-0000-0000-000000000001",
  created_at: "2026-08-08T00:00:00Z",
  updated_at: "2026-08-08T01:00:00Z",
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

describe("NotificationSettingsPanel", () => {
  it("loads editable endpoint, secret reference and retry settings", async () => {
    vi.spyOn(apiClient, "getNotificationConfiguration").mockResolvedValue(configuration);
    view = await mountWithAuth(<NotificationSettingsPanel />, auth, "/admin/configuration");
    await flush();

    expect((view.container.querySelector("#endpoint_url") as HTMLInputElement).value).toBe(
      configuration.endpoint_url,
    );
    expect((view.container.querySelector("#secret_reference") as HTMLInputElement).value).toBe(
      "KNOWAGENT_NOTIFICATION_TOKEN",
    );
    expect(view.container.textContent).toContain("密钥值不会保存到数据库");
  });

  it("saves changed endpoint through the administration API", async () => {
    vi.spyOn(apiClient, "getNotificationConfiguration").mockResolvedValue(configuration);
    const update = vi
      .spyOn(apiClient, "updateNotificationConfiguration")
      .mockResolvedValue({ ...configuration, endpoint_url: "https://notify.company.internal/v2" });
    view = await mountWithAuth(<NotificationSettingsPanel />, auth, "/admin/configuration");
    await flush();

    await setInput(
      view.container.querySelector("#endpoint_url")!,
      "https://notify.company.internal/v2",
    );
    await click(
      [...view.container.querySelectorAll("button")].find(
        (button) => button.textContent?.trim() === "保存通知配置",
      )!,
    );
    await flush();

    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ endpoint_url: "https://notify.company.internal/v2" }),
    );
  });

  it("allows a disabled configuration to keep an empty endpoint", async () => {
    const disabled = {
      ...configuration,
      enabled: false,
      endpoint_url: "",
      auth_type: "NONE" as const,
      auth_header_name: null,
      secret_reference: null,
    };
    vi.spyOn(apiClient, "getNotificationConfiguration").mockResolvedValue(disabled);
    const update = vi
      .spyOn(apiClient, "updateNotificationConfiguration")
      .mockResolvedValue(disabled);
    view = await mountWithAuth(<NotificationSettingsPanel />, auth, "/admin/configuration");
    await flush();

    await click(
      [...view.container.querySelectorAll("button")].find(
        (button) => button.textContent?.trim() === "保存通知配置",
      )!,
    );
    await flush();

    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: false, endpoint_url: "" }),
    );
  });

  it("shows a retry action when configuration loading fails", async () => {
    const load = vi
      .spyOn(apiClient, "getNotificationConfiguration")
      .mockRejectedValueOnce(new Error("unavailable"))
      .mockResolvedValueOnce(configuration);
    view = await mountWithAuth(<NotificationSettingsPanel />, auth, "/admin/configuration");
    await flush();

    expect(view.container.textContent).toContain("通知配置加载失败");
    await click(view.container.querySelector('[aria-label="重试加载通知配置"]')!);
    await flush();
    expect(load).toHaveBeenCalledTimes(2);
  });
});
