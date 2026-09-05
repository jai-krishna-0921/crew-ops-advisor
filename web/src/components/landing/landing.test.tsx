import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { Landing } from "./landing";

beforeEach(() => {
  class IntersectionObserverStub {
    observe() {}
    disconnect() {}
  }

  vi.stubGlobal("IntersectionObserver", IntersectionObserverStub);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows six generic capabilities in the three tier ladder", () => {
  render(<Landing />);

  expect(
    screen.getByRole("heading", {
      name: "Lookup → Consequence → Recommendation",
    }),
  ).toBeTruthy();
  expect(screen.getAllByTestId("capability-card")).toHaveLength(6);
  expect(screen.getByText("Simulate a sick call")).toBeTruthy();
  expect(screen.queryByText(/C-1042 calls in sick/)).toBeNull();
});

it("collects task details before handing the question to chat", () => {
  const { container } = render(<Landing />);

  fireEvent.click(
    screen.getByRole("button", { name: /^Simulate a sick call/ }),
  );
  expect(screen.getByRole("dialog", { name: "Simulate a sick call" })).toBeTruthy();

  fireEvent.change(screen.getByLabelText("Crew ID"), {
    target: { value: "C-1042" },
  });
  fireEvent.change(screen.getByLabelText("Date"), {
    target: { value: "2026-09-15" },
  });

  const question = container.querySelector<HTMLInputElement>(
    'input[name="q"]',
  );
  expect(question?.value).toBe(
    "C-1042 calls in sick on 2026-09-15. Which flights are immediately uncrewed?",
  );
  expect(
    screen.getByRole<HTMLButtonElement>("button", {
      name: "Continue to chat",
    }).disabled,
  ).toBe(false);
});

it("toggles the hero answer between lookup and recommendation output", () => {
  render(<Landing />);

  expect(screen.getByText("How much duty headroom does C-1042 have?")).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "Recommendation" }));

  expect(screen.getByText("Ranked legal options")).toBeTruthy();
  expect(screen.getByText("INR 18,500")).toBeTruthy();
  expect(screen.getAllByText("Legal").length).toBeGreaterThan(0);
});
