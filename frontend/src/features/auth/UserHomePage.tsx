import { Select } from "antd";
import { MessageSquareText } from "lucide-react";
import type { ReactNode } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { BusinessSystemView } from "../../api/types";
import { FeedbackState } from "../../shared/FeedbackState";
import { toUiError, type UiError } from "../../shared/uiError";
import { useAuth } from "./authContextValue";

export function UserHomePage(): ReactNode {
  const { user } = useAuth();
  const [systems, setSystems] = useState<BusinessSystemView[]>([]);
  const [selectedSystemId, setSelectedSystemId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<UiError | null>(null);
  const requestSequence = useRef(0);
  const selectedSystem = systems.find((item) => item.id === selectedSystemId) ?? null;

  const loadSystems = useCallback(async (): Promise<void> => {
    const requestId = ++requestSequence.current;
    setLoading(true);
    try {
      const items = await apiClient.listSystems("ACTIVE");
      if (requestId === requestSequence.current) {
        setSystems(items);
        setError(null);
      }
    } catch (requestError: unknown) {
      if (requestId === requestSequence.current) {
        setError(toUiError(requestError, "业务系统列表加载失败"));
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

  return (
    <section className="question-workspace">
      <div className="question-toolbar">
        <div>
          <h1>问答</h1>
          <p>{user?.role === "SYSTEM_OWNER" ? "系统负责人" : "普通用户"}</p>
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
      {error && systems.length === 0 ? (
        <FeedbackState
          status="error"
          title="业务系统加载失败"
          error={error}
          retryLabel="重试加载业务系统"
          retrying={loading}
          onRetry={() => void loadSystems()}
        />
      ) : loading && systems.length === 0 ? (
        <FeedbackState status="loading" title="正在加载业务系统" />
      ) : selectedSystem ? (
        <div className="system-selection-state">
          <MessageSquareText size={24} aria-hidden="true" />
          <strong>当前系统：{selectedSystem.name}</strong>
          <span>{selectedSystem.code}</span>
        </div>
      ) : (
        <FeedbackState
          status="empty"
          title={systems.length ? "请选择要咨询的业务系统" : "暂无可用业务系统"}
        />
      )}
      {error && systems.length > 0 ? (
        <FeedbackState
          status="error"
          title="业务系统刷新失败"
          error={error}
          retryLabel="重试加载业务系统"
          retrying={loading}
          onRetry={() => void loadSystems()}
        />
      ) : null}
    </section>
  );
}
