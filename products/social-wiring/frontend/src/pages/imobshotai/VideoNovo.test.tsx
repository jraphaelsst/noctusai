import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import VideoNovo from "./VideoNovo";

afterEach(cleanup);

describe("ImobShotAI video placeholder", () => {
  it("says video is coming and links back to the board", () => {
    render(
      <MemoryRouter>
        <VideoNovo />
      </MemoryRouter>,
    );
    expect(screen.getByText("Vídeo em breve")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voltar ao quadro" })).toHaveAttribute("href", "/imobshotai");
  });
});
