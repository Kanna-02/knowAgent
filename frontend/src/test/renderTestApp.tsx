import { App as AntApp } from "antd";
import { act, type ReactNode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

import { AuthContext, type AuthContextValue } from "../features/auth/authContextValue";

export interface MountedView {
  container: HTMLDivElement;
  root: Root;
  unmount: () => Promise<void>;
}

export async function mountWithAuth(
  node: ReactNode,
  auth: AuthContextValue,
  route = "/",
): Promise<MountedView> {
  const container = document.createElement("div");
  document.body.append(container);
  const root = createRoot(container);
  act(() => {
    root.render(
      <AntApp>
        <MemoryRouter initialEntries={[route]}>
          <AuthContext.Provider value={auth}>{node}</AuthContext.Provider>
        </MemoryRouter>
      </AntApp>,
    );
  });
  await Promise.resolve();
  return {
    container,
    root,
    unmount: async () => {
      act(() => root.unmount());
      await Promise.resolve();
      container.remove();
    },
  };
}

export async function setInput(input: HTMLInputElement, value: string): Promise<void> {
  const descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value");
  if (!descriptor?.set) throw new Error("HTML input value setter is unavailable");
  act(() => {
    descriptor.set?.bind(input)(value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await Promise.resolve();
}

export async function click(element: Element): Promise<void> {
  await act(async () => {
    (element as HTMLElement).click();
    await Promise.resolve();
  });
}

export async function mouseDown(element: Element): Promise<void> {
  act(() => {
    element.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
  });
  await Promise.resolve();
}

export async function flush(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}
