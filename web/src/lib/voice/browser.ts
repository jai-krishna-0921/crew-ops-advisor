import { API_BASE } from "@/lib/api";
import type { VoiceAudio, VoiceConnection, VoiceEvent, VoiceProvider, VoiceStatus } from "./types";

export async function voiceStatus(signal?: AbortSignal): Promise<VoiceStatus> {
  const response = await fetch(`${API_BASE}/api/voice/status`, { signal });
  if (!response.ok) throw new Error("Voice settings could not be loaded.");
  return response.json();
}

export function connectVoice(provider: VoiceProvider, event: (event: VoiceEvent) => void,
  closed: () => void, signal?: AbortSignal): Promise<VoiceConnection> {
  return new Promise((resolve, reject) => {
    const url = new URL(`${API_BASE}/api/voice/session`);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    url.searchParams.set("provider", provider);
    const socket = new WebSocket(url);
    let ready = false;
    let intentional = false;
    const timer = setTimeout(() => {
      close(); reject(new Error("Voice connection timed out. Check voice configuration and try again."));
    }, 15000);
    const close = () => { intentional = true; clearTimeout(timer); socket.close(); };
    const abort = () => { close(); reject(new DOMException("Voice cancelled", "AbortError")); };
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) { abort(); return; }
    socket.onmessage = ({ data }) => {
      try {
        const message = JSON.parse(data) as VoiceEvent;
        if (message.type === "ready") {
          clearTimeout(timer);
          ready = true;
          resolve({ close, send: (command) => {
            if (socket.readyState !== WebSocket.OPEN) { closed(); return; }
            if (socket.bufferedAmount > 2_000_000) { close(); closed(); return; }
            socket.send(JSON.stringify(command));
          } });
        } else if (!ready && message.type === "error") {
          close(); reject(new Error(message.message));
        } else event(message);
      } catch {
        close();
        if (ready) closed();
        else reject(new Error("The voice service returned an invalid response."));
      }
    };
    socket.onerror = () => {
      if (!ready) { close(); reject(new Error("Could not reach the voice service. Check the server and retry.")); }
    };
    socket.onclose = () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      if (!intentional) {
        if (ready) closed(); else reject(new Error("Voice connection closed. Check configuration and retry."));
      }
    };
  });
}

export async function createVoiceAudio(capture: boolean,
  onFrame: (pcm: Int16Array, rms: number) => void, signal?: AbortSignal): Promise<VoiceAudio> {
  if (!window.isSecureContext || !window.AudioContext || (capture && !navigator.mediaDevices?.getUserMedia)) {
    throw new Error("Voice needs a supported browser on localhost or HTTPS.");
  }
  const context = new AudioContext();
  let stream: MediaStream | null = null;
  let worklet: AudioWorkletNode | null = null;
  let source: MediaStreamAudioSourceNode | null = null;
  let mute: GainNode | null = null;
  const input = context.createAnalyser();
  const output = context.createAnalyser();
  input.fftSize = output.fftSize = 256;
  output.connect(context.destination);
  const sources = new Set<AudioBufferSourceNode>();
  const waiters = new Set<() => void>();
  let next = 0;
  let ended = false;
  const resolveDrains = () => {
    if (sources.size === 0) { waiters.forEach((resolve) => resolve()); waiters.clear(); }
  };
  const stop = () => {
    for (const node of sources) { node.onended = null; node.stop(); node.disconnect(); }
    sources.clear(); next = 0; resolveDrains();
  };
  const close = () => {
    if (ended) return;
    ended = true;
    stop();
    stream?.getTracks().forEach((track) => track.stop());
    worklet?.disconnect();
    source?.disconnect();
    mute?.disconnect();
    input.disconnect(); output.disconnect();
    signal?.removeEventListener("abort", close);
    void context.close();
  };
  signal?.addEventListener("abort", close, { once: true });
  try {
    await context.resume();
    if (capture) {
      if (!context.audioWorklet) throw new Error("This browser does not support voice recording.");
      stream = await navigator.mediaDevices.getUserMedia({ audio: {
        channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      } });
      if (ended || signal?.aborted) {
        stream.getTracks().forEach((track) => track.stop());
        throw new DOMException("Voice cancelled", "AbortError");
      }
      stream.getAudioTracks().forEach((track) => { track.enabled = false; });
      await context.audioWorklet.addModule("/voice-capture.js");
      if (ended) throw new DOMException("Voice cancelled", "AbortError");
      source = context.createMediaStreamSource(stream);
      worklet = new AudioWorkletNode(context, "voice-capture");
      mute = context.createGain(); mute.gain.value = 0;
      source.connect(input);
      source.connect(worklet).connect(mute).connect(context.destination);
      worklet.port.onmessage = ({ data }) => { if (!ended) onFrame(data.pcm, data.rms); };
    }
    if (ended || signal?.aborted) throw new DOMException("Voice cancelled", "AbortError");
    return {
      capture(enabled) {
        if (ended) return;
        stream?.getAudioTracks().forEach((track) => { track.enabled = enabled; });
        worklet?.port.postMessage({ enabled });
      },
      play(data, sampleRate) {
        if (ended || context.state !== "running") throw new Error("Audio playback is suspended.");
        if (sampleRate !== 24000) throw new Error("Unsupported playback format.");
        const binary = atob(data);
        if (binary.length % 2) throw new Error("Incomplete audio sample.");
        const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
        const view = new DataView(bytes.buffer);
        const buffer = context.createBuffer(1, bytes.length / 2, sampleRate);
        const samples = buffer.getChannelData(0);
        for (let i = 0; i < samples.length; i++) samples[i] = view.getInt16(i * 2, true) / 32768;
        const node = context.createBufferSource();
        node.buffer = buffer;
        node.connect(output);
        sources.add(node);
        node.onended = () => { sources.delete(node); node.disconnect(); resolveDrains(); };
        next = Math.max(context.currentTime + 0.04, next);
        node.start(next); next += buffer.duration;
      },
      drain: () => sources.size ? new Promise<void>((resolve) => waiters.add(resolve)) : Promise.resolve(),
      stop, close,
      spectrum(speaking) {
        const analyser = speaking ? output : input;
        const bins = new Uint8Array(analyser.frequencyBinCount);
        if (!ended) analyser.getByteFrequencyData(bins);
        return bins;
      },
    };
  } catch (error) {
    close();
    if (error instanceof DOMException && error.name === "NotAllowedError") {
      throw new Error("Microphone access was denied. Allow it in browser settings and retry.");
    }
    if (error instanceof DOMException && ["NotFoundError", "NotReadableError"].includes(error.name)) {
      throw new Error("No microphone is available. Connect one or close the app using it, then retry.");
    }
    throw error;
  }
}
