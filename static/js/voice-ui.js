/**
 * Basılı tut = kayıt; dalga = mikrofon RMS; transkript contenteditable.
 */
(function () {
  var stack = document.getElementById("voice-wave-stack");
  var btn = document.getElementById("voice-record-btn");
  var audioEl = document.getElementById("voice-audio");
  var transcriptEl = document.getElementById("voice-transcript");
  var statusEl = document.getElementById("voice-status");
  var errEl = document.getElementById("voice-error");
  var audioEmpty = document.getElementById("voice-audio-empty");

  if (!btn || !stack) return;

  var mediaStream = null;
  var mediaRecorder = null;
  var chunks = [];
  var audioContext = null;
  var analyser = null;
  var rafId = null;
  var recording = false;

  function setStatus(t) {
    if (statusEl) statusEl.textContent = t || "";
  }

  function setError(t) {
    if (errEl) {
      errEl.textContent = t || "";
      errEl.hidden = !t;
    }
  }

  function rms(samples) {
    var sum = 0;
    var n = samples.length;
    for (var i = 0; i < n; i++) {
      var v = (samples[i] - 128) / 128;
      sum += v * v;
    }
    return Math.sqrt(sum / n);
  }

  function tick() {
    if (!analyser || !recording) return;
    var buf = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(buf);
    var level = Math.min(1, rms(buf) * 5.5);
    stack.style.setProperty("--voice-level", String(level));
    rafId = requestAnimationFrame(tick);
  }

  function stopAnalyser() {
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
    stack.style.setProperty("--voice-level", "0");
  }

  async function startRecording() {
    setError("");
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      setError("Mikrofon izni gerekli.");
      return;
    }

    audioContext = new (window.AudioContext || window.webkitAudioContext)();
    var source = audioContext.createMediaStreamSource(mediaStream);
    analyser = audioContext.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.65;
    source.connect(analyser);

    chunks = [];
    var mime = "audio/webm;codecs=opus";
    if (!MediaRecorder.isTypeSupported(mime)) mime = "audio/webm";

    try {
      mediaRecorder = new MediaRecorder(mediaStream, { mimeType: mime });
    } catch (e) {
      mediaRecorder = new MediaRecorder(mediaStream);
    }

    mediaRecorder.ondataavailable = function (e) {
      if (e.data && e.data.size) chunks.push(e.data);
    };

    mediaRecorder.onstop = function () {
      stopAnalyser();
      stack.classList.add("is-idle");
      btn.classList.remove("is-recording");
      recording = false;
      setStatus("");

      if (chunks.length) {
        if (audioEl && audioEl.src && audioEl.src.indexOf("blob:") === 0) {
          try {
            URL.revokeObjectURL(audioEl.src);
          } catch (e) {}
        }
        var blob = new Blob(chunks, { type: mediaRecorder.mimeType || "audio/webm" });
        var url = URL.createObjectURL(blob);
        if (audioEl) {
          audioEl.src = url;
          audioEl.hidden = false;
        }
        if (audioEmpty) audioEmpty.hidden = true;
        if (transcriptEl && !transcriptEl.textContent.trim()) {
          transcriptEl.textContent =
            "Kayıt hazır. Sunucu transkripti için /voice/upload kullanın; metni burada düzenleyebilirsiniz.";
        }
      }

      if (mediaStream) {
        mediaStream.getTracks().forEach(function (t) {
          t.stop();
        });
        mediaStream = null;
      }
      if (audioContext) {
        audioContext.close().catch(function () {});
        audioContext = null;
      }
    };

    mediaRecorder.start(100);
    recording = true;
    btn.classList.add("is-recording");
    stack.classList.remove("is-idle");
    setStatus("Kayıt…");
    tick();
  }

  function stopRecording() {
    if (!recording || !mediaRecorder) return;
    if (mediaRecorder.state !== "inactive") mediaRecorder.stop();
  }

  function onDown(e) {
    e.preventDefault();
    if (recording) return;
    startRecording();
  }

  function onUp(e) {
    e.preventDefault();
    if (!recording) return;
    stopRecording();
  }

  btn.addEventListener("mousedown", onDown);
  btn.addEventListener("mouseup", onUp);
  btn.addEventListener("mouseleave", function (e) {
    if (recording) onUp(e);
  });

  btn.addEventListener(
    "touchstart",
    function (e) {
      onDown(e);
    },
    { passive: false }
  );
  btn.addEventListener(
    "touchend",
    function (e) {
      onUp(e);
    },
    { passive: false }
  );
  btn.addEventListener("touchcancel", function (e) {
    if (recording) onUp(e);
  });

  stack.classList.add("is-idle");
})();
