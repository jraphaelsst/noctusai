import "@testing-library/jest-dom";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { SettingsProvider, useWebsiteSettings } from "../lib/settings";
import { defaultSettings } from "../content/defaults";

afterEach(cleanup);

function Probe() {
  const settings = useWebsiteSettings();
  return <div data-testid="pricing">{String(settings.sections.pricing)}</div>;
}

describe("SettingsProvider", () => {
  it("falls back to content/defaults.ts when #nx-settings is absent", () => {
    render(
      <SettingsProvider>
        <Probe />
      </SettingsProvider>,
    );
    expect(screen.getByTestId("pricing")).toHaveTextContent(String(defaultSettings.sections.pricing));
  });

  it("falls back to defaults when the placeholder was never substituted (__NX_SETTINGS__)", () => {
    const script = document.createElement("script");
    script.id = "nx-settings";
    script.type = "application/json";
    script.textContent = "__NX_SETTINGS__";
    document.head.appendChild(script);

    render(
      <SettingsProvider>
        <Probe />
      </SettingsProvider>,
    );
    expect(screen.getByTestId("pricing")).toHaveTextContent(String(defaultSettings.sections.pricing));
    document.head.removeChild(script);
  });

  it("adopts the injected settings JSON after mount when present and valid", async () => {
    const script = document.createElement("script");
    script.id = "nx-settings";
    script.type = "application/json";
    script.textContent = JSON.stringify({ ...defaultSettings, sections: { ...defaultSettings.sections, pricing: false } });
    document.head.appendChild(script);

    render(
      <SettingsProvider>
        <Probe />
      </SettingsProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("pricing")).toHaveTextContent("false"));
    document.head.removeChild(script);
  });
});
