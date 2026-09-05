"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import type { Conversation } from "@/lib/use-conversation";
import { VoiceController } from "./controller";
import { connectVoice, createVoiceAudio, voiceStatus } from "./browser";
import type { VoiceProvider, VoiceStatus } from "./types";

export function useVoice(conversation: Conversation) {
  const [controller] = useState(() => new VoiceController({
    ask: conversation.ask, audio: createVoiceAudio, connect: connectVoice,
  }));
  useEffect(() => { controller.setAsk(conversation.ask); }, [controller, conversation.ask]);
  const state = useSyncExternalStore(controller.subscribe, controller.snapshot, controller.snapshot);
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [statusError, setStatusError] = useState(false);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const abort = new AbortController();
    let saved: string | null = null;
    try { saved = localStorage.getItem("crewops.voice.provider.v1"); } catch { /* Optional preference. */ }
    void voiceStatus(abort.signal).then((value) => {
      setStatus(value); setStatusError(false);
      if (controller.snapshot().phase === "off") {
        const selection = ["sarvam", "gemini"].includes(saved ?? "")
          ? saved as VoiceProvider : value.default_provider;
        controller.selectProvider(selection);
      }
    }).catch(() => { if (!abort.signal.aborted) setStatusError(true); });
    return () => abort.abort();
  }, [controller, refresh]);

  useEffect(() => {
    for (const turn of conversation.turns) {
      if (turn.reply || turn.error || turn.done) {
        controller.settle(turn.localId, turn.reply, turn.error?.message);
      }
    }
  }, [conversation.turns, controller]);

  useEffect(() => {
    const hidden = () => { if (document.hidden) controller.end(); };
    document.addEventListener("visibilitychange", hidden);
    return () => { document.removeEventListener("visibilitychange", hidden); controller.end(); };
  }, [controller]);

  const selectProvider = (provider: VoiceProvider) => {
    controller.selectProvider(provider);
    try { localStorage.setItem("crewops.voice.provider.v1", provider); } catch { /* Optional preference. */ }
  };
  return { controller, state, status, statusError, selectProvider,
    refreshStatus: () => setRefresh((value) => value + 1) };
}
