import { Button, Dropdown, Layout, type MenuProps, Tooltip } from "antd";
import { LogOut, ShieldCheck, UserRound, UsersRound } from "lucide-react";
import type { ReactNode } from "react";
import { Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/authContextValue";

const { Header, Sider, Content } = Layout;

export function AdminShell(): ReactNode {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const accountMenu: MenuProps["items"] = [
    {
      key: "logout",
      label: "退出登录",
      icon: <LogOut size={15} />,
      onClick: () => {
        void logout().finally(() => navigate("/admin/login", { replace: true }));
      },
    },
  ];
  return (
    <Layout className="app-layout">
      <Sider
        width="var(--sidebar-width)"
        className="app-sidebar"
        breakpoint="lg"
        collapsedWidth={0}
      >
        <div className="sidebar-brand">
          <span className="brand-mark brand-mark-small">
            <ShieldCheck size={18} />
          </span>
          <span>KnowAgent 管理</span>
        </div>
        <nav className="sidebar-nav" aria-label="管理导航">
          <Button type="text" className="nav-item nav-item-active" icon={<UsersRound size={18} />}>
            用户与角色
          </Button>
        </nav>
      </Sider>
      <Layout>
        <Header className="app-header">
          <div className="header-title">平台管理</div>
          <Dropdown menu={{ items: accountMenu }} placement="bottomRight" trigger={["click"]}>
            <Tooltip title="账号菜单">
              <Button
                type="text"
                className="account-menu"
                icon={<UserRound size={17} />}
                aria-label="账号菜单"
              >
                {user?.display_name}
              </Button>
            </Tooltip>
          </Dropdown>
        </Header>
        <Content className="app-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
