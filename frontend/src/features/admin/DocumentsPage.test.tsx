import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act } from "react";

import { ApiError, apiClient } from "../../api/client";
import type {
  BusinessSystemView,
  DocumentPage,
  DocumentVersionPage,
  DocumentVersionView,
  DocumentView,
  IngestionJobPage,
  IngestionJobView,
  PublishVersionResponse,
  RetireVersionResponse,
} from "../../api/types";
import {
  click,
  flush,
  mountWithAuth,
  mouseDown,
  setInput,
  type MountedView,
} from "../../test/renderTestApp";
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
  current_published_version_no: null,
  latest_version_no: 1,
  latest_version_status: "READY_DRAFT",
  version_count: 1,
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

const ingestionJob: IngestionJobView = {
  job_id: "50000000-0000-0000-0000-000000000001",
  document_id: doc.id,
  document_version_id: version.id,
  version_no: 1,
  system_id: system.id,
  document_name: doc.name,
  filename: version.filename,
  media_type: version.media_type,
  version_status: "READY_DRAFT",
  publish_status: "DRAFT",
  status: "SUCCEEDED",
  stage: "COMPLETED",
  progress: 100,
  attempt: 1,
  max_attempts: 3,
  error_code: null,
  error_message: null,
  next_retry_at: null,
  lease_expires_at: null,
  celery_task_id: "celery-1",
  created_at: version.created_at,
  updated_at: version.updated_at,
};

const ingestionJobPage: IngestionJobPage = {
  items: [],
  page: 1,
  page_size: 20,
  total: 0,
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

beforeEach(() => {
  vi.spyOn(apiClient, "listIngestionJobs").mockResolvedValue(ingestionJobPage);
});

afterEach(async () => {
  for (const view of views.reverse()) await view.unmount();
  views = [];
  document.body.innerHTML = "";
  window.sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("DocumentsPage", () => {
  it("imports a document into the selected system and shows the ingestion job", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listDocuments").mockResolvedValue({ ...docPage, items: [] });
    const upload = vi.spyOn(apiClient, "uploadDocument").mockResolvedValue(ingestionJob);

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();

    await click(view.container.querySelector('[aria-label="导入文档"]')!);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["# Guide\n"], "guide.md", { type: "text/markdown" });
    await act(async () => {
      Object.defineProperty(input, "files", { configurable: true, value: [file] });
      input.dispatchEvent(new Event("change", { bubbles: true }));
      await Promise.resolve();
    });
    await click(document.querySelector('[aria-label="开始导入"]')!);
    await flush();

    expect(upload).toHaveBeenCalledWith(system.id, file, expect.any(Object));
    expect(document.body.textContent).toContain("入库任务已完成");

    await click(document.querySelector(".ant-modal-footer .ant-btn-default")!);
    await flush();

    expect(view.container.textContent).toContain("最近导入");
    expect(view.container.textContent).toContain("100%");
    expect(view.container.querySelector('[aria-label="查看导入进度"]')).not.toBeNull();
  });

  it("allows a failed ingestion job to be retried", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listDocuments").mockResolvedValue({ ...docPage, items: [] });
    vi.spyOn(apiClient, "uploadDocument").mockResolvedValue({
      ...ingestionJob,
      status: "FAILED",
      progress: 60,
      error_code: "EMBEDDING_UNAVAILABLE",
      error_message: "向量服务暂时不可用",
    });
    const retry = vi.spyOn(apiClient, "retryIngestionJob").mockResolvedValue(ingestionJob);

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();
    await click(view.container.querySelector('[aria-label="导入文档"]')!);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["# Guide\n"], "guide.md", { type: "text/markdown" });
    await act(async () => {
      Object.defineProperty(input, "files", { configurable: true, value: [file] });
      input.dispatchEvent(new Event("change", { bubbles: true }));
      await Promise.resolve();
    });
    await click(document.querySelector('[aria-label="开始导入"]')!);
    await flush();
    expect(document.body.textContent).toContain("向量服务暂时不可用");

    await click(document.querySelector('[aria-label="重试入库"]')!);
    await flush();
    expect(retry).toHaveBeenCalledWith(ingestionJob.job_id);
    expect(document.body.textContent).toContain("入库任务已完成");
  });

  it("restores active ingestion jobs from the server after the page is mounted", async () => {
    const runningJob = { ...ingestionJob, status: "RUNNING" as const, progress: 42 };
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listDocuments").mockResolvedValue({ ...docPage, items: [] });
    const listIngestionJobs = vi.spyOn(apiClient, "listIngestionJobs");
    listIngestionJobs.mockResolvedValue({
      ...ingestionJobPage,
      items: [runningJob],
      total: 1,
    });

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();
    await flush();

    await click(view.container.querySelector('[aria-label="导入任务"]')!);
    await flush();
    expect(listIngestionJobs).toHaveBeenCalledWith(system.id, {
      page: 1,
      pageSize: 20,
    });
    expect(view.container.textContent).toContain("42%");
    expect(view.container.textContent).toContain("处理中");
  });

  it("retries a failed job from the ingestion task table", async () => {
    const failedJob = {
      ...ingestionJob,
      status: "FAILED" as const,
      progress: 70,
      error_code: "INVALID_FILE",
      error_message: "文件无法解析",
    };
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listDocuments").mockResolvedValue(docPage);
    const listIngestionJobs = vi.spyOn(apiClient, "listIngestionJobs");
    listIngestionJobs.mockResolvedValue({
      ...ingestionJobPage,
      items: [failedJob],
      total: 1,
    });
    const retry = vi.spyOn(apiClient, "retryIngestionJob").mockResolvedValue({
      ...failedJob,
      status: "QUEUED",
      progress: 0,
      error_code: null,
      error_message: null,
    });

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();
    await click(view.container.querySelector('[aria-label="导入任务"]')!);
    await flush();
    await click(view.container.querySelector('[aria-label="重试导入任务"]')!);
    await flush();

    expect(retry).toHaveBeenCalledWith(failedJob.job_id);
  });

  it("imports a new version from an existing document row", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listDocuments").mockResolvedValue(docPage);
    const upload = vi.spyOn(apiClient, "uploadDocument").mockResolvedValue({
      ...ingestionJob,
      version_no: 2,
    });

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();
    await click(view.container.querySelector('[aria-label="导入新版本"]')!);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["# Guide v2\n"], "guide-v2.md", { type: "text/markdown" });
    await act(async () => {
      Object.defineProperty(input, "files", { configurable: true, value: [file] });
      input.dispatchEvent(new Event("change", { bubbles: true }));
      await Promise.resolve();
    });
    await click(document.querySelector('[aria-label="开始导入"]')!);
    await flush();

    expect(document.body.textContent).toContain("ESB 接口文档.docx");
    expect(upload).toHaveBeenCalledWith(
      system.id,
      file,
      expect.objectContaining({ documentId: doc.id }),
    );
  });

  it("searches documents by name on the server", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    const listDocuments = vi.spyOn(apiClient, "listDocuments").mockResolvedValue(docPage);

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();
    await setInput(view.container.querySelector('[aria-label="搜索文档名称"]')!, "接口规范");
    await click(view.container.querySelector('[aria-label="搜索文档"]')!);
    await flush();

    expect(listDocuments).toHaveBeenLastCalledWith(system.id, {
      page: 1,
      pageSize: 20,
      search: "接口规范",
    });
  });

  it("filters documents by processing and publication status", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    const listDocuments = vi.spyOn(apiClient, "listDocuments").mockResolvedValue(docPage);

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();

    const selects = view.container.querySelectorAll(".document-filter-controls .ant-select");
    await mouseDown(selects[0] as Element);
    await click(
      [...document.body.querySelectorAll(".ant-select-item-option")].find((option) =>
        option.textContent?.includes("处理失败"),
      )!,
    );
    await mouseDown(selects[1] as Element);
    await click(
      [...document.body.querySelectorAll(".ant-select-item-option")].find((option) =>
        option.textContent?.includes("未发布"),
      )!,
    );
    await flush();

    expect(listDocuments).toHaveBeenLastCalledWith(system.id, {
      page: 1,
      pageSize: 20,
      latestStatus: "FAILED",
      published: false,
    });
  });

  it("deletes a document after confirmation", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listDocuments").mockResolvedValue(docPage);
    const remove = vi.spyOn(apiClient, "deleteDocument").mockResolvedValue();

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();

    await click(view.container.querySelector('[aria-label="删除文档"]')!);
    await flush();
    await click(document.body.querySelector(".ant-popconfirm-buttons .ant-btn-primary")!);
    await flush();
    await flush();

    expect(remove).toHaveBeenCalledWith(system.id, doc.id);
  });

  it("searches and filters versions inside the drawer", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listDocuments").mockResolvedValue(docPage);
    const listVersions = vi.spyOn(apiClient, "listDocumentVersions").mockResolvedValue(versionPage);

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();
    await click(view.container.querySelector('[aria-label="查看文档版本"]')!);
    await flush();

    await setInput(document.body.querySelector('[aria-label="搜索版本文件名"]')!, "guide");
    await click(document.body.querySelector('[aria-label="搜索版本"]')!);
    await mouseDown(document.body.querySelector('[aria-label="筛选版本处理状态"]')!);
    await click(
      [...document.body.querySelectorAll(".ant-select-item-option")].find((option) =>
        option.textContent?.includes("处理失败"),
      )!,
    );
    await mouseDown(document.body.querySelector('[aria-label="筛选版本发布状态"]')!);
    await click(
      [...document.body.querySelectorAll(".ant-select-item-option")].find((option) =>
        option.textContent?.includes("草稿"),
      )!,
    );
    await flush();

    expect(listVersions).toHaveBeenLastCalledWith(system.id, doc.id, {
      page: 1,
      pageSize: 20,
      search: "guide",
      statuses: ["FAILED"],
      publishStatuses: ["DRAFT"],
    });
  });

  it("deletes a version after confirmation", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listDocuments").mockResolvedValue(docPage);
    vi.spyOn(apiClient, "listDocumentVersions").mockResolvedValue(versionPage);
    const remove = vi.spyOn(apiClient, "deleteDocumentVersion").mockResolvedValue();

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();
    await click(view.container.querySelector('[aria-label="查看文档版本"]')!);
    await flush();

    await click(document.body.querySelector('[aria-label="删除版本"]')!);
    await flush();
    await click(document.body.querySelector(".ant-popconfirm-buttons .ant-btn-primary")!);
    await flush();
    await flush();

    expect(remove).toHaveBeenCalledWith(system.id, doc.id, version.id);
  });

  it("keeps a long upload filename inside the upload dialog", async () => {
    vi.spyOn(apiClient, "listSystems").mockResolvedValue([system]);
    vi.spyOn(apiClient, "listDocuments").mockResolvedValue({ ...docPage, items: [] });

    const view = await mountWithAuth(<DocumentsPage />, auth, "/admin/documents");
    views.push(view);
    await settleChain();
    await click(view.container.querySelector('[aria-label="导入文档"]')!);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["# Guide\n"], `${"very-long-document-name-".repeat(12)}.md`, {
      type: "text/markdown",
    });
    await act(async () => {
      Object.defineProperty(input, "files", { configurable: true, value: [file] });
      input.dispatchEvent(new Event("change", { bubbles: true }));
      await Promise.resolve();
    });

    const filename = document.querySelector(".document-upload-form .ant-upload-list-item-name");
    expect(filename).not.toBeNull();
    expect(filename?.textContent).toContain("very-long-document-name");
  });

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
