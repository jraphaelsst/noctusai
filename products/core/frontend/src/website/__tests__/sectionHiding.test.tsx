import "@testing-library/jest-dom";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { SettingsProvider, useWebsiteSettings } from "../lib/settings";
import { MarkedSection } from "../lib/markers";
import { defaultSettings } from "../content/defaults";

afterEach(cleanup);

/**
 * A hidden section renders NOTHING (not CSS-hidden markup) — contract §4:
 * "removed from the prerendered HTML ... not hidden with CSS."
 */
function PricingProbe() {
  const settings = useWebsiteSettings();
  if (!settings.sections.pricing) return null;
  return (
    <MarkedSection sectionKey="pricing">
      <div data-testid="pricing-section">pricing content</div>
    </MarkedSection>
  );
}

describe("section hiding", () => {
  it("renders the section when the setting is on (default)", () => {
    render(
      <SettingsProvider>
        <PricingProbe />
      </SettingsProvider>,
    );
    expect(defaultSettings.sections.pricing).toBe(true);
    expect(screen.getByTestId("pricing-section")).toBeInTheDocument();
  });

  it("renders nothing when the setting is off — no DOM node at all, not display:none", async () => {
    const script = document.createElement("script");
    script.id = "nx-settings";
    script.type = "application/json";
    script.textContent = JSON.stringify({ ...defaultSettings, sections: { ...defaultSettings.sections, pricing: false } });
    document.head.appendChild(script);

    render(
      <SettingsProvider>
        <PricingProbe />
      </SettingsProvider>,
    );

    // First paint still matches defaults (pricing on) — no hydration
    // mismatch. After the injected settings apply, the node must be
    // ABSENT from the DOM entirely — never merely CSS-hidden.
    await waitFor(() => expect(screen.queryByTestId("pricing-section")).not.toBeInTheDocument());
    document.head.removeChild(script);
  });
});
