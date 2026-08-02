import { Button, Drawer, Dropdown, Layout, type MenuProps, Tooltip } from "antd";
import { LogOut, Menu, ShieldCheck, UserRound } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../features/auth/authContextValue";

const { Header, Sider, Content } = Layout;

export interface WorkspaceNavItem {
  path: string;
  label: string;
  icon: ReactNode;
}

interface WorkspaceShellProps {
  brand: string;
  navigationLabel: string;
  loginPath: string;
  items: WorkspaceNavItem[];
}

export function WorkspaceShell({
  brand,
  navigationLabel,
  loginPath,
  items,
}: WorkspaceShellProps): ReactNode {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const activeItem =
    items.find(
      (item) => location.pathname === item.path || location.pathname.startsWith(`${item.path}/`),
    ) ?? items[0];
  const returnToLogin = (): void => {
    void navigate(loginPath, { replace: true });
  };
  const accountMenu: MenuProps["items"] = [
    {
      key: "logout",
      label: "退出登录",
      icon: <LogOut size={15} />,
      onClick: () => {
        void logout().then(returnToLogin, returnToLogin);
      },
    },
  ];

  const navigation = (mobile = false): ReactNode => (
    <nav className="sidebar-nav" aria-label={navigationLabel}>
      {items.map((item) => {
        const active = activeItem?.path === item.path;
        return (
          <Button
            key={item.path}
            type="text"
            className={`nav-item ${active ? "nav-item-active" : ""}`}
            icon={item.icon}
            aria-current={active ? "page" : undefined}
            onClick={() => {
              if (mobile) setMobileNavigationOpen(false);
              void navigate(item.path);
            }}
          >
            {item.label}
          </Button>
        );
      })}
    </nav>
  );

  const brandNode = (
    <div className="sidebar-brand">
      <span className="brand-mark brand-mark-small">
        <ShieldCheck size={18} aria-hidden="true" />
      </span>
      <span>{brand}</span>
    </div>
  );

  return (
    <Layout className="app-layout">
      <Sider width="var(--sidebar-width)" className="app-sidebar workspace-desktop-sidebar">
        {brandNode}
        {navigation()}
      </Sider>
      <Drawer
        className="workspace-mobile-drawer"
        placement="left"
        size="var(--sidebar-width)"
        title={brandNode}
        open={mobileNavigationOpen}
        onClose={() => setMobileNavigationOpen(false)}
      >
        {navigation(true)}
      </Drawer>
      <Layout>
        <Header className="app-header">
          <div className="header-context">
            <Tooltip title={`打开${navigationLabel}`}>
              <Button
                type="text"
                className="mobile-navigation-trigger"
                icon={<Menu size={19} />}
                aria-label={`打开${navigationLabel}`}
                onClick={() => setMobileNavigationOpen(true)}
              />
            </Tooltip>
            <span className="header-title">{activeItem?.label ?? brand}</span>
          </div>
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
