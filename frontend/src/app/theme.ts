import type { ThemeConfig } from "antd";

import { designTokens } from "../shared/designTokens";

export const theme: ThemeConfig = {
  token: {
    colorPrimary: designTokens.colors.primary,
    colorInfo: designTokens.colors.info,
    colorSuccess: designTokens.colors.success,
    colorWarning: designTokens.colors.warning,
    colorError: designTokens.colors.error,
    colorText: designTokens.colors["text-primary"],
    colorTextSecondary: designTokens.colors["text-secondary"],
    colorBorder: designTokens.colors.border,
    colorBgBase: designTokens.colors.background,
    colorBgContainer: designTokens.colors.surface,
    borderRadius: designTokens.radius.md,
    controlHeight: Number.parseInt(designTokens.layout["control-height"], 10),
    fontFamily: designTokens.typography["font-family"],
    fontSize: Number.parseInt(designTokens.typography["body-size"], 10),
  },
  components: {
    Button: { primaryShadow: designTokens.shadows.none },
    Card: { boxShadow: designTokens.shadows.none },
    Layout: {
      bodyBg: designTokens.colors.background,
      headerBg: designTokens.colors.surface,
      siderBg: designTokens.colors.surface,
    },
    Table: { headerBg: designTokens.colors["surface-elevated"] },
  },
};
