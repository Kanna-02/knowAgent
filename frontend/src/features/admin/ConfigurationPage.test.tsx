import { afterEach, describe, expect, it, vi } from "vitest";
import { act } from "react";

import { apiClient } from "../../api/client";
import type { PromptDefinitionView, RetrievalProfileView } from "../../api/types";
import {
  click,
  flush,
  mountWithAuth,
  mouseDown,
  setInput,
  type MountedView,
} from "../../test/renderTestApp";
import type { AuthContextValue } from "../auth/authContextValue";
import { ConfigurationPage } from "./ConfigurationPage";

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

const prompts: PromptDefinitionView[] = [
  {
    scenario: "grounded_answer",
    version: "grounded-answer-v1",
    content: "只使用证据回答。",
    enabled: true,
    created_at: "2026-08-03T00:00:00Z",
    change_note: "初始版本",
  },
  {
    scenario: "grounded_answer",
    version: "grounded-answer-v2",
    content: "更严格地使用证据回答。",
    enabled: false,
    created_at: "2026-08-07T00:00:00Z",
    change_note: "严格引用",
  },
];

const profiles: RetrievalProfileView[] = [
  {
    name: "default",
    version: "profile-v1",
    keyword_top_k: 20,
    vector_top_k: 20,
    result_top_k: 10,
    rrf_k: 60,
    keyword_weight: 1,
    vector_weight: 1,
    rerank_candidate_top_k: 20,
    rerank_top_k: 10,
    evidence_max_items: 6,
    evidence_max_characters: 12000,
    is_active: true,
    created_at: "2026-08-07T00:00:00Z",
    change_note: "初始配置",
  },
  {
    name: "default",
    version: "profile-v2",
    keyword_top_k: 24,
    vector_top_k: 20,
    result_top_k: 10,
    rrf_k: 60,
    keyword_weight: 1.2,
    vector_weight: 1,
    rerank_candidate_top_k: 20,
    rerank_top_k: 10,
    evidence_max_items: 6,
    evidence_max_characters: 12000,
    is_active: false,
    created_at: "2026-08-07T01:00:00Z",
    change_note: "提高关键词召回",
  },
];

let view: MountedView | null = null;

afterEach(async () => {
  if (view) await view.unmount();
  view = null;
  document.body.innerHTML = "";
  vi.restoreAllMocks();
});

function mockLists(): void {
  vi.spyOn(apiClient, "listPromptDefinitions").mockResolvedValue({
    items: prompts,
    page: 1,
    page_size: 100,
    total: prompts.length,
  });
  vi.spyOn(apiClient, "listRetrievalProfiles").mockResolvedValue({
    items: profiles,
    page: 1,
    page_size: 100,
    total: profiles.length,
  });
}

function findButton(text: string): HTMLButtonElement {
  const button = [...document.body.querySelectorAll("button")].find(
    (element) => element.textContent?.trim() === text,
  );
  if (!button) throw new Error(`missing button: ${text}`);
  return button;
}

async function setTextarea(id: string, value: string): Promise<void> {
  const textarea = document.querySelector<HTMLTextAreaElement>(`#${id}`);
  if (!textarea) throw new Error(`missing textarea: ${id}`);
  const descriptor = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
  await act(async () => {
    descriptor?.set?.call(textarea, value);
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    textarea.dispatchEvent(new Event("change", { bubbles: true }));
    await Promise.resolve();
  });
}

describe("ConfigurationPage", () => {
  it("renders prompt and retrieval profile versions", async () => {
    mockLists();
    view = await mountWithAuth(<ConfigurationPage />, auth, "/admin/configuration");
    await flush();
    await flush();

    expect(view.container.textContent).toContain("grounded-answer-v1");
    expect(view.container.textContent).toContain("grounded-answer-v2");
    const profileTab = [...view.container.querySelectorAll('[role="tab"]')].find((element) =>
      element.textContent?.includes("检索配置版本"),
    );
    await click(profileTab!);
    await flush();
    expect(view.container.textContent).toContain("profile-v1");
    expect(view.container.textContent).toContain("关键词 Top-K");
  });

  it("activates an inactive prompt version after confirmation", async () => {
    mockLists();
    const activate = vi
      .spyOn(apiClient, "activatePromptDefinition")
      .mockResolvedValue({ ...prompts[1]!, enabled: true });
    view = await mountWithAuth(<ConfigurationPage />, auth, "/admin/configuration");
    await flush();
    await flush();

    const activateButton = [...view.container.querySelectorAll("button")].find(
      (element) => element.textContent?.trim() === "激活",
    );
    await click(activateButton!);
    await flush();
    const confirmButton = document.body.querySelector<HTMLButtonElement>(
      ".ant-popconfirm-buttons .ant-btn-primary",
    );
    await click(confirmButton!);
    await flush();

    expect(activate).toHaveBeenCalledWith("grounded_answer", "grounded-answer-v2");
  });

  it("creates a versioned query rewrite prompt", async () => {
    mockLists();
    const create = vi
      .spyOn(apiClient, "createPromptDefinition")
      .mockResolvedValue({ ...prompts[1]!, scenario: "query_rewrite" });
    view = await mountWithAuth(<ConfigurationPage />, auth, "/admin/configuration");
    await flush();
    await flush();

    await click(findButton("新建提示词版本"));
    await flush();
    await mouseDown(document.querySelector('.ant-drawer [role="combobox"]')!);
    await flush();
    const queryRewriteOption = [...document.querySelectorAll(".ant-select-item-option")].find(
      (element) => element.textContent?.includes("查询改写"),
    );
    await click(queryRewriteOption!);
    await setInput(document.querySelector("#version")!, "query-rewrite-v2");
    await setTextarea("content", "结合历史消息改写当前问题。");
    await setTextarea("change_note", "补充助手回答上下文");
    await click(findButton("创建版本"));
    await flush();

    expect(create).toHaveBeenCalledWith({
      scenario: "query_rewrite",
      version: "query-rewrite-v2",
      content: "结合历史消息改写当前问题。",
      change_note: "补充助手回答上下文",
    });
  });

  it("creates and activates a retrieval profile version", async () => {
    mockLists();
    const create = vi.spyOn(apiClient, "createRetrievalProfile").mockResolvedValue(profiles[1]!);
    const activate = vi
      .spyOn(apiClient, "activateRetrievalProfile")
      .mockResolvedValue({ ...profiles[1]!, is_active: true });
    view = await mountWithAuth(<ConfigurationPage />, auth, "/admin/configuration");
    await flush();
    await flush();

    const profileTab = [...view.container.querySelectorAll('[role="tab"]')].find((element) =>
      element.textContent?.includes("检索配置版本"),
    );
    await click(profileTab!);
    await flush();
    await click(findButton("新建检索配置版本"));
    await flush();
    await setInput(document.querySelector("#version")!, "profile-v3");
    await setTextarea("change_note", "验证版本创建");
    await click(findButton("创建版本"));
    await flush();
    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "default",
        version: "profile-v3",
        keyword_top_k: 20,
        change_note: "验证版本创建",
      }),
    );

    await click(view.container.querySelector('[data-row-key="default:profile-v2"] button')!);
    await flush();
    await click(
      document.body.querySelector<HTMLButtonElement>(".ant-popconfirm-buttons .ant-btn-primary")!,
    );
    await flush();
    expect(activate).toHaveBeenCalledWith("default", "profile-v2");
  });

  it("shows list errors and retries both configuration sources", async () => {
    const promptList = vi
      .spyOn(apiClient, "listPromptDefinitions")
      .mockRejectedValueOnce(new Error("prompt unavailable"))
      .mockResolvedValueOnce({ items: prompts, page: 1, page_size: 100, total: prompts.length });
    const profileList = vi
      .spyOn(apiClient, "listRetrievalProfiles")
      .mockRejectedValueOnce(new Error("profile unavailable"))
      .mockResolvedValueOnce({ items: profiles, page: 1, page_size: 100, total: profiles.length });
    view = await mountWithAuth(<ConfigurationPage />, auth, "/admin/configuration");
    await flush();
    await flush();

    expect(view.container.textContent).toContain("提示词版本加载失败");
    await click(view.container.querySelector('[aria-label="重试"]')!);
    await flush();
    expect(promptList).toHaveBeenCalledTimes(2);
    expect(view.container.textContent).toContain("grounded-answer-v1");

    const profileTab = [...view.container.querySelectorAll('[role="tab"]')].find((element) =>
      element.textContent?.includes("检索配置版本"),
    );
    await click(profileTab!);
    await flush();
    expect(view.container.textContent).toContain("检索配置版本加载失败");
    await click(view.container.querySelector('[aria-label="重试"]')!);
    await flush();
    expect(profileList).toHaveBeenCalledTimes(2);
    expect(view.container.textContent).toContain("profile-v1");
  });
});
