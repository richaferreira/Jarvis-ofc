// Ponto de integração: VAD contínuo em AudioWorklet/WebRTC, executado no cliente.
export interface SpeechOutput {
  stopPlayback(): void;
  cancelSynthesis(): void;
  clearAudioQueue(): void;
}

export class BargeInController {
  generation: string | null = null;

  constructor(private socket: WebSocket, private output: SpeechOutput) {}

  // Conecte ao onSpeechStart do VAD. Não espere STT nem confirmação do servidor.
  onSpeechStart(): void {
    this.generation = null;
    this.output.stopPlayback();
    this.output.cancelSynthesis();
    this.output.clearAudioQueue();
    if (this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ type: "barge_in" }));
    }
  }

  onFinalTranscript(text: string): void {
    this.socket.send(JSON.stringify({ type: "user", text }));
  }

  onStarted(generation: string): void {
    this.generation = generation;
  }

  acceptsToken(generation: string): boolean {
    return generation === this.generation;
  }
}
// Habilite echoCancellation na captura; valide falsos positivos em ambiente real.
// Este contrato não inclui o modelo VAD, STT contínuo nem um frontend completo.
