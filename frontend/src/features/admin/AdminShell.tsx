import { ServerCog, Settings2, UsersRound } from "lucide-react";
import type { ReactNode } from "react";

import { WorkspaceShell } from "../../shared/WorkspaceShell";

export function AdminShell(): ReactNode {
  return (
    <WorkspaceShell
      brand="KnowAgent 管理"
      navigationLabel="管理导航"
      loginPath="/admin/login"
      items={[
        {
          path: "/admin/accounts",
          label: "用户与角色",
          icon: <UsersRound size={18} />,
        },
        {
          path: "/admin/systems",
          label: "业务系统",
          icon: <ServerCog size={18} />,
        },
        {
          path: "/admin/configuration",
          label: "问答配置",
          icon: <Settings2 size={18} />,
        },
      ]}
    />
  );
}
