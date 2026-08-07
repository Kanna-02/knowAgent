import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../api/client";
import type { BusinessSystemView, ConversationView, QuestionStreamEvent } from "../../api/types";
import { click, flush, mountWithAuth, mouseDown, type MountedView } from "../../test/renderTestApp";
import type { AuthContextValue } from "./authContextValue";
import { UserHomePage } from "./UserHomePage";

const SYSTEM_ID = "20000000-0000-0000-0000-000000000001";
const CONVERSATION_ID = "40000000-0000-0000-0000-000000000001";

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

const conversation: ConversationView = {
  id: CONVERSATION_ID,
  system_id: SYSTEM_ID,
  account_id: "10000000-0000-0000-0000-000000000001",
  title: "问题",
  created_at: "2026-08-02T10:00:00Z",
  updated_at: "2026-08-02T10:00:00Z",
};

const auth: AuthContextValue = {
  user: {
    id: "10000000-0000-0000-0000-000000000001",
    username: "alice",
    display_name: "Alice",
    role: "USER",
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

class FakeEventSource {
  static last: FakeEventSource | null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.last = this;
  }
  close() {
    this.open = false;
    if (FakeEventSource.last === this) FakeEventSource.last = null;
  }
  open = true;
  emit(event: QuestionStreamEvent): void {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(event) }));
  }
}

function setTextareaValue(textarea: HTMLTextAreaElement, value: string): void {
  const descriptor = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
  descriptor?.set?.call(textarea, value);
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
}

let view: MountedView | null = null;

afterEach(async () => {
  if (view) await view.unmount();
  view = null;
  document.body.innerHTML = "";
  FakeEventSource.last = null;
  vi.restoreAllMocks();
  (globalThis as { EventSource: unknown }).EventSource = undefined;
  (window as { EventSource: unknown }).EventSource = undefined;
});

async function selectSystem(container: HTMLElement): Promise<void> {
  await mouseDown(container.querySelector('[role="combobox"]')!);
  await flush();
  const option = [...document.querySelectorAll(".ant-select-item-option")].find((item) =>
    item.textContent?.includes("企业服务总线"),
  );
  (option as HTMLElement).click();
  await flush();
}

describe("UserHomePage SSE stream", () => {
  it("renders the streamed answer until completion", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listConversations").mockResolvedValue({
      items: [],
      page: 1,
      page_size: 100,
      total: 0,
    });
    vi.spyOn(apiClient, "createConversation").mockResolvedValue(conversation);
    (globalThis as { EventSource: unknown }).EventSource = FakeEventSource;
    window.EventSource = FakeEventSource as unknown as typeof EventSource;

    view = await mountWithAuth(<UserHomePage />, auth, "/app");
    await flush();
    await selectSystem(view.container);
    expect(view.container.textContent).toContain("当前系统：企业服务总线");

    const startStream = vi.spyOn(apiClient, "startQuestionStream").mockResolvedValue({
      token: "stream-token",
      account_id: auth.user!.id,
      run_id: "30000000-0000-0000-0000-000000000001",
      system_id: SYSTEM_ID,
      question: "问题",
      required_terms: [],
      conversation_id: CONVERSATION_ID,
      retrieval_profile: null,
      expires_at: "2026-08-02T12:00:00Z",
    });

    const textarea = view.container.querySelector(
      'textarea[aria-label="问题输入"]',
    ) as HTMLTextAreaElement;
    setTextareaValue(textarea, "问题");
    await flush();

    await click(view.container.querySelector('[aria-label="提交问题"]') as Element);
    await flush();
    await flush();

    expect(startStream).toHaveBeenCalledWith({
      system_id: SYSTEM_ID,
      question: "问题",
      required_terms: [],
      conversation_id: CONVERSATION_ID,
    });

    const source = FakeEventSource.last;
    expect(source).not.toBeNull();
    source!.emit({
      type: "retrieval_started",
      run_id: "x",
      system_id: SYSTEM_ID,
      question: "问题",
      rewritten_query: "企业服务总线问题",
      intent: "follow_up",
      rewrite_prompt_version: "query-rewrite-v1",
    });
    await flush();
    source!.emit({
      type: "evidence_ready",
      run_id: "x",
      evidence: [],
      degraded_reasons: ["RERANK_UNAVAILABLE"],
    });
    await flush();
    source!.emit({
      type: "decision",
      run_id: "x",
      outcome: "sufficient",
      policy_version: "evidence-v1",
      reason_codes: [],
      decided_at: "2026-08-02T10:00:00Z",
    });
    await flush();
    source!.emit({ type: "answer_delta", run_id: "x", delta: "第一" });
    await flush();
    source!.emit({ type: "answer_delta", run_id: "x", delta: "段" });
    await flush();
    source!.emit({
      type: "answer_completed",
      run_id: "x",
      answer: {
        text: "第一段：完整答案",
        claims: [],
        citations: [],
        model: "qwen",
        prompt_version: "grounded-answer-v1",
      },
      degraded_reasons: ["RERANK_UNAVAILABLE"],
    });
    await flush();

    expect(view.container.textContent).toContain("第一段：完整答案");
    expect(view.container.textContent).toContain("已完成");
    expect(view.container.textContent).toContain("检索已降级");
    expect(view.container.textContent).toContain("基础融合排序");
    expect(view.container.textContent).toContain("已关联上下文");
  });

  it("surfaces refusal and ticket routing when evidence is insufficient", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listConversations").mockResolvedValue({
      items: [],
      page: 1,
      page_size: 100,
      total: 0,
    });
    vi.spyOn(apiClient, "createConversation").mockResolvedValue(conversation);
    (globalThis as { EventSource: unknown }).EventSource = FakeEventSource;
    window.EventSource = FakeEventSource as unknown as typeof EventSource;
    vi.spyOn(apiClient, "startQuestionStream").mockResolvedValue({
      token: "stream-token",
      account_id: auth.user!.id,
      run_id: "30000000-0000-0000-0000-000000000001",
      system_id: SYSTEM_ID,
      question: "问题",
      required_terms: [],
      conversation_id: CONVERSATION_ID,
      retrieval_profile: null,
      expires_at: "2026-08-02T12:00:00Z",
    });

    view = await mountWithAuth(<UserHomePage />, auth, "/app");
    await flush();
    await selectSystem(view.container);
    const textarea = view.container.querySelector(
      'textarea[aria-label="问题输入"]',
    ) as HTMLTextAreaElement;
    setTextareaValue(textarea, "问题");
    await flush();
    await click(view.container.querySelector('[aria-label="提交问题"]') as Element);
    await flush();

    const source = FakeEventSource.last!;
    source.emit({
      type: "refused",
      run_id: "x",
      ticket_id: "90000000-0000-0000-0000-000000000001",
      outcome: "insufficient",
      reason_codes: ["no_evidence"],
      policy_version: "evidence-v1",
      decided_at: "2026-08-02T10:00:00Z",
      degraded_reasons: ["VECTOR_UNAVAILABLE"],
    });
    await flush();

    expect(view.container.textContent).toContain("无法基于现有知识回答此问题");
    expect(view.container.textContent).toContain("工单");
    expect(view.container.textContent).toContain("仅使用关键词检索");
  });
});
