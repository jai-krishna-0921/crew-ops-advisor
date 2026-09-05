import type { Reply } from "@/lib/contracts";
import type { VoiceAudio, VoiceConnection, VoiceDependencies, VoiceEvent, VoiceProvider, VoiceState } from "./types";

export class VoiceController {
  private state: VoiceState = { provider: "sarvam", phase: "off", handsFree: false,
    muted: false, transcript: "", error: null, speakingTurn: null };
  private listeners = new Set<() => void>();
  private generation = 0;
  private abort: AbortController | null = null;
  private audio: VoiceAudio | null = null;
  private connection: VoiceConnection | null = null;
  private request = "";
  private pendingTurn: string | null = null;
  private preRoll: Int16Array[] = [];
  private voiced = 0;
  private silence = 0;
  private samples = 0;

  constructor(private dependencies: VoiceDependencies) {}
  setAsk = (ask: VoiceDependencies["ask"]) => { this.dependencies.ask = ask; };
  snapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private update(patch: Partial<VoiceState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((listener) => listener());
  }

  selectProvider = (provider: VoiceProvider) => {
    if (provider === this.state.provider) return;
    this.end();
    this.update({ provider });
  };

  start = async (handsFree = true) => {
    this.end();
    const gen = this.generation;
    this.abort = new AbortController();
    const signal = this.abort.signal;
    this.update({ phase: "preparing", handsFree, error: null, muted: false });
    try {
      // Both promises clean up their own result if the user cancels while
      // permission or the network is still pending.
      await Promise.all([
        this.dependencies.audio(handsFree, this.frame, signal).then((audio) => {
          if (gen !== this.generation) audio.close(); else this.audio = audio;
        }),
        this.dependencies.connect(this.state.provider, (event) => {
          if (gen === this.generation) this.receive(event);
        }, () => {
          if (gen === this.generation) this.fail("Voice disconnected. Retry or choose another provider.");
        }, signal).then((connection) => {
          if (gen !== this.generation) connection.close(); else this.connection = connection;
        }),
      ]);
      if (gen !== this.generation) return false;
      if (handsFree) this.listen();
      return true;
    } catch (error) {
      if (gen === this.generation) this.fail(error instanceof Error ? error.message : "Voice could not start.");
      return false;
    }
  };

  end = () => {
    this.generation++;
    this.abort?.abort();
    this.abort = null;
    this.request = "";
    this.pendingTurn = null;
    this.connection?.close();
    this.connection = null;
    this.audio?.close();
    this.audio = null;
    this.resetCapture();
    this.update({ phase: "off", handsFree: false, speakingTurn: null, muted: false, transcript: "", error: null });
  };

  fail = (message: string) => { this.end(); this.update({ phase: "error", error: message }); };
  private resetCapture() { this.preRoll = []; this.voiced = 0; this.silence = 0; this.samples = 0; }
  private cancelRequest() {
    if (this.request) this.connection?.send({ type: "cancel", request_id: this.request });
    this.request = "";
    this.audio?.capture(false);
    this.audio?.stop();
    this.resetCapture();
  }

  private listen() {
    this.request = "";
    this.resetCapture();
    this.update({ phase: this.state.muted ? "muted" : "listening", speakingTurn: null, transcript: "" });
    this.audio?.capture(!this.state.muted);
  }

  private frame = (pcm: Int16Array, rms: number) => {
    if (this.state.phase !== "listening" || this.state.muted) return;
    const seconds = pcm.length / 16000;
    if (!this.request) {
      this.preRoll.push(pcm);
      if (this.preRoll.length > 6) this.preRoll.shift();
      this.voiced = rms >= 0.012 ? this.voiced + seconds : 0;
      if (this.voiced < 0.3) return;
      this.request = crypto.randomUUID();
      this.connection?.send({ type: "listen", request_id: this.request });
      for (const previous of this.preRoll) this.sendAudio(previous);
      this.preRoll = [];
    } else this.sendAudio(pcm);
    this.silence = rms < 0.012 ? this.silence + seconds : 0;
    if (this.silence >= 1.2 || this.samples >= 16000 * 59.8) this.finish();
  };

  private sendAudio(pcm: Int16Array) {
    this.samples += pcm.length;
    // Explicit little endian serialization also works on big endian hosts.
    const bytes = new Uint8Array(pcm.length * 2);
    const view = new DataView(bytes.buffer);
    pcm.forEach((value, i) => view.setInt16(i * 2, value, true));
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    this.connection?.send({ type: "audio", request_id: this.request, data: btoa(binary) });
  }

  finish = () => {
    if (!this.request || this.state.phase !== "listening") return;
    this.audio?.capture(false);
    this.update({ phase: "transcribing" });
    this.connection?.send({ type: "finish", request_id: this.request });
  };

  submit = (question: string) => {
    const text = question.trim();
    if (!text) return;
    const speak = this.state.handsFree && this.connection !== null;
    if (speak) this.cancelRequest(); else if (this.connection) this.end();
    const turn = this.dependencies.ask(text);
    if (speak && turn) {
      this.pendingTurn = turn;
      this.update({ phase: "thinking", transcript: text, speakingTurn: null });
    }
  };

  settle = (turnId: string, reply: Reply | null, error?: string) => {
    if (turnId !== this.pendingTurn) return;
    this.pendingTurn = null;
    if (error || !reply) { this.fail(error ?? "The advisor did not return an answer."); return; }
    this.speak(reply, turnId);
  };

  private speak(reply: Reply, turnId: string) {
    if (!this.connection) return;
    this.cancelRequest();
    if (!reply.abstention && !["verified", "repaired"].includes(reply.verification.status)) {
      this.fail("This answer has no verified prose to read aloud."); return;
    }
    this.request = crypto.randomUUID();
    this.update({ phase: "preparing", speakingTurn: turnId });
    const { headline, text, caveats, abstention, verification } = reply;
    this.connection.send({ type: "speak", request_id: this.request,
      reply: { headline, text, caveats, abstention, verification } });
  }

  read = async (reply: Reply, turnId: string) => {
    if (this.state.speakingTurn === turnId) { this.interrupt(); return; }
    if (!this.connection || !this.audio) {
      if (!await this.start(false)) return;
    }
    this.pendingTurn = null;
    this.speak(reply, turnId);
  };

  interrupt = () => {
    this.pendingTurn = null;
    this.cancelRequest();
    if (this.state.handsFree) this.listen(); else this.end();
  };

  toggleMute = () => {
    const muted = !this.state.muted;
    this.update({ muted });
    if (["listening", "muted", "transcribing"].includes(this.state.phase)) {
      this.cancelRequest();
      this.listen();
    }
  };

  spectrum = () => this.audio?.spectrum(this.state.phase === "speaking") ?? new Uint8Array(48);

  private receive(event: VoiceEvent) {
    if (event.type === "ready") return;
    if (event.type === "error" && !event.request_id) { this.fail(event.message); return; }
    if (!this.request || event.request_id !== this.request) return;
    if (event.type === "error") { this.fail(event.message); return; }
    if (event.type === "partial") this.update({ transcript: event.text });
    if (event.type === "final") {
      this.request = "";
      if (event.text.trim()) this.submit(event.text); else this.listen();
    }
    if (event.type === "audio") {
      try { this.audio?.play(event.data, event.sample_rate); this.update({ phase: "speaking" }); }
      catch { this.fail("Audio playback failed. Retry to enable sound."); }
    }
    if (event.type === "complete") {
      const request = this.request;
      const gen = this.generation;
      void this.audio?.drain().then(() => {
        if (gen !== this.generation || request !== this.request) return;
        if (this.state.handsFree) this.listen(); else this.end();
      }).catch(() => { if (gen === this.generation) this.fail("Audio playback was interrupted. Try again."); });
    }
  }
}
