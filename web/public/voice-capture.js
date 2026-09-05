/* global AudioWorkletProcessor, registerProcessor, sampleRate */
// Average input samples into 16 kHz PCM frames. No audio leaves this worklet
// while disabled, including while the advisor is speaking.
class VoiceCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.enabled = false;
    this.reset();
    this.port.onmessage = ({ data }) => {
      this.enabled = data.enabled;
      this.reset();
    };
  }
  reset() {
    this.phase = 0;
    this.sum = 0;
    this.weight = 0;
    this.frame = new Int16Array(1600);
    this.index = 0;
    this.energy = 0;
  }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (!this.enabled || !input) return true;
    const width = sampleRate / 16000;
    for (const sample of input) {
      let remaining = 1;
      while (remaining > 0.000001) {
        const weight = Math.min(remaining, width - this.phase);
        this.sum += sample * weight;
        this.weight += weight;
        this.phase += weight;
        remaining -= weight;
        if (this.phase >= width - 0.000001) {
          const value = Math.max(-1, Math.min(1, this.sum / this.weight));
          this.frame[this.index++] = Math.round(value * (value < 0 ? 32768 : 32767));
          this.energy += value * value;
          this.phase = this.sum = this.weight = 0;
          if (this.index === this.frame.length) {
            this.port.postMessage({ pcm: this.frame, rms: Math.sqrt(this.energy / this.index) }, [this.frame.buffer]);
            this.frame = new Int16Array(1600);
            this.index = this.energy = 0;
          }
        }
      }
    }
    return true;
  }
}
registerProcessor("voice-capture", VoiceCapture);
