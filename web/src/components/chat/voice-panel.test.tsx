import { fireEvent, render, screen, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { VoicePanel } from "./voice-panel";
import { VoiceController } from "@/lib/voice/controller";

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("offers one provider selector and usable start control", () => {
  const controller = new VoiceController({ ask: () => null,
    audio: vi.fn(), connect: vi.fn() });
  const select = vi.fn();
  const start = vi.spyOn(controller, "start").mockResolvedValue(true);
  render(<VoicePanel controller={controller} state={controller.snapshot()} status={null}
    statusError={false} onRefresh={vi.fn()} onProvider={select} disabled={false} />);
  fireEvent.change(screen.getByRole("combobox", { name: "Voice provider" }), { target: { value: "gemini" } });
  expect(select).toHaveBeenCalledWith("gemini");
  fireEvent.click(screen.getByRole("button", { name: "Start voice conversation" }));
  expect(start).toHaveBeenCalled();
});

it("announces errors and allows retry or closing the panel", () => {
  const controller = new VoiceController({ ask: () => null, audio: vi.fn(), connect: vi.fn() });
  controller.fail("Microphone access was denied.");
  render(<VoicePanel controller={controller} state={controller.snapshot()} status={null}
    statusError={false} onRefresh={vi.fn()} onProvider={vi.fn()} disabled={false} />);
  expect(screen.getByRole("alert").textContent).toContain("Microphone access was denied");
  expect(screen.getByRole("button", { name: "Retry voice conversation" })).toBeTruthy();
});
