import { Alert, Button, Dropdown, Empty, Select, type MenuProps } from "antd";
import { LogOut, MessageSquareText, ShieldCheck, UserRound } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError, apiClient } from "../../api/client";
import type { BusinessSystemView } from "../../api/types";
import { useAuth } from "./authContextValue";

export function UserHomePage(): ReactNode {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [systems, setSystems] = useState<BusinessSystemView[]>([]);
  const [selectedSystemId, setSelectedSystemId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const selectedSystem = systems.find((item) => item.id === selectedSystemId) ?? null;

  useEffect(() => {
    let active = true;
    void apiClient
      .listSystems("ACTIVE")
      .then((items) => {
        if (!active) return;
        setSystems(items);
        setError(null);
      })
      .catch((requestError: unknown) => {
        if (active) {
          setError(
            requestError instanceof ApiError ? requestError.message : "业务系统列表加载失败",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);
  const menu: MenuProps["items"] = [
    {
      key: "logout",
      icon: <LogOut size={15} />,
      label: "退出登录",
      onClick: () => void logout().finally(() => navigate("/login", { replace: true })),
    },
  ];
  return (
    <main className="user-shell">
      <header className="user-header">
        <div className="sidebar-brand">
          <span className="brand-mark brand-mark-small">
            <ShieldCheck size={18} />
          </span>
          <span>KnowAgent</span>
        </div>
        <Dropdown menu={{ items: menu }} trigger={["click"]}>
          <Button type="text" icon={<UserRound size={17} />}>
            {user?.display_name}
          </Button>
        </Dropdown>
      </header>
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
        {error ? (
          <Alert type="error" showIcon message={error} />
        ) : selectedSystem ? (
          <div className="system-selection-state">
            <MessageSquareText size={24} aria-hidden="true" />
            <strong>当前系统：{selectedSystem.name}</strong>
            <span>{selectedSystem.code}</span>
          </div>
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={systems.length || loading ? "请选择要咨询的业务系统" : "暂无可用业务系统"}
          />
        )}
      </section>
    </main>
  );
}
