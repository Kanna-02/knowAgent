import {
  Alert,
  App,
  Button,
  Drawer,
  Input,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
  Timeline,
} from "antd";
import { ArrowRight, CheckCircle2, Lock, MessageSquarePlus, RefreshCw } from "lucide-react";
import { Ticket as TicketIcon } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type {
  BusinessSystemView,
  TicketReplyView,
  TicketStatus,
  TicketTransitionView,
  TicketView,
} from "../../api/types";
import { FeedbackState } from "../../shared/FeedbackState";
import { toUiError, type UiError } from "../../shared/uiError";
import { useAuth } from "../auth/authContextValue";

interface ReplyDraft {
  body: string;
  sending: boolean;
}

const TICKET_FILTERS: { value: TicketStatus | "all"; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "open", label: "待处理" },
  { value: "assigned", label: "已指派" },
  { value: "in_progress", label: "处理中" },
  { value: "resolved", label: "已解决" },
  { value: "closed", label: "已关闭" },
];

const STATUS_LABEL: Record<TicketStatus, string> = {
  open: "待处理",
  assigned: "已指派",
  in_progress: "处理中",
  resolved: "已解决",
  closed: "已关闭",
};

const STATUS_COLOR: Record<TicketStatus, string> = {
  open: "default",
  assigned: "blue",
  in_progress: "processing",
  resolved: "success",
  closed: "default",
};

export function TicketsPage(): ReactNode {
  const { message } = App.useApp();
  const { user } = useAuth();
  const canManage = user?.role === "SYSTEM_OWNER" || user?.role === "ADMIN";
  const [systems, setSystems] = useState<BusinessSystemView[]>([]);
  const [ticketStatus, setTicketStatus] = useState<TicketStatus | "all">("all");
  const [systemId, setSystemId] = useState<string>("all");
  const [tickets, setTickets] = useState<TicketView[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<UiError | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [selectedTicket, setSelectedTicket] = useState<TicketView | null>(null);
  const loadId = useRef(0);

  const loadSystems = useCallback(async (): Promise<void> => {
    try {
      setSystems(await apiClient.listSystems());
    } catch {
      // System filter stays optional; list still loads across accessible systems.
    }
  }, []);

  const loadTickets = useCallback(
    async (targetPage = page, targetPageSize = pageSize): Promise<void> => {
      const requestId = ++loadId.current;
      setLoading(true);
      try {
        const result = await apiClient.listTickets({
          page: targetPage,
          pageSize: targetPageSize,
          ...(systemId !== "all" ? { systemId } : {}),
          ...(ticketStatus !== "all" ? { status: ticketStatus } : {}),
        });
        if (requestId === loadId.current) {
          setTickets(result.items);
          setTotal(result.total);
          setError(null);
        }
      } catch (requestError: unknown) {
        if (requestId === loadId.current) {
          setError(toUiError(requestError, "工单列表加载失败"));
        }
      } finally {
        if (requestId === loadId.current) setLoading(false);
      }
    },
    [page, pageSize, systemId, ticketStatus],
  );

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadSystems();
      void loadTickets();
    }, 0);
    return () => {
      window.clearTimeout(timeoutId);
      loadId.current += 1;
    };
  }, [loadSystems, loadTickets]);

  const reload = async (): Promise<void> => {
    await loadTickets();
    if (selectedTicket) {
      try {
        setSelectedTicket(await apiClient.getTicket(selectedTicket.id));
      } catch (error: unknown) {
        void message.error(toUiError(error, "工单刷新失败").message);
      }
    }
  };

  return (
    <section className="page-section">
      <div className="page-heading-row">
        <div>
          <h1>工单</h1>
          <p>知识缺口工单与状态流转</p>
        </div>
        <Button
          icon={<RefreshCw size={16} />}
          aria-label="刷新工单列表"
          onClick={() => void reload()}
        >
          刷新
        </Button>
      </div>
      <div className="table-toolbar">
        <Segmented<TicketStatus | "all">
          value={ticketStatus}
          options={TICKET_FILTERS}
          onChange={(value) => {
            setTicketStatus(value);
            setPage(1);
          }}
        />
        <Select<string>
          value={systemId}
          placeholder="按业务系统筛选"
          aria-label="业务系统筛选"
          className="system-filter"
          style={{ width: 220 }}
          options={[
            { value: "all", label: "全部系统" },
            ...systems.map((system) => ({
              value: system.id,
              label: system.name,
            })),
          ]}
          onChange={(value) => {
            setSystemId(value);
            setPage(1);
          }}
        />
      </div>
      {error ? (
        <FeedbackState
          status="error"
          title="工单列表加载失败"
          error={error}
          retryLabel="重试加载工单列表"
          retrying={loading}
          onRetry={() => void loadTickets()}
        />
      ) : null}
      <Table<TicketView>
        rowKey="id"
        loading={loading}
        dataSource={tickets}
        scroll={{ x: 880 }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          onChange: (nextPage, nextPageSize) => {
            setPage(nextPage);
            setPageSize(nextPageSize);
          },
        }}
        locale={{ emptyText: "暂无工单" }}
        columns={[
          {
            title: "工单",
            dataIndex: "title",
            width: 280,
            render: (value: string, item) => (
              <button
                type="button"
                className="ticket-title-button"
                onClick={() => setSelectedTicket(item)}
              >
                <strong>{value}</strong>
                <span>{item.source_run_id.slice(0, 8)}</span>
              </button>
            ),
          },
          {
            title: "问题",
            dataIndex: "question",
            ellipsis: true,
            render: (value: string) => value,
          },
          {
            title: "出现次数",
            dataIndex: "occurrence_count",
            width: 100,
            render: (value: number) => (value > 1 ? `x${value}` : "1"),
          },
          {
            title: "状态",
            dataIndex: "status",
            width: 110,
            render: (value: TicketStatus) => (
              <Tag color={STATUS_COLOR[value]}>{STATUS_LABEL[value]}</Tag>
            ),
          },
          {
            title: "更新时间",
            dataIndex: "updated_at",
            width: 180,
            render: (value: string) => new Date(value).toLocaleString(),
          },
        ]}
      />
      <TicketDetailDrawer
        ticket={selectedTicket}
        canManage={canManage}
        onClose={() => setSelectedTicket(null)}
        onChanged={reload}
      />
    </section>
  );
}

function TicketDetailDrawer({
  ticket,
  canManage,
  onClose,
  onChanged,
}: {
  ticket: TicketView | null;
  canManage: boolean;
  onClose: () => void;
  onChanged: () => Promise<void>;
}): ReactNode {
  const { message } = App.useApp();
  const [replies, setReplies] = useState<TicketReplyView[]>([]);
  const [transitions, setTransitions] = useState<TicketTransitionView[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<UiError | null>(null);
  const [draft, setDraft] = useState<ReplyDraft>({ body: "", sending: false });
  const [answer, setAnswer] = useState("");
  const [answerSending, setAnswerSending] = useState(false);
  const [transitioning, setTransitioning] = useState(false);
  const detailRequestId = useRef(0);

  const loadDetail = useCallback(async (ticketId: string): Promise<void> => {
    const requestId = ++detailRequestId.current;
    setLoading(true);
    setError(null);
    try {
      const [replyList, transitionList] = await Promise.all([
        apiClient.listTicketReplies(ticketId),
        apiClient.listTicketTransitions(ticketId),
      ]);
      if (requestId === detailRequestId.current) {
        setReplies(replyList);
        setTransitions(transitionList);
      }
    } catch (requestError: unknown) {
      if (requestId === detailRequestId.current) {
        setError(toUiError(requestError, "工单详情加载失败"));
      }
    } finally {
      if (requestId === detailRequestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!ticket) return;
    const timeoutId = window.setTimeout(() => void loadDetail(ticket.id), 0);
    return () => {
      window.clearTimeout(timeoutId);
      detailRequestId.current += 1;
    };
  }, [ticket, loadDetail]);

  const sendReply = async (): Promise<void> => {
    if (!ticket || !draft.body.trim() || draft.sending) return;
    setDraft((prev) => ({ ...prev, sending: true }));
    try {
      const reply = await apiClient.replyTicket(ticket.id, draft.body.trim());
      setReplies((prev) => [...prev, reply]);
      setDraft({ body: "", sending: false });
      void message.success("回复已发送");
      await onChanged();
    } catch (error: unknown) {
      void message.error(toUiError(error, "回复发送失败").message);
    } finally {
      setDraft((prev) => ({ ...prev, sending: false }));
    }
  };

  const submitAnswerForReview = async (): Promise<void> => {
    if (!ticket || !answer.trim() || answerSending) return;
    setAnswerSending(true);
    try {
      await apiClient.submitTicketAnswer(ticket.id, answer.trim());
      setAnswer("");
      void message.success("答案候选已提交审核");
      await onChanged();
    } catch (error: unknown) {
      void message.error(toUiError(error, "答案提交失败").message);
    } finally {
      setAnswerSending(false);
    }
  };

  const transition = async (
    action: "start" | "resolve" | "close" | "reopen",
    label: string,
    body?: string,
  ): Promise<void> => {
    if (!ticket || transitioning) return;
    setTransitioning(true);
    try {
      const updated = await apiClient.transitionTicket(ticket.id, action, body);
      void message.success(`${label}成功`);
      await onChanged();
      void loadDetail(updated.id);
    } catch (error: unknown) {
      void message.error(toUiError(error, `${label}失败`).message);
    } finally {
      setTransitioning(false);
    }
  };

  return (
    <Drawer
      title={
        <span className="drawer-title">
          <TicketIcon size={18} /> 工单详情
        </span>
      }
      size={520}
      open={Boolean(ticket)}
      destroyOnHidden
      onClose={onClose}
    >
      {ticket ? (
        <div className="ticket-detail">
          <div className="ticket-detail-header">
            <h2>{ticket.title}</h2>
            <Tag color={STATUS_COLOR[ticket.status]}>{STATUS_LABEL[ticket.status]}</Tag>
          </div>
          <p className="ticket-detail-question">{ticket.question}</p>
          <dl className="ticket-meta">
            <dt>关联运行</dt>
            <dd>
              <code>{ticket.source_run_id}</code>
            </dd>
            <dt>出现次数</dt>
            <dd>{ticket.occurrence_count}</dd>
            <dt>创建时间</dt>
            <dd>{new Date(ticket.created_at).toLocaleString()}</dd>
          </dl>

          {canManage ? (
            <div className="ticket-transition-actions">
              <Space wrap>
                {ticket.status === "open" ? (
                  <Button
                    icon={<ArrowRight size={15} />}
                    aria-label="开始处理工单"
                    loading={transitioning}
                    disabled={transitioning}
                    onClick={() => void transition("start", "开始处理")}
                  >
                    开始处理
                  </Button>
                ) : null}
                {ticket.status === "in_progress" || ticket.status === "assigned" ? (
                  <Button
                    icon={<CheckCircle2 size={15} />}
                    aria-label="标记为已解决"
                    loading={transitioning}
                    disabled={transitioning}
                    onClick={() => void transition("resolve", "标记已解决")}
                  >
                    标记已解决
                  </Button>
                ) : null}
                {ticket.status !== "closed" ? (
                  <Popconfirm
                    title="关闭此工单？"
                    description="关闭后无法再继续处理"
                    okText="确认"
                    cancelText="取消"
                    onConfirm={() => void transition("close", "关闭工单", "关闭工单")}
                  >
                    <Button
                      icon={<Lock size={15} />}
                      aria-label="关闭工单"
                      loading={transitioning}
                      disabled={transitioning}
                    >
                      关闭
                    </Button>
                  </Popconfirm>
                ) : null}
                {ticket.status === "closed" || ticket.status === "resolved" ? (
                  <Button
                    icon={<RefreshCw size={15} />}
                    aria-label="重新打开工单"
                    loading={transitioning}
                    disabled={transitioning}
                    onClick={() => void transition("reopen", "重新打开")}
                  >
                    重新打开
                  </Button>
                ) : null}
              </Space>
            </div>
          ) : null}

          {error ? (
            <Alert type="error" showIcon message="工单详情加载失败" description={error.message} />
          ) : null}

          <section className="ticket-replies">
            <h3>
              <MessageSquarePlus size={16} /> 回复 ({replies.length})
            </h3>
            {loading ? (
              <p className="muted">加载中...</p>
            ) : replies.length === 0 ? (
              <p className="muted">暂无回复</p>
            ) : (
              <ul className="reply-list">
                {replies.map((reply) => (
                  <li key={reply.id}>
                    <div className="reply-header">
                      <Tag>{reply.author_role}</Tag>
                      <span className="reply-time">
                        {new Date(reply.created_at).toLocaleString()}
                      </span>
                    </div>
                    <p style={{ whiteSpace: "pre-wrap" }}>{reply.body}</p>
                  </li>
                ))}
              </ul>
            )}
            <Input.TextArea
              value={draft.body}
              onChange={(event) => setDraft((prev) => ({ ...prev, body: event.target.value }))}
              placeholder="追加回复..."
              maxLength={10000}
              autoSize={{ minRows: 2, maxRows: 5 }}
              aria-label="回复内容"
            />
            <Button
              type="primary"
              loading={draft.sending}
              disabled={!draft.body.trim()}
              onClick={() => void sendReply()}
            >
              发送回复
            </Button>
          </section>

          {canManage ? (
            <section className="ticket-answer-candidate">
              <h3>提交答案候选（进入审核回流）</h3>
              <Input.TextArea
                value={answer}
                onChange={(event) => setAnswer(event.target.value)}
                placeholder="撰写候选答案，提交后进入审核流程"
                maxLength={10000}
                autoSize={{ minRows: 3, maxRows: 6 }}
                aria-label="答案候选"
              />
              <Button
                type="primary"
                loading={answerSending}
                disabled={!answer.trim()}
                onClick={() => void submitAnswerForReview()}
              >
                提交答案
              </Button>
            </section>
          ) : null}

          {transitions.length > 0 ? (
            <section className="ticket-transitions">
              <h3>状态流转</h3>
              <Timeline
                items={transitions.map((transition) => ({
                  key: transition.id,
                  children: (
                    <Space direction="vertical" size={0}>
                      <strong>{transition.action}</strong>
                      <span className="muted">
                        {transition.from_status ? STATUS_LABEL[transition.from_status] : "新建"}
                        <ArrowRight size={12} /> {STATUS_LABEL[transition.to_status]}
                      </span>
                      <span className="muted">
                        {new Date(transition.created_at).toLocaleString()}
                      </span>
                    </Space>
                  ),
                }))}
              />
            </section>
          ) : null}
        </div>
      ) : null}
    </Drawer>
  );
}
