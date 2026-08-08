import { Button, Input, Select, Space, Table, Tag, Tooltip } from "antd";
import type { TablePaginationConfig } from "antd/es/table";
import { RefreshCw, Search } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { AuditLogView } from "../../api/types";
import { FeedbackState } from "../../shared/FeedbackState";
import { toUiError, type UiError } from "../../shared/uiError";

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function resultTag(result: string): ReactNode {
  if (result === "success") return <Tag color="success">成功</Tag>;
  if (result === "failure") return <Tag color="error">失败</Tag>;
  return <Tag>{result}</Tag>;
}

export function AuditLogsPage(): ReactNode {
  const [items, setItems] = useState<AuditLogView[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<UiError | null>(null);

  const [actionFilter, setActionFilter] = useState<string>("");
  const [objectTypeFilter, setObjectTypeFilter] = useState<string>("");
  const [resultFilter, setResultFilter] = useState<string | null>(null);

  const loadRequestId = useRef(0);

  const load = useCallback(async (): Promise<void> => {
    const requestId = ++loadRequestId.current;
    setLoading(true);
    try {
      const result = await apiClient.listAuditLogs({
        page,
        pageSize,
        ...(actionFilter.trim() ? { action: actionFilter.trim() } : {}),
        ...(objectTypeFilter.trim() ? { object_type: objectTypeFilter.trim() } : {}),
        ...(resultFilter ? { result: resultFilter } : {}),
      });
      if (requestId === loadRequestId.current) {
        setItems(result.items);
        setTotal(result.total);
        setLoadError(null);
      }
    } catch (error: unknown) {
      if (requestId === loadRequestId.current) {
        setLoadError(toUiError(error, "审计日志加载失败"));
      }
    } finally {
      if (requestId === loadRequestId.current) setLoading(false);
    }
  }, [page, pageSize, actionFilter, objectTypeFilter, resultFilter]);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void load(), 0);
    return () => {
      window.clearTimeout(timeoutId);
      loadRequestId.current += 1;
    };
  }, [load]);

  const applyFilters = (): void => {
    setPage(1);
    void load();
  };

  return (
    <section className="page-section">
      <div className="page-heading-row">
        <div>
          <h1>审计日志</h1>
          <p>共 {total} 条记录</p>
        </div>
      </div>
      <div className="table-toolbar">
        <Space wrap>
          <Input
            placeholder="操作类型"
            value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            onPressEnter={applyFilters}
            style={{ width: 180 }}
            aria-label="筛选操作类型"
          />
          <Input
            placeholder="对象类型"
            value={objectTypeFilter}
            onChange={(e) => setObjectTypeFilter(e.target.value)}
            onPressEnter={applyFilters}
            style={{ width: 160 }}
            aria-label="筛选对象类型"
          />
          <Select<string | null>
            allowClear
            placeholder="全部结果"
            value={resultFilter}
            style={{ width: 120 }}
            options={[
              { value: "success", label: "成功" },
              { value: "failure", label: "失败" },
            ]}
            onChange={(value) => {
              setResultFilter(value);
              setPage(1);
            }}
            aria-label="筛选结果"
          />
          <Tooltip title="应用筛选">
            <Button icon={<Search size={16} />} aria-label="应用筛选" onClick={applyFilters} />
          </Tooltip>
        </Space>
        <Tooltip title="刷新">
          <Button
            icon={<RefreshCw size={16} />}
            aria-label="刷新审计日志"
            onClick={() => void load()}
          />
        </Tooltip>
      </div>
      {loadError ? (
        <FeedbackState
          status="error"
          title="审计日志加载失败"
          error={loadError}
          retryLabel="重试加载审计日志"
          retrying={loading}
          onRetry={() => void load()}
        />
      ) : null}
      <Table<AuditLogView>
        rowKey="id"
        loading={loading}
        dataSource={items}
        locale={{ emptyText: "暂无审计记录" }}
        scroll={{ x: 920 }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (value) => `共 ${value} 项`,
        }}
        onChange={(pagination: TablePaginationConfig) => {
          setPage(pagination.current ?? 1);
          setPageSize(pagination.pageSize ?? 20);
        }}
        columns={[
          {
            title: "时间",
            dataIndex: "created_at",
            width: 180,
            render: (value: string) => formatDateTime(value),
          },
          {
            title: "操作者",
            dataIndex: "actor_id",
            width: 180,
            ellipsis: true,
            render: (value: string | null) =>
              value ? <code className="audit-id">{value.slice(0, 8)}</code> : "-",
          },
          {
            title: "操作",
            dataIndex: "action",
            width: 180,
            ellipsis: { showTitle: false },
            render: (value: string) => (
              <Tooltip title={value}>
                <Tag className="audit-action-tag">{value}</Tag>
              </Tooltip>
            ),
          },
          {
            title: "对象类型",
            dataIndex: "object_type",
            width: 140,
            ellipsis: true,
            render: (value: string | null) => value ?? "-",
          },
          {
            title: "结果",
            dataIndex: "result",
            width: 100,
            render: (value: string) => resultTag(value),
          },
          {
            title: "追踪 ID",
            dataIndex: "request_id",
            width: 140,
            ellipsis: true,
            render: (value: string | null) =>
              value ? <code className="audit-id">{value.slice(0, 8)}</code> : "-",
          },
          {
            title: "详情",
            key: "detail",
            ellipsis: true,
            render: (_, record) => {
              if (record.detail) return record.detail;
              if (record.context_data && Object.keys(record.context_data).length > 0) {
                return JSON.stringify(record.context_data);
              }
              return "-";
            },
          },
        ]}
      />
    </section>
  );
}
