/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";

afterEach(() => {
  cleanup();
});

describe("Popover", () => {
  it("does not render content until opened", () => {
    render(
      <Popover>
        <PopoverTrigger>abrir</PopoverTrigger>
        <PopoverContent>conteúdo do popover</PopoverContent>
      </Popover>,
    );
    expect(screen.queryByText("conteúdo do popover")).not.toBeInTheDocument();
  });

  it("shows content after the trigger is clicked", async () => {
    const user = userEvent.setup();
    render(
      <Popover>
        <PopoverTrigger>abrir</PopoverTrigger>
        <PopoverContent>conteúdo do popover</PopoverContent>
      </Popover>,
    );
    await user.click(screen.getByText("abrir"));
    await waitFor(() => expect(screen.getByText("conteúdo do popover")).toBeInTheDocument());
  });
});
