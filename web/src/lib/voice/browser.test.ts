import { afterEach, describe, expect, it, vi } from "vitest";
import { connectVoice, createVoiceAudio } from "./browser";

class Socket {
  static OPEN = 1;
  static latest: Socket;
  readyState = 1;
  bufferedAmount = 0;
  onmessage?: (message: { data: string }) => void;
  onclose?: () => void;
  close = vi.fn(() => this.onclose?.());
  send = vi.fn();
  constructor() { Socket.latest = this; }
}

afterEach(() => vi.unstubAllGlobals());

describe("browser transport", () => {
  it("reports malformed responses after a successful connection", async () => {
    vi.stubGlobal("WebSocket", Socket);
    const closed = vi.fn();
    const pending = connectVoice("local", vi.fn(), closed);
    Socket.latest.onmessage?.({ data: '{"type":"ready","provider":"local"}' });
    await pending;
    Socket.latest.onmessage?.({ data: "invalid" });
    expect(closed).toHaveBeenCalledOnce();
  });

  it("closes a pending connection on cancellation", async () => {
    vi.stubGlobal("WebSocket", Socket);
    const abort = new AbortController();
    const pending = connectVoice("gemini", vi.fn(), vi.fn(), abort.signal);
    abort.abort();
    await expect(pending).rejects.toThrow("Voice cancelled");
    expect(Socket.latest.close).toHaveBeenCalledOnce();
  });

  it("read aloud schedules PCM at 24 kHz, drains, and releases audio without a microphone", async () => {
    const nodes: { onended: (() => void) | null; start: ReturnType<typeof vi.fn>; stop: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn> }[] = [];
    const close = vi.fn();
    const createBuffer = vi.fn((_channels: number, size: number, rate: number) => ({
      duration: size / rate, getChannelData: () => new Float32Array(size),
    }));
    class Context {
      state = "running";
      currentTime = 1;
      destination = {};
      resume = vi.fn(async () => {});
      close = close;
      createBuffer = createBuffer;
      createAnalyser = () => ({ connect: vi.fn(), disconnect: vi.fn(), frequencyBinCount: 128, getByteFrequencyData: vi.fn() });
      createBufferSource = () => {
        const node = { onended: null, start: vi.fn(), stop: vi.fn(), disconnect: vi.fn(), connect: vi.fn() };
        nodes.push(node);
        return node;
      };
    }
    vi.stubGlobal("isSecureContext", true);
    vi.stubGlobal("AudioContext", Context);
    const audio = await createVoiceAudio(false, vi.fn());
    audio.play("AQABAA==", 24000);
    audio.play("AQABAA==", 24000);
    expect(createBuffer).toHaveBeenCalledWith(1, 2, 24000);
    expect(nodes[1].start.mock.calls[0][0]).toBeGreaterThan(nodes[0].start.mock.calls[0][0]);
    const drained = vi.fn();
    void audio.drain().then(drained);
    await Promise.resolve();
    expect(drained).not.toHaveBeenCalled();
    audio.stop();
    await Promise.resolve();
    expect(drained).toHaveBeenCalledOnce();
    expect(nodes[0].stop).toHaveBeenCalledOnce();
    audio.close(); audio.close();
    expect(close).toHaveBeenCalledOnce();
  });
});
