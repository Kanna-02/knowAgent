import rawTokens from "../../../docs/product/15-frontend-design-tokens.json";

type DesignTokens = typeof rawTokens;

export const designTokens: DesignTokens = rawTokens;

export function applyDesignTokenVariables(root: HTMLElement = document.documentElement): void {
  const { colors, layout, radius, shadows, spacing, transitions, typography } = designTokens;
  const variables: Record<string, string> = {
    "--color-primary": colors.primary,
    "--color-primary-hover": colors["primary-hover"],
    "--color-primary-active": colors["primary-active"],
    "--color-secondary": colors.secondary,
    "--color-background": colors.background,
    "--color-surface": colors.surface,
    "--color-surface-elevated": colors["surface-elevated"],
    "--color-text-primary": colors["text-primary"],
    "--color-text-secondary": colors["text-secondary"],
    "--color-text-disabled": colors["text-disabled"],
    "--color-border": colors.border,
    "--color-border-focus": colors["border-focus"],
    "--color-success": colors.success,
    "--color-error": colors.error,
    "--color-warning": colors.warning,
    "--color-info": colors.info,
    "--radius-sm": `${radius.sm}px`,
    "--radius-md": `${radius.md}px`,
    "--radius-lg": `${radius.lg}px`,
    "--shadow-sm": shadows.sm,
    "--shadow-none": shadows.none,
    "--shadow-md": shadows.md,
    "--shadow-lg": shadows.lg,
    "--font-family": typography["font-family"],
    "--font-body-size": typography["body-size"],
    "--font-small-size": typography["small-size"],
    "--font-h1-size": typography["h1-size"],
    "--font-h2-size": typography["h2-size"],
    "--font-h3-size": typography["h3-size"],
    "--font-heading-weight": String(typography["heading-weight"]),
    "--line-height": String(typography["body-line-height"]),
    "--sidebar-width": layout["sidebar-width"],
    "--content-max-width": layout["content-max-width"],
    "--toolbar-height": layout["toolbar-height"],
    "--control-height": layout["control-height"],
    "--icon-button-size": layout["icon-button-size"],
    "--transition-fast": transitions.fast,
    "--transition-normal": transitions.normal,
  };
  spacing.scale.forEach((value, index) => {
    variables[`--space-${index}`] = `${value}px`;
  });
  Object.entries(variables).forEach(([name, value]) => root.style.setProperty(name, value));
}
