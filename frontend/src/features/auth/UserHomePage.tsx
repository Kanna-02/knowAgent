import { Alert, Button, Input, Popconfirm, Select, Space, Tag, Tooltip, Typography } from "antd";
import { Loader2, MessageSquareText, Plus, RefreshCw, Send, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type {
  BusinessSystemView,
  ConversationMessageView,
  ConversationView,
  IntentKind,
  QuestionStreamEvent,
} from "../../api/types";
import { FeedbackState } from "../../shared/FeedbackState";
import { toUiError, type UiError } from "../../shared/uiError";
import { useAuth } from "./authContextValue";

interface StreamState {
  phase: "idle" | "preparing" | "streaming" | "completed" | "refused" | "error";
  streamedText: string;
  ticketId: string | null;
  errorMessage: string | null;
  degradedReasons: string[];
  pendingQuestion: string | null;
  intent: IntentKind | null;
  rewrittenQuery: string | null;
  rewritePromptVersion: string | null;
}

const INITIAL_STREAM: StreamState = {
  phase: "idle",
  streamedText: "",
  ticketId: null,
  errorMessage: null,
  degradedReasons: [],
  pendingQuestion: null,
  intent: null,
  rewrittenQuery: null,
  rewritePromptVersion: null,
};

export function UserHomePage(): ReactNode {
  const { user } = useAuth();
  const roleLabel =
    user?.role === "SYSTEM_OWNER" ? "系统负责人" : user?.role === "ADMIN" ? "管理员" : "普通用户";
  const [systems, setSystems] = useState<BusinessSystemView[]>([]);
  const [selectedSystemId, setSelectedSystemId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [systemError, setSystemError] = useState<UiError | null>(null);
  const [conversations, setConversations] = useState<ConversationView[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [conversationMessages, setConversationMessages] = useState<ConversationMessageView[]>([]);
  const [conversationLoading, setConversationLoading] = useState(false);
  const [conversationError, setConversationError] = useState<UiError | null>(null);
  const [question, setQuestion] = useState("");
  const [requiredTerms, setRequiredTerms] = useState("");
  const [stream, setStream] = useState<StreamState>(INITIAL_STREAM);
  const [submitting, setSubmitting] = useState(false);
  const requestSequence = useRef(0);
  const conversationRequestSequence = useRef(0);
  const terminalRunsRef = useRef(new Set<string>());
  const eventSourceRef = useRef<EventSource | null>(null);
  const streamRef = useRef<StreamState>(INITIAL_STREAM);
  const selectedSystem = systems.find((item) => item.id === selectedSystemId) ?? null;

  useEffect(() => {
    streamRef.current = stream;
  }, [stream]);

  const loadSystems = useCallback(async (): Promise<void> => {
    const requestId = ++requestSequence.current;
    setLoading(true);
    try {
      const items = await apiClient.listSystems("ACTIVE");
      if (requestId === requestSequence.current) {
        setSystems(items);
        setSystemError(null);
      }
    } catch (requestError: unknown) {
      if (requestId === requestSequence.current) {
        setSystemError(toUiError(requestError, "业务系统列表加载失败"));
      }
    } finally {
      if (requestId === requestSequence.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadSystems(), 0);
    return () => {
      window.clearTimeout(timeoutId);
      requestSequence.current += 1;
    };
  }, [loadSystems]);

  // Tear down an in-flight EventSource on unmount so streams never leak.
  useEffect(() => {
    return () => {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    };
  }, []);

  const closeStream = useCallback((): void => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
  }, []);

  const loadConversationDetail = useCallback(async (conversationId: string): Promise<void> => {
    const requestId = ++conversationRequestSequence.current;
    setConversationLoading(true);
    try {
      const detail = await apiClient.getConversation(conversationId);
      if (requestId === conversationRequestSequence.current) {
        setConversationMessages(detail.messages);
        setConversationError(null);
      }
    } catch (requestError: unknown) {
      if (requestId === conversationRequestSequence.current) {
        setConversationError(toUiError(requestError, "会话加载失败"));
      }
    } finally {
      if (requestId === conversationRequestSequence.current) setConversationLoading(false);
    }
  }, []);

  const loadConversations = useCallback(
    async (systemId: string): Promise<void> => {
      const requestId = ++conversationRequestSequence.current;
      setConversationLoading(true);
      try {
        const page = await apiClient.listConversations(systemId);
        if (requestId !== conversationRequestSequence.current) return;
        setConversations(page.items);
        setConversationError(null);
        const first = page.items[0] ?? null;
        setSelectedConversationId(first?.id ?? null);
        if (first) {
          await loadConversationDetail(first.id);
        } else {
          setConversationMessages([]);
          setConversationLoading(false);
        }
      } catch (requestError: unknown) {
        if (requestId === conversationRequestSequence.current) {
          setConversations([]);
          setSelectedConversationId(null);
          setConversationMessages([]);
          setConversationError(toUiError(requestError, "会话列表加载失败"));
          setConversationLoading(false);
        }
      }
    },
    [loadConversationDetail],
  );

  const changeSystem = (systemId: string): void => {
    closeStream();
    streamRef.current = INITIAL_STREAM;
    setStream(INITIAL_STREAM);
    setSelectedSystemId(systemId);
    setConversations([]);
    setSelectedConversationId(null);
    setConversationMessages([]);
    setConversationError(null);
    conversationRequestSequence.current += 1;
    void loadConversations(systemId);
  };

  const handleEvent = useCallback((event: MessageEvent) => {
    let parsed: QuestionStreamEvent | null = null;
    try {
      parsed = JSON.parse(String(event.data)) as QuestionStreamEvent;
    } catch {
      return;
    }
    if (parsed === null) return;
    const current = streamRef.current;
    let next = current;
    switch (parsed.type) {
      case "retrieval_started":
        next = {
          ...current,
          phase: "streaming",
          errorMessage: null,
          intent: parsed.intent,
          rewrittenQuery: parsed.rewritten_query,
          rewritePromptVersion: parsed.rewrite_prompt_version,
        };
        break;
      case "evidence_ready":
        next = { ...current, degradedReasons: parsed.degraded_reasons };
        break;
      case "decision":
        break;
      case "answer_delta":
        next = {
          ...current,
          phase: "streaming",
          streamedText: current.streamedText + parsed.delta,
        };
        break;
      case "answer_completed":
        if (!terminalRunsRef.current.has(parsed.run_id)) {
          terminalRunsRef.current.add(parsed.run_id);
          setConversationMessages((messages) => [
            ...messages,
            _localUserMessage(parsed.run_id, current),
            {
              id: `local-${parsed.run_id}-assistant`,
              role: "assistant",
              content: parsed.answer.text,
              intent: null,
              rewritten_query: null,
              rewrite_prompt_version: null,
              created_at: new Date().toISOString(),
            },
          ]);
        }
        next = {
          ...current,
          phase: "completed",
          pendingQuestion: null,
          streamedText: parsed.answer.text,
          degradedReasons: parsed.degraded_reasons,
        };
        break;
      case "refused":
        if (!terminalRunsRef.current.has(parsed.run_id)) {
          terminalRunsRef.current.add(parsed.run_id);
          setConversationMessages((messages) => [
            ...messages,
            _localUserMessage(parsed.run_id, current),
          ]);
        }
        next = {
          ...current,
          phase: "refused",
          pendingQuestion: null,
          ticketId: parsed.ticket_id,
          degradedReasons: parsed.degraded_reasons,
        };
        break;
      case "error":
        next = { ...current, phase: "error", errorMessage: parsed.message };
        break;
    }
    streamRef.current = next;
    setStream(next);
  }, []);

  const startNewConversation = (): void => {
    closeStream();
    setSelectedConversationId(null);
    setConversationMessages([]);
    setConversationError(null);
    setStream(INITIAL_STREAM);
  };

  const selectConversation = (conversationId: string): void => {
    closeStream();
    setSelectedConversationId(conversationId);
    setConversationMessages([]);
    setStream(INITIAL_STREAM);
    void loadConversationDetail(conversationId);
  };

  const deleteCurrentConversation = async (): Promise<void> => {
    if (!selectedConversationId || !selectedSystemId) return;
    setConversationLoading(true);
    try {
      await apiClient.deleteConversation(selectedConversationId);
      closeStream();
      setStream(INITIAL_STREAM);
      await loadConversations(selectedSystemId);
    } catch (requestError: unknown) {
      setConversationError(toUiError(requestError, "会话删除失败"));
      setConversationLoading(false);
    }
  };

  const ensureConversation = async (questionText: string): Promise<string> => {
    if (selectedConversationId) return selectedConversationId;
    if (!selectedSystemId) throw new Error("system is required");
    const created = await apiClient.createConversation(selectedSystemId, questionText.slice(0, 60));
    setConversations((items) => [created, ...items]);
    setSelectedConversationId(created.id);
    return created.id;
  };

  const submitQuestion = async (): Promise<void> => {
    if (!selectedSystemId || !question.trim() || submitting) return;
    const questionText = question.trim();
    closeStream();
    const preparing: StreamState = {
      phase: "preparing",
      streamedText: "",
      ticketId: null,
      errorMessage: null,
      degradedReasons: [],
      pendingQuestion: questionText,
      intent: null,
      rewrittenQuery: null,
      rewritePromptVersion: null,
    };
    streamRef.current = preparing;
    setStream(preparing);
    setSubmitting(true);
    try {
      const conversationId = await ensureConversation(questionText);
      const token = await apiClient.startQuestionStream({
        system_id: selectedSystemId,
        question: questionText,
        required_terms: requiredTerms
          .split(",")
          .map((term) => term.trim())
          .filter(Boolean),
        conversation_id: conversationId,
      });
      const source = new EventSource(apiClient.streamEventsUrl(token.token));
      eventSourceRef.current = source;
      source.onmessage = handleEvent;
      source.onerror = () => {
        if (eventSourceRef.current === source) {
          setStream((prev) =>
            prev.phase === "completed" || prev.phase === "refused"
              ? prev
              : {
                  ...prev,
                  phase: "error",
                  errorMessage: prev.errorMessage ?? "问答流连接已断开，请稍后重试",
                },
          );
        }
        closeStream();
      };
      setQuestion("");
    } catch (requestError: unknown) {
      setStream({
        ...INITIAL_STREAM,
        phase: "error",
        pendingQuestion: questionText,
        errorMessage: toUiError(requestError, "问答请求失败").message,
      });
    } finally {
      setSubmitting(false);
    }
  };

  const resetConversation = (): void => {
    closeStream();
    setStream(INITIAL_STREAM);
  };

  return (
    <section className="question-workspace">
      <div className="question-toolbar">
        <div className="question-toolbar-heading">
          <div className="question-toolbar-kicker">
            <MessageSquareText size={16} aria-hidden="true" />
            <span>知识问答</span>
          </div>
          <h1>问答</h1>
          <p>{roleLabel} · 回答将基于已发布知识并附带引用</p>
        </div>
        <div className="question-toolbar-system">
          <span className="question-toolbar-label">业务系统</span>
          <Select<string>
            value={selectedSystemId}
            loading={loading}
            className="system-selector"
            placeholder="选择业务系统"
            aria-label="选择业务系统"
            options={systems.map((item) => ({
              value: item.id,
              label: `${item.name} (${item.code})`,
            }))}
            onChange={changeSystem}
          />
        </div>
      </div>
      {systemError && systems.length === 0 ? (
        <FeedbackState
          status="error"
          title="业务系统加载失败"
          error={systemError}
          retryLabel="重试加载业务系统"
          retrying={loading}
          onRetry={() => void loadSystems()}
        />
      ) : loading && systems.length === 0 ? (
        <FeedbackState status="loading" title="正在加载业务系统" />
      ) : !selectedSystem ? (
        <FeedbackState
          status="empty"
          title={systems.length ? "请选择要咨询的业务系统" : "暂无可用业务系统"}
        />
      ) : (
        <div className="question-session">
          <div className="conversation-toolbar">
            <div className="conversation-toolbar-title">
              <span className="conversation-toolbar-label">当前对话</span>
              <Select<string>
                value={selectedConversationId}
                loading={conversationLoading}
                className="conversation-selector"
                placeholder="新会话"
                aria-label="选择会话"
                options={conversations.map((item) => ({ value: item.id, label: item.title }))}
                onChange={selectConversation}
              />
            </div>
            <Space size="small" className="conversation-toolbar-actions">
              <Tooltip title="新建会话">
                <Button
                  icon={<Plus size={16} />}
                  aria-label="新建会话"
                  disabled={submitting}
                  onClick={startNewConversation}
                />
              </Tooltip>
              {selectedConversationId ? (
                <Popconfirm
                  title="删除当前会话？"
                  description="会话消息将一并删除，此操作不可撤销。"
                  okText="删除"
                  cancelText="取消"
                  okButtonProps={{ danger: true }}
                  onConfirm={() => void deleteCurrentConversation()}
                >
                  <Tooltip title="删除会话">
                    <Button
                      danger
                      icon={<Trash2 size={16} />}
                      aria-label="删除会话"
                      disabled={submitting || conversationLoading}
                    />
                  </Tooltip>
                </Popconfirm>
              ) : null}
            </Space>
          </div>
          {conversationError ? (
            <FeedbackState
              status="error"
              title="会话加载失败"
              error={conversationError}
              retryLabel="重试加载会话"
              retrying={conversationLoading}
              onRetry={() => void loadConversations(selectedSystem.id)}
            />
          ) : (
            <ConversationThread
              messages={conversationMessages}
              loading={conversationLoading}
              systemName={selectedSystem.name}
              hideLatestAssistant={stream.phase === "completed"}
            />
          )}
          {stream.phase !== "idle" ? <QuestionStreamView state={stream} /> : null}
          <div className="question-composer">
            <div className="composer-input-shell">
              <Input.TextArea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="向知识库提问"
                maxLength={2000}
                autoSize={{ minRows: 2, maxRows: 6 }}
                aria-label="问题输入"
                onPressEnter={(event) => {
                  if (!event.shiftKey) {
                    event.preventDefault();
                    void submitQuestion();
                  }
                }}
              />
              <div className="composer-action-row">
                <span className="composer-context">
                  当前系统：<strong>{selectedSystem.name}</strong>
                </span>
                <Button
                  type="primary"
                  shape="circle"
                  icon={
                    submitting || stream.phase === "streaming" || stream.phase === "preparing" ? (
                      <Loader2 size={16} className="spin" />
                    ) : (
                      <Send size={16} />
                    )
                  }
                  aria-label="提交问题"
                  loading={submitting}
                  disabled={!question.trim()}
                  onClick={() => void submitQuestion()}
                />
              </div>
            </div>
            <div className="composer-secondary-row">
              <Input
                value={requiredTerms}
                onChange={(event) => setRequiredTerms(event.target.value)}
                placeholder="必含术语，逗号分隔（可选）"
                maxLength={200}
                aria-label="必含术语"
                prefix={<span className="composer-secondary-label">检索约束</span>}
              />
              <Space>
                {stream.phase !== "idle" ? (
                  <Tooltip title="清空当前结果">
                    <Button
                      icon={<RefreshCw size={16} />}
                      aria-label="清空当前结果"
                      disabled={submitting}
                      onClick={resetConversation}
                    />
                  </Tooltip>
                ) : null}
              </Space>
            </div>
          </div>
        </div>
      )}
      {systemError && systems.length > 0 ? (
        <FeedbackState
          status="error"
          title="业务系统刷新失败"
          error={systemError}
          retryLabel="重试加载业务系统"
          retrying={loading}
          onRetry={() => void loadSystems()}
        />
      ) : null}
    </section>
  );
}

function QuestionStreamView({ state }: { state: StreamState }): ReactNode {
  return (
    <div className="current-conversation-turn">
      {state.pendingQuestion ? (
        <div className="conversation-message conversation-message-user">
          <span className="conversation-message-label">你</span>
          <Typography.Paragraph>{state.pendingQuestion}</Typography.Paragraph>
        </div>
      ) : null}
      <QuestionStreamStatus state={state} />
    </div>
  );
}

function QuestionStreamStatus({ state }: { state: StreamState }): ReactNode {
  if (state.phase === "preparing") {
    return (
      <div className="question-stream-streaming" aria-label="正在准备问答流">
        <Alert
          type="info"
          showIcon
          message="正在准备问答流..."
          description="已发起检索请求，等待证据与回答"
        />
      </div>
    );
  }
  if (state.phase === "error") {
    return (
      <div className="question-stream-error" aria-label="问答失败">
        <Alert type="error" showIcon message="问答失败" description={state.errorMessage} />
      </div>
    );
  }
  if (state.phase === "refused") {
    return (
      <Space
        direction="vertical"
        size="middle"
        className="question-stream-result"
        aria-label="已拒答并创建工单"
      >
        <RewriteStatus state={state} />
        <RetrievalDegradation reasons={state.degradedReasons} />
        <Alert
          type="warning"
          showIcon
          message="无法基于现有知识回答此问题"
          description={
            state.ticketId ? (
              <>
                已为该知识缺口创建工单，可在
                <Typography.Link href={`/app/tickets`}>工单</Typography.Link>
                页面跟踪处理进度。
              </>
            ) : (
              "已为该知识缺口创建工单"
            )
          }
        />
      </Space>
    );
  }
  if (state.phase === "streaming" && state.streamedText === "") {
    return (
      <Space
        direction="vertical"
        size="middle"
        className="question-stream-result"
        aria-label="正在检索证据"
      >
        <RewriteStatus state={state} />
        <RetrievalDegradation reasons={state.degradedReasons} />
        <Alert type="info" showIcon message="正在检索证据..." />
      </Space>
    );
  }
  return (
    <Space direction="vertical" size="middle" className="question-stream-answer-wrap">
      <RewriteStatus state={state} />
      <RetrievalDegradation reasons={state.degradedReasons} />
      <div className="question-stream-answer" aria-label="问答回答">
        <div className="answer-toolbar">
          <Space>
            <MessageSquareText size={16} />
            <strong>回答</strong>
            <Tag color={state.phase === "completed" ? "success" : "processing"}>
              {state.phase === "completed" ? "已完成" : "生成中"}
            </Tag>
          </Space>
        </div>
        <Typography.Paragraph style={{ whiteSpace: "pre-wrap" }}>
          {state.streamedText}
          {state.phase === "streaming" ? <span className="cursor-blink">▍</span> : null}
        </Typography.Paragraph>
      </div>
    </Space>
  );
}

function ConversationThread({
  messages,
  loading,
  systemName,
  hideLatestAssistant,
}: {
  messages: ConversationMessageView[];
  loading: boolean;
  systemName: string;
  hideLatestAssistant: boolean;
}): ReactNode {
  if (loading && messages.length === 0) {
    return <FeedbackState status="loading" title="正在加载会话" />;
  }
  if (messages.length === 0) {
    return <div className="conversation-empty">新会话 · {systemName}</div>;
  }
  const visibleMessages =
    hideLatestAssistant && messages[messages.length - 1]?.id.startsWith("local-")
      ? messages.slice(0, -1)
      : messages;
  return (
    <div className="conversation-thread" aria-label="会话消息">
      {visibleMessages.map((message) => (
        <div
          key={message.id}
          className={`conversation-message conversation-message-${message.role}`}
        >
          <div className="conversation-message-heading">
            <span className="conversation-message-label">
              {message.role === "user" ? "你" : "助手"}
            </span>
            {message.intent === "follow_up" ? <Tag color="blue">关联上下文</Tag> : null}
          </div>
          <Typography.Paragraph>{message.content}</Typography.Paragraph>
        </div>
      ))}
    </div>
  );
}

function RewriteStatus({ state }: { state: StreamState }): ReactNode {
  if (state.intent !== "follow_up") return null;
  return (
    <Tooltip
      title={
        state.rewrittenQuery ? `检索问题：${state.rewrittenQuery}` : "已结合当前会话改写检索问题"
      }
    >
      <Tag color="blue">已关联上下文</Tag>
    </Tooltip>
  );
}

function _localUserMessage(runId: string, state: StreamState): ConversationMessageView {
  return {
    id: `local-${runId}-user`,
    role: "user",
    content: state.pendingQuestion ?? "",
    intent: state.intent,
    rewritten_query: state.rewrittenQuery,
    rewrite_prompt_version: state.rewritePromptVersion,
    created_at: new Date().toISOString(),
  };
}

function RetrievalDegradation({ reasons }: { reasons: string[] }): ReactNode {
  if (reasons.length === 0) return null;
  const descriptions: string[] = [];
  if (reasons.includes("VECTOR_UNAVAILABLE")) {
    descriptions.push("向量检索暂不可用，当前仅使用关键词检索");
  }
  if (reasons.includes("RERANK_UNAVAILABLE")) {
    descriptions.push("重排服务暂不可用，当前使用基础融合排序");
  }
  return (
    <Alert
      type="warning"
      showIcon
      message="检索已降级"
      description={descriptions.length > 0 ? descriptions.join("；") : "部分检索能力暂不可用"}
    />
  );
}
