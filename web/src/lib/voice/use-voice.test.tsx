import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { Conversation } from "@/lib/use-conversation";
import { useVoice } from "./use-voice";

const audio = vi.hoisted(() => ({ capture: vi.fn(), close: vi.fn(), stop: vi.fn(), play: vi.fn(),
  drain: vi.fn(async () => {}), spectrum: () => new Uint8Array(48) }));
const close = vi.hoisted(() => vi.fn());
vi.mock("./browser", () => ({
  createVoiceAudio: async () => audio,
  connectVoice: async () => ({ send: vi.fn(), close }),
  voiceStatus: async () => ({ default_provider: "local", providers: [] }),
}));

afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

it("ends voice when the tab hides and on unmount without replaying history", async () => {
  const conversation = { ask: vi.fn(() => "turn-1"), turns: [] } as unknown as Conversation;
  const hook = renderHook(() => useVoice(conversation));
  await waitFor(() => expect(hook.result.current.status).not.toBeNull());
  await act(async () => { await hook.result.current.controller.start(); });
  expect(hook.result.current.state.phase).toBe("listening");
  vi.spyOn(document, "hidden", "get").mockReturnValue(true);
  act(() => { document.dispatchEvent(new Event("visibilitychange")); });
  expect(hook.result.current.state.phase).toBe("off");
  expect(close).toHaveBeenCalled();
  expect(audio.close).toHaveBeenCalled();
  expect(conversation.ask).not.toHaveBeenCalled();
  await act(async () => { await hook.result.current.controller.start(); });
  const before = audio.close.mock.calls.length;
  hook.unmount();
  expect(audio.close.mock.calls.length).toBeGreaterThan(before);
});
