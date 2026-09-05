import type { Reply } from "@/lib/contracts";

export type VoiceProvider = "local" | "sarvam" | "gemini";
export type SpeechDetailLevel = "full" | "summary" | "details";
export type VoicePhase = "off" | "preparing" | "listening" | "transcribing" | "thinking" | "speaking" | "muted" | "error";
export interface VoiceState {
  provider: VoiceProvider;
  phase: VoicePhase;
  handsFree: boolean;
  muted: boolean;
  transcript: string;
  error: string | null;
  speakingTurn: string | null;
}
export type SpeechReply = Pick<Reply, "headline" | "text" | "caveats" | "abstention" | "verification">;
export type VoiceCommand =
  | { type: "listen" | "finish" | "cancel"; request_id: string }
  | { type: "audio"; request_id: string; data: string }
  | { type: "speak"; request_id: string; reply: SpeechReply; detail_level?: SpeechDetailLevel };
export type VoiceEvent =
  | { type: "ready"; provider: VoiceProvider }
  | { type: "partial" | "final"; request_id: string; text: string }
  | { type: "audio"; request_id: string; data: string; sample_rate: number }
  | { type: "complete"; request_id: string; has_more?: boolean }
  | { type: "cancelled"; request_id: string }
  | { type: "error"; request_id: string; message: string };
export interface VoiceStatus {
  default_provider: VoiceProvider;
  providers: { id: VoiceProvider; configured: boolean; connected: boolean | null;
    location: "local" | "cloud"; stt_loaded: boolean | null; tts_loaded: boolean | null }[];
}
export interface VoiceAudio {
  capture: (enabled: boolean) => void;
  play: (data: string, sampleRate: number) => void;
  drain: () => Promise<void>;
  stop: () => void;
  close: () => void;
  spectrum: (speaking: boolean) => Uint8Array;
}
export interface VoiceConnection { send: (command: VoiceCommand) => void; close: () => void }
export interface VoiceDependencies {
  ask: (question: string) => string | null;
  audio: (capture: boolean, frame: (pcm: Int16Array, rms: number) => void, signal?: AbortSignal) => Promise<VoiceAudio>;
  connect: (provider: VoiceProvider, event: (event: VoiceEvent) => void,
    closed: () => void, signal?: AbortSignal) => Promise<VoiceConnection>;
}
