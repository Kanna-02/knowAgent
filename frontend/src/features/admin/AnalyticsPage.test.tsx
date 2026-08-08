import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiClient } from "../../api/client";
import {
  BusinessSystemView,
  FrequentQuestionPage,
  KnowledgeGapPage,
  SystemOverviewView,
} from "../../api/types";
import { click, flush, mountWithAuth, type MountedView } from "../../test/renderTestApp";
import type { AuthContextValue } from "../auth/authContextValue";
import { AnalyticsPage } from "./AnalyticsPage";

const system: BusinessSystemView = {
  id: "20000000-0000-0000-0000-000000000001",
  code: "ESB",
  name: "企业服务总线",
  description: null,
  status: "ACTIVE",
  owners: [],
  created_at: "2026-08-02T10:00:00Z",
  updated_at: "2026-08-02T10:00:00Z",
};

const overview: SystemOverviewView = {
  system_id: system.id,
  question_count: 150,
  refusal_count: 30,
  open_ticket_count: 12,
  resolved_ticket_count: 45,
  total_ticket_count: 57,
};

const frequentPage: FrequentQuestionPage = {
  items: [
    {
      normalized_question: "如何申请 ESB 接口权限",
      occurrence_count: 25,
      refusal_count: 5,
      ticket_count: 3,
    },
  ],
  total: 1,
};

const gapPage: KnowledgeGapPage = {
  items: [
    {
      normalized_question: "ESB 数据格式不支持 CSV",
      gap_source: "refusal",
      occurrence_count: 8,
      last_seen_at: "2026-08-06T14:00:00Z",
    },
  ],
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

/**
 * Flush enough times to settle the two-hop async chain:
 * mount -> setTimeout(loadSystems) -> setSelectedSystemId -> setTimeout(loadAnalytics).
 * Each flush() drains one timer tick; a second flush covers the effect re-run.
 */
async function settleChain(): Promise<void> {
  await flush();
  await flush();
}

describe("AnalyticsPage", () => {
  it("loads overview, frequent questions, and knowledge gaps", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "getSystemOverview").mockResolvedValue(overview);
    vi.spyOn(apiClient, "listFrequentQuestions").mockResolvedValue(frequentPage);
    vi.spyOn(apiClient, "listKnowledgeGaps").mockResolvedValue(gapPage);

    const view = await mountWithAuth(<AnalyticsPage />, auth, "/admin/analytics");
    views.push(view);
    await settleChain();

    expect(view.container.textContent).toContain("150");
    expect(view.container.textContent).toContain("30");
    expect(view.container.textContent).toContain("如何申请 ESB 接口权限");
    expect(view.container.textContent).toContain("ESB 数据格式不支持 CSV");
    expect(view.container.textContent).toContain("拒答");
  });

  it("shows error state when analytics data fails to load", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    const getOverview = vi
      .spyOn(apiClient, "getSystemOverview")
      .mockRejectedValueOnce(
        new ApiError(503, {
          code: "DEPENDENCY_UNAVAILABLE",
          message: "服务暂时不可用",
          request_id: "req-analytics",
        }),
      )
      .mockResolvedValue(overview);
    vi.spyOn(apiClient, "listFrequentQuestions").mockResolvedValue(frequentPage);
    vi.spyOn(apiClient, "listKnowledgeGaps").mockResolvedValue(gapPage);

    const view = await mountWithAuth(<AnalyticsPage />, auth, "/admin/analytics");
    views.push(view);
    await settleChain();

    expect(view.container.textContent).toContain("req-analytics");

    await click(view.container.querySelector('[aria-label="重试加载分析数据"]')!);
    await flush();
    expect(getOverview).toHaveBeenCalledTimes(2);
    await flush();
    expect(view.container.textContent).toContain("150");
  });

  it("refreshes analytics data on click", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    const getOverview = vi.spyOn(apiClient, "getSystemOverview").mockResolvedValue(overview);
    vi.spyOn(apiClient, "listFrequentQuestions").mockResolvedValue(frequentPage);
    vi.spyOn(apiClient, "listKnowledgeGaps").mockResolvedValue(gapPage);

    const view = await mountWithAuth(<AnalyticsPage />, auth, "/admin/analytics");
    views.push(view);
    await settleChain();

    await click(view.container.querySelector('[aria-label="刷新分析数据"]')!);
    await flush();

    expect(getOverview).toHaveBeenCalledTimes(2);
    expect(view.container.textContent).toContain("150");
  });

  it("renders zero counters and unsolved-ticket gaps", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "getSystemOverview").mockResolvedValue({
      ...overview,
      question_count: 0,
      refusal_count: 0,
      open_ticket_count: 0,
      resolved_ticket_count: 0,
    });
    vi.spyOn(apiClient, "listFrequentQuestions").mockResolvedValue({
      items: [
        {
          normalized_question: "零拒答问题",
          occurrence_count: 1,
          refusal_count: 0,
          ticket_count: 0,
        },
      ],
      total: 1,
    });
    vi.spyOn(apiClient, "listKnowledgeGaps").mockResolvedValue({
      items: [
        {
          normalized_question: "尚未解决的问题",
          gap_source: "unsolved_ticket",
          occurrence_count: 1,
          last_seen_at: "2026-08-06T14:00:00Z",
        },
      ],
      total: 1,
    });

    const view = await mountWithAuth(<AnalyticsPage />, auth, "/admin/analytics");
    views.push(view);
    await settleChain();

    expect(view.container.textContent).toContain("零拒答问题");
    expect(view.container.textContent).toContain("未解决工单");
  });

  it("recovers after the business-system list fails", async () => {
    const listSystems = vi
      .spyOn(apiClient, "listSystems")
      .mockRejectedValueOnce(new Error("systems unavailable"))
      .mockResolvedValueOnce([]);
    const getOverview = vi.spyOn(apiClient, "getSystemOverview");
    vi.spyOn(apiClient, "listFrequentQuestions");
    vi.spyOn(apiClient, "listKnowledgeGaps");

    const view = await mountWithAuth(<AnalyticsPage />, auth, "/admin/analytics");
    views.push(view);
    await flush();
    expect(view.container.textContent).toContain("业务系统列表加载失败");

    await click(view.container.querySelector('[aria-label="重试加载业务系统列表"]')!);
    await flush();
    await click(view.container.querySelector('[aria-label="刷新分析数据"]')!);
    await flush();

    expect(listSystems).toHaveBeenCalledTimes(3);
    expect(getOverview).not.toHaveBeenCalled();
  });
});
