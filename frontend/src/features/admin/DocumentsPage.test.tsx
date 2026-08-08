import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiClient } from "../../api/client";
import type {
  BusinessSystemView,
  DocumentPage,
  DocumentVersionPage,
  DocumentVersionView,
  DocumentView,
  PublishVersionResponse,
  RetireVersionResponse,
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

const retireResponse: RetireVersionResponse = {
  document_id: doc.id,
  version_id: version.id,
  system_id: system.id,
  publish_status: "RETIRED",
  retired_at: "2026-08-08T12:00:00Z",
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

  it("recovers document and version lists independently", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    const listDocuments = vi
      .spyOn(apiClient, "listDocuments")
      .mockRejectedValueOnce(new Error("documents unavailable"))
      .mockResolvedValue(docPage);
    const listVersions = vi
      .spyOn(apiClient, "listDocumentVersions")
      .mockRejectedValueOnce(new Error("versions unavailable"))
      .mockResolvedValue(versionPage);

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();
    expect(view.container.textContent).toContain("文档列表加载失败");

    await click(view.container.querySelector('[aria-label="重试加载文档列表"]')!);
    await flush();
    expect(listDocuments).toHaveBeenCalledTimes(2);
    expect(view.container.textContent).toContain("ESB 接口文档.docx");

    await click(view.container.querySelector('[aria-label="查看文档版本"]')!);
    await flush();
    expect(document.body.textContent).toContain("版本列表加载失败");
    await click(document.body.querySelector('[aria-label="重试加载版本列表"]')!);
    await flush();

    expect(listVersions).toHaveBeenCalledTimes(2);
    expect(document.body.textContent).toContain("esb_v1.docx");
  });

  it("shows the selection prompt when no active systems are available", async () => {
    const listSystems = vi.spyOn(apiClient, "listSystems").mockResolvedValue([]);
    const listDocuments = vi.spyOn(apiClient, "listDocuments");

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();

    expect(view.container.textContent).toContain("请先选择业务系统");
    await click(view.container.querySelector('[aria-label="刷新文档列表"]')!);
    await flush();

    expect(listSystems).toHaveBeenCalledTimes(2);
    expect(listDocuments).not.toHaveBeenCalled();
  });

  it("loads the selected document page from table pagination", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    const listDocuments = vi.spyOn(apiClient, "listDocuments").mockResolvedValue({
      ...docPage,
      total: 21,
    });

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();

    await click(view.container.querySelector(".ant-pagination-item-2")!);
    await flush();
    await flush();

    expect(listDocuments).toHaveBeenLastCalledWith(system.id, { page: 2, pageSize: 20 });
  });

  it("renders all publication states and retires a published version", async () => {
    const publishedVersion: DocumentVersionView = {
      ...version,
      id: "40000000-0000-0000-0000-000000000002",
      filename: "esb_published.docx",
      size_bytes: 512,
      publish_status: "PUBLISHED",
    };
    const retiredVersion: DocumentVersionView = {
      ...version,
      id: "40000000-0000-0000-0000-000000000003",
      filename: "esb_retired.docx",
      size_bytes: 2 * 1024 * 1024,
      publish_status: "RETIRED",
    };
    const publishedDocument = {
      ...doc,
      current_published_version_id: publishedVersion.id,
    };
    const versionsWithAllStatuses = {
      ...versionPage,
      items: [publishedVersion, retiredVersion, version],
      total: 3,
    };
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listDocuments").mockResolvedValue({
      ...docPage,
      items: [publishedDocument],
    });
    vi.spyOn(apiClient, "listDocumentVersions").mockResolvedValue(versionsWithAllStatuses);
    const retire = vi
      .spyOn(apiClient, "retireDocumentVersion")
      .mockResolvedValue({ ...retireResponse, version_id: publishedVersion.id });

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();

    expect(view.container.textContent).toContain("已发布");
    await click(view.container.querySelector('[aria-label="查看文档版本"]')!);
    await flush();

    expect(document.body.textContent).toContain("512 B");
    expect(document.body.textContent).toContain("2.0 MB");
    expect(document.body.textContent).toContain("已退役");
    await click(document.body.querySelector('[aria-label="退役版本"]')!);
    await flush();
    await click(document.body.querySelector(".ant-popconfirm-buttons .ant-btn-primary")!);
    await flush();
    await flush();

    expect(retire).toHaveBeenCalledWith(system.id, doc.id, publishedVersion.id);
  });

  it("reports publication and retirement failures", async () => {
    const publishedVersion: DocumentVersionView = {
      ...version,
      id: "40000000-0000-0000-0000-000000000004",
      filename: "esb_published.docx",
      publish_status: "PUBLISHED",
    };
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listDocuments").mockResolvedValue(docPage);
    vi.spyOn(apiClient, "listDocumentVersions").mockResolvedValue({
      ...versionPage,
      items: [version, publishedVersion],
      total: 2,
    });
    vi.spyOn(apiClient, "publishDocumentVersion").mockRejectedValue(new Error("publish failed"));
    vi.spyOn(apiClient, "retireDocumentVersion").mockRejectedValue(new Error("retire failed"));

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();
    await click(view.container.querySelector('[aria-label="查看文档版本"]')!);
    await flush();

    await click(document.body.querySelector('[aria-label="发布版本"]')!);
    await flush();
    await click(document.body.querySelector(".ant-popconfirm-buttons .ant-btn-primary")!);
    await flush();
    expect(document.body.textContent).toContain("版本发布失败");

    await click(document.body.querySelector('[aria-label="退役版本"]')!);
    await flush();
    const confirmationButtons = document.body.querySelectorAll(
      ".ant-popconfirm-buttons .ant-btn-primary",
    );
    await click(confirmationButtons[confirmationButtons.length - 1]!);
    await flush();
    expect(document.body.textContent).toContain("版本退役失败");
  });
});
