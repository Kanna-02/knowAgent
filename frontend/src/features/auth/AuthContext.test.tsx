import { App as AntApp } from "antd";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../../api/client";
import type { CurrentUser, SessionView } from "../../api/types";
import { AuthProvider } from "./AuthContext";
import { type AuthContextValue, useAuth } from "./authContextValue";
import { LoginPage } from "./LoginPage";

const user: CurrentUser = {
  id: "10000000-0000-0000-0000-000000000001",
  username: "alice",
  display_name: "Alice",
  role: "USER",
  status: "ACTIVE",
  must_change_password: false,
  system_roles: [],
};

const session: SessionView = {
  user,
  must_change_password: false,
  csrf_token: "csrf-token",
  expires_at: "2026-08-02T12:00:00Z",
};

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  act(() => root.unmount());
  await Promise.resolve();
  container.remove();
  vi.restoreAllMocks();
});

function render(children: ReactNode): void {
  root.render(
    <AntApp>
      <MemoryRouter>
        <AuthProvider>{children}</AuthProvider>
      </MemoryRouter>
    </AntApp>,
  );
}

async function renderProvider(children: ReactNode): Promise<void> {
  act(() => render(children));
  await act(async () => {
    await Promise.resolve();
  });
}

function Observer({ capture }: { capture: (value: AuthContextValue) => void }): null {
  capture(useAuth());
  return null;
}

describe("AuthProvider", () => {
  it("keeps the login form unavailable while session bootstrap is pending", async () => {
    vi.spyOn(apiClient, "me").mockImplementation(() => new Promise(() => undefined));

    await renderProvider(<LoginPage entry="user" />);

    expect(container.querySelector("input")).toBeNull();
    expect(container.querySelector('[aria-label="正在检查登录状态"]')).not.toBeNull();
  });

  it("clears a bootstrap error after a later successful login", async () => {
    vi.spyOn(apiClient, "me").mockRejectedValue(new Error("认证服务暂时不可用"));
    vi.spyOn(apiClient, "login").mockResolvedValue(session);
    let context!: AuthContextValue;

    await renderProvider(<Observer capture={(value) => (context = value)} />);
    expect(context.bootstrapError).toBe("认证服务暂时不可用");

    await act(async () => {
      await context.login("user", "alice", "Temporary1!");
    });

    expect(context.user).toEqual(user);
    expect(context.bootstrapError).toBeNull();
  });

  it("uses a stable bootstrap error for non-Error failures", async () => {
    vi.spyOn(apiClient, "me").mockRejectedValue({ reason: "offline" });
    let context!: AuthContextValue;

    await renderProvider(<Observer capture={(value) => (context = value)} />);

    expect(context.bootstrapError).toBe("认证服务暂时不可用");
  });

  it("ignores fulfilled and rejected bootstrap requests after unmount", async () => {
    let resolveBootstrap!: (value: CurrentUser) => void;
    let rejectBootstrap!: (reason: unknown) => void;
    const fulfilled = new Promise<CurrentUser>((resolve) => {
      resolveBootstrap = resolve;
    });
    const rejected = new Promise<CurrentUser>((_, reject) => {
      rejectBootstrap = reject;
    });
    const me = vi
      .spyOn(apiClient, "me")
      .mockReturnValueOnce(fulfilled)
      .mockReturnValueOnce(rejected);
    const fulfilledCapture = vi.fn<(value: AuthContextValue) => void>();

    await renderProvider(<Observer capture={fulfilledCapture} />);
    act(() => root.render(<div>provider removed</div>));
    await act(async () => {
      resolveBootstrap(user);
      await fulfilled;
      await Promise.resolve();
    });
    expect(fulfilledCapture).toHaveBeenCalledTimes(1);

    const rejectedCapture = vi.fn<(value: AuthContextValue) => void>();
    await renderProvider(<Observer capture={rejectedCapture} />);
    act(() => root.render(<div>provider removed again</div>));
    await act(async () => {
      rejectBootstrap(new Error("late failure"));
      try {
        await rejected;
      } catch {
        // AuthProvider consumes this rejection; awaiting here only settles the test promise.
      }
      await Promise.resolve();
    });

    expect(me).toHaveBeenCalledTimes(2);
    expect(rejectedCapture).toHaveBeenCalledTimes(1);
  });

  it("clears local identity even when server logout fails", async () => {
    vi.spyOn(apiClient, "me").mockResolvedValue(user);
    vi.spyOn(apiClient, "logout").mockRejectedValue(new Error("Session expired"));
    let context!: AuthContextValue;

    await renderProvider(<Observer capture={(value) => (context = value)} />);
    expect(context.user).toEqual(user);

    let logoutError: unknown;
    await act(async () => {
      try {
        await context.logout();
      } catch (error: unknown) {
        logoutError = error;
      }
    });

    expect(logoutError).toEqual(new Error("Session expired"));
    expect(context.user).toBeNull();
  });

  it("refreshes identity after password change and reacts to unauthorized events", async () => {
    const changedUser = { ...user, display_name: "Alice Updated" };
    vi.spyOn(apiClient, "me").mockResolvedValueOnce(user).mockResolvedValueOnce(changedUser);
    vi.spyOn(apiClient, "changePassword").mockResolvedValue(undefined);
    let context!: AuthContextValue;

    await renderProvider(<Observer capture={(value) => (context = value)} />);
    await act(async () => {
      await context.changePassword("Temporary1!", "Replacement2@");
    });
    expect(context.user).toEqual(changedUser);

    act(() => {
      window.dispatchEvent(new Event("knowagent:auth-unauthorized"));
    });
    expect(context.user).toBeNull();
    expect(context.bootstrapError).toBeNull();
  });
});
