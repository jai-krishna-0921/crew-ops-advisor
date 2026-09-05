// @vitest-environment node
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { describe, expect, it } from "vitest";

interface Capture {
  port: { onmessage: (message: { data: { enabled: boolean } }) => void };
  process: (inputs: Float32Array[][]) => void;
}

describe("microphone worklet", () => {
  it.each([16000, 44100, 48000])("normalizes %i Hz and discards gated audio", (rate) => {
    const messages: { pcm: Int16Array; rms: number }[] = [];
    let Constructor!: new () => Capture;
    runInNewContext(readFileSync("public/voice-capture.js", "utf8"), {
      sampleRate: rate,
      AudioWorkletProcessor: class { port = { postMessage: (frame: typeof messages[number]) => messages.push(frame) }; },
      registerProcessor: (_name: string, value: typeof Constructor) => { Constructor = value; },
    });
    const capture = new Constructor();
    const input = new Float32Array(rate).fill(0.25);
    capture.process([[input]]);
    expect(messages).toHaveLength(0);
    capture.port.onmessage({ data: { enabled: true } });
    for (let offset = 0; offset < input.length; offset += 128) capture.process([[input.slice(offset, offset + 128)]]);
    expect(messages).toHaveLength(10);
    expect(messages[0].pcm.length).toBe(1600);
    expect(messages[0].pcm[0]).toBe(8192);
    expect(messages[0].rms).toBeCloseTo(0.25);
    capture.port.onmessage({ data: { enabled: false } });
    capture.process([[input]]);
    expect(messages).toHaveLength(10);
  });
});
