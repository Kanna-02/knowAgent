import { Button, Dropdown, type MenuProps } from "antd";
import { CheckCircle2, LogOut, ShieldCheck, UserRound } from "lucide-react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "./authContextValue";

export function UserHomePage(): ReactNode {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
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
      <section className="user-welcome">
        <CheckCircle2 size={28} aria-hidden="true" />
        <h1>登录成功</h1>
        <p>{user?.role === "SYSTEM_OWNER" ? "系统负责人" : "普通用户"}</p>
      </section>
    </main>
  );
}
