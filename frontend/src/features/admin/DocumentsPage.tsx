import {
  Alert,
  App,
  Button,
  Drawer,
  Modal,
  Popconfirm,
  Progress,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Upload,
} from "antd";
import type { TablePaginationConfig } from "antd/es/table";
import type { UploadFile } from "antd/es/upload/interface";
import { Archive, ChevronRight, FileText, RefreshCw, Rocket, UploadCloud } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type {
  BusinessSystemView,
  DocumentView,
  DocumentVersionView,
  IngestionJobView,
  PublicationStatus,
} from "../../api/types";
import { FeedbackState } from "../../shared/FeedbackState";
import { toUiError, type UiError } from "../../shared/uiError";

const publishStatusLabels: Record<PublicationStatus, { label: string; color: string }> = {
  DRAFT: { label: "草稿", color: "default" },
  PUBLISHED: { label: "已发布", color: "success" },
  RETIRED: { label: "已退役", color: "warning" },
};

const ingestionStatusLabels: Record<IngestionJobView["status"], string> = {
  QUEUED: "排队中",
  RUNNING: "处理中",
  RETRY_SCHEDULED: "等待重试",
  SUCCEEDED: "已完成",
  FAILED: "失败",
};

const ingestionStageLabels: Record<IngestionJobView["stage"], string> = {
  STORED: "文件已保存",
  PARSING: "解析文档",
  CHUNKING: "切分知识片段",
  COMPLETED: "索引完成",
};

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

  const [documents, setDocuments] = useState<DocumentView[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [docsError, setDocsError] = useState<UiError | null>(null);
  const [docsPage, setDocsPage] = useState(1);
  const [docsPageSize, setDocsPageSize] = useState(20);
  const [docsTotal, setDocsTotal] = useState(0);

  const [versions, setVersions] = useState<DocumentVersionView[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionsError, setVersionsError] = useState<UiError | null>(null);
  const [versionsDrawerOpen, setVersionsDrawerOpen] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<DocumentView | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadFileList, setUploadFileList] = useState<UploadFile[]>([]);
  const [uploadName, setUploadName] = useState("");
  const [uploadJob, setUploadJob] = useState<IngestionJobView | null>(null);
  const [uploadError, setUploadError] = useState<UiError | null>(null);
  const [uploading, setUploading] = useState(false);

  const systemsRequestId = useRef(0);
  const docsRequestId = useRef(0);
  const versionsRequestId = useRef(0);
  const selectedSystemIdRef = useRef<string | null>(null);

  const loadSystems = useCallback(async (): Promise<void> => {
    const requestId = ++systemsRequestId.current;
    setSystemsLoading(true);
    try {
      const result = await apiClient.listSystems("ACTIVE");
      if (requestId === systemsRequestId.current) {
        setSystems(result);
        setSystemsError(null);
        if (result.length && !selectedSystemIdRef.current) {
          selectedSystemIdRef.current = result[0]!.id;
          setSelectedSystemId(result[0]!.id);
        }
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
    ): Promise<void> => {
      const requestId = ++docsRequestId.current;
      setDocsLoading(true);
      try {
        const result = await apiClient.listDocuments(systemId, {
          page: targetPage,
          pageSize: targetPageSize,
        });
        if (requestId === docsRequestId.current) {
          setDocuments(result.items);
          setDocsTotal(result.total);
          setDocsError(null);
        }
      } catch (error: unknown) {
        if (requestId === docsRequestId.current) {
          setDocsError(toUiError(error, "文档列表加载失败"));
        }
      } finally {
        if (requestId === docsRequestId.current) setDocsLoading(false);
      }
    },
    [docsPage, docsPageSize],
  );

  const loadVersions = useCallback(async (systemId: string, documentId: string): Promise<void> => {
    const requestId = ++versionsRequestId.current;
    setVersionsLoading(true);
    try {
      const result = await apiClient.listDocumentVersions(systemId, documentId, {
        page: 1,
        pageSize: 100,
      });
      if (requestId === versionsRequestId.current) {
        setVersions(result.items);
        setVersionsError(null);
      }
    } catch (error: unknown) {
      if (requestId === versionsRequestId.current) {
        setVersionsError(toUiError(error, "版本列表加载失败"));
      }
    } finally {
      if (requestId === versionsRequestId.current) setVersionsLoading(false);
    }
  }, []);

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

  const openVersions = (doc: DocumentView): void => {
    setSelectedDocument(doc);
    setVersionsDrawerOpen(true);
    if (selectedSystemId) void loadVersions(selectedSystemId, doc.id);
  };

  const publishVersion = async (version: DocumentVersionView): Promise<void> => {
    if (!selectedSystemId || !selectedDocument) return;
    setActionLoading(true);
    try {
      await apiClient.publishDocumentVersion(selectedSystemId, selectedDocument.id, version.id);
      void message.success("版本已发布");
      await loadVersions(selectedSystemId, selectedDocument.id);
      await loadDocuments(selectedSystemId, docsPage, docsPageSize);
    } catch (error: unknown) {
      void message.error(toUiError(error, "版本发布失败").message);
    } finally {
      setActionLoading(false);
    }
  };

  const retireVersion = async (version: DocumentVersionView): Promise<void> => {
    if (!selectedSystemId || !selectedDocument) return;
    setActionLoading(true);
    try {
      await apiClient.retireDocumentVersion(selectedSystemId, selectedDocument.id, version.id);
      void message.success("版本已退役");
      await loadVersions(selectedSystemId, selectedDocument.id);
      await loadDocuments(selectedSystemId, docsPage, docsPageSize);
    } catch (error: unknown) {
      void message.error(toUiError(error, "版本退役失败").message);
    } finally {
      setActionLoading(false);
    }
  };

  const openUpload = (): void => {
    setUploadFileList([]);
    setUploadName("");
    setUploadJob(null);
    setUploadError(null);
    setUploadOpen(true);
  };

  const closeUpload = (): void => {
    if (uploading) return;
    setUploadOpen(false);
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
        documentName: uploadName,
      });
      setUploadJob(job);
      void message.success("文档已提交入库");
      await loadDocuments(selectedSystemId, 1, docsPageSize);
      setDocsPage(1);
    } catch (error: unknown) {
      setUploadError(toUiError(error, "文档导入失败"));
    } finally {
      setUploading(false);
    }
  };

  const retryUpload = async (): Promise<void> => {
    if (!uploadJob) return;
    setUploading(true);
    setUploadError(null);
    try {
      setUploadJob(await apiClient.retryIngestionJob(uploadJob.job_id));
    } catch (error: unknown) {
      setUploadError(toUiError(error, "入库任务重试失败"));
    } finally {
      setUploading(false);
    }
  };

  useEffect(() => {
    if (!uploadJob || uploadJob.status === "SUCCEEDED" || uploadJob.status === "FAILED") return;
    const timerId = window.setTimeout(() => {
      void apiClient
        .getIngestionJob(uploadJob.job_id)
        .then(setUploadJob)
        .catch((error: unknown) => setUploadError(toUiError(error, "入库任务状态获取失败")));
    }, 2000);
    return () => window.clearTimeout(timerId);
  }, [uploadJob]);

  return (
    <section className="page-section">
      <div className="page-heading-row">
        <div>
          <h1>文档版本管理</h1>
          <p>管理业务系统的文档发布与退役</p>
        </div>
        <Button
          type="primary"
          icon={<UploadCloud size={16} />}
          aria-label="导入文档"
          disabled={!selectedSystemId}
          onClick={openUpload}
        >
          导入文档
        </Button>
      </div>
      <div className="table-toolbar">
        <Space wrap>
          <Select<string>
            loading={systemsLoading}
            placeholder="选择业务系统"
            value={selectedSystemId}
            style={{ minWidth: 200 }}
            options={systems.map((sys) => ({ value: sys.id, label: sys.name }))}
            onChange={(value) => {
              selectedSystemIdRef.current = value;
              setSelectedSystemId(value);
              setDocsPage(1);
            }}
            aria-label="选择业务系统"
          />
        </Space>
        <Tooltip title="刷新">
          <Button
            icon={<RefreshCw size={16} />}
            aria-label="刷新文档列表"
            onClick={() => {
              void loadSystems();
              if (selectedSystemId) void loadDocuments(selectedSystemId);
            }}
          />
        </Tooltip>
      </div>
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
        locale={{ emptyText: selectedSystemId ? "该系统暂无文档" : "请先选择业务系统" }}
        scroll={{ x: 760 }}
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
            width: 320,
            render: (value: string) => (
              <div className="account-cell">
                <FileText size={15} aria-hidden="true" />
                <strong>{value}</strong>
              </div>
            ),
          },
          {
            title: "当前发布版本",
            key: "current_version",
            width: 160,
            render: (_, doc) =>
              doc.current_published_version_id ? (
                <Tag color="success">已发布</Tag>
              ) : (
                <Tag>未发布</Tag>
              ),
          },
          {
            title: "创建时间",
            dataIndex: "created_at",
            width: 180,
            render: (value: string) => formatDateTime(value),
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
            width: 100,
            fixed: "right",
            render: (_, doc) => (
              <Tooltip title="查看版本">
                <Button
                  type="text"
                  icon={<ChevronRight size={16} />}
                  aria-label="查看文档版本"
                  onClick={() => openVersions(doc)}
                />
              </Tooltip>
            ),
          },
        ]}
      />
      <Drawer
        title={
          <span className="drawer-title">
            <FileText size={18} /> {selectedDocument?.name} — 版本列表
          </span>
        }
        size={560}
        open={versionsDrawerOpen}
        destroyOnHidden
        onClose={() => setVersionsDrawerOpen(false)}
      >
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
          pagination={false}
          scroll={{ x: 480 }}
          locale={{ emptyText: "暂无版本" }}
          columns={[
            {
              title: "版本",
              dataIndex: "version_no",
              width: 70,
              render: (value: number) => `v${value}`,
            },
            {
              title: "文件名",
              dataIndex: "filename",
              ellipsis: true,
            },
            {
              title: "大小",
              dataIndex: "size_bytes",
              width: 90,
              render: (value: number) => formatFileSize(value),
            },
            {
              title: "处理状态",
              dataIndex: "status",
              width: 100,
              render: (value: string) => <Tag>{value}</Tag>,
            },
            {
              title: "发布状态",
              dataIndex: "publish_status",
              width: 90,
              render: (value: PublicationStatus) => {
                const cfg = publishStatusLabels[value];
                return <Tag color={cfg.color}>{cfg.label}</Tag>;
              },
            },
            {
              title: "操作",
              key: "actions",
              width: 80,
              render: (_, version) => (
                <Space size={0}>
                  {version.publish_status === "DRAFT" || version.publish_status === "RETIRED" ? (
                    <Popconfirm
                      title="发布此版本？"
                      description="发布后会原子切换当前发布指针并退役旧版本。"
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
                          loading={actionLoading}
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
                          loading={actionLoading}
                        />
                      </Tooltip>
                    </Popconfirm>
                  ) : null}
                </Space>
              ),
            },
          ]}
        />
      </Drawer>
      <Modal
        title={
          <span className="drawer-title">
            <UploadCloud size={18} /> 导入知识文档
          </span>
        }
        open={uploadOpen}
        destroyOnHidden
        onCancel={closeUpload}
        okText="开始导入"
        cancelText="关闭"
        okButtonProps={{
          "aria-label": "开始导入",
          loading: uploading,
          disabled: uploadFileList.length === 0 || !selectedSystemId || uploadJob !== null,
        }}
        onOk={() => void submitUpload()}
      >
        <div className="document-upload-form">
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
          <label className="document-upload-name">
            <span>知识库名称（可选）</span>
            <input
              value={uploadName}
              maxLength={255}
              placeholder="留空时使用文件名"
              onChange={(event) => setUploadName(event.target.value)}
            />
          </label>
          {uploadError ? <Alert type="error" showIcon message={uploadError.message} /> : null}
          {uploadJob ? (
            <div className="document-upload-job" aria-live="polite">
              <div className="document-upload-job-header">
                <strong>{uploadJob.document_name}</strong>
                <Tag color={uploadJob.status === "FAILED" ? "error" : "processing"}>
                  {ingestionStatusLabels[uploadJob.status]}
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
                  loading={uploading}
                  onClick={() => void retryUpload()}
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
