/**
 * Interactive Emergency Voice Helpline Client (Gnani Prisma & Timbre).
 */
(function () {
  let callSid = null;
  let disasterId = null;
  let timerInterval = null;
  let secondsElapsed = 0;
  let mediaRecorder = null;
  let audioChunks = [];
  let isRecording = false;

  const btnStart = document.getElementById("btn-call-start");
  const btnMic = document.getElementById("btn-call-mic");
  const btnEnd = document.getElementById("btn-call-end");
  const btnSendText = document.getElementById("btn-send-text");
  const textInput = document.getElementById("text-override-input");
  const languageSelect = document.getElementById("language-select");
  const statusBadge = document.getElementById("call-status-badge");
  const timerDisplay = document.getElementById("call-timer");
  const avatar = document.getElementById("avatar");
  const dialogLog = document.getElementById("dialog-log");
  const micInstruction = document.getElementById("mic-instruction");
  const resultCard = document.getElementById("result-card");
  const resPriority = document.getElementById("res-priority");
  const resUnit = document.getElementById("res-unit");
  const btnTrackTicket = document.getElementById("btn-track-ticket");

  // Load active disaster ID or fallback to demo scenario ID
  async function resolveDisasterId() {
    try {
      const res = await fetch("/api/v1/incidents");
      if (res.ok) {
        const incidents = await res.json();
        if (incidents.length > 0 && incidents[0].disaster_id) {
          return incidents[0].disaster_id;
        }
      }
    } catch (e) {
      console.warn("Could not fetch incidents for disaster ID:", e);
    }
    // Default fallback disaster UUID from seed
    return "a3be54b7-3012-492c-adc6-ff90dbc26f8c";
  }

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
      const audio = new Audio("data:audio/wav;base64," + b64);
      audio.play().catch((err) => console.log("Audio autoplay prevented:", err));
    } catch (e) {
      console.warn("Could not play audio:", e);
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

  // 1. Start Call
  btnStart.addEventListener("click", async () => {
    disasterId = await resolveDisasterId();
    setStatus("CONNECTING TO 112 DISPATCH...", "status-listening");
    btnStart.disabled = true;

    try {
      const res = await fetch("/api/v1/ivr/calls/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          disaster_id: disasterId,
          caller_phone: "+919820011223",
          language_code: languageSelect.value,
        }),
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
      avatar.classList.add("active");
      languageSelect.disabled = true;
      startTimer();

      setStatus("CALL CONNECTED — LISTENING", "status-connected");
      micInstruction.textContent = "Tap blue microphone to speak, or type response below";

      addBubble("agent", "Raahat Helpline Agent", data.prompt_text);
      playAudioBase64(data.prompt_audio_base64);
    } catch (err) {
      setStatus("CALL FAILED — RETRY", "status-standby");
      btnStart.disabled = false;
      alert("Could not start call: " + err.message);
    }
  });

  // 2. Microphone Recording
  btnMic.addEventListener("click", async () => {
    if (!isRecording) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = (e) => {
          if (e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = async () => {
          const audioBlob = new Blob(audioChunks, { type: "audio/wav" });
          stream.getTracks().forEach((t) => t.stop());
          await sendTurnAudio(audioBlob);
        };

        mediaRecorder.start();
        isRecording = true;
        btnMic.classList.add("recording");
        setStatus("RECORDING YOUR VOICE...", "status-listening");
        micInstruction.textContent = "Recording... Tap microphone again when finished speaking";
      } catch (err) {
        console.warn("Microphone access denied or unavailable, use text box:", err);
        alert("Microphone not available. Please type your reply in the text box below.");
      }
    } else {
      // Stop recording and send
      mediaRecorder.stop();
      isRecording = false;
      btnMic.classList.remove("recording");
      setStatus("PROCESSING VIA GNANI PRISMA...", "status-speaking");
      micInstruction.textContent = "Processing speech via Gnani Prisma v3.0...";
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
      alert("Turn failed: " + err.message);
    }
  }

  // 4. Send Text Turn
  btnSendText.addEventListener("click", async () => {
    const text = textInput.value.trim();
    if (!text || !callSid) return;
    textInput.value = "";

    const formData = new FormData();
    formData.append("text_override", text);

    setStatus("PROCESSING...", "status-speaking");
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

  // 5. Send DTMF Keypad Digits
  document.querySelectorAll(".btn-keypad").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!callSid) return;
      const digit = btn.getAttribute("data-digit");
      addBubble("user", "You (Keypad DTMF)", `[Keypad: ${digit}]`);

      const formData = new FormData();
      formData.append("dtmf_digits", digit);

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
      addBubble("user", `You (${data.detected_language || "speech"})`, data.caller_transcript);
    }

    addBubble("agent", "Raahat Helpline Agent", data.prompt_text);
    playAudioBase64(data.prompt_audio_base64);

    if (data.is_completed) {
      setStatus("CALL COMPLETED — RESCUE PROPOSED", "status-completed");
      stopTimer();
      avatar.classList.remove("active");
      btnMic.style.display = "none";
      btnEnd.style.display = "none";
      micInstruction.textContent = "Disaster report submitted. Emergency dispatch unit proposed.";

      resultCard.style.display = "block";
      resPriority.textContent = data.priority ? data.priority.toUpperCase() : "P0 CRITICAL";
      resUnit.textContent = data.proposed_resource || "NDRF Motorboat Alpha-1 (Proposed)";
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
    avatar.classList.remove("active");
    btnMic.style.display = "none";
    btnEnd.style.display = "none";
    btnStart.style.display = "flex";
    btnStart.disabled = false;
    languageSelect.disabled = false;
    micInstruction.textContent = "Call ended.";
  });
})();
