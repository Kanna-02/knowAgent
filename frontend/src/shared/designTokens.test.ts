import { describe, expect, it } from "vitest";

import { applyDesignTokenVariables, designTokens } from "./designTokens";

describe("design token bridge", () => {
  it("applies documented tokens to the root element", () => {
    applyDesignTokenVariables();

    expect(document.documentElement.style.getPropertyValue("--color-primary")).toBe(
      designTokens.colors.primary,
    );
    expect(document.documentElement.style.getPropertyValue("--space-4")).toBe("16px");
  });
});
