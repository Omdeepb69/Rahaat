/**
 * In-browser audio recorder using MediaRecorder API.
 */
export class AudioRecorder {
  constructor() {
    this.mediaRecorder = null;
    this.audioChunks = [];
    this.audioBlob = null;
    this.stream = null;
    this.isRecording = false;
    this.timerInterval = null;
    this.secondsRecorded = 0;
  }

  async start(onTick = null) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("Microphone recording is not supported in this browser.");
    }

    this.audioChunks = [];
    this.audioBlob = null;
    this.secondsRecorded = 0;

    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    
    // Choose preferred MIME type supported by browser
    let mimeType = "audio/webm";
    if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
      mimeType = "audio/webm;codecs=opus";
    } else if (MediaRecorder.isTypeSupported("audio/ogg;codecs=opus")) {
      mimeType = "audio/ogg;codecs=opus";
    } else if (MediaRecorder.isTypeSupported("audio/mp4")) {
      mimeType = "audio/mp4";
    }

    this.mediaRecorder = new MediaRecorder(this.stream, { mimeType });

    this.mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        this.audioChunks.push(e.data);
      }
    };

    this.mediaRecorder.start(250); // collect 250ms chunks
    this.isRecording = true;

    if (onTick) {
      onTick(this.secondsRecorded);
      this.timerInterval = setInterval(() => {
        this.secondsRecorded++;
        onTick(this.secondsRecorded);
        if (this.secondsRecorded >= 120) {
          // Cap maximum recording at 2 minutes
          this.stop();
        }
      }, 1000);
    }
  }

  stop() {
    return new Promise((resolve) => {
      if (!this.mediaRecorder || this.mediaRecorder.state === "inactive") {
        this.isRecording = false;
        resolve(this.audioBlob);
        return;
      }

      if (this.timerInterval) {
        clearInterval(this.timerInterval);
        this.timerInterval = null;
      }

      this.mediaRecorder.onstop = () => {
        const mimeType = this.mediaRecorder.mimeType || "audio/webm";
        this.audioBlob = new Blob(this.audioChunks, { type: mimeType });
        this.isRecording = false;

        // Stop all audio tracks to release microphone hardware
        if (this.stream) {
          this.stream.getTracks().forEach((track) => track.stop());
          this.stream = null;
        }

        resolve(this.audioBlob);
      };

      this.mediaRecorder.stop();
    });
  }

  getBlob() {
    return this.audioBlob;
  }
}

