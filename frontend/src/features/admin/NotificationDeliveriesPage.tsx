import { App, Button, Popconfirm, Select, Space, Table, Tag, Tooltip } from "antd";
import type { TablePaginationConfig } from "antd/es/table";
import { RefreshCw, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type {
  NotificationDeliveryStatus,
  NotificationDeliveryView,
  NotificationEventType,
} from "../../api/types";
import { FeedbackState } from "../../shared/FeedbackState";
import { toUiError, type UiError } from "../../shared/uiError";

export function NotificationDeliveriesPage(): ReactNode {
  const { message } = App.useApp();
  const [items, setItems] = useState<NotificationDeliveryView[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [statusFilter, setStatusFilter] = useState<NotificationDeliveryStatus | null>(null);
  const [eventFilter, setEventFilter] = useState<NotificationEventType | null>(null);
  const [loading, setLoading] = useState(true);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<UiError | null>(null);
  const requestId = useRef(0);

  const load = useCallback(async (): Promise<void> => {
    const current = ++requestId.current;
    setLoading(true);
    try {
      const result = await apiClient.listNotificationDeliveries({
        page,
        pageSize,
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(eventFilter ? { eventType: eventFilter } : {}),
      });
      if (current === requestId.current) {
        setItems(result.items);
        setTotal(result.total);
        setLoadError(null);
      }
    } catch (error: unknown) {
      if (current === requestId.current) setLoadError(toUiError(error, "通知记录加载失败"));
    } finally {
      if (current === requestId.current) setLoading(false);
    }
  }, [eventFilter, page, pageSize, statusFilter]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => {
      window.clearTimeout(timer);
      requestId.current += 1;
    };
  }, [load]);

  const retry = async (deliveryId: string): Promise<void> => {
    setRetryingId(deliveryId);
    try {
      await apiClient.retryNotificationDelivery(deliveryId);
      void message.success("通知已进入重试队列");
      await load();
    } catch (error: unknown) {
      void message.error(toUiError(error, "通知重试失败").message);
    } finally {
      setRetryingId(null);
    }
  };

  return (
    <section className="page-section">
      <div className="page-heading-row">
        <div>
          <h1>通知记录</h1>
          <p>共 {total} 条投递记录</p>
        </div>
      </div>
      <div className="table-toolbar">
        <Space wrap>
          <Select<NotificationDeliveryStatus>
            allowClear
            placeholder="全部状态"
            aria-label="筛选通知状态"
            value={statusFilter}
            options={STATUS_OPTIONS}
            onChange={(value) => {
              setStatusFilter(value);
              setPage(1);
            }}
          />
          <Select<NotificationEventType>
            allowClear
            placeholder="全部事件"
            aria-label="筛选通知事件"
            value={eventFilter}
            options={EVENT_OPTIONS}
            onChange={(value) => {
              setEventFilter(value);
              setPage(1);
            }}
          />
        </Space>
        <Tooltip title="刷新">
          <Button
            icon={<RefreshCw size={16} />}
            aria-label="刷新通知记录"
            loading={loading}
            onClick={() => void load()}
          />
        </Tooltip>
      </div>
      {loadError ? (
        <FeedbackState
          status="error"
          title="通知记录加载失败"
          error={loadError}
          retryLabel="重试加载通知记录"
          retrying={loading}
          onRetry={() => void load()}
        />
      ) : null}
      <Table<NotificationDeliveryView>
        rowKey="id"
        loading={loading}
        dataSource={items}
        locale={{ emptyText: "暂无通知记录" }}
        scroll={{ x: 1180 }}
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
          { title: "时间", dataIndex: "created_at", width: 180, render: formatDateTime },
          { title: "事件", dataIndex: "event_type", width: 130, render: eventLabel },
          { title: "接收人", dataIndex: "recipient_address", width: 180, ellipsis: true },
          {
            title: "状态",
            dataIndex: "status",
            width: 130,
            render: deliveryStatusTag,
          },
          { title: "累计尝试", dataIndex: "attempt_count", width: 100 },
          {
            title: "下次尝试",
            dataIndex: "next_attempt_at",
            width: 180,
            render: (value: string | null) => (value ? formatDateTime(value) : "-"),
          },
          {
            title: "失败原因",
            key: "error",
            width: 260,
            ellipsis: true,
            render: (_, item) =>
              item.last_error_code
                ? `${item.last_error_code}${item.last_error_message ? `：${item.last_error_message}` : ""}`
                : "-",
          },
          {
            title: "Provider 消息 ID",
            dataIndex: "provider_message_id",
            width: 180,
            ellipsis: true,
            render: (value: string | null) => value ?? "-",
          },
          {
            title: "操作",
            key: "actions",
            width: 100,
            fixed: "right",
            render: (_, item) =>
              item.status === "PERMANENT_FAILURE" ? (
                <Popconfirm
                  title="重新投递此通知？"
                  description="累计尝试次数会保留，并开始新的自动重试周期。"
                  okText="重试"
                  cancelText="取消"
                  onConfirm={() => void retry(item.id)}
                >
                  <Button
                    size="small"
                    icon={<RotateCcw size={15} />}
                    loading={retryingId === item.id}
                  >
                    重试
                  </Button>
                </Popconfirm>
              ) : null,
          },
        ]}
      />
    </section>
  );
}

const STATUS_OPTIONS = [
  { value: "PENDING", label: "待投递" },
  { value: "QUEUED", label: "已入队" },
  { value: "DELIVERING", label: "投递中" },
  { value: "RETRY_SCHEDULED", label: "等待重试" },
  { value: "DELIVERED", label: "已送达" },
  { value: "PERMANENT_FAILURE", label: "永久失败" },
  { value: "SKIPPED", label: "已跳过" },
] satisfies { value: NotificationDeliveryStatus; label: string }[];

const EVENT_OPTIONS = [
  { value: "ticket_created", label: "工单创建" },
  { value: "ticket_replied", label: "负责人回复" },
] satisfies { value: NotificationEventType; label: string }[];

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("zh-CN");
}

function eventLabel(value: NotificationEventType): string {
  return EVENT_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

function deliveryStatusTag(value: NotificationDeliveryStatus): ReactNode {
  const label = STATUS_OPTIONS.find((option) => option.value === value)?.label ?? value;
  if (value === "DELIVERED") return <Tag color="success">{label}</Tag>;
  if (value === "PERMANENT_FAILURE") return <Tag color="error">{label}</Tag>;
  if (value === "RETRY_SCHEDULED") return <Tag color="warning">{label}</Tag>;
  if (value === "DELIVERING" || value === "QUEUED") return <Tag color="processing">{label}</Tag>;
  return <Tag>{label}</Tag>;
}
