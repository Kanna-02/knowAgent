import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiClient } from "../../api/client";
import type {
  BusinessSystemView,
  DocumentPage,
  DocumentVersionPage,
  DocumentVersionView,
  DocumentView,
  PublishVersionResponse,
} from "../../api/types";
import { click, flush, mountWithAuth, type MountedView } from "../../test/renderTestApp";
import type { AuthContextValue } from "../auth/authContextValue";
import { DocumentsPage } from "./DocumentsPage";

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

const doc: DocumentView = {
  id: "30000000-0000-0000-0000-000000000001",
  system_id: system.id,
  name: "ESB 接口文档.docx",
  current_published_version_id: null,
  created_at: "2026-08-03T10:00:00Z",
  updated_at: "2026-08-03T10:00:00Z",
};

const docPage: DocumentPage = {
  items: [doc],
  page: 1,
  page_size: 20,
  total: 1,
};

const version: DocumentVersionView = {
  id: "40000000-0000-0000-0000-000000000001",
  document_id: doc.id,
  system_id: system.id,
  version_no: 1,
  filename: "esb_v1.docx",
  media_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  size_bytes: 102400,
  sha256: "abc123",
  status: "READY_DRAFT",
  publish_status: "DRAFT",
  chunk_count: 10,
  parser_name: "docx",
  parser_version: "1.0",
  published_at: null,
  retired_at: null,
  created_at: "2026-08-03T10:00:00Z",
  updated_at: "2026-08-03T10:00:00Z",
};

const versionPage: DocumentVersionPage = {
  items: [version],
  page: 1,
  page_size: 100,
  total: 1,
};

const publishResponse: PublishVersionResponse = {
  document_id: doc.id,
  version_id: version.id,
  system_id: system.id,
  publish_status: "PUBLISHED",
  published_at: "2026-08-07T12:00:00Z",
};

/**
 * Flush twice to settle the two-hop async chain:
 * mount -> setTimeout(loadSystems) -> setSelectedSystemId -> setTimeout(loadDocuments).
 */
async function settleChain(): Promise<void> {
  await flush();
  await flush();
}

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

describe("DocumentsPage", () => {
  it("loads systems and documents, then shows versions drawer", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listDocuments").mockResolvedValue(docPage);
    vi.spyOn(apiClient, "listDocumentVersions").mockResolvedValue(versionPage);
    vi.spyOn(apiClient, "publishDocumentVersion").mockResolvedValue(publishResponse);

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();

    expect(view.container.textContent).toContain("ESB 接口文档.docx");

    await click(view.container.querySelector('[aria-label="查看文档版本"]')!);
    await flush();
    expect(document.body.textContent).toContain("esb_v1.docx");
    expect(document.body.textContent).toContain("草稿");
  });

  it("publishes a draft version via confirm", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listDocuments").mockResolvedValue(docPage);
    vi.spyOn(apiClient, "listDocumentVersions").mockResolvedValue(versionPage);
    const publish = vi
      .spyOn(apiClient, "publishDocumentVersion")
      .mockResolvedValue(publishResponse);

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();

    await click(view.container.querySelector('[aria-label="查看文档版本"]')!);
    await flush();

    const publishButton = document.querySelector('[aria-label="发布版本"]');
    expect(publishButton).not.toBeNull();
    await click(publishButton!);
    await flush();
    await click(document.querySelector(".ant-popconfirm-buttons .ant-btn-primary")!);
    await flush();
    await flush();

    expect(publish).toHaveBeenCalledWith(system.id, doc.id, version.id);
  });

  it("shows error when loading systems fails and recovers via retry", async () => {
    const listSystems = vi
      .spyOn(apiClient, "listSystems")
      .mockRejectedValueOnce(
        new ApiError(503, {
          code: "DEPENDENCY_UNAVAILABLE",
          message: "服务暂时不可用",
          request_id: "req-001",
        }),
      )
      .mockResolvedValue([system]);
    vi.spyOn(apiClient, "listDocuments").mockResolvedValue(docPage);

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();

    expect(view.container.textContent).toContain("req-001");

    await click(view.container.querySelector('[aria-label="重试加载业务系统列表"]')!);
    await flush();
    await flush();
    expect(listSystems).toHaveBeenCalledTimes(2);
    await flush();

    expect(view.container.textContent).not.toContain("req-001");
  });

  it("ignores a stale document request after another refresh", async () => {
    let resolveStale!: (value: DocumentPage) => void;
    const stalePromise = new Promise<DocumentPage>((resolve) => {
      resolveStale = resolve;
    });
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listDocuments")
      .mockReturnValueOnce(stalePromise)
      .mockResolvedValue(docPage);

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();

    await click(view.container.querySelector('[aria-label="刷新文档列表"]')!);
    await flush();

    resolveStale({ ...docPage, items: [{ ...doc, name: "旧文档" }] });
    await flush();
    await flush();

    expect(view.container.textContent).toContain("ESB 接口文档.docx");
    expect(view.container.textContent).not.toContain("旧文档");
  });
});
