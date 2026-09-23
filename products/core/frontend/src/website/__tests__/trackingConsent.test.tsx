import "@testing-library/jest-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useEffect } from "react";
import { cleanup, render, waitFor } from "@testing-library/react";
import { SettingsProvider } from "../lib/settings";
import { ConsentProvider, useConsent } from "../lib/consent";
import { TrackingLoader } from "../components/TrackingLoader";
import { defaultSettings } from "../content/defaults";

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  document.getElementById("nx-ga4")?.remove();
  document.getElementById("nx-plausible")?.remove();
  window.localStorage.clear();
});

function Harness({ decide }: { decide?: "accept" | "reject" }) {
  const { accept, reject } = useConsent();
  useEffect(() => {
    if (decide === "accept") accept();
    if (decide === "reject") reject();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <TrackingLoader />;
}

function renderWithSettings(settingsOverride: typeof defaultSettings, decide?: "accept" | "reject") {
  const script = document.createElement("script");
  script.id = "nx-settings";
  script.type = "application/json";
  script.textContent = JSON.stringify(settingsOverride);
  document.head.appendChild(script);
  render(
    <SettingsProvider>
      <ConsentProvider>
        <Harness decide={decide} />
      </ConsentProvider>
    </SettingsProvider>,
  );
  return () => document.head.removeChild(script);
}

describe("TrackingLoader — contract D8: id configured AND consent granted", () => {
  it("loads nothing when no tracking ids are configured, even after consent", async () => {
    const cleanup1 = renderWithSettings(defaultSettings, "accept");
    await new Promise((r) => setTimeout(r, 10));
    expect(document.getElementById("nx-ga4")).toBeNull();
    expect(document.getElementById("nx-plausible")).toBeNull();
    cleanup1();
  });

  it("does NOT load GA4 when an id is configured but consent was rejected", async () => {
    const settings = { ...defaultSettings, tracking: { ...defaultSettings.tracking, ga4_id: "G-TEST123" } };
    const cleanup1 = renderWithSettings(settings, "reject");
    await new Promise((r) => setTimeout(r, 10));
    expect(document.getElementById("nx-ga4")).toBeNull();
    cleanup1();
  });

  it("loads GA4 only when an id IS configured AND measurement consent is granted", async () => {
    const settings = { ...defaultSettings, tracking: { ...defaultSettings.tracking, ga4_id: "G-TEST123" } };
    const cleanup1 = renderWithSettings(settings, "accept");
    await waitFor(() => expect(document.getElementById("nx-ga4")).not.toBeNull());
    cleanup1();
  });
});
