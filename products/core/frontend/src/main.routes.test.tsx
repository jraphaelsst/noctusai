/**
 * Core route topology (phase P0 of the core.noctusai.com retirement):
 * `/painel` renders the dashboard, `/` stays as an alias until P3, and an
 * unauthenticated visitor lands on `/login` (the website owns `/` on the
 * shared host). Landing stays routed until P3.
 */
import { describe, it, expect, vi, beforeAll } from "vitest";

const captured: { config?: any } = {};

vi.mock("@noctusai/seed", () => ({
  createProductApp: (config: unknown) => {
    captured.config = config;
    return () => null;
  },
}));
vi.mock("react-dom/client", () => ({
  default: { createRoot: () => ({ render: () => undefined }) },
}));
vi.mock("./lib/seed-auth-adapter", () => ({ coreAuthProvider: {} }));
vi.mock("./components/layout/CoreLayout", () => ({ CoreLayout: () => null }));
vi.mock("./components/NotificationBell", () => ({ notificationHooks: {}, openInProduct: () => undefined }));
vi.mock("./index.css", () => ({}));

beforeAll(async () => {
  document.body.innerHTML = '<div id="root"></div>';
  await import("./main");
});

const route = (path: string) => captured.config.routes.find((r: { path: string }) => r.path === path);

describe("core routes", () => {
  it("mounts the dashboard at /painel", () => {
    expect(route("/painel")).toBeDefined();
  });

  it("keeps / as an alias of the same dashboard component", () => {
    expect(route("/").component).toBe(route("/painel").component);
  });

  it("sends unauthenticated visitors to /login", () => {
    expect(captured.config.unauthRedirect).toBe("/login");
  });

  it("keeps Landing wired until P3", () => {
    expect(captured.config.Landing).toBeDefined();
  });
});
