import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../api/client";
import type {
  BusinessSystemView,
  TicketStatus,
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

async function setTextArea(element: HTMLTextAreaElement, value: string): Promise<void> {
  const descriptor = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
  if (!descriptor?.set) throw new Error("HTML textarea value setter is unavailable");
  descriptor.set.call(element, value);
  element.dispatchEvent(new Event("input", { bubbles: true }));
  element.dispatchEvent(new Event("change", { bubbles: true }));
  await flush();
}

function buttonWithText(text: string): HTMLButtonElement {
  const button = Array.from(document.body.querySelectorAll("button")).find((candidate) =>
    candidate.textContent?.includes(text),
  );
  if (!button) throw new Error(`Button not found: ${text}`);
  return button;
}

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

  it("applies status filters and renders repeated occurrences", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    const listTickets = vi.spyOn(apiClient, "listTickets").mockResolvedValue({
      items: [{ ...ticket, occurrence_count: 3 }],
      page: 1,
      page_size: 20,
      total: 1,
    });
    view = await mountWithAuth(<TicketsPage />, ownerAuth, "/app/tickets");
    await flush();
    expect(view.container.textContent).toContain("x3");

    listTickets.mockClear();
    const inProgressFilter = Array.from(view.container.querySelectorAll("label")).find(
      (label) => label.textContent === "处理中",
    );
    if (!inProgressFilter) throw new Error("In-progress ticket filter not found");
    await click(inProgressFilter);
    await flush();

    expect(listTickets).toHaveBeenLastCalledWith({
      page: 1,
      pageSize: 20,
      status: "in_progress",
    });
  });

  it("sends replies, submits answer candidates, and starts ticket processing", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listTickets").mockResolvedValue({
      items: [ticket],
      page: 1,
      page_size: 20,
      total: 1,
    });
    vi.spyOn(apiClient, "getTicket").mockResolvedValue(ticket);
    vi.spyOn(apiClient, "listTicketReplies").mockResolvedValue([]);
    vi.spyOn(apiClient, "listTicketTransitions").mockResolvedValue([]);
    const replyTicket = vi.spyOn(apiClient, "replyTicket").mockResolvedValue({
      id: "50000000-0000-0000-0000-000000000002",
      ticket_id: ticket.id,
      system_id: SYSTEM_ID,
      author_id: ticket.requester_id,
      author_role: "reviewer",
      body: "已定位连接池耗尽",
      created_at: "2026-08-02T12:00:00Z",
    });
    const submitAnswer = vi.spyOn(apiClient, "submitTicketAnswer").mockResolvedValue();
    const transitionTicket = vi
      .spyOn(apiClient, "transitionTicket")
      .mockResolvedValue({ ...ticket, status: "in_progress" });

    view = await mountWithAuth(<TicketsPage />, ownerAuth, "/app/tickets");
    await flush();
    await click(view.container.querySelector(".ticket-title-button") as Element);
    await flush();

    await setTextArea(
      document.body.querySelector('[aria-label="回复内容"]') as HTMLTextAreaElement,
      "已定位连接池耗尽",
    );
    await click(buttonWithText("发送回复"));
    await flush();
    expect(replyTicket).toHaveBeenCalledWith(ticket.id, "已定位连接池耗尽");
    expect(document.body.textContent).toContain("已定位连接池耗尽");

    await setTextArea(
      document.body.querySelector('[aria-label="答案候选"]') as HTMLTextAreaElement,
      "扩容连接池并重启连接器",
    );
    await click(buttonWithText("提交答案"));
    await flush();
    expect(submitAnswer).toHaveBeenCalledWith(ticket.id, "扩容连接池并重启连接器");

    await click(document.body.querySelector('[aria-label="开始处理工单"]') as Element);
    await flush();
    expect(transitionTicket).toHaveBeenCalledWith(ticket.id, "start", undefined);
  });

  it("recovers the ticket list and reports detail and mutation failures", async () => {
    vi.spyOn(apiClient, "listSystems").mockRejectedValue(new Error("systems unavailable"));
    vi.spyOn(apiClient, "listTickets")
      .mockRejectedValueOnce(new Error("tickets unavailable"))
      .mockResolvedValue({ items: [ticket], page: 1, page_size: 20, total: 1 });
    vi.spyOn(apiClient, "listTicketReplies").mockRejectedValue(new Error("detail unavailable"));
    vi.spyOn(apiClient, "listTicketTransitions").mockResolvedValue([]);
    vi.spyOn(apiClient, "replyTicket").mockRejectedValue(new Error("reply unavailable"));
    vi.spyOn(apiClient, "submitTicketAnswer").mockRejectedValue(new Error("answer unavailable"));
    vi.spyOn(apiClient, "transitionTicket").mockRejectedValue(new Error("transition unavailable"));

    view = await mountWithAuth(<TicketsPage />, ownerAuth, "/app/tickets");
    await flush();
    expect(view.container.textContent).toContain("工单列表加载失败");
    await click(view.container.querySelector('[aria-label="重试加载工单列表"]') as Element);
    await flush();
    await click(view.container.querySelector(".ticket-title-button") as Element);
    await flush();
    expect(document.body.textContent).toContain("工单详情加载失败");

    await setTextArea(
      document.body.querySelector('[aria-label="回复内容"]') as HTMLTextAreaElement,
      "retry reply",
    );
    await click(buttonWithText("发送回复"));
    await flush();
    await setTextArea(
      document.body.querySelector('[aria-label="答案候选"]') as HTMLTextAreaElement,
      "retry answer",
    );
    await click(buttonWithText("提交答案"));
    await flush();
    await click(document.body.querySelector('[aria-label="开始处理工单"]') as Element);
    await flush();

    expect(document.body.textContent).toContain("回复发送失败");
    expect(document.body.textContent).toContain("答案提交失败");
    expect(document.body.textContent).toContain("开始处理失败");
  });

  it.each<[TicketStatus, string]>([
    ["assigned", "标记为已解决"],
    ["in_progress", "标记为已解决"],
    ["resolved", "重新打开工单"],
    ["closed", "重新打开工单"],
  ])("shows the valid management action for %s tickets", async (status, actionLabel) => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listTickets").mockResolvedValue({
      items: [{ ...ticket, status }],
      page: 1,
      page_size: 20,
      total: 1,
    });
    vi.spyOn(apiClient, "listTicketReplies").mockResolvedValue([]);
    vi.spyOn(apiClient, "listTicketTransitions").mockResolvedValue([]);

    view = await mountWithAuth(<TicketsPage />, ownerAuth, "/app/tickets");
    await flush();
    await click(view.container.querySelector(".ticket-title-button") as Element);
    await flush();

    expect(document.body.querySelector(`[aria-label="${actionLabel}"]`)).not.toBeNull();
    if (status === "closed") {
      expect(document.body.querySelector('[aria-label="关闭工单"]')).toBeNull();
    }
  });
});
