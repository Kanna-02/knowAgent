import { Button, Select, Space, Statistic, Table, Tag, Tooltip } from "antd";
import { Activity, AlertTriangle, MessageSquare, RefreshCw, Ticket } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type {
  BusinessSystemView,
  FrequentQuestionView,
  GapSource,
  KnowledgeGapView,
  SystemOverviewView,
} from "../../api/types";
import { FeedbackState } from "../../shared/FeedbackState";
import { toUiError, type UiError } from "../../shared/uiError";

const gapSourceLabels: Record<GapSource, { label: string; color: string }> = {
  refusal: { label: "拒答", color: "error" },
  unsolved_ticket: { label: "未解决工单", color: "warning" },
};

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function AnalyticsPage(): ReactNode {
  const [systems, setSystems] = useState<BusinessSystemView[]>([]);
  const [systemsLoading, setSystemsLoading] = useState(true);
  const [systemsError, setSystemsError] = useState<UiError | null>(null);
  const [selectedSystemId, setSelectedSystemId] = useState<string | null>(null);

  const [overview, setOverview] = useState<SystemOverviewView | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overviewError, setOverviewError] = useState<UiError | null>(null);

  const [frequent, setFrequent] = useState<FrequentQuestionView[]>([]);
  const [frequentLoading, setFrequentLoading] = useState(false);

  const [gaps, setGaps] = useState<KnowledgeGapView[]>([]);
  const [gapsLoading, setGapsLoading] = useState(false);

  const systemsRequestId = useRef(0);
  const dataRequestId = useRef(0);
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

  const loadAnalytics = useCallback(async (systemId: string): Promise<void> => {
    const requestId = ++dataRequestId.current;
    setOverviewLoading(true);
    setFrequentLoading(true);
    setGapsLoading(true);
    try {
      const [overviewResult, frequentResult, gapsResult] = await Promise.all([
        apiClient.getSystemOverview(systemId),
        apiClient.listFrequentQuestions(systemId, { top_n: 20 }),
        apiClient.listKnowledgeGaps(systemId, { top_n: 20 }),
      ]);
      if (requestId === dataRequestId.current) {
        setOverview(overviewResult);
        setOverviewError(null);
        setFrequent(frequentResult.items);
        setGaps(gapsResult.items);
      }
    } catch (error: unknown) {
      if (requestId === dataRequestId.current) {
        const uiError = toUiError(error, "分析数据加载失败");
        setOverviewError(uiError);
      }
    } finally {
      if (requestId === dataRequestId.current) {
        setOverviewLoading(false);
        setFrequentLoading(false);
        setGapsLoading(false);
      }
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
    const timeoutId = window.setTimeout(() => void loadAnalytics(selectedSystemId), 0);
    return () => {
      window.clearTimeout(timeoutId);
      dataRequestId.current += 1;
    };
  }, [selectedSystemId, loadAnalytics]);

  const refresh = (): void => {
    void loadSystems();
    if (selectedSystemId) void loadAnalytics(selectedSystemId);
  };

  return (
    <section className="page-section">
      <div className="page-heading-row">
        <div>
          <h1>分析仪表盘</h1>
          <p>按业务系统查看问题量、高频问题和知识缺口</p>
        </div>
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
            }}
            aria-label="选择业务系统"
          />
        </Space>
        <Tooltip title="刷新">
          <Button icon={<RefreshCw size={16} />} aria-label="刷新分析数据" onClick={refresh} />
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
      {selectedSystemId && overviewError ? (
        <FeedbackState
          status="error"
          title="分析数据加载失败"
          error={overviewError}
          retryLabel="重试加载分析数据"
          retrying={overviewLoading}
          onRetry={() => void loadAnalytics(selectedSystemId)}
        />
      ) : null}
      <div className="analytics-overview-row">
        <div className="overview-stat">
          <Statistic
            title="问题总数"
            value={overview?.question_count ?? 0}
            prefix={<MessageSquare size={18} aria-hidden="true" />}
            loading={overviewLoading}
          />
        </div>
        <div className="overview-stat">
          <Statistic
            title="拒答次数"
            value={overview?.refusal_count ?? 0}
            prefix={<AlertTriangle size={18} aria-hidden="true" />}
            loading={overviewLoading}
          />
        </div>
        <div className="overview-stat">
          <Statistic
            title="未解决工单"
            value={overview?.open_ticket_count ?? 0}
            prefix={<Ticket size={18} aria-hidden="true" />}
            loading={overviewLoading}
          />
        </div>
        <div className="overview-stat">
          <Statistic
            title="已解决工单"
            value={overview?.resolved_ticket_count ?? 0}
            prefix={<Activity size={18} aria-hidden="true" />}
            loading={overviewLoading}
          />
        </div>
      </div>
      <div className="analytics-tables-row">
        <div className="analytics-table-column">
          <h2 className="analytics-section-title">高频问题</h2>
          <Table<FrequentQuestionView>
            rowKey="normalized_question"
            loading={frequentLoading}
            dataSource={frequent}
            size="small"
            pagination={{ pageSize: 10, showSizeChanger: false }}
            scroll={{ x: 520 }}
            locale={{ emptyText: "暂无高频问题" }}
            columns={[
              {
                title: "问题",
                dataIndex: "normalized_question",
                ellipsis: true,
              },
              {
                title: "出现次数",
                dataIndex: "occurrence_count",
                width: 100,
                render: (value: number) => value,
              },
              {
                title: "拒答",
                dataIndex: "refusal_count",
                width: 80,
                render: (value: number) =>
                  value > 0 ? <Tag color="error">{value}</Tag> : <span>0</span>,
              },
              {
                title: "工单",
                dataIndex: "ticket_count",
                width: 80,
                render: (value: number) =>
                  value > 0 ? <Tag color="warning">{value}</Tag> : <span>0</span>,
              },
            ]}
          />
        </div>
        <div className="analytics-table-column">
          <h2 className="analytics-section-title">知识缺口</h2>
          <Table<KnowledgeGapView>
            rowKey={(record) => `${record.normalized_question}-${record.gap_source}`}
            loading={gapsLoading}
            dataSource={gaps}
            size="small"
            pagination={{ pageSize: 10, showSizeChanger: false }}
            scroll={{ x: 520 }}
            locale={{ emptyText: "暂无知识缺口" }}
            columns={[
              {
                title: "问题",
                dataIndex: "normalized_question",
                ellipsis: true,
              },
              {
                title: "来源",
                dataIndex: "gap_source",
                width: 120,
                render: (value: GapSource) => {
                  const cfg = gapSourceLabels[value];
                  return <Tag color={cfg.color}>{cfg.label}</Tag>;
                },
              },
              {
                title: "出现次数",
                dataIndex: "occurrence_count",
                width: 90,
                render: (value: number) => value,
              },
              {
                title: "最近出现",
                dataIndex: "last_seen_at",
                width: 160,
                render: (value: string) => formatDateTime(value),
              },
            ]}
          />
        </div>
      </div>
    </section>
  );
}
