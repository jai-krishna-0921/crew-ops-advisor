import { describe, expect, it, vi } from "vitest";
import type { Reply } from "@/lib/contracts";
import { VoiceController } from "./controller";
import type { VoiceAudio, VoiceEvent } from "./types";

const reply = { text: "C-1042 is at BLR.", verification: { status: "verified" },
  caveats: [], headline: null, abstention: null } as unknown as Reply;

function setup() {
  let receive: (event: VoiceEvent) => void = () => {};
  let frame: (pcm: Int16Array, rms: number) => void = () => {};
  const send = vi.fn();
  const close = vi.fn();
  const audio: VoiceAudio = { capture: vi.fn(), play: vi.fn(), drain: vi.fn(async () => {}),
    stop: vi.fn(), close: vi.fn(), spectrum: vi.fn(() => new Uint8Array(48)) };
  const ask = vi.fn(() => "turn-1");
  const controller = new VoiceController({ ask,
    audio: async (_capture, onFrame) => { frame = onFrame; return audio; },
    connect: async (_provider, onEvent) => { receive = onEvent; return { send, close }; },
  });
  return { controller, audio, ask, send, close,
    receive: (event: VoiceEvent) => receive(event),
    frame: (rms: number) => frame(new Int16Array(1600), rms),
  };
}

describe("voice conversation lifecycle", () => {
  it("waits for speech, sends one final transcript, and resumes after playback", async () => {
    const s = setup();
    await s.controller.start();
    for (let i = 0; i < 30; i++) s.frame(0);
    expect(s.send).not.toHaveBeenCalled();
    for (let i = 0; i < 5; i++) s.frame(0.15);
    for (let i = 0; i < 13; i++) s.frame(0);
    const id = s.send.mock.calls.find(([c]) => c.type === "listen")![0].request_id;
    expect(s.controller.snapshot().phase).toBe("transcribing");
    s.receive({ type: "partial", request_id: id, text: "Who is" });
    expect(s.ask).not.toHaveBeenCalled();
    s.receive({ type: "final", request_id: id, text: "Who is at BLR?" });
    s.receive({ type: "final", request_id: id, text: "Who is at BLR?" });
    expect(s.ask).toHaveBeenCalledTimes(1);
    s.controller.settle("turn-1", reply);
    const speech = s.send.mock.calls.find(([c]) => c.type === "speak")![0];
    s.receive({ type: "audio", request_id: speech.request_id, data: "AAA=", sample_rate: 24000 });
    s.receive({ type: "complete", request_id: speech.request_id });
    await vi.waitFor(() => expect(s.controller.snapshot().phase).toBe("listening"));
    expect(s.audio.play).toHaveBeenCalledOnce();
  });

  it("ignores empty and stale transcripts after ending or changing providers", async () => {
    const s = setup();
    await s.controller.start();
    for (let i = 0; i < 4; i++) s.frame(0.1);
    const id = s.send.mock.calls[0][0].request_id;
    s.controller.selectProvider("sarvam");
    s.receive({ type: "final", request_id: id, text: "stale question" });
    expect(s.ask).not.toHaveBeenCalled();
    expect(s.close).toHaveBeenCalled();
    expect(s.audio.close).toHaveBeenCalled();
    expect(s.controller.snapshot().provider).toBe("sarvam");
  });

  it("interrupts speech without replaying a late completion", async () => {
    const s = setup();
    await s.controller.start();
    s.controller.submit("Who is at BLR?");
    s.controller.settle("turn-1", reply);
    const id = s.send.mock.calls.find(([c]) => c.type === "speak")![0].request_id;
    s.controller.interrupt();
    s.receive({ type: "audio", request_id: id, data: "AAA=", sample_rate: 24000 });
    expect(s.audio.play).not.toHaveBeenCalled();
    expect(s.controller.snapshot().phase).toBe("listening");
  });

  it("read aloud never requests a microphone and ends after playback", async () => {
    const s = setup();
    await s.controller.read(reply, "old-turn");
    const id = s.send.mock.calls.find(([c]) => c.type === "speak")![0].request_id;
    expect(s.audio.capture).not.toHaveBeenCalledWith(true);
    s.receive({ type: "complete", request_id: id });
    await vi.waitFor(() => expect(s.controller.snapshot().phase).toBe("off"));
  });

  it("keeps mute through completion and releases audio on failures", async () => {
    const s = setup();
    await s.controller.start();
    s.controller.submit("A question");
    s.controller.toggleMute();
    s.controller.settle("turn-1", reply);
    const id = s.send.mock.calls.find(([c]) => c.type === "speak")![0].request_id;
    s.receive({ type: "complete", request_id: id });
    await vi.waitFor(() => expect(s.controller.snapshot().phase).toBe("muted"));
    s.controller.fail("Connection lost");
    expect(s.controller.snapshot().phase).toBe("error");
    expect(s.audio.close).toHaveBeenCalled();
  });

  it("cleans up microphone permission that resolves after cancellation", async () => {
    const s = setup();
    let resolve!: (value: VoiceAudio) => void;
    const pending = new Promise<VoiceAudio>((r) => { resolve = r; });
    const c = new VoiceController({ ask: s.ask, audio: () => pending,
      connect: async () => ({ send: s.send, close: s.close }) });
    const starting = c.start();
    c.end();
    resolve(s.audio);
    await starting;
    expect(s.audio.close).toHaveBeenCalled();
    expect(c.snapshot().phase).toBe("off");
  });

  it("ignores a finalized empty recording and caps continuous speech", async () => {
    const s = setup();
    await s.controller.start();
    for (let i = 0; i < 610; i++) s.frame(0.1);
    const id = s.send.mock.calls[0][0].request_id;
    expect(s.send.mock.calls.filter(([c]) => c.type === "finish")).toHaveLength(1);
    const bytes = s.send.mock.calls.filter(([c]) => c.type === "audio").reduce((n, [c]) => n + atob(c.data).length, 0);
    expect(bytes).toBeLessThanOrEqual(16000 * 2 * 60);
    s.receive({ type: "final", request_id: id, text: "  " });
    expect(s.ask).not.toHaveBeenCalled();
    expect(s.controller.snapshot().phase).toBe("listening");
  });

  it("discards capture while thinking and speaking, and ignores a cancelled drain", async () => {
    const s = setup();
    let resolve!: () => void;
    vi.mocked(s.audio.drain).mockImplementation(() => new Promise<void>((r) => { resolve = r; }));
    await s.controller.start();
    s.controller.submit("Check duty hours");
    for (let i = 0; i < 10; i++) s.frame(0.2);
    s.controller.settle("turn-1", reply);
    const id = s.send.mock.calls.find(([c]) => c.type === "speak")![0].request_id;
    s.receive({ type: "audio", request_id: id, data: "AAA=", sample_rate: 24000 });
    for (let i = 0; i < 10; i++) s.frame(0.2);
    expect(s.send.mock.calls.filter(([c]) => c.type === "listen")).toHaveLength(0);
    s.receive({ type: "complete", request_id: id });
    expect(s.controller.snapshot().phase).toBe("speaking");
    s.controller.end();
    resolve();
    await Promise.resolve();
    expect(s.controller.snapshot().phase).toBe("off");
  });

  it("never speaks rejected prose or a restored answer without a pending voice turn", async () => {
    const s = setup();
    s.controller.settle("old-turn", reply);
    expect(s.send).not.toHaveBeenCalled();
    await s.controller.read({ ...reply, verification: { ...reply.verification, status: "rejected" } }, "bad-turn");
    expect(s.send.mock.calls.filter(([c]) => c.type === "speak")).toHaveLength(0);
    expect(s.controller.snapshot().phase).toBe("error");
  });
});
