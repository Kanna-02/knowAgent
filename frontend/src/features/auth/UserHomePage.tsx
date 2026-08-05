import {
  Alert,
  Button,
  Input,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { Loader2, MessageSquareText, RefreshCw, Send } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type {
  BusinessSystemView,
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
}

const INITIAL_STREAM: StreamState = {
  phase: "idle",
  streamedText: "",
  ticketId: null,
  errorMessage: null,
};

export function UserHomePage(): ReactNode {
  const { user } = useAuth();
  const roleLabel = user?.role === "SYSTEM_OWNER" ? "系统负责人" : user?.role === "ADMIN" ? "管理员" : "普通用户";
  const [systems, setSystems] = useState<BusinessSystemView[]>([]);
  const [selectedSystemId, setSelectedSystemId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [systemError, setSystemError] = useState<UiError | null>(null);
  const [question, setQuestion] = useState("");
  const [requiredTerms, setRequiredTerms] = useState("");
  const [stream, setStream] = useState<StreamState>(INITIAL_STREAM);
  const [submitting, setSubmitting] = useState(false);
  const requestSequence = useRef(0);
  const eventSourceRef = useRef<EventSource | null>(null);
  const selectedSystem = systems.find((item) => item.id === selectedSystemId) ?? null;

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

  const handleEvent = useCallback((event: MessageEvent) => {
    let parsed: QuestionStreamEvent | null = null;
    try {
      parsed = JSON.parse(String(event.data)) as QuestionStreamEvent;
    } catch {
      return;
    }
    if (parsed === null) return;
    setStream((prev) => {
      switch (parsed.type) {
        case "retrieval_started":
          return { ...prev, phase: "streaming", errorMessage: null };
        case "evidence_ready":
        case "decision":
          return prev;
        case "answer_delta":
          return { ...prev, phase: "streaming", streamedText: prev.streamedText + parsed.delta };
        case "answer_completed":
          return {
            ...prev,
            phase: "completed",
            // The fully structured answer supersedes the accumulated deltas.
            streamedText: parsed.answer.text,
          };
        case "refused":
          return {
            ...prev,
            phase: "refused",
            ticketId: parsed.ticket_id,
          };
        case "error":
          return { ...prev, phase: "error", errorMessage: parsed.message };
        default:
          return prev;
      }
    });
  }, []);

  const submitQuestion = async (): Promise<void> => {
    if (!selectedSystemId || !question.trim() || submitting) return;
    closeStream();
    setStream({
      phase: "preparing",
      streamedText: "",
      ticketId: null,
      errorMessage: null,
    });
    setSubmitting(true);
    try {
      const token = await apiClient.startQuestionStream({
        system_id: selectedSystemId,
        question: question.trim(),
        required_terms: requiredTerms
          .split(",")
          .map((term) => term.trim())
          .filter(Boolean),
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
    } catch (requestError: unknown) {
      setStream({
        ...INITIAL_STREAM,
        phase: "error",
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
        <div>
          <h1>问答</h1>
          <p>{roleLabel} · 选择业务系统后提问，回答将逐字流式返回并附引用</p>
        </div>
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
          onChange={setSelectedSystemId}
        />
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
       <div className="question-composer">
          <p className="composer-context">
            当前系统：<strong>{selectedSystem.name}</strong>
          </p>
         <Input.TextArea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="输入问题（最多 2000 字）"
            maxLength={2000}
            autoSize={{ minRows: 2, maxRows: 6 }}
            aria-label="问题输入"
          />
          <Input
            value={requiredTerms}
            onChange={(event) => setRequiredTerms(event.target.value)}
            placeholder="必含术语，逗号分隔（可选）"
            maxLength={200}
            aria-label="必含术语"
          />
          <Space>
            <Button
              type="primary"
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
            >
              提交问题
            </Button>
            {stream.phase !== "idle" ? (
              <Tooltip title="清空并重新提问">
                <Button
                  icon={<RefreshCw size={16} />}
                  aria-label="重置问答"
                  disabled={submitting}
                  onClick={resetConversation}
                >
                  重置
                </Button>
              </Tooltip>
            ) : null}
          </Space>
        </div>
      )}
      {stream.phase !== "idle" ? <QuestionStreamView state={stream} /> : null}
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
      <div className="question-stream-refused" aria-label="已拒答并创建工单">
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
      </div>
    );
  }
  if (state.phase === "streaming" && state.streamedText === "") {
    return (
      <div className="question-stream-streaming" aria-label="正在检索证据">
        <Alert type="info" showIcon message="正在检索证据..." />
      </div>
    );
  }
  return (
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
  );
}
