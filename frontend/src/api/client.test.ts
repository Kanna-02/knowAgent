import { afterEach, describe, expect, it, vi } from "vitest";

import { AUTH_UNAUTHORIZED_EVENT, ApiClient, ApiError } from "./client";

function jsonResponse(body: object, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ApiClient", () => {
  it("drops the csrf token when logout reports an expired session", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        jsonResponse({
          user: {
            id: "10000000-0000-0000-0000-000000000001",
            username: "alice",
            display_name: "Alice",
            role: "USER",
            status: "ACTIVE",
            must_change_password: false,
            system_roles: [],
          },
          must_change_password: false,
          csrf_token: "csrf-token",
          expires_at: "2026-08-02T12:00:00Z",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse(
          {
            code: "SESSION_INVALID",
            message: "登录状态已失效，请重新登录",
            request_id: "request-id",
          },
          401,
        ),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const client = new ApiClient();
    await client.login("user", "alice", "Temporary1!");

    await expect(client.logout()).rejects.toThrow("登录状态已失效，请重新登录");
    await client.changePassword("Temporary1!", "Replacement2@");

    const requestHeaders = fetchMock.mock.calls[2]?.[1]?.headers;
    expect(new Headers(requestHeaders).has("X-CSRF-Token")).toBe(false);
  });

  it("builds account queries and sends account mutations", async () => {
    const currentUser = {
      id: "10000000-0000-0000-0000-000000000001",
      username: "admin",
      display_name: "Admin",
      role: "ADMIN",
      status: "ACTIVE",
      must_change_password: false,
      system_roles: [],
    };
    const account = {
      ...currentUser,
      source: "ADMIN_CREATED",
      credential_batch: null,
      external_provider: null,
      created_at: "2026-08-02T12:00:00Z",
      updated_at: "2026-08-02T12:00:00Z",
    };
    const accountPage = { items: [account], page: 1, page_size: 20, total: 1 };
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(currentUser))
      .mockResolvedValueOnce(jsonResponse(accountPage))
      .mockResolvedValueOnce(jsonResponse(accountPage))
      .mockResolvedValueOnce(jsonResponse(account, 201))
      .mockResolvedValueOnce(jsonResponse(account));
    const client = new ApiClient();

    await client.me();
    await client.listAccounts({ page: 1, pageSize: 20 });
    await client.listAccounts({
      page: 2,
      pageSize: 10,
      role: "ADMIN",
      status: "ACTIVE",
      search: "second admin",
    });
    await client.createAdmin({
      username: "second.admin",
      display_name: "Second Admin",
      temporary_password: "Temporary22@",
    });
    await client.setAccountStatus(account.id, "DISABLED");

    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/v1/admin/accounts?page=1&page_size=20");
    expect(fetchMock.mock.calls[2]?.[0]).toContain("role=ADMIN&status=ACTIVE&search=second+admin");
    expect(fetchMock.mock.calls[3]?.[1]?.method).toBe("POST");
    expect(fetchMock.mock.calls[4]?.[1]?.method).toBe("PATCH");
  });

  it("builds business-system queries and mutations", async () => {
    const businessSystem = {
      id: "20000000-0000-0000-0000-000000000001",
      code: "ESB",
      name: "企业服务总线",
      description: null,
      status: "ACTIVE",
      owners: [],
      created_at: "2026-08-02T12:00:00Z",
      updated_at: "2026-08-02T12:00:00Z",
    };
    const owner = {
      account_id: "10000000-0000-0000-0000-000000000002",
      username: "owner",
      display_name: "Owner",
    };
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([businessSystem]))
      .mockResolvedValueOnce(jsonResponse([businessSystem]))
      .mockResolvedValueOnce(
        jsonResponse({ items: [businessSystem], page: 1, page_size: 20, total: 1 }),
      )
      .mockResolvedValueOnce(jsonResponse(businessSystem, 201))
      .mockResolvedValueOnce(jsonResponse({ ...businessSystem, status: "DISABLED" }))
      .mockResolvedValueOnce(jsonResponse([owner]));
    const client = new ApiClient();

    await client.listSystems();
    await client.listSystems("ACTIVE");
    await client.listAdminSystems({ page: 1, pageSize: 20 });
    await client.createSystem({ code: "ESB", name: "企业服务总线" });
    await client.updateSystem(businessSystem.id, { status: "DISABLED" });
    await client.assignSystemOwners(businessSystem.id, [owner.account_id], true);

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/v1/systems");
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/v1/systems?status=ACTIVE");
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/v1/admin/systems?page=1&page_size=20");
    expect(fetchMock.mock.calls[3]?.[1]?.method).toBe("POST");
    expect(fetchMock.mock.calls[4]?.[1]?.method).toBe("PATCH");
    expect(fetchMock.mock.calls[5]?.[1]?.method).toBe("PUT");
    expect(fetchMock.mock.calls[5]?.[1]?.body).toBe(
      JSON.stringify({ account_ids: [owner.account_id], replace_existing: true }),
    );
  });

  it("normalizes an empty gateway error into a traceable API error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(null, {
        status: 502,
        headers: { "X-Request-ID": "gateway-request-id" },
      }),
    );
    const client = new ApiClient();

    const request = client.me();
    await expect(request).rejects.toBeInstanceOf(ApiError);
    await expect(request).rejects.toMatchObject({
      code: "HTTP_ERROR",
      message: "服务暂时不可用，请稍后重试",
      requestId: "gateway-request-id",
      status: 502,
    });
  });

  it("maps the complete API surface to versioned endpoints and mutation methods", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(() => Promise.resolve(jsonResponse({ csrf_token: "response-csrf" })));
    const client = new ApiClient();
    const retrievalProfile = {} as Parameters<ApiClient["createRetrievalProfile"]>[0];
    const notificationConfiguration = {} as Parameters<
      ApiClient["updateNotificationConfiguration"]
    >[0];

    await client.login("admin", "admin", "Temporary1!");
    await client.startQuestionStream({
      system_id: "system-1",
      question: "How?",
      required_terms: ["ESB"],
      conversation_id: "conversation-1",
      retrieval_profile: "balanced",
    });
    await client.listConversations("system-1", 2, 25);
    await client.createConversation("system-1", "Incident");
    await client.getConversation("conversation-1");
    await client.deleteConversation("conversation-1");
    await client.listPromptDefinitions({ page: 2, pageSize: 10, scenario: "grounded_answer" });
    await client.createPromptDefinition({
      scenario: "grounded_answer",
      version: "v2",
      content: "Answer with evidence",
      change_note: "coverage contract",
    });
    await client.activatePromptDefinition("grounded_answer", "v2");
    await client.listRetrievalProfiles({ page: 2, pageSize: 10, name: "balanced" });
    await client.createRetrievalProfile(retrievalProfile);
    await client.activateRetrievalProfile("balanced", "v2");
    await client.listTickets({
      page: 2,
      pageSize: 10,
      systemId: "system-1",
      status: "in_progress",
    });
    await client.getTicket("ticket-1");
    await client.listTicketReplies("ticket-1");
    await client.listTicketTransitions("ticket-1");
    await client.replyTicket("ticket-1", "Investigating");
    await client.submitTicketAnswer("ticket-1", "Resolved by restarting the connector");
    await client.transitionTicket("ticket-1", "close", "Resolved");
    await client.transitionTicket("ticket-1", "reopen");
    await client.listDocuments("system-1", { page: 2, pageSize: 10 });
    await client.listDocumentVersions("system-1", "document-1", { page: 2, pageSize: 10 });
    await client.publishDocumentVersion("system-1", "document-1", "version-1");
    await client.retireDocumentVersion("system-1", "document-1", "version-1");
    await client.getSystemOverview("system-1", {
      started_at: "2026-08-01T00:00:00Z",
      ended_at: "2026-08-08T00:00:00Z",
    });
    await client.listFrequentQuestions("system-1", {
      started_at: "2026-08-01T00:00:00Z",
      ended_at: "2026-08-08T00:00:00Z",
      top_n: 25,
    });
    await client.listKnowledgeGaps("system-1", {
      started_at: "2026-08-01T00:00:00Z",
      ended_at: "2026-08-08T00:00:00Z",
      top_n: 25,
    });
    await client.listAuditLogs({
      page: 2,
      pageSize: 10,
      actor_id: "account-1",
      action: "ticket.close",
      object_type: "ticket",
      object_id: "ticket-1",
      result: "success",
      started_at: "2026-08-01T00:00:00Z",
      ended_at: "2026-08-08T00:00:00Z",
    });
    await client.getNotificationConfiguration();
    await client.updateNotificationConfiguration(notificationConfiguration);
    await client.listNotificationDeliveries({
      page: 2,
      pageSize: 10,
      status: "PERMANENT_FAILURE",
      eventType: "ticket_replied",
    });
    await client.retryNotificationDelivery("delivery-1");

    const calls = fetchMock.mock.calls.map(([url, init]) => ({
      url,
      method: init?.method ?? "GET",
      body: init?.body,
    }));
    expect(calls).toContainEqual({
      url: "/api/v1/questions/stream",
      method: "POST",
      body: JSON.stringify({
        system_id: "system-1",
        question: "How?",
        required_terms: ["ESB"],
        conversation_id: "conversation-1",
        retrieval_profile: "balanced",
      }),
    });
    expect(calls).toContainEqual({
      url: "/api/v1/tickets/ticket-1/close",
      method: "POST",
      body: JSON.stringify({ body: "Resolved" }),
    });
    expect(
      calls.some(
        ({ url }) =>
          url ===
          "/api/v1/admin/audit-logs?page=2&page_size=10&actor_id=account-1&action=ticket.close&object_type=ticket&object_id=ticket-1&result=success&started_at=2026-08-01T00%3A00%3A00Z&ended_at=2026-08-08T00%3A00%3A00Z",
      ),
    ).toBe(true);
    expect(client.streamEventsUrl("token + slash/")).toBe(
      "/api/v1/questions/stream/events?token=token%20%2B%20slash%2F",
    );
  });

  it("omits every optional filter and applies request defaults", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(() => Promise.resolve(jsonResponse({})));
    const client = new ApiClient();

    await client.startQuestionStream({ system_id: "system-1", question: "How?" });
    await client.listConversations("system-1");
    await client.listAdminSystems({ page: 1, pageSize: 20 });
    await client.listPromptDefinitions({ page: 1, pageSize: 20 });
    await client.listRetrievalProfiles({ page: 1, pageSize: 20 });
    await client.listTickets({ page: 1, pageSize: 20 });
    await client.getSystemOverview("system-1");
    await client.listFrequentQuestions("system-1", {});
    await client.listKnowledgeGaps("system-1", {});
    await client.listAuditLogs({ page: 1, pageSize: 20 });
    await client.listNotificationDeliveries({ page: 1, pageSize: 20 });

    const urls = fetchMock.mock.calls.map(([url]) => url);
    expect(urls).toContain("/api/v1/conversations?system_id=system-1&page=1&page_size=100");
    expect(urls).toContain("/api/v1/systems/system-1/analytics/overview");
    expect(urls).toContain("/api/v1/systems/system-1/analytics/frequent-questions");
    expect(urls).toContain("/api/v1/systems/system-1/analytics/knowledge-gaps");
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe(
      JSON.stringify({
        system_id: "system-1",
        question: "How?",
        required_terms: [],
        conversation_id: null,
        retrieval_profile: null,
      }),
    );
  });

  it("uses response csrf rotation and fallback errors for malformed bodies", async () => {
    const unauthorized = vi.fn();
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, unauthorized, { once: true });
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "account-1" }), {
          status: 200,
          headers: { "Content-Type": "application/json", "X-CSRF-Token": "rotated" },
        }),
      )
      .mockResolvedValueOnce(new Response("not-json", { status: 400 }))
      .mockResolvedValueOnce(jsonResponse({ message: "missing fields" }, 401));
    const client = new ApiClient();

    await client.me();
    await expect(client.changePassword("old", "new")).rejects.toMatchObject({
      code: "HTTP_ERROR",
      message: "请求未完成，请稍后重试",
      status: 400,
    });
    await expect(client.me()).rejects.toMatchObject({
      code: "HTTP_ERROR",
      message: "请求未完成，请稍后重试",
      status: 401,
    });

    expect(new Headers(fetchMock.mock.calls[1]?.[1]?.headers).get("X-CSRF-Token")).toBe("rotated");
    expect(unauthorized).toHaveBeenCalledOnce();
  });
});
