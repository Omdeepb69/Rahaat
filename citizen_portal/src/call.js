/**
 * Interactive Emergency Voice Helpline Client (Gnani Prisma v3.0 & Timbre).
 * Real-time Web Audio frequency visualizer, dynamic active disaster context,
 * DTMF keypad routing, and live rescue ticket dispatch linking.
 */
(function () {
  let callSid = null;
  let disasterId = null;
  let timerInterval = null;
  let secondsElapsed = 0;
  let mediaRecorder = null;
  let audioChunks = [];
  let isRecording = false;

  // Web Audio Visualizer state
  let audioCtx = null;
  let analyserNode = null;
  let sourceNode = null;
  let visualizerAnimId = null;
  let orbVisualMode = "idle"; // "idle", "listening", "speaking"

  const btnStart = document.getElementById("btn-call-start");
  const btnMic = document.getElementById("btn-call-mic");
  const btnEnd = document.getElementById("btn-call-end");
  const btnSendText = document.getElementById("btn-send-text");
  const textInput = document.getElementById("text-override-input");
  const languageSelect = document.getElementById("language-select");
  const statusBadge = document.getElementById("call-status-badge");
  const timerDisplay = document.getElementById("call-timer");
  const orbCenter = document.getElementById("orb-center");
  const orbLabel = document.getElementById("orb-label");
  const avatar = document.getElementById("avatar");
  const dialogLog = document.getElementById("dialog-log");
  const micInstruction = document.getElementById("mic-instruction");
  const resultCard = document.getElementById("result-card");
  const resPriority = document.getElementById("res-priority");
  const resUnit = document.getElementById("res-unit");
  const btnTrackTicket = document.getElementById("btn-track-ticket");
  const disasterNameBadge = document.getElementById("disaster-name-badge");
  const canvas = document.getElementById("voice-canvas");
  const ctx = canvas ? canvas.getContext("2d") : null;

  // ── Canvas Audio Visualizer ──────────────────────────────────────────────────

  let pulseAngle = 0;
  function startVisualizerLoop() {
    if (!ctx || !canvas) return;

    function render() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;
      const baseRadius = 46;

      pulseAngle += 0.04;

      if (orbVisualMode === "listening" && analyserNode) {
        // Real-time audio frequency bar spectrum from microphone
        const bufferLength = analyserNode.frequencyBinCount;
        const dataArray = new Uint8Array(bufferLength);
        analyserNode.getByteFrequencyData(dataArray);

        const bars = 24;
        const step = (Math.PI * 2) / bars;

        for (let i = 0; i < bars; i++) {
          const val = dataArray[i % bufferLength] || 0;
          const barHeight = Math.max(4, (val / 255) * 36);
          const angle = i * step;

          const x1 = cx + Math.cos(angle) * (baseRadius + 2);
          const y1 = cy + Math.sin(angle) * (baseRadius + 2);
          const x2 = cx + Math.cos(angle) * (baseRadius + 2 + barHeight);
          const y2 = cy + Math.sin(angle) * (baseRadius + 2 + barHeight);

          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          ctx.lineWidth = 3;
          ctx.strokeStyle = `rgba(245, 158, 11, ${0.4 + (val / 255) * 0.6})`;
          ctx.lineCap = "round";
          ctx.stroke();
        }
      } else if (orbVisualMode === "speaking") {
        // Harmonic undulating wave for Timbre speech synthesis
        const waveRadius = baseRadius + 10 + Math.sin(pulseAngle * 2) * 6;
        ctx.beginPath();
        ctx.arc(cx, cy, waveRadius, 0, Math.PI * 2);
        ctx.lineWidth = 3;
        ctx.strokeStyle = "rgba(139, 92, 246, 0.7)";
        ctx.shadowColor = "#8b5cf6";
        ctx.shadowBlur = 14;
        ctx.stroke();
        ctx.shadowBlur = 0;

        ctx.beginPath();
        ctx.arc(cx, cy, waveRadius + 14 + Math.cos(pulseAngle * 1.5) * 4, 0, Math.PI * 2);
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = "rgba(236, 72, 153, 0.4)";
        ctx.stroke();
      } else {
        // Idle gentle breathing orbital ring
        const breathing = Math.sin(pulseAngle) * 3;
        ctx.beginPath();
        ctx.arc(cx, cy, baseRadius + 8 + breathing, 0, Math.PI * 2);
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = "rgba(56, 189, 248, 0.35)";
        ctx.stroke();
      }

      visualizerAnimId = requestAnimationFrame(render);
    }

    if (!visualizerAnimId) {
      render();
    }
  }

  startVisualizerLoop();

  function setOrbState(mode, labelText, icon) {
    orbVisualMode = mode;
    if (orbLabel) orbLabel.textContent = labelText;
    if (avatar && icon) avatar.textContent = icon;

    if (orbCenter) {
      orbCenter.className = `orb-center ${mode}`;
      if (mode !== "idle") {
        orbCenter.classList.add("active-pulse");
      }
    }
  }

  // ── Dynamic Active Disaster Resolution ──────────────────────────────────────

  async function resolveDisasterId() {
    try {
      const res = await fetch("/api/v1/disasters/active");
      if (res.ok) {
        const d = await res.json();
        if (d && d.id) {
          if (disasterNameBadge) {
            disasterNameBadge.textContent = `ZONE: ${d.name} (${d.status.toUpperCase()})`;
          }
          return d.id;
        }
      }
    } catch (e) {
      console.warn("Could not fetch active disaster:", e);
    }

    // Secondary fallback: query disasters list
    try {
      const res = await fetch("/api/v1/disasters");
      if (res.ok) {
        const list = await res.json();
        if (list.length > 0) {
          if (disasterNameBadge) {
            disasterNameBadge.textContent = `ZONE: ${list[0].name}`;
          }
          return list[0].id;
        }
      }
    } catch (e) {
      console.warn("Could not fetch disasters list:", e);
    }

    if (disasterNameBadge) {
      disasterNameBadge.textContent = "ZONE: ACTIVE DISASTER RESPONSE";
    }
    return null;
  }

  // Automatically resolve active disaster on page load
  resolveDisasterId().then((id) => {
    disasterId = id;
  });

  // ── UI Helpers ─────────────────────────────────────────────────────────────

  function setStatus(text, badgeClass) {
    statusBadge.textContent = text;
    statusBadge.className = `call-status-badge ${badgeClass}`;
  }

  function addBubble(sender, label, text) {
    const bubble = document.createElement("div");
    bubble.className = `bubble ${sender}`;
    const lbl = document.createElement("div");
    lbl.className = "bubble-label";
    lbl.textContent = label;
    bubble.appendChild(lbl);
    const content = document.createElement("div");
    content.textContent = text;
    bubble.appendChild(content);
    dialogLog.appendChild(bubble);
    dialogLog.scrollTop = dialogLog.scrollHeight;
  }

  function playAudioBase64(b64) {
    if (!b64) return;
    try {
      setOrbState("speaking", "TIMBRE TTS", "🔊");
      const audio = new Audio("data:audio/wav;base64," + b64);
      audio.onended = () => {
        setOrbState("idle", "CONNECTED", "🎙️");
      };
      audio.play().catch((err) => {
        console.log("Audio autoplay prevented:", err);
        setOrbState("idle", "CONNECTED", "🎙️");
      });
    } catch (e) {
      console.warn("Could not play audio:", e);
      setOrbState("idle", "CONNECTED", "🎙️");
    }
  }

  function startTimer() {
    secondsElapsed = 0;
    timerInterval = setInterval(() => {
      secondsElapsed++;
      const m = String(Math.floor(secondsElapsed / 60)).padStart(2, "0");
      const s = String(secondsElapsed % 60).padStart(2, "0");
      timerDisplay.textContent = `${m}:${s}`;
    }, 1000);
  }

  function stopTimer() {
    if (timerInterval) clearInterval(timerInterval);
  }

  // ── Call Lifecycle ──────────────────────────────────────────────────────────

  // 1. Start Call
  btnStart.addEventListener("click", async () => {
    if (!disasterId) {
      disasterId = await resolveDisasterId();
    }

    setStatus("CONNECTING TO 112 DISPATCH...", "status-listening");
    setOrbState("listening", "CONNECTING", "📡");
    btnStart.disabled = true;

    try {
      const payload = {
        caller_phone: "+919820011223",
        language_code: languageSelect.value,
      };
      if (disasterId) {
        payload.disaster_id = disasterId;
      }

      const res = await fetch("/api/v1/ivr/calls/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      }

      const data = await res.json();
      callSid = data.call_sid;

      // Update UI for ongoing call
      btnStart.style.display = "none";
      btnMic.style.display = "flex";
      btnEnd.style.display = "flex";
      languageSelect.disabled = true;
      startTimer();

      setStatus("CALL CONNECTED — LISTENING", "status-connected");
      setOrbState("idle", "READY", "🎙️");
      micInstruction.textContent = "Tap blue microphone to speak, or type response below";

      addBubble("agent", "Raahat Helpline Agent", data.prompt_text);
      playAudioBase64(data.prompt_audio_base64);
    } catch (err) {
      setStatus("CALL FAILED — RETRY", "status-standby");
      setOrbState("idle", "STANDBY", "🎙️");
      btnStart.disabled = false;
      alert("Could not start call: " + err.message);
    }
  });

  // 2. Microphone Recording with Live Frequency Analyzer
  btnMic.addEventListener("click", async () => {
    if (!isRecording) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

        // Wire Web Audio API analyser
        try {
          if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
          }
          if (audioCtx.state === "suspended") {
            await audioCtx.resume();
          }
          sourceNode = audioCtx.createMediaStreamSource(stream);
          analyserNode = audioCtx.createAnalyser();
          analyserNode.fftSize = 64;
          sourceNode.connect(analyserNode);
        } catch (audioErr) {
          console.warn("Could not wire AudioContext visualizer:", audioErr);
        }

        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = (e) => {
          if (e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = async () => {
          let recordedBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
          stream.getTracks().forEach((t) => t.stop());
          if (sourceNode) sourceNode.disconnect();
          analyserNode = null;

          // Convert client audio to clean 16kHz Mono PCM WAV for Gnani Prisma
          try {
            const arrayBuf = await recordedBlob.arrayBuffer();
            const decodeCtx = new (window.AudioContext || window.webkitAudioContext)();
            const audioBuffer = await decodeCtx.decodeAudioData(arrayBuf);
            const wavArrayBuffer = encodeAudioBufferToWav(audioBuffer);
            recordedBlob = new Blob([wavArrayBuffer], { type: "audio/wav" });
            decodeCtx.close();
          } catch (convErr) {
            console.warn("Direct WAV conversion fallback to raw blob:", convErr);
          }

          await sendTurnAudio(recordedBlob);
        };

        mediaRecorder.start();
        isRecording = true;
        btnMic.classList.add("recording");
        setOrbState("listening", "LISTENING", "🎤");
        setStatus("RECORDING VIA GNANI PRISMA...", "status-listening");
        micInstruction.textContent = "Listening... Tap microphone again when finished speaking";
      } catch (err) {
        console.warn("Microphone access denied or unavailable, use text box:", err);
        alert("Microphone not available. Please type your reply in the text box below.");
      }
    } else {
      // Stop recording and send
      mediaRecorder.stop();
      isRecording = false;
      btnMic.classList.remove("recording");
      setOrbState("idle", "PRISMA v3.0", "⏳");
      setStatus("TRANSCRIBING VIA GNANI PRISMA v3.0...", "status-speaking");
      micInstruction.textContent = "Transcribing Indic speech via Gnani Prisma v3.0...";
    }
  });

  // 3. Send Voice Turn
  async function sendTurnAudio(audioBlob) {
    const formData = new FormData();
    formData.append("audio_file", audioBlob, "caller_voice.wav");

    try {
      const res = await fetch(`/api/v1/ivr/calls/${callSid}/turn`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) throw new Error(`Turn failed: ${await res.text()}`);
      const data = await res.json();
      handleTurnResult(data);
    } catch (err) {
      setStatus("ERROR IN TURN — TRY AGAIN", "status-listening");
      setOrbState("idle", "ERROR", "⚠️");
      alert("Turn failed: " + err.message);
    }
  }

  // 4. Send Text Turn
  btnSendText.addEventListener("click", async () => {
    const text = textInput.value.trim();
    if (!text) return;

    // If call hasn't been started yet, start it automatically before sending
    if (!callSid) {
      setStatus("INITIALIZING CALL...", "status-listening");
      btnStart.disabled = true;
      try {
        if (!disasterId) {
          disasterId = await resolveDisasterId();
        }
        const payload = {
          caller_phone: "+919820011223",
          language_code: languageSelect.value || "indic-auto",
        };
        if (disasterId) payload.disaster_id = disasterId;

        const startRes = await fetch("/api/v1/ivr/calls/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!startRes.ok) throw new Error(`Could not initiate call: ${await startRes.text()}`);
        const startData = await startRes.json();
        callSid = startData.call_sid;

        btnStart.style.display = "none";
        btnMic.style.display = "flex";
        btnEnd.style.display = "flex";
        languageSelect.disabled = true;
        startTimer();

        addBubble("agent", "Raahat Helpline Agent", startData.prompt_text);
      } catch (err) {
        setStatus("CALL FAILED — RETRY", "status-standby");
        btnStart.disabled = false;
        alert("Failed to start call: " + err.message);
        return;
      }
    }

    textInput.value = "";
    addBubble("user", "You (Text)", text);

    const formData = new FormData();
    formData.append("text_override", text);

    setStatus("PROCESSING VIA GNANI & LLM...", "status-speaking");
    setOrbState("idle", "PROCESSING", "⏳");
    try {
      const res = await fetch(`/api/v1/ivr/calls/${callSid}/turn`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      handleTurnResult(data);
    } catch (err) {
      alert("Error: " + err.message);
    }
  });

  // Allow 'Enter' key on text override input
  textInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      btnSendText.click();
    }
  });

  // 5. Send DTMF Keypad Digits
  document.querySelectorAll(".btn-keypad").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!callSid) return;
      const digit = btn.getAttribute("data-digit");
      addBubble("user", "You (Keypad DTMF)", `[Keypad Digit: ${digit}]`);

      const formData = new FormData();
      formData.append("dtmf_digits", digit);

      setStatus("TRANSMITTING DTMF TONE...", "status-speaking");
      try {
        const res = await fetch(`/api/v1/ivr/calls/${callSid}/turn`, {
          method: "POST",
          body: formData,
        });
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        handleTurnResult(data);
      } catch (err) {
        console.error("DTMF turn failed:", err);
      }
    });
  });

  // 6. Handle Turn Result
  function handleTurnResult(data) {
    if (data.caller_transcript) {
      addBubble("user", `You (${data.detected_language || "spoken"})`, data.caller_transcript);
    }

    addBubble("agent", "Raahat Helpline Agent", data.prompt_text);
    playAudioBase64(data.prompt_audio_base64);

    // Update real-time AI cognitive telemetry panel
    const telemetryPanel = document.getElementById("ai-telemetry-panel");
    const telLoc = document.getElementById("telemetry-location");
    const telCount = document.getElementById("telemetry-count");
    const telNeeds = document.getElementById("telemetry-needs");
    const aiPriority = document.getElementById("ai-priority-badge");

    if (telemetryPanel) {
      telemetryPanel.style.display = "block";
      if (telLoc && data.extracted_location) {
        telLoc.textContent = data.extracted_location;
        telLoc.style.color = "#38bdf8";
      }
      if (telCount && data.extracted_people_count !== null && data.extracted_people_count !== undefined) {
        telCount.textContent = `${data.extracted_people_count} individuals`;
        telCount.style.color = "#fbbf24";
      }
      if (telNeeds && data.extracted_needs && data.extracted_needs.length) {
        telNeeds.textContent = data.extracted_needs.join(", ").toUpperCase();
        telNeeds.style.color = "#ec4899";
      }
      if (aiPriority && data.assessed_priority) {
        aiPriority.textContent = `PRIORITY ${data.assessed_priority}`;
        aiPriority.className = `badge-priority badge-${data.assessed_priority.toLowerCase()}`;
      }
    }

    if (data.is_completed) {
      setStatus("CALL COMPLETED — RESCUE AUTHORIZED", "status-completed");
      stopTimer();
      setOrbState("idle", "RESCUED", "✓");
      btnMic.style.display = "none";
      btnEnd.style.display = "none";
      micInstruction.textContent = "Disaster report submitted. Emergency rescue team dispatched.";

      resultCard.style.display = "block";
      resPriority.textContent = data.priority ? `${data.priority.toUpperCase()}` : "P0 CRITICAL";
      resPriority.className = `badge-priority badge-${(data.priority || "p0").toLowerCase()}`;
      resUnit.textContent = data.proposed_resource || "NDRF Motorboat Alpha-1 (Assigned)";

      if (data.report_id) {
        btnTrackTicket.href = `/sos/track.html?report_id=${data.report_id}`;
      }
    } else {
      setStatus("LISTENING FOR NEXT RESPONSE", "status-connected");
      micInstruction.textContent = "Tap blue microphone to reply, or type below";
    }
  }

  // 7. End Call
  btnEnd.addEventListener("click", () => {
    stopTimer();
    setStatus("CALL TERMINATED BY USER", "status-standby");
    setOrbState("idle", "STANDBY", "🎙️");
    btnMic.style.display = "none";
    btnEnd.style.display = "none";
    btnStart.style.display = "flex";
    btnStart.disabled = false;
    languageSelect.disabled = false;
    micInstruction.textContent = "Emergency call ended.";
  });

  // Client-side PCM WAV Encoder for Gnani Indic STT compatibility
  function encodeAudioBufferToWav(buffer) {
    const numChannels = 1;
    const sampleRate = buffer.sampleRate || 16000;
    const format = 1; // PCM
    const bitDepth = 16;
    const channelData = buffer.getChannelData(0);
    const dataLength = channelData.length * (bitDepth / 8);
    const headerLength = 44;
    const totalLength = headerLength + dataLength;

    const arrayBuffer = new ArrayBuffer(totalLength);
    const view = new DataView(arrayBuffer);

    function writeString(view, offset, string) {
      for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
      }
    }

    writeString(view, 0, "RIFF");
    view.setUint32(4, 36 + dataLength, true);
    writeString(view, 8, "WAVE");
    writeString(view, 12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, format, true);
    view.setUint16(22, numChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * numChannels * (bitDepth / 8), true);
    view.setUint16(32, numChannels * (bitDepth / 8), true);
    view.setUint16(34, bitDepth, true);
    writeString(view, 36, "data");
    view.setUint32(40, dataLength, true);

    let offset = 44;
    for (let i = 0; i < channelData.length; i++) {
      const s = Math.max(-1, Math.min(1, channelData[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      offset += 2;
    }

    return arrayBuffer;
  }
})();
