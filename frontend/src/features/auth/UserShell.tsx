import { MessageSquareText, TicketCheck } from "lucide-react";
import type { ReactNode } from "react";

import { WorkspaceShell } from "../../shared/WorkspaceShell";

export function UserShell(): ReactNode {
  return (
    <WorkspaceShell
      brand="KnowAgent"
      navigationLabel="用户导航"
      loginPath="/login"
      items={[
        {
          path: "/app/question",
          label: "问答",
          icon: <MessageSquareText size={18} />,
        },
        {
          path: "/app/tickets",
          label: "工单",
          icon: <TicketCheck size={18} />,
        },
      ]}
    />
  );
}
