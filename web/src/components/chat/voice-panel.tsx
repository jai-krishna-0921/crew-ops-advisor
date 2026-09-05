"use client";

import { useEffect, useRef } from "react";
import { ArrowUpIcon, MicrophoneIcon, MicrophoneSlashIcon, WaveformIcon, XIcon, HandPalmIcon } from "@phosphor-icons/react/dist/ssr";
import type { VoiceController } from "@/lib/voice/controller";
import type { VoicePhase, VoiceState, VoiceStatus } from "@/lib/voice/types";
import { cx } from "@/components/ui/tone";

const LABELS: Record<VoicePhase, string> = {
  off: "Talk to your advisor", preparing: "Preparing voice", listening: "Listening",
  transcribing: "Transcribing", thinking: "Thinking", speaking: "Speaking", muted: "Microphone muted", error: "Voice paused",
};
const HINTS: Record<VoicePhase, string> = {
  off: "Speak naturally. Keep the conversation going.", preparing: "Getting your voice ready…",
  listening: "I'm listening. Pause when you're ready to send.", transcribing: "Turning your words into a question…",
  thinking: "Your advisor is working on the answer…", speaking: "Tap interrupt when you want to speak.",
  muted: "Unmute whenever you're ready to continue.", error: "You can retry or keep typing.",
};

export function VoicePanel({ controller, state, status, statusError, onRefresh, disabled }: {
  controller: VoiceController; state: VoiceState; status: VoiceStatus | null;
  statusError: boolean; onRefresh: () => void; disabled: boolean;
}) {
  const expanded = state.phase !== "off";
  const selected = status?.providers.find((provider) => provider.id === state.provider);
  const missing = selected && !selected.configured;
  const inactive = state.phase === "off" || state.phase === "error";
  return (
    <section aria-label="Voice conversation" className={cx("voice-panel voice-panel-inline overflow-hidden", expanded && "voice-panel-expanded")}>
      <div className="flex flex-wrap items-center gap-2 px-3.5 py-2.5">
        <WaveformIcon size={18} weight="bold" aria-hidden className="text-accent" />
        <span role="status" aria-live="polite" className="text-base font-semibold text-ink">{LABELS[state.phase]}</span>
        <div className="ml-auto flex items-center gap-2">
          {inactive ? (
            <button type="button" disabled={disabled} onClick={() => { onRefresh(); void controller.start(); }}
              aria-label={state.phase === "error" ? "Retry voice conversation" : "Start voice conversation"}
              className="voice-start inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold disabled:opacity-40">
              <MicrophoneIcon size={13} weight="fill" aria-hidden />{state.phase === "error" ? "Retry" : "Start"}
            </button>
          ) : (
            <button type="button" onClick={controller.end} aria-label="End voice conversation"
              className="inline-flex size-7 items-center justify-center rounded-full text-ink-2 hover:bg-hover">
              <XIcon size={14} weight="bold" aria-hidden />
            </button>
          )}
        </div>
      </div>
      {expanded ? <>
        <Spectrum controller={controller} phase={state.phase} />
        <div className="voice-inline-details px-3 pb-2">
          {state.error ? <p role="alert" className="mb-2 text-base text-breach">{state.error}</p> : null}
          <p className="min-h-5 min-w-0 flex-1 truncate text-left text-sm text-ink-2" title={state.transcript || undefined}>
            {state.transcript || HINTS[state.phase]}
          </p>
          {!inactive ? <div className="flex shrink-0 justify-end gap-1.5">
            {state.handsFree ? <button type="button" onClick={controller.toggleMute} aria-pressed={state.muted}
              aria-label={state.muted ? "Unmute microphone" : "Mute microphone"}
              className="voice-control">
              {state.muted ? <MicrophoneSlashIcon size={15} aria-hidden /> : <MicrophoneIcon size={15} aria-hidden />}
              {state.muted ? "Unmute" : "Mute"}
            </button> : null}
            {state.phase === "listening" ? <button type="button" onClick={controller.finish} className="voice-control">
              <ArrowUpIcon size={14} weight="bold" aria-hidden />Send now
            </button> : null}
            {state.speakingTurn ? <button type="button" onClick={controller.interrupt} className="voice-control voice-interrupt">
              <HandPalmIcon size={15} weight="fill" aria-hidden />Interrupt
            </button> : null}
            <button type="button" onClick={controller.end} className="voice-control">End</button>
          </div> : null}
        </div>
      </> : null}
      {missing ? <p className="px-4 pb-2 text-xs text-ink-2">Set {state.provider === "sarvam" ? "SARVAM_API_KEY" : "GEMINI_API_KEY"} on the server to connect.</p> : null}
      {statusError && inactive ? <button type="button" onClick={onRefresh} className="px-4 pb-2 text-xs text-ink-2 underline">Refresh voice availability</button> : null}
    </section>
  );
}

function Spectrum({ controller, phase }: { controller: VoiceController; phase: VoicePhase }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const node = canvas.current;
    const context = node?.getContext("2d");
    if (!node || !context) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let animation = 0;
    let previous = 0;
    const heights = new Float32Array(48).fill(3);
    const draw = (time: number) => {
      animation = requestAnimationFrame(draw);
      if (time - previous < (reduced.matches ? 250 : 32)) return;
      previous = time;
      const width = node.clientWidth;
      const height = node.clientHeight;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      if (node.width !== width * ratio || node.height !== height * ratio) {
        node.width = width * ratio; node.height = height * ratio;
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      const live = phase === "listening" || phase === "speaking";
      const bins = live ? controller.spectrum() : new Uint8Array(48);
      const processing = ["preparing", "thinking", "transcribing"].includes(phase);
      const gradient = context.createLinearGradient(0, 0, width, 0);
      gradient.addColorStop(0, "#9caed3"); gradient.addColorStop(0.5, "#3453a0"); gradient.addColorStop(1, "#7399b0");
      context.fillStyle = gradient;
      const step = (width - 32) / 48;
      for (let i = 0; i < 48; i++) {
        const index = Math.floor(Math.abs(i - 23.5) / 24 * Math.min(bins.length - 1, 72));
        const energy = bins[index] / 255;
        const target = live ? 3 + energy * (height - 12) : 3;
        heights[i] += (target - heights[i]) * 0.28;
        const pulse = processing && !reduced.matches ? 0.55 + Math.sin(time / 500 + i / 6) * 0.25 : 0.8;
        context.globalAlpha = pulse;
        const bar = Math.max(3, heights[i]);
        context.beginPath();
        context.roundRect(16 + i * step, (height - bar) / 2, Math.max(2, step - 3), bar, 3);
        context.fill();
      }
      context.globalAlpha = 1;
    };
    animation = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animation);
  }, [controller, phase]);
  return <canvas ref={canvas} aria-hidden="true" className="voice-inline-spectrum block h-8 w-full" />;
}
