# Voice conversation

Open `/ask` and press Start or the microphone button. The server-configured
default provider is used automatically. Speak normally and pause to send. The advisor reads
the answer summary, then listens for your response in the same thread.
The spectrum follows microphone input and playback. Partial cloud transcripts
are previews; only the finalized utterance is sent as a question.

In hands-free mode, the advisor reads the verified headline first and asks if
you want more information. Say yes, continue, or ask for details to hear the
remaining verified prose and caveats. Say no to skip it, or ask another question
to move on immediately. The existing Read aloud control still reads the full
answer because it does not request microphone access.

Mute pauses the microphone. Interrupt stops playback and resumes listening.
End releases the microphone and connection. Switching providers or conversations,
leaving the page, or hiding the tab also ends voice. A submitted answer can still
finish in text. Read aloud on an existing answer works without microphone access.

## Cloud setup

Put either or both keys in the repository `.env.local`, then restart the API:

```dotenv
SARVAM_API_KEY=your-sarvam-key
GEMINI_API_KEY=your-gemini-key
CREWOPS_VOICE_PROVIDER=sarvam
```

`CREWOPS_VOICE_PROVIDER` accepts `sarvam` or `gemini`; the default is `sarvam`.
Each session uses the configured provider for both transcription and speech. There is no automatic provider
fallback. Cloud providers work without installing or running VoiceKit.

Keys stay on the server. No key is placed in `NEXT_PUBLIC_*`, browser storage,
status responses, or voice error messages. These keys do not change the
reasoning provider. Status distinguishes configured credentials from successful
connectivity; provider authentication/model access is checked on actual use.

| Setting | Default |
|---|---|
| `CREWOPS_SARVAM_STT_MODEL` | `saaras:v3-realtime` |
| `CREWOPS_SARVAM_TTS_MODEL` | `bulbul:v3` |
| `CREWOPS_SARVAM_VOICE` | `shubh` |
| `CREWOPS_GEMINI_STT_MODEL` | `gemini-3.5-transcribe-live` |
| `CREWOPS_GEMINI_TTS_MODEL` | `gemini-3.1-flash-tts-preview` |
| `CREWOPS_GEMINI_VOICE` | `Kore` |

Gemini uses dedicated Live transcription plus text recitation, rather than
letting a native speech conversation compose operational answers. Account model
availability and preview API behavior can vary. An unavailable model or rejected
key produces a visible error; choose another configured provider to continue.

## Local VoiceKit (disabled for hosting)

The legacy sibling `../voice` project uses Python 3.10 through 3.12 in its own `.venv`.
The advisor can keep using Python 3.13. Override `VOICE_DIR` or `VOICE_PYTHON`
when needed. On macOS, install `espeak-ng` for Kokoro first.

```bash
make install-voice                 # reuses an existing voice environment
make voice-download                # fetch Whisper and Kokoro before offline use
make dev-voice                     # web :3000, advisor :8000, voice :8001
```

When web and API are already running, use `make voice` alone. The launcher loads
the repository `.env.local` and `.env` using the same precedence as the advisor.

```dotenv
CREWOPS_VOICE_LOCAL_URL=http://127.0.0.1:8001
CREWOPS_VOICE_LOCAL_VOICE=af_heart
# Optional, applied to both VoiceKit and the advisor's outgoing requests:
CREWOPS_VOICE_LOCAL_KEY=your-local-token
# After downloading the models:
VOICE_OFFLINE=true
```

Whisper defaults to the balanced profile. VoiceKit's `VOICE_STT_PROFILE`,
`VOICE_MODEL_CACHE`, and other settings remain available. The first inference
loads model weights and takes longer than a warm turn. Text chat works while
the voice service is unavailable.

## Transport and grounding

`GET /api/voice/status` returns the default provider and public cloud-provider
configuration. The legacy local provider is not advertised there.

`WS /api/voice/session?provider=sarvam|gemini` fixes the provider for that
connection. After `ready`, send JSON commands with a unique `request_id`:

* `listen`: start one utterance.
* `audio`: base64 mono signed PCM16, little endian, 16 kHz in `data`.
* `finish`: finalize the utterance.
* `speak`: send `reply` with headline, text, caveats, abstention, and verification.
* `cancel`: cancel the matching request.

Responses are `partial`/`final` with text, `audio` with base64 PCM16 at 24 kHz,
`complete`, `cancelled`, or sanitized `error`. All request events carry the
request ID. There is one active operation per connection, bounded recording
length, and one prefetched synthesis chunk. WebSocket origins use the same
allowlist as the API's CORS policy.

An AudioWorklet converts actual microphone samples to 16 kHz. The browser keeps
a short pre-roll, requires sustained speech, and finalizes after roughly 1.2
seconds of silence or at the 60-second limit. Capture is disabled during
transcription completion, thinking, and playback, avoiding self-transcription.

Final transcripts call the existing `/api/chat`. No voice provider receives the
operational dataset or produces an answer. Hands-free speech selects the existing
verified or repaired headline first, then selects the remaining prose and caveats
only after an affirmative response. Refusals use the abstention explanation.
Rejected drafts are not spoken. Tables, evidence, and tool traces remain visible.
Long replies are split without changing identifiers, values, or dates.

## Verification and limitations

`make check` includes offline Python transport/provider tests and Vitest browser
lifecycle/component tests. They use fake audio and mocked provider responses.
Live smoke tests are opt-in; see the test module for environment switches.

```bash
cd api
CREWOPS_RUN_VOICE_SMOKE=local uv run pytest tests/server/test_voice_smoke.py -s
# With the corresponding server key configured, replace local with sarvam or gemini.
```

The smoke test synthesizes a short synthetic question and transcribes it twice
to check cold and warm behavior. Cloud runs consume provider quota. If models
are missing after enabling offline mode, run `VOICE_OFFLINE=false make
voice-download` from the repository root.

Validation on 2026-09-05: local round trips passed with VoiceKit forced offline
(5.66 seconds initially, 1.42 seconds warm). The in-app browser verified restored
history without autoplay, read-aloud without microphone permission, reactive
playback, interruption, missing cloud-key errors, permission-pending cancellation,
and desktop/390px layouts. Automated tests cover resampling at 16/44.1/48 kHz,
voice lifecycle, tab hiding, provider protocols, errors, grounding, and cleanup.
Live Sarvam/Gemini calls require keys that were unavailable during validation;
separate Chrome/Safari microphone checks remain manual.

The production build passes with `pnpm exec next build --webpack`. Turbopack's
worker port binding is restricted in the validation environment. The full Python
suite retains two existing golden failures, S4 and S6, reproduced against the
unchanged original commit; voice checks pass independently.

Use localhost or HTTPS in a browser with AudioWorklet and Web Audio support.
Allow microphone permission on the first voice session. V1 targets English,
including Indian English, and tap-to-interrupt. It does not perform automatic
translation or voice-triggered interruption. Background noise can affect pause
detection and transcription; the visible transcript and typed chat remain
available for corrections. Cloud speech needs network connectivity and provider
quota. Raw microphone recordings are not persisted by the advisor.

Provider references: [Sarvam realtime transcription](https://docs.sarvam.ai/api/api-guides-tutorials/speech-to-text/realtime-streaming),
[Sarvam speech streaming](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/streaming-api/http-stream),
[Gemini Live transcription](https://ai.google.dev/gemini-api/docs/live-api/live-transcribe),
[Gemini TTS](https://ai.google.dev/gemini-api/docs/speech-generation).
