import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiClient, ApiError } from "./client";

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
});
