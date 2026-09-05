"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import type { Conversation } from "@/lib/use-conversation";
import { VoiceController } from "./controller";
import { connectVoice, createVoiceAudio, voiceStatus } from "./browser";
import type { VoiceStatus } from "./types";

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
    void voiceStatus(abort.signal).then((value) => {
      setStatus(value); setStatusError(false);
      if (controller.snapshot().phase === "off") {
        controller.selectProvider(value.default_provider);
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

  return { controller, state, status, statusError,
    refreshStatus: () => setRefresh((value) => value + 1) };
}
