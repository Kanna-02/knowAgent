import type {
  AccountPage,
  AccountRole,
  AccountStatus,
  AccountView,
  ApiErrorBody,
  BusinessSystemPage,
  BusinessSystemStatus,
  BusinessSystemView,
  CurrentUser,
  SessionView,
  SystemOwnerView,
} from "./types";

export const AUTH_UNAUTHORIZED_EVENT = "knowagent:auth-unauthorized";

export class ApiError extends Error {
  readonly code: string;
  readonly requestId: string;
  readonly status: number;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.code = body.code;
    this.requestId = body.request_id;
    this.status = status;
  }
}

export class ApiClient {
  private csrfToken: string | null = null;

  async login(entry: "user" | "admin", username: string, password: string): Promise<SessionView> {
    const session = await this.request<SessionView>(`/auth/${entry}/sessions`, {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    this.csrfToken = session.csrf_token;
    return session;
  }

  async me(): Promise<CurrentUser> {
    return this.request<CurrentUser>("/auth/me");
  }

  async changePassword(currentPassword: string, newPassword: string): Promise<void> {
    await this.request<void>("/auth/password/change", {
      method: "POST",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
  }

  async logout(): Promise<void> {
    try {
      await this.request<void>("/auth/session", { method: "DELETE" });
    } finally {
      this.csrfToken = null;
    }
  }

  async listAccounts(filters: {
    page: number;
    pageSize: number;
    role?: AccountRole;
    status?: AccountStatus;
    search?: string;
  }): Promise<AccountPage> {
    const query = new URLSearchParams({
      page: String(filters.page),
      page_size: String(filters.pageSize),
    });
    if (filters.role) query.set("role", filters.role);
    if (filters.status) query.set("status", filters.status);
    if (filters.search) query.set("search", filters.search);
    return this.request<AccountPage>(`/admin/accounts?${query.toString()}`);
  }

  async createAdmin(payload: {
    username: string;
    display_name: string;
    temporary_password: string;
  }): Promise<AccountView> {
    return this.request<AccountView>("/admin/accounts", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async setAccountStatus(accountId: string, status: AccountStatus): Promise<AccountView> {
    return this.request<AccountView>(`/admin/accounts/${accountId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
  }

  async listSystems(status?: BusinessSystemStatus): Promise<BusinessSystemView[]> {
    const query = status ? `?status=${status}` : "";
    return this.request<BusinessSystemView[]>(`/systems${query}`);
  }

  async listAdminSystems(filters: {
    page: number;
    pageSize: number;
    status?: BusinessSystemStatus;
  }): Promise<BusinessSystemPage> {
    const query = new URLSearchParams({
      page: String(filters.page),
      page_size: String(filters.pageSize),
    });
    if (filters.status) query.set("status", filters.status);
    return this.request<BusinessSystemPage>(`/admin/systems?${query.toString()}`);
  }

  async createSystem(payload: {
    code: string;
    name: string;
    description?: string | null;
    status?: BusinessSystemStatus;
  }): Promise<BusinessSystemView> {
    return this.request<BusinessSystemView>("/admin/systems", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async updateSystem(
    systemId: string,
    payload: {
      name?: string;
      description?: string | null;
      status?: BusinessSystemStatus;
    },
  ): Promise<BusinessSystemView> {
    return this.request<BusinessSystemView>(`/admin/systems/${systemId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
  }

  async assignSystemOwners(
    systemId: string,
    accountIds: string[],
    replaceExisting: boolean,
  ): Promise<SystemOwnerView[]> {
    return this.request<SystemOwnerView[]>(`/admin/systems/${systemId}/owners`, {
      method: "PUT",
      body: JSON.stringify({ account_ids: accountIds, replace_existing: replaceExisting }),
    });
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    if (init.body) headers.set("Content-Type", "application/json");
    if (this.csrfToken && init.method && init.method !== "GET") {
      headers.set("X-CSRF-Token", this.csrfToken);
    }
    const response = await fetch(`/api/v1${path}`, {
      ...init,
      headers,
      credentials: "include",
    });
    const csrfToken = response.headers.get("X-CSRF-Token");
    if (csrfToken) this.csrfToken = csrfToken;
    if (!response.ok) {
      const body = await this.readErrorBody(response);
      if (response.status === 401) {
        this.csrfToken = null;
        window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT));
      }
      throw new ApiError(response.status, body);
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  private async readErrorBody(response: Response): Promise<ApiErrorBody> {
    const fallback: ApiErrorBody = {
      code: "HTTP_ERROR",
      message: response.status >= 500 ? "服务暂时不可用，请稍后重试" : "请求未完成，请稍后重试",
      request_id: response.headers.get("X-Request-ID") ?? "",
    };
    const text = await response.text();
    if (!text) return fallback;
    try {
      const candidate = JSON.parse(text) as Partial<ApiErrorBody>;
      if (
        typeof candidate.code === "string" &&
        typeof candidate.message === "string" &&
        typeof candidate.request_id === "string"
      ) {
        return candidate as ApiErrorBody;
      }
      return fallback;
    } catch {
      return fallback;
    }
  }
}

export const apiClient = new ApiClient();
