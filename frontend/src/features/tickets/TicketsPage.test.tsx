import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../api/client";
import type {
  BusinessSystemView,
  TicketTransitionView,
  TicketReplyView,
  TicketView,
} from "../../api/types";
import { click, flush, mountWithAuth, type MountedView } from "../../test/renderTestApp";
import type { AuthContextValue } from "../auth/authContextValue";
import { TicketsPage } from "./TicketsPage";

const SYSTEM_ID = "20000000-0000-0000-0000-000000000001";

const system: BusinessSystemView = {
  id: SYSTEM_ID,
  code: "ESB",
  name: "企业服务总线",
  description: null,
  status: "ACTIVE",
  owners: [],
  created_at: "2026-08-02T10:00:00Z",
  updated_at: "2026-08-02T10:00:00Z",
};

const ticket: TicketView = {
  id: "40000000-0000-0000-0000-000000000001",
  system_id: SYSTEM_ID,
  requester_id: "10000000-0000-0000-0000-000000000001",
  source_run_id: "30000000-0000-0000-0000-000000000001",
  assignee_id: null,
  status: "open",
  priority: "normal",
  title: "ESB 连接超时",
  question: "如何排查 ESB 连接超时？",
  normalized_question: "如何排查 esb 连接超时",
  occurrence_count: 1,
  created_at: "2026-08-02T10:00:00Z",
  updated_at: "2026-08-02T10:00:00Z",
};

const ownerAuth: AuthContextValue = {
  user: {
    id: "10000000-0000-0000-0000-000000000001",
    username: "owner",
    display_name: "Owner",
    role: "SYSTEM_OWNER",
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

describe("TicketsPage", () => {
  it("lists tickets and renders empty state", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listTickets").mockResolvedValue({
      items: [],
      page: 1,
      page_size: 20,
      total: 0,
    });
    view = await mountWithAuth(<TicketsPage />, ownerAuth, "/app/tickets");
    await flush();

    expect(view.container.textContent).toContain("暂无工单");
  });

  it("opens a ticket detail with replies, transitions, and management actions", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listTickets").mockResolvedValue({
      items: [ticket],
      page: 1,
      page_size: 20,
      total: 1,
    });
    const replies: TicketReplyView[] = [
      {
        id: "50000000-0000-0000-0000-000000000001",
        ticket_id: ticket.id,
        system_id: SYSTEM_ID,
        author_id: ticket.requester_id,
        author_role: "requester",
        body: "补充：复现于生产环境",
        created_at: "2026-08-02T11:00:00Z",
      },
    ];
    const transitions: TicketTransitionView[] = [
      {
        id: "60000000-0000-0000-0000-000000000001",
        ticket_id: ticket.id,
        system_id: SYSTEM_ID,
        actor_id: ticket.requester_id,
        from_status: null,
        to_status: "open",
        action: "create",
        created_at: "2026-08-02T10:00:00Z",
      },
    ];
    vi.spyOn(apiClient, "listTicketReplies").mockResolvedValue(replies);
    vi.spyOn(apiClient, "listTicketTransitions").mockResolvedValue(transitions);

    view = await mountWithAuth(<TicketsPage />, ownerAuth, "/app/tickets");
    await flush();
    expect(view.container.textContent).toContain("ESB 连接超时");

    await click(view.container.querySelector(".ticket-title-button") as Element);
    await flush();

    const body = document.body;
    expect(body.textContent).toContain("如何排查 ESB 连接超时？");
    expect(body.textContent).toContain("补充：复现于生产环境");
    expect(body.textContent).toContain("状态流转");
    expect(body.querySelector('[aria-label="开始处理工单"]')).not.toBeNull();
    expect(body.querySelector('[aria-label="关闭工单"]')).not.toBeNull();
    expect(body.textContent).toContain("提交答案候选");
  });

  it("hides management UI for ordinary users", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listTickets").mockResolvedValue({
      items: [ticket],
      page: 1,
      page_size: 20,
      total: 1,
    });
    vi.spyOn(apiClient, "listTicketReplies").mockResolvedValue([]);
    vi.spyOn(apiClient, "listTicketTransitions").mockResolvedValue([]);

    const ownerUser = ownerAuth.user as NonNullable<typeof ownerAuth.user>;
    const userAuth: AuthContextValue = {
      ...ownerAuth,
      user: {
        id: ownerUser.id,
        username: ownerUser.username,
        display_name: ownerUser.display_name,
        role: "USER",
        status: ownerUser.status,
        must_change_password: ownerUser.must_change_password,
        system_roles: ownerUser.system_roles,
      },
    };
    view = await mountWithAuth(<TicketsPage />, userAuth, "/app/tickets");
    await flush();
    await click(view.container.querySelector(".ticket-title-button") as Element);
    await flush();

    expect(document.body.querySelector('[aria-label="开始处理工单"]')).toBeNull();
    expect(document.body.textContent).not.toContain("提交答案候选");
    expect(document.body.querySelector('[aria-label="回复内容"]')).not.toBeNull();
  });
});
