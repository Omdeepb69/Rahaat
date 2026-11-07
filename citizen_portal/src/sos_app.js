/**
 * Citizen Emergency SOS Portal logic.
 */
import { AudioRecorder } from "./recorder.js";
import { getLiveLocation } from "./geolocation.js";

const recorder = new AudioRecorder();
let currentAudioBlob = null;
let currentCoords = null;

document.addEventListener("DOMContentLoaded", () => {
  const btnRecord = document.getElementById("btn-record");
  const recordStatus = document.getElementById("record-status");
  const audioPreview = document.getElementById("audio-preview");
  const btnLocation = document.getElementById("btn-location");
  const locationDetails = document.getElementById("location-details");
  const sosForm = document.getElementById("sos-form");
  const btnSubmit = document.getElementById("btn-submit");
  const alertContainer = document.getElementById("alert-container");

  function showAlert(msg, isError = true) {
    alertContainer.innerHTML = `
      <div style="background-color: ${isError ? '#7f1d1d' : '#065f46'}; color: #fff; padding: 12px; border-radius: 8px; margin-bottom: 14px; font-weight: 600;">
        ${msg}
      </div>
    `;
  }

  // 1. Voice Recording Toggle
  if (btnRecord) {
    btnRecord.addEventListener("click", async () => {
      if (!recorder.isRecording) {
        try {
          await recorder.start((seconds) => {
            const mins = String(Math.floor(seconds / 60)).padStart(2, "0");
            const secs = String(seconds % 60).padStart(2, "0");
            recordStatus.textContent = `Recording... ${mins}:${secs} (Tap to Stop)`;
            recordStatus.classList.add("active");
          });
          btnRecord.classList.add("recording");
          btnRecord.innerHTML = "⏹️";
        } catch (err) {
          showAlert(err.message);
        }
      } else {
        currentAudioBlob = await recorder.stop();
        btnRecord.classList.remove("recording");
        btnRecord.innerHTML = "🎤";
        recordStatus.textContent = "Voice note recorded successfully! (आवाज़ रिकॉर्ड हो गई)";
        recordStatus.classList.remove("active");

        if (currentAudioBlob) {
          const audioUrl = URL.createObjectURL(currentAudioBlob);
          audioPreview.src = audioUrl;
          audioPreview.style.display = "block";
        }
      }
    });
  }

  // 2. Geolocation Share
  if (btnLocation) {
    btnLocation.addEventListener("click", async () => {
      btnLocation.disabled = true;
      btnLocation.textContent = "Detecting GPS... (स्थान खोज रहे हैं...)";
      try {
        currentCoords = await getLiveLocation();
        btnLocation.textContent = "✓ Location Shared (स्थान प्राप्त हुआ)";
        btnLocation.classList.add("shared");
        locationDetails.textContent = `Lat: ${currentCoords.latitude.toFixed(5)}, Lon: ${currentCoords.longitude.toFixed(5)} (Accuracy: ±${Math.round(currentCoords.accuracy)}m)`;
      } catch (err) {
        btnLocation.textContent = "Share My GPS Location (मेरा स्थान साझा करें)";
        showAlert(err.message);
      } finally {
        btnLocation.disabled = false;
      }
    });
  }

  // 3. Form Submission
  if (sosForm) {
    sosForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      btnSubmit.disabled = true;
      btnSubmit.textContent = "SENDING EMERGENCY SOS... (मदद भेजी जा रही है...)";

      const callerName = document.getElementById("caller_name").value.trim();
      const phoneNumber = document.getElementById("phone_number").value.trim();
      const locationText = document.getElementById("location_text").value.trim();
      const peopleCount = parseInt(document.getElementById("people_count").value, 10) || 1;
      const situationDesc = document.getElementById("situation_description").value.trim();

      const checkedNeeds = Array.from(
        document.querySelectorAll("input[name='needs']:checked")
      ).map((cb) => cb.value);

      try {
        let res;
        if (currentAudioBlob) {
          // Multipart form with audio
          const formData = new FormData();
          formData.append("audio", currentAudioBlob, "voice_sos.webm");
          if (callerName) formData.append("caller_name", callerName);
          if (phoneNumber) formData.append("phone_number", phoneNumber);
          if (locationText) formData.append("location_text", locationText);
          if (currentCoords) {
            formData.append("latitude", currentCoords.latitude);
            formData.append("longitude", currentCoords.longitude);
          }
          formData.append("people_count", peopleCount);
          if (situationDesc) formData.append("situation_description", situationDesc);
          if (checkedNeeds.length > 0) formData.append("needs", JSON.stringify(checkedNeeds));

          res = await fetch("/api/v1/reports/channels/web/voice", {
            method: "POST",
            body: formData,
          });
        } else {
          // Standard JSON Web SOS
          const payload = {
            caller_name: callerName || null,
            phone_number: phoneNumber || null,
            location_text: locationText || "Unspecified Location",
            latitude: currentCoords ? currentCoords.latitude : null,
            longitude: currentCoords ? currentCoords.longitude : null,
            people_count: peopleCount,
            situation_description: situationDesc || "Emergency distress report submitted via web SOS portal",
            needs: checkedNeeds,
          };

          res = await fetch("/api/v1/reports/channels/web", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
        }

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || `Server error ${res.status}`);
        }

        const data = await res.json();
        const reportId = data.report_id;
        window.location.href = `/sos/track.html?report_id=${encodeURIComponent(reportId)}`;
      } catch (err) {
        showAlert(`Failed to send SOS: ${err.message}`);
        btnSubmit.disabled = false;
        btnSubmit.textContent = "SEND DISTRESS CALL NOW (तत्काल मदद भेजें)";
      }
    });
  }
});

