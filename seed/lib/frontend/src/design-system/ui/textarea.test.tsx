/// <reference types="@testing-library/jest-dom" />
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Textarea } from "./textarea";

afterEach(() => {
  cleanup();
});

describe("Textarea", () => {
  it("renders SW's classes (min-h-[80px], text-base md:text-sm)", () => {
    render(<Textarea aria-label="descricao" />);
    const el = screen.getByRole("textbox", { name: "descricao" });
    expect(el).toHaveClass("min-h-[80px]", "text-base", "md:text-sm");
  });

  it("forwards typed input", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Textarea aria-label="descricao" onChange={onChange} />);
    await user.type(screen.getByRole("textbox", { name: "descricao" }), "oi");
    expect(onChange).toHaveBeenCalled();
  });

  it("merges a custom className", () => {
    render(<Textarea aria-label="descricao" className="custom-class" />);
    expect(screen.getByRole("textbox", { name: "descricao" })).toHaveClass("custom-class");
  });
});
