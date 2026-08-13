import {
  Alert,
  App,
  Button,
  Drawer,
  Input,
  Modal,
  Popconfirm,
  Progress,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Upload,
} from "antd";
import type { TablePaginationConfig } from "antd/es/table";
import type { UploadFile } from "antd/es/upload/interface";
import {
  Archive,
  ChevronRight,
  Eye,
  FilePlus2,
  FileText,
  RefreshCw,
  Rocket,
  Search,
  Trash2,
  UploadCloud,
} from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type {
  BusinessSystemView,
  DocumentVersionStatus,
  DocumentVersionView,
  DocumentView,
  IngestionJobStatus,
  IngestionJobView,
  PublicationStatus,
} from "../../api/types";
import { FeedbackState } from "../../shared/FeedbackState";
import { toUiError, type UiError } from "../../shared/uiError";

type ManagementView = "documents" | "jobs";
type JobFilter = "ALL" | "ACTIVE" | "SUCCEEDED" | "FAILED";
type DocumentPublishedFilter = "ALL" | "PUBLISHED" | "UNPUBLISHED";
type VersionStatusFilter = "ALL" | DocumentVersionStatus;
type VersionPublishFilter = "ALL" | PublicationStatus;

const ACTIVE_JOB_STATUSES: IngestionJobStatus[] = ["QUEUED", "RUNNING", "RETRY_SCHEDULED"];

const publishStatusLabels: Record<PublicationStatus, { label: string; color: string }> = {
  DRAFT: { label: "草稿", color: "default" },
  PUBLISHED: { label: "已发布", color: "success" },
  RETIRED: { label: "已退役", color: "warning" },
};

const versionStatusLabels: Record<DocumentVersionStatus, { label: string; color: string }> = {
  UPLOADED: { label: "等待处理", color: "default" },
  PARSING: { label: "解析中", color: "processing" },
  CHUNKING: { label: "切分中", color: "processing" },
  CHUNKED: { label: "索引中", color: "processing" },
  READY_DRAFT: { label: "待发布", color: "success" },
  OCR_REQUIRED: { label: "需要 OCR", color: "warning" },
  FAILED: { label: "处理失败", color: "error" },
};

const ingestionStatusLabels: Record<IngestionJobStatus, { label: string; color: string }> = {
  QUEUED: { label: "排队中", color: "default" },
  RUNNING: { label: "处理中", color: "processing" },
  RETRY_SCHEDULED: { label: "等待重试", color: "warning" },
  SUCCEEDED: { label: "已完成", color: "success" },
  FAILED: { label: "失败", color: "error" },
};

const ingestionStageLabels: Record<IngestionJobView["stage"], string> = {
  STORED: "文件已保存",
  PARSING: "解析文档",
  CHUNKING: "切分与索引",
  COMPLETED: "索引完成",
};

function ingestionStatusLabel(job: IngestionJobView): string {
  if (
    (job.status === "RUNNING" || job.status === "QUEUED") &&
    job.lease_expires_at !== null &&
    new Date(job.lease_expires_at).getTime() < Date.now()
  ) {
    return "处理超时，等待恢复";
  }
  return ingestionStatusLabels[job.status].label;
}

function jobStatuses(filter: JobFilter): IngestionJobStatus[] | undefined {
  if (filter === "ACTIVE") return ACTIVE_JOB_STATUSES;
  if (filter === "SUCCEEDED" || filter === "FAILED") return [filter];
  return undefined;
}

function isActiveJob(job: IngestionJobView): boolean {
  return ACTIVE_JOB_STATUSES.includes(job.status);
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDateTime(value: string | null): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function DocumentsPage(): ReactNode {
  const { message } = App.useApp();
  const [systems, setSystems] = useState<BusinessSystemView[]>([]);
  const [systemsLoading, setSystemsLoading] = useState(true);
  const [systemsError, setSystemsError] = useState<UiError | null>(null);
  const [selectedSystemId, setSelectedSystemId] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<ManagementView>("documents");

  const [documents, setDocuments] = useState<DocumentView[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [docsError, setDocsError] = useState<UiError | null>(null);
  const [docsPage, setDocsPage] = useState(1);
  const [docsPageSize, setDocsPageSize] = useState(20);
  const [docsTotal, setDocsTotal] = useState(0);
  const [documentQuery, setDocumentQuery] = useState("");
  const [appliedDocumentQuery, setAppliedDocumentQuery] = useState("");
  const [docLatestStatus, setDocLatestStatus] = useState<DocumentVersionStatus | "ALL">("ALL");
  const [docPublished, setDocPublished] = useState<DocumentPublishedFilter>("ALL");

  const [jobs, setJobs] = useState<IngestionJobView[]>([]);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobsError, setJobsError] = useState<UiError | null>(null);
  const [jobsPage, setJobsPage] = useState(1);
  const [jobsPageSize, setJobsPageSize] = useState(20);
  const [jobsTotal, setJobsTotal] = useState(0);
  const [jobFilter, setJobFilter] = useState<JobFilter>("ALL");
  const [jobQuery, setJobQuery] = useState("");
  const [appliedJobQuery, setAppliedJobQuery] = useState("");
  const [selectedJob, setSelectedJob] = useState<IngestionJobView | null>(null);
  const [jobActionId, setJobActionId] = useState<string | null>(null);

  const [versions, setVersions] = useState<DocumentVersionView[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionsError, setVersionsError] = useState<UiError | null>(null);
  const [versionsDrawerOpen, setVersionsDrawerOpen] = useState(false);
  const [versionsPage, setVersionsPage] = useState(1);
  const [versionsPageSize, setVersionsPageSize] = useState(20);
  const [versionsTotal, setVersionsTotal] = useState(0);
  const [versionQuery, setVersionQuery] = useState("");
  const [appliedVersionQuery, setAppliedVersionQuery] = useState("");
  const [versionStatusFilter, setVersionStatusFilter] = useState<VersionStatusFilter>("ALL");
  const [versionPublishFilter, setVersionPublishFilter] = useState<VersionPublishFilter>("ALL");
  const [selectedDocument, setSelectedDocument] = useState<DocumentView | null>(null);
  const [versionActionId, setVersionActionId] = useState<string | null>(null);
  const [documentActionId, setDocumentActionId] = useState<string | null>(null);

  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadTarget, setUploadTarget] = useState<DocumentView | null>(null);
  const [uploadFileList, setUploadFileList] = useState<UploadFile[]>([]);
  const [uploadName, setUploadName] = useState("");
  const [uploadJob, setUploadJob] = useState<IngestionJobView | null>(null);
  const [uploadError, setUploadError] = useState<UiError | null>(null);
  const [uploading, setUploading] = useState(false);

  const systemsRequestId = useRef(0);
  const docsRequestId = useRef(0);
  const jobsRequestId = useRef(0);
  const versionsRequestId = useRef(0);
  const selectedSystemIdRef = useRef<string | null>(null);

  const loadSystems = useCallback(async (): Promise<void> => {
    const requestId = ++systemsRequestId.current;
    setSystemsLoading(true);
    try {
      const result = await apiClient.listSystems("ACTIVE");
      if (requestId !== systemsRequestId.current) return;
      setSystems(result);
      setSystemsError(null);
      if (result.length && !selectedSystemIdRef.current) {
        selectedSystemIdRef.current = result[0]!.id;
        setSelectedSystemId(result[0]!.id);
      }
    } catch (error: unknown) {
      if (requestId === systemsRequestId.current) {
        setSystemsError(toUiError(error, "业务系统列表加载失败"));
      }
    } finally {
      if (requestId === systemsRequestId.current) setSystemsLoading(false);
    }
  }, []);

  const loadDocuments = useCallback(
    async (
      systemId: string,
      targetPage = docsPage,
      targetPageSize = docsPageSize,
      targetSearch = appliedDocumentQuery,
      targetLatestStatus = docLatestStatus,
      targetPublished = docPublished,
    ): Promise<void> => {
      const requestId = ++docsRequestId.current;
      setDocsLoading(true);
      try {
        const result = await apiClient.listDocuments(systemId, {
          page: targetPage,
          pageSize: targetPageSize,
          ...(targetSearch.trim() ? { search: targetSearch.trim() } : {}),
          ...(targetLatestStatus !== "ALL" ? { latestStatus: targetLatestStatus } : {}),
          ...(targetPublished !== "ALL" ? { published: targetPublished === "PUBLISHED" } : {}),
        });
        if (requestId !== docsRequestId.current) return;
        setDocuments(result.items);
        setDocsTotal(result.total);
        setDocsError(null);
      } catch (error: unknown) {
        if (requestId === docsRequestId.current) {
          setDocsError(toUiError(error, "文档列表加载失败"));
        }
      } finally {
        if (requestId === docsRequestId.current) setDocsLoading(false);
      }
    },
    [appliedDocumentQuery, docLatestStatus, docPublished, docsPage, docsPageSize],
  );

  const loadJobs = useCallback(
    async (
      systemId: string,
      targetPage = jobsPage,
      targetPageSize = jobsPageSize,
      targetFilter = jobFilter,
      targetSearch = appliedJobQuery,
    ): Promise<void> => {
      const requestId = ++jobsRequestId.current;
      setJobsLoading(true);
      try {
        const statuses = jobStatuses(targetFilter);
        const result = await apiClient.listIngestionJobs(systemId, {
          page: targetPage,
          pageSize: targetPageSize,
          ...(statuses ? { statuses } : {}),
          ...(targetSearch.trim() ? { search: targetSearch.trim() } : {}),
        });
        if (requestId !== jobsRequestId.current) return;
        setJobs(result.items);
        setJobsTotal(result.total);
        setJobsError(null);
        setSelectedJob((current) =>
          current ? (result.items.find((job) => job.job_id === current.job_id) ?? current) : null,
        );
      } catch (error: unknown) {
        if (requestId === jobsRequestId.current) {
          setJobsError(toUiError(error, "导入任务加载失败"));
        }
      } finally {
        if (requestId === jobsRequestId.current) setJobsLoading(false);
      }
    },
    [appliedJobQuery, jobFilter, jobsPage, jobsPageSize],
  );

  const loadVersions = useCallback(
    async (
      systemId: string,
      documentId: string,
      targetPage = versionsPage,
      targetPageSize = versionsPageSize,
      targetSearch = appliedVersionQuery,
      targetStatus = versionStatusFilter,
      targetPublishStatus = versionPublishFilter,
    ): Promise<void> => {
      const requestId = ++versionsRequestId.current;
      setVersionsLoading(true);
      try {
        const result = await apiClient.listDocumentVersions(systemId, documentId, {
          page: targetPage,
          pageSize: targetPageSize,
          ...(targetSearch.trim() ? { search: targetSearch.trim() } : {}),
          ...(targetStatus !== "ALL" ? { statuses: [targetStatus] } : {}),
          ...(targetPublishStatus !== "ALL" ? { publishStatuses: [targetPublishStatus] } : {}),
        });
        if (requestId !== versionsRequestId.current) return;
        setVersions(result.items);
        setVersionsTotal(result.total);
        setVersionsError(null);
      } catch (error: unknown) {
        if (requestId === versionsRequestId.current) {
          setVersionsError(toUiError(error, "版本列表加载失败"));
        }
      } finally {
        if (requestId === versionsRequestId.current) setVersionsLoading(false);
      }
    },
    [
      appliedVersionQuery,
      versionPublishFilter,
      versionStatusFilter,
      versionsPage,
      versionsPageSize,
    ],
  );

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadSystems(), 0);
    return () => {
      window.clearTimeout(timeoutId);
      systemsRequestId.current += 1;
    };
  }, [loadSystems]);

  useEffect(() => {
    if (!selectedSystemId) return;
    const timeoutId = window.setTimeout(() => void loadDocuments(selectedSystemId), 0);
    return () => {
      window.clearTimeout(timeoutId);
      docsRequestId.current += 1;
    };
  }, [selectedSystemId, loadDocuments]);

  useEffect(() => {
    if (!selectedSystemId) return;
    const timeoutId = window.setTimeout(() => void loadJobs(selectedSystemId), 0);
    return () => {
      window.clearTimeout(timeoutId);
      jobsRequestId.current += 1;
    };
  }, [selectedSystemId, loadJobs]);

  useEffect(() => {
    if (!selectedSystemId || !jobs.some(isActiveJob)) return;
    const timeoutId = window.setTimeout(
      () => void loadJobs(selectedSystemId, jobsPage, jobsPageSize, jobFilter),
      2500,
    );
    return () => window.clearTimeout(timeoutId);
  }, [jobFilter, jobs, jobsPage, jobsPageSize, loadJobs, selectedSystemId]);

  useEffect(() => {
    if (!uploadJob || !isActiveJob(uploadJob)) return;
    const timeoutId = window.setTimeout(() => {
      void apiClient
        .getIngestionJob(uploadJob.job_id)
        .then((job) => {
          setUploadJob(job);
          setUploadError(null);
          setSelectedJob((current) => (current?.job_id === job.job_id ? job : current));
          if (!isActiveJob(job) && selectedSystemId) {
            void loadJobs(selectedSystemId);
            void loadDocuments(selectedSystemId);
          }
        })
        .catch((error: unknown) => {
          setUploadError(toUiError(error, "入库任务状态获取失败"));
        });
    }, 2000);
    return () => window.clearTimeout(timeoutId);
  }, [loadDocuments, loadJobs, selectedSystemId, uploadJob]);

  const selectSystem = (value: string): void => {
    selectedSystemIdRef.current = value;
    setSelectedSystemId(value);
    setDocsPage(1);
    setJobsPage(1);
    setSelectedJob(null);
    setUploadJob(null);
  };

  const refreshCurrentView = (): void => {
    void loadSystems();
    if (!selectedSystemId) return;
    if (activeView === "documents") void loadDocuments(selectedSystemId);
    else void loadJobs(selectedSystemId);
  };

  const applyDocumentSearch = (): void => {
    setDocsPage(1);
    setAppliedDocumentQuery(documentQuery.trim());
  };

  const changeDocumentStatusFilter = (value: DocumentVersionStatus | "ALL"): void => {
    setDocLatestStatus(value);
    setDocsPage(1);
  };

  const changeDocumentPublishedFilter = (value: DocumentPublishedFilter): void => {
    setDocPublished(value);
    setDocsPage(1);
  };

  const applyJobSearch = (): void => {
    const query = jobQuery.trim();
    setAppliedJobQuery(query);
    setJobsPage(1);
  };

  const applyVersionSearch = (): void => {
    const query = versionQuery.trim();
    setAppliedVersionQuery(query);
    setVersionsPage(1);
    if (selectedSystemId && selectedDocument) {
      void loadVersions(
        selectedSystemId,
        selectedDocument.id,
        1,
        versionsPageSize,
        query,
        versionStatusFilter,
        versionPublishFilter,
      );
    }
  };

  const changeVersionStatusFilter = (value: VersionStatusFilter): void => {
    setVersionStatusFilter(value);
    setVersionsPage(1);
    if (selectedSystemId && selectedDocument) {
      void loadVersions(
        selectedSystemId,
        selectedDocument.id,
        1,
        versionsPageSize,
        appliedVersionQuery,
        value,
        versionPublishFilter,
      );
    }
  };

  const changeVersionPublishFilter = (value: VersionPublishFilter): void => {
    setVersionPublishFilter(value);
    setVersionsPage(1);
    if (selectedSystemId && selectedDocument) {
      void loadVersions(
        selectedSystemId,
        selectedDocument.id,
        1,
        versionsPageSize,
        appliedVersionQuery,
        versionStatusFilter,
        value,
      );
    }
  };

  const openVersions = (document: DocumentView): void => {
    setSelectedDocument(document);
    setVersionsPage(1);
    setVersionsDrawerOpen(true);
    if (selectedSystemId) void loadVersions(selectedSystemId, document.id, 1, versionsPageSize);
  };

  const openUpload = (target: DocumentView | null = null): void => {
    setUploadTarget(target);
    setUploadFileList([]);
    setUploadName("");
    setUploadJob(null);
    setUploadError(null);
    setUploadOpen(true);
  };

  const submitUpload = async (): Promise<void> => {
    const file = uploadFileList[0]?.originFileObj;
    if (!selectedSystemId || !file) {
      setUploadError(toUiError(new Error("请选择要导入的文档"), "请选择要导入的文档"));
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      const job = await apiClient.uploadDocument(selectedSystemId, file, {
        ...(uploadTarget ? { documentId: uploadTarget.id } : { documentName: uploadName }),
      });
      setUploadJob(job);
      setUploadFileList([]);
      void message.success(uploadTarget ? "新版本已提交导入" : "文档已提交导入");
      setDocsPage(1);
      setJobsPage(1);
      await Promise.all([
        loadDocuments(selectedSystemId, 1, docsPageSize),
        loadJobs(selectedSystemId, 1, jobsPageSize),
      ]);
    } catch (error: unknown) {
      setUploadError(toUiError(error, "文档导入失败"));
    } finally {
      setUploading(false);
    }
  };

  const retryJob = async (job: IngestionJobView): Promise<void> => {
    setJobActionId(job.job_id);
    try {
      const retried = await apiClient.retryIngestionJob(job.job_id);
      setSelectedJob((current) => (current?.job_id === retried.job_id ? retried : current));
      setUploadJob((current) => (current?.job_id === retried.job_id ? retried : current));
      void message.success("导入任务已重新排队");
      if (selectedSystemId) await loadJobs(selectedSystemId);
    } catch (error: unknown) {
      void message.error(toUiError(error, "导入任务重试失败").message);
    } finally {
      setJobActionId(null);
    }
  };

  const publishVersion = async (version: DocumentVersionView): Promise<void> => {
    if (!selectedSystemId || !selectedDocument) return;
    setVersionActionId(version.id);
    try {
      await apiClient.publishDocumentVersion(selectedSystemId, selectedDocument.id, version.id);
      void message.success("版本已发布");
      await Promise.all([
        loadVersions(selectedSystemId, selectedDocument.id),
        loadDocuments(selectedSystemId),
      ]);
    } catch (error: unknown) {
      void message.error(toUiError(error, "版本发布失败").message);
    } finally {
      setVersionActionId(null);
    }
  };

  const retireVersion = async (version: DocumentVersionView): Promise<void> => {
    if (!selectedSystemId || !selectedDocument) return;
    setVersionActionId(version.id);
    try {
      await apiClient.retireDocumentVersion(selectedSystemId, selectedDocument.id, version.id);
      void message.success("版本已退役");
      await Promise.all([
        loadVersions(selectedSystemId, selectedDocument.id),
        loadDocuments(selectedSystemId),
      ]);
    } catch (error: unknown) {
      void message.error(toUiError(error, "版本退役失败").message);
    } finally {
      setVersionActionId(null);
    }
  };

  const deleteVersion = async (version: DocumentVersionView): Promise<void> => {
    if (!selectedSystemId || !selectedDocument) return;
    setVersionActionId(version.id);
    try {
      await apiClient.deleteDocumentVersion(selectedSystemId, selectedDocument.id, version.id);
      void message.success("版本已删除");
      await Promise.all([
        loadVersions(selectedSystemId, selectedDocument.id),
        loadDocuments(selectedSystemId),
      ]);
    } catch (error: unknown) {
      void message.error(toUiError(error, "版本删除失败").message);
    } finally {
      setVersionActionId(null);
    }
  };

  const deleteDocument = async (document: DocumentView): Promise<void> => {
    if (!selectedSystemId) return;
    setDocumentActionId(document.id);
    try {
      await apiClient.deleteDocument(selectedSystemId, document.id);
      void message.success("文档已删除");
      if (selectedDocument?.id === document.id) {
        setVersionsDrawerOpen(false);
        setSelectedDocument(null);
      }
      setDocsPage(1);
      await loadDocuments(selectedSystemId, 1, docsPageSize);
    } catch (error: unknown) {
      void message.error(toUiError(error, "文档删除失败").message);
    } finally {
      setDocumentActionId(null);
    }
  };

  const documentTable = (
    <>
      <div className="document-view-toolbar">
        <div className="document-filter-controls">
          <div className="document-search-controls">
            <Input
              value={documentQuery}
              allowClear
              aria-label="搜索文档名称"
              placeholder="搜索文档名称"
              onChange={(event) => setDocumentQuery(event.target.value)}
              onPressEnter={applyDocumentSearch}
            />
            <Tooltip title="搜索">
              <Button
                icon={<Search size={16} />}
                aria-label="搜索文档"
                onClick={applyDocumentSearch}
              />
            </Tooltip>
          </div>
          <Select<DocumentVersionStatus | "ALL">
            value={docLatestStatus}
            aria-label="筛选文档处理状态"
            options={[
              { value: "ALL", label: "全部处理状态" },
              ...Object.entries(versionStatusLabels).map(([value, config]) => ({
                value: value as DocumentVersionStatus,
                label: config.label,
              })),
            ]}
            onChange={changeDocumentStatusFilter}
          />
          <Select<DocumentPublishedFilter>
            value={docPublished}
            aria-label="筛选文档发布状态"
            options={[
              { value: "ALL", label: "全部发布状态" },
              { value: "PUBLISHED", label: "已发布" },
              { value: "UNPUBLISHED", label: "未发布" },
            ]}
            onChange={changeDocumentPublishedFilter}
          />
        </div>
        <span className="toolbar-summary">共 {docsTotal} 个文档</span>
      </div>
      {selectedSystemId && docsError ? (
        <FeedbackState
          status="error"
          title="文档列表加载失败"
          error={docsError}
          retryLabel="重试加载文档列表"
          retrying={docsLoading}
          onRetry={() => void loadDocuments(selectedSystemId)}
        />
      ) : null}
      <Table<DocumentView>
        rowKey="id"
        loading={docsLoading}
        dataSource={documents}
        locale={{ emptyText: selectedSystemId ? "没有符合条件的文档" : "请先选择业务系统" }}
        scroll={{ x: 980 }}
        pagination={{
          current: docsPage,
          pageSize: docsPageSize,
          total: docsTotal,
          showSizeChanger: true,
          showTotal: (value) => `共 ${value} 项`,
        }}
        onChange={(pagination: TablePaginationConfig) => {
          setDocsPage(pagination.current ?? 1);
          setDocsPageSize(pagination.pageSize ?? 20);
        }}
        columns={[
          {
            title: "文档名称",
            dataIndex: "name",
            width: 300,
            render: (value: string, document) => (
              <div className="document-name-cell">
                <FileText size={16} aria-hidden="true" />
                <div>
                  <strong>{value}</strong>
                  <span>
                    {document.version_count} 个版本
                    {document.latest_version_status
                      ? ` · ${versionStatusLabels[document.latest_version_status].label}`
                      : ""}
                  </span>
                </div>
              </div>
            ),
          },
          {
            title: "最新版本",
            key: "latest_version",
            width: 130,
            render: (_, document) =>
              document.latest_version_no ? `v${document.latest_version_no}` : "-",
          },
          {
            title: "最新处理状态",
            dataIndex: "latest_version_status",
            width: 140,
            render: (value: DocumentVersionStatus | null) => {
              if (!value) return <Tag>暂无版本</Tag>;
              const config = versionStatusLabels[value];
              return <Tag color={config.color}>{config.label}</Tag>;
            },
          },
          {
            title: "当前发布",
            key: "current_version",
            width: 130,
            render: (_, document) =>
              document.current_published_version_id ? (
                <Tag color="success">
                  {document.current_published_version_no
                    ? `v${document.current_published_version_no}`
                    : "已发布"}
                </Tag>
              ) : (
                <Tag>未发布</Tag>
              ),
          },
          {
            title: "更新时间",
            dataIndex: "updated_at",
            width: 180,
            render: (value: string) => formatDateTime(value),
          },
          {
            title: "操作",
            key: "actions",
            width: 160,
            fixed: "right",
            render: (_, document) => (
              <Space size={0}>
                <Tooltip title="导入新版本">
                  <Button
                    type="text"
                    icon={<FilePlus2 size={16} />}
                    aria-label="导入新版本"
                    onClick={() => openUpload(document)}
                  />
                </Tooltip>
                <Tooltip title="查看版本">
                  <Button
                    type="text"
                    icon={<ChevronRight size={16} />}
                    aria-label="查看文档版本"
                    onClick={() => openVersions(document)}
                  />
                </Tooltip>
                <Popconfirm
                  title="删除此文档？"
                  description="将删除全部版本、知识片段和文件，且不可恢复。"
                  okText="确认"
                  cancelText="取消"
                  onConfirm={() => void deleteDocument(document)}
                >
                  <Tooltip title="删除文档">
                    <Button
                      type="text"
                      danger
                      icon={<Trash2 size={16} />}
                      aria-label="删除文档"
                      loading={documentActionId === document.id}
                    />
                  </Tooltip>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />
    </>
  );

  const jobTable = (
    <>
      <div className="document-view-toolbar">
        <div className="document-filter-controls">
          <div className="document-search-controls">
            <Input
              value={jobQuery}
              allowClear
              aria-label="搜索导入任务"
              placeholder="搜索文档名称"
              onChange={(event) => setJobQuery(event.target.value)}
              onPressEnter={applyJobSearch}
            />
            <Tooltip title="搜索">
              <Button
                icon={<Search size={16} />}
                aria-label="搜索导入任务"
                onClick={applyJobSearch}
              />
            </Tooltip>
          </div>
          <Select<JobFilter>
            value={jobFilter}
            aria-label="筛选导入任务"
            options={[
              { value: "ALL", label: "全部任务" },
              { value: "ACTIVE", label: "正在导入" },
              { value: "SUCCEEDED", label: "导入完成" },
              { value: "FAILED", label: "导入失败" },
            ]}
            onChange={(value) => {
              setJobFilter(value);
              setJobsPage(1);
            }}
          />
        </div>
        <span className="toolbar-summary">共 {jobsTotal} 个任务</span>
      </div>
      {selectedSystemId && jobsError ? (
        <FeedbackState
          status="error"
          title="导入任务加载失败"
          error={jobsError}
          retryLabel="重试加载导入任务"
          retrying={jobsLoading}
          onRetry={() => void loadJobs(selectedSystemId)}
        />
      ) : null}
      <Table<IngestionJobView>
        rowKey="job_id"
        loading={jobsLoading}
        dataSource={jobs}
        locale={{ emptyText: selectedSystemId ? "暂无导入任务" : "请先选择业务系统" }}
        scroll={{ x: 1080 }}
        pagination={{
          current: jobsPage,
          pageSize: jobsPageSize,
          total: jobsTotal,
          showSizeChanger: true,
          showTotal: (value) => `共 ${value} 项`,
        }}
        onChange={(pagination: TablePaginationConfig) => {
          setJobsPage(pagination.current ?? 1);
          setJobsPageSize(pagination.pageSize ?? 20);
        }}
        columns={[
          {
            title: "文档 / 文件",
            key: "document",
            width: 300,
            render: (_, job) => (
              <div className="account-cell">
                <strong>{job.document_name}</strong>
                <span>
                  v{job.version_no} · {ingestionStatusLabel(job)} · {job.filename}
                </span>
              </div>
            ),
          },
          {
            title: "任务状态",
            dataIndex: "status",
            width: 130,
            render: (_: IngestionJobStatus, job) => {
              const config = ingestionStatusLabels[job.status];
              return <Tag color={config.color}>{ingestionStatusLabel(job)}</Tag>;
            },
          },
          {
            title: "当前阶段",
            dataIndex: "stage",
            width: 140,
            render: (value: IngestionJobView["stage"]) => ingestionStageLabels[value],
          },
          {
            title: "进度",
            dataIndex: "progress",
            width: 190,
            render: (value: number, job) => (
              <Progress
                percent={value}
                size="small"
                {...(job.status === "FAILED" ? { status: "exception" as const } : {})}
              />
            ),
          },
          {
            title: "尝试次数",
            key: "attempt",
            width: 100,
            render: (_, job) => `${job.attempt}/${job.max_attempts}`,
          },
          {
            title: "更新时间",
            dataIndex: "updated_at",
            width: 180,
            render: (value: string) => formatDateTime(value),
          },
          {
            title: "操作",
            key: "actions",
            fixed: "right",
            width: 100,
            render: (_, job) => (
              <Space size={0}>
                <Tooltip title="查看详情">
                  <Button
                    type="text"
                    icon={<Eye size={16} />}
                    aria-label="查看导入任务详情"
                    onClick={() => setSelectedJob(job)}
                  />
                </Tooltip>
                {job.status === "FAILED" ? (
                  <Tooltip title="重试">
                    <Button
                      type="text"
                      icon={<RefreshCw size={16} />}
                      aria-label="重试导入任务"
                      loading={jobActionId === job.job_id}
                      onClick={() => void retryJob(job)}
                    />
                  </Tooltip>
                ) : null}
              </Space>
            ),
          },
        ]}
      />
    </>
  );

  return (
    <section className="page-section document-management-page">
      <div className="page-heading-row">
        <div>
          <h1>文档版本管理</h1>
          <p>管理文档导入、处理进度、版本发布与退役</p>
        </div>
        <Button
          type="primary"
          icon={<UploadCloud size={16} />}
          aria-label="导入文档"
          disabled={!selectedSystemId}
          onClick={() => openUpload()}
        >
          导入文档
        </Button>
      </div>

      <div className="table-toolbar document-system-toolbar">
        <Select<string>
          loading={systemsLoading}
          placeholder="选择业务系统"
          value={selectedSystemId}
          options={systems.map((system) => ({ value: system.id, label: system.name }))}
          onChange={selectSystem}
          aria-label="选择业务系统"
        />
        <Tooltip title="刷新当前视图">
          <Button
            icon={<RefreshCw size={16} />}
            aria-label="刷新文档列表"
            onClick={refreshCurrentView}
          />
        </Tooltip>
      </div>

      {uploadJob ? (
        <div className="document-ingestion-status" aria-live="polite">
          <div className="document-ingestion-status-copy">
            <span className="toolbar-summary">最近导入</span>
            <strong>{uploadJob.document_name}</strong>
            <span className="drawer-context">
              {ingestionStageLabels[uploadJob.stage]} · {ingestionStatusLabel(uploadJob)}
            </span>
          </div>
          <Progress
            percent={uploadJob.progress}
            size="small"
            format={(percent) => `${percent ?? 0}%`}
            {...(uploadJob.status === "FAILED" ? { status: "exception" as const } : {})}
          />
          <Tooltip title="查看导入进度">
            <Button
              type="text"
              icon={<Eye size={16} />}
              aria-label="查看导入进度"
              onClick={() => {
                setSelectedJob(uploadJob);
                setActiveView("jobs");
              }}
            />
          </Tooltip>
        </div>
      ) : null}

      {systemsError ? (
        <FeedbackState
          status="error"
          title="业务系统列表加载失败"
          error={systemsError}
          retryLabel="重试加载业务系统列表"
          retrying={systemsLoading}
          onRetry={() => void loadSystems()}
        />
      ) : null}

      <Tabs
        activeKey={activeView}
        onChange={(key) => setActiveView(key as ManagementView)}
        items={[
          {
            key: "documents",
            label: <span aria-label="文档库">文档库</span>,
            children: documentTable,
          },
          {
            key: "jobs",
            label: <span aria-label="导入任务">导入任务</span>,
            children: jobTable,
          },
        ]}
      />

      <Drawer
        title={
          <span className="drawer-title">
            <FileText size={18} /> {selectedDocument?.name} - 版本列表
          </span>
        }
        size={640}
        open={versionsDrawerOpen}
        destroyOnHidden
        onClose={() => setVersionsDrawerOpen(false)}
      >
        <div className="document-view-toolbar version-view-toolbar">
          <div className="document-filter-controls">
            <div className="document-search-controls">
              <Input
                value={versionQuery}
                allowClear
                aria-label="搜索版本文件名"
                placeholder="搜索文件名"
                onChange={(event) => setVersionQuery(event.target.value)}
                onPressEnter={applyVersionSearch}
              />
              <Tooltip title="搜索">
                <Button
                  icon={<Search size={16} />}
                  aria-label="搜索版本"
                  onClick={applyVersionSearch}
                />
              </Tooltip>
            </div>
            <Select<VersionStatusFilter>
              value={versionStatusFilter}
              aria-label="筛选版本处理状态"
              options={[
                { value: "ALL", label: "全部状态" },
                ...Object.entries(versionStatusLabels).map(([value, config]) => ({
                  value: value as DocumentVersionStatus,
                  label: config.label,
                })),
              ]}
              onChange={changeVersionStatusFilter}
            />
            <Select<VersionPublishFilter>
              value={versionPublishFilter}
              aria-label="筛选版本发布状态"
              options={[
                { value: "ALL", label: "全部发布状态" },
                { value: "DRAFT", label: "草稿" },
                { value: "PUBLISHED", label: "已发布" },
                { value: "RETIRED", label: "已退役" },
              ]}
              onChange={changeVersionPublishFilter}
            />
          </div>
          <span className="toolbar-summary">共 {versionsTotal} 个版本</span>
        </div>
        {versionsError ? (
          <FeedbackState
            status="error"
            title="版本列表加载失败"
            error={versionsError}
            retryLabel="重试加载版本列表"
            retrying={versionsLoading}
            onRetry={() => {
              if (selectedSystemId && selectedDocument) {
                void loadVersions(selectedSystemId, selectedDocument.id);
              }
            }}
          />
        ) : null}
        <Table<DocumentVersionView>
          rowKey="id"
          loading={versionsLoading}
          dataSource={versions}
          size="small"
          scroll={{ x: 860 }}
          locale={{ emptyText: "暂无版本" }}
          pagination={{
            current: versionsPage,
            pageSize: versionsPageSize,
            total: versionsTotal,
            showSizeChanger: true,
            showTotal: (value) => `共 ${value} 个版本`,
          }}
          onChange={(pagination: TablePaginationConfig) => {
            const nextPage = pagination.current ?? 1;
            const nextSize = pagination.pageSize ?? 20;
            setVersionsPage(nextPage);
            setVersionsPageSize(nextSize);
            if (selectedSystemId && selectedDocument) {
              void loadVersions(selectedSystemId, selectedDocument.id, nextPage, nextSize);
            }
          }}
          columns={[
            {
              title: "版本",
              dataIndex: "version_no",
              width: 70,
              render: (value: number) => `v${value}`,
            },
            { title: "文件名", dataIndex: "filename", ellipsis: true },
            {
              title: "大小",
              dataIndex: "size_bytes",
              width: 90,
              render: (value: number) => formatFileSize(value),
            },
            {
              title: "处理状态",
              dataIndex: "status",
              width: 110,
              render: (value: DocumentVersionStatus) => {
                const config = versionStatusLabels[value];
                return <Tag color={config.color}>{config.label}</Tag>;
              },
            },
            {
              title: "发布状态",
              dataIndex: "publish_status",
              width: 100,
              render: (value: PublicationStatus) => {
                const config = publishStatusLabels[value];
                return <Tag color={config.color}>{config.label}</Tag>;
              },
            },
            {
              title: "知识片段",
              dataIndex: "chunk_count",
              width: 90,
              render: (value: number) => (value > 0 ? `${value} 个` : "-"),
            },
            {
              title: "创建时间",
              dataIndex: "created_at",
              width: 170,
              render: (value: string) => formatDateTime(value),
            },
            {
              title: "操作",
              key: "actions",
              width: 120,
              render: (_, version) => (
                <Space size={0}>
                  {version.status === "READY_DRAFT" &&
                  (version.publish_status === "DRAFT" || version.publish_status === "RETIRED") ? (
                    <Popconfirm
                      title="发布此版本？"
                      description="发布后会切换当前版本并退役旧版本。"
                      okText="确认"
                      cancelText="取消"
                      onConfirm={() => void publishVersion(version)}
                    >
                      <Tooltip title="发布">
                        <Button
                          type="text"
                          size="small"
                          icon={<Rocket size={15} />}
                          aria-label="发布版本"
                          loading={versionActionId === version.id}
                        />
                      </Tooltip>
                    </Popconfirm>
                  ) : null}
                  {version.publish_status === "PUBLISHED" ? (
                    <Popconfirm
                      title="退役此版本？"
                      description="退役后该版本的知识片段不再可检索。"
                      okText="确认"
                      cancelText="取消"
                      onConfirm={() => void retireVersion(version)}
                    >
                      <Tooltip title="退役">
                        <Button
                          type="text"
                          size="small"
                          icon={<Archive size={15} />}
                          aria-label="退役版本"
                          loading={versionActionId === version.id}
                        />
                      </Tooltip>
                    </Popconfirm>
                  ) : null}
                  <Popconfirm
                    title="删除此版本？"
                    description="将删除该版本文件、知识片段和导入记录，且不可恢复。"
                    okText="确认"
                    cancelText="取消"
                    onConfirm={() => void deleteVersion(version)}
                  >
                    <Tooltip title="删除版本">
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<Trash2 size={15} />}
                        aria-label="删除版本"
                        loading={versionActionId === version.id}
                      />
                    </Tooltip>
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Drawer>

      <Drawer
        title="导入任务详情"
        size={480}
        open={selectedJob !== null}
        destroyOnHidden
        onClose={() => setSelectedJob(null)}
      >
        {selectedJob ? (
          <div className="ingestion-job-detail">
            <div className="ingestion-job-detail-heading">
              <div>
                <strong>{selectedJob.document_name}</strong>
                <span>
                  v{selectedJob.version_no} · {selectedJob.filename}
                </span>
              </div>
              <Tag color={ingestionStatusLabels[selectedJob.status].color}>
                {ingestionStatusLabel(selectedJob)}
              </Tag>
            </div>
            <Progress
              percent={selectedJob.progress}
              {...(selectedJob.status === "FAILED" ? { status: "exception" as const } : {})}
            />
            {selectedJob.error_message ? (
              <Alert
                type="error"
                showIcon
                title={selectedJob.error_message}
                description={selectedJob.error_code ?? undefined}
              />
            ) : null}
            <dl className="ingestion-job-metadata">
              <dt>当前阶段</dt>
              <dd>{ingestionStageLabels[selectedJob.stage]}</dd>
              <dt>尝试次数</dt>
              <dd>
                {selectedJob.attempt}/{selectedJob.max_attempts}
              </dd>
              <dt>创建时间</dt>
              <dd>{formatDateTime(selectedJob.created_at)}</dd>
              <dt>更新时间</dt>
              <dd>{formatDateTime(selectedJob.updated_at)}</dd>
              <dt>下次重试</dt>
              <dd>{formatDateTime(selectedJob.next_retry_at)}</dd>
            </dl>
            {selectedJob.status === "FAILED" ? (
              <Button
                type="primary"
                icon={<RefreshCw size={16} />}
                loading={jobActionId === selectedJob.job_id}
                onClick={() => void retryJob(selectedJob)}
              >
                重新导入
              </Button>
            ) : null}
          </div>
        ) : null}
      </Drawer>

      <Modal
        title={
          <span className="drawer-title">
            <UploadCloud size={18} />
            {uploadTarget ? `导入「${uploadTarget.name}」的新版本` : "导入新文档"}
          </span>
        }
        open={uploadOpen}
        destroyOnHidden
        onCancel={() => {
          if (!uploading) setUploadOpen(false);
        }}
        okText="开始导入"
        cancelText="关闭"
        okButtonProps={{
          "aria-label": "开始导入",
          loading: uploading,
          disabled: uploadFileList.length === 0 || !selectedSystemId,
        }}
        onOk={() => void submitUpload()}
      >
        <div className="document-upload-form">
          {uploadTarget ? (
            <div className="upload-target-context">
              <FileText size={16} aria-hidden="true" />
              <span>
                新文件将作为 <strong>{uploadTarget.name}</strong> 的下一个版本导入
              </span>
            </div>
          ) : null}
          <Upload.Dragger
            accept=".pdf,.docx,.md,.markdown,.xlsx"
            maxCount={1}
            multiple={false}
            fileList={uploadFileList}
            beforeUpload={() => false}
            onChange={({ fileList }) => setUploadFileList(fileList.slice(-1))}
            onRemove={() => {
              setUploadFileList([]);
              return true;
            }}
          >
            <p className="ant-upload-drag-icon">
              <UploadCloud size={28} aria-hidden="true" />
            </p>
            <p className="ant-upload-text">点击或拖拽文档到这里</p>
            <p className="ant-upload-hint">
              支持 PDF、DOCX、Markdown 和 XLSX，单个文件不超过 25 MB
            </p>
          </Upload.Dragger>
          {!uploadTarget ? (
            <label className="document-upload-name">
              <span>文档名称（可选）</span>
              <input
                value={uploadName}
                maxLength={255}
                placeholder="留空时使用文件名"
                onChange={(event) => setUploadName(event.target.value)}
              />
            </label>
          ) : null}
          {uploadError ? <Alert type="error" showIcon title={uploadError.message} /> : null}
          {uploadJob ? (
            <div className="document-upload-job" aria-live="polite">
              <div className="document-upload-job-header">
                <strong>{uploadJob.document_name}</strong>
                <Tag color={ingestionStatusLabels[uploadJob.status].color}>
                  {ingestionStatusLabel(uploadJob)}
                </Tag>
              </div>
              <Progress
                percent={uploadJob.progress}
                {...(uploadJob.status === "FAILED" ? { status: "exception" as const } : {})}
              />
              <span className="drawer-context">
                {ingestionStageLabels[uploadJob.stage]} · v{uploadJob.version_no}
                {uploadJob.error_message ? ` · ${uploadJob.error_message}` : ""}
              </span>
              {uploadJob.status === "FAILED" ? (
                <Button
                  icon={<RefreshCw size={15} />}
                  aria-label="重试入库"
                  loading={jobActionId === uploadJob.job_id}
                  onClick={() => void retryJob(uploadJob)}
                >
                  重试入库
                </Button>
              ) : null}
              {uploadJob.status === "SUCCEEDED" ? (
                <span className="document-upload-success">入库任务已完成，可在版本列表中发布</span>
              ) : null}
            </div>
          ) : null}
        </div>
      </Modal>
    </section>
  );
}
