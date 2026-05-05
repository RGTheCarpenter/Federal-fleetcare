const trackingRuntime = {
  intervalId: null,
  busy: false,
};

function getTrackingData() {
  return window.FLEETCARE_TRACKING || {};
}

function setTrackingMessage({ mode, lastSavedAt, error } = {}) {
  const modeNode = document.querySelector("[data-tracking-mode]");
  const lastSavedNode = document.querySelector("[data-tracking-last-saved]");
  const errorNode = document.querySelector("[data-tracking-error]");
  const tracking = getTrackingData();

  if (modeNode) {
    const nextMode = mode || (tracking.tripActive ? "Trip active" : "Ready");
    modeNode.textContent = nextMode;
    modeNode.classList.remove("active", "warning", "danger");
    modeNode.classList.add(
      nextMode === "Tracking paused" ? "danger" :
      tracking.tripActive ? "warning" : "active",
    );
  }

  if (lastSavedNode) {
    lastSavedNode.textContent = lastSavedAt || tracking.lastSavedAt || "No GPS point saved yet";
  }

  if (errorNode) {
    const message = error || "";
    errorNode.hidden = !message;
    errorNode.textContent = message;
  }
}

async function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Unable to read file"));
    reader.readAsDataURL(file);
  });
}

function updateOfflineBanner() {
  const banner = document.querySelector("[data-offline-banner]");
  if (!banner) {
    return;
  }
  banner.hidden = navigator.onLine;
}

async function bindEncodedUploads() {
  const inputs = document.querySelectorAll("input[type='file'][data-encode-target]");
  for (const input of inputs) {
    input.addEventListener("change", async () => {
      const file = input.files && input.files[0];
      const form = input.form;
      if (!file || !form) {
        return;
      }

      const dataTarget = form.querySelector(`input[name="${input.dataset.encodeTarget}"]`);
      const nameTarget = form.querySelector(`input[name="${input.dataset.nameTarget}"]`);
      const previewTarget = document.getElementById(input.dataset.previewTarget || "");

      try {
        const dataUrl = await fileToDataUrl(file);
        if (dataTarget) dataTarget.value = dataUrl;
        if (nameTarget) nameTarget.value = file.name;

        if (previewTarget) {
          const isImage = dataUrl.startsWith("data:image/");
          previewTarget.innerHTML = isImage
            ? `<div class="upload-preview"><img src="${dataUrl}" alt="${file.name}"><span>${file.name}</span></div>`
            : `<div class="upload-preview"><span>${file.name}</span></div>`;
        }
      } catch (error) {
        window.alert("That file could not be attached. Please try another photo or document.");
      }
    });
  }
}

function bindShareButton() {
  const button = document.querySelector("[data-share-app]");
  if (!button) {
    return;
  }

  button.addEventListener("click", async () => {
    const payload = {
      title: button.dataset.shareTitle || "RG Fleet",
      text: button.dataset.shareText || "",
      url: button.dataset.shareUrl || window.location.origin,
    };

    try {
      const capacitorShare = window.Capacitor?.Plugins?.Share;
      if (capacitorShare?.share) {
        await capacitorShare.share(payload);
        return;
      }
      if (navigator.share) {
        await navigator.share(payload);
        return;
      }
      await navigator.clipboard.writeText(payload.url);
      window.alert("The app link has been copied.");
    } catch (error) {
      if (payload.url) {
        window.prompt("Copy this RG Fleet link:", payload.url);
      }
    }
  });
}

function bindPdfDownloads() {
  const forms = document.querySelectorAll("form[action='/reports/fleet.pdf'], form[action$='/reports/fleet.pdf']");
  if (!forms.length) {
    return;
  }

  for (const form of forms) {
    form.addEventListener("submit", async (event) => {
      const browserPlugin = window.Capacitor?.Plugins?.Browser;
      const isNativeApp = !!window.Capacitor?.isNativePlatform?.();
      if (!browserPlugin?.open || !isNativeApp) {
        return;
      }

      event.preventDefault();
      const submitButton = form.querySelector("button[type='submit']");
      const originalText = submitButton?.textContent || "Download PDF";
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = "Opening PDF...";
      }

      try {
        const url = new URL(form.action, window.location.origin);
        const params = new URLSearchParams(new FormData(form));
        for (const [key, value] of params.entries()) {
          if (String(value).trim()) {
            url.searchParams.append(key, value);
          }
        }
        await browserPlugin.open({ url: url.toString() });
      } catch (error) {
        window.alert("RG Fleet could not open the PDF report. Please try again.");
      } finally {
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.textContent = originalText;
        }
      }
    });
  }
}

function populateGpsFields(form, coords) {
  const latitude = form.querySelector("input[name='latitude']");
  const longitude = form.querySelector("input[name='longitude']");
  const accuracy = form.querySelector("input[name='accuracy_meters']");
  if (latitude) latitude.value = String(coords.latitude);
  if (longitude) longitude.value = String(coords.longitude);
  if (accuracy) accuracy.value = String(coords.accuracy || "");
}

async function requestNativeLocationPermission() {
  const capacitorGeo = window.Capacitor?.Plugins?.Geolocation;
  if (!capacitorGeo?.requestPermissions) {
    return null;
  }
  try {
    return await capacitorGeo.requestPermissions();
  } catch (error) {
    return null;
  }
}

async function getCurrentPosition() {
  const capacitorGeo = window.Capacitor?.Plugins?.Geolocation;
  if (capacitorGeo?.getCurrentPosition) {
    await requestNativeLocationPermission();
    const position = await capacitorGeo.getCurrentPosition({
      enableHighAccuracy: true,
      timeout: 15000,
      maximumAge: 30000,
    });
    return position.coords;
  }

  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (position) => resolve(position.coords),
      reject,
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 },
    );
  });
}

async function requestLocationAccess() {
  if (!navigator.geolocation && !window.Capacitor?.Plugins?.Geolocation) {
    throw new Error("This device does not support GPS location capture.");
  }
  await getCurrentPosition();
}

function bindLocationAccessButton() {
  const button = document.querySelector("[data-request-location]");
  if (!button) {
    return;
  }

  button.addEventListener("click", async () => {
    button.disabled = true;
    const originalText = button.textContent;
    button.textContent = "Checking access...";
    try {
      await requestLocationAccess();
      setTrackingMessage({ error: "", mode: getTrackingData().tripActive ? "Trip active" : "Ready" });
      button.textContent = "Location access ready";
      window.setTimeout(() => {
        button.disabled = false;
        button.textContent = originalText;
      }, 1200);
    } catch (error) {
      setTrackingMessage({ error: "Location access is still blocked. Open your browser or app settings and allow precise location." });
      button.disabled = false;
      button.textContent = originalText;
    }
  });
}

function bindGpsCapture() {
  const forms = document.querySelectorAll("[data-gps-form]");
  for (const form of forms) {
    const button = form.querySelector("[data-capture-gps]");
    if (!button) {
      continue;
    }

    const originalText = button.textContent;

    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "Getting location...";

      try {
        const coords = await getCurrentPosition();
        populateGpsFields(form, coords);
        setTrackingMessage({ error: "" });
        button.textContent = "Location captured";
        window.setTimeout(() => {
          button.disabled = false;
          button.textContent = originalText;
        }, 1200);
      } catch (error) {
        button.disabled = false;
        button.textContent = originalText;
        setTrackingMessage({ error: "RG Fleet could not get your location. Make sure location access is allowed." });
        window.alert("RG Fleet could not get your location. Make sure location access is allowed.");
      }
    });
  }
}

function getTripLogForm() {
  const forms = document.querySelectorAll("[data-trip-log-form]");
  for (const form of forms) {
    const tripId = form.querySelector("input[name='trip_id']");
    if (tripId && tripId.value) {
      return form;
    }
  }
  return null;
}

async function submitTripCheckpoint(reason) {
  const gpsForm = getTripLogForm();
  const tracking = getTrackingData();
  if (!gpsForm || !tracking.tripActive || trackingRuntime.busy) {
    return;
  }
  if (!navigator.onLine || document.hidden) {
    setTrackingMessage({ mode: "Tracking paused" });
    return;
  }

  trackingRuntime.busy = true;
  try {
    const coords = await getCurrentPosition();
    populateGpsFields(gpsForm, coords);
    const body = new URLSearchParams(new FormData(gpsForm));
    await fetch("/gps/add", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
    });
    const now = new Date();
    const savedAt = `${now.toLocaleDateString()} ${now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
    window.FLEETCARE_TRACKING = { ...tracking, lastSavedAt: savedAt };
    setTrackingMessage({
      mode: reason === "resume" ? "Trip active" : "Trip active",
      lastSavedAt: savedAt,
      error: "",
    });
  } catch (error) {
    setTrackingMessage({ error: "A trip checkpoint could not be saved. RG Fleet will try again on the next cycle." });
  } finally {
    trackingRuntime.busy = false;
  }
}

function bindAutoTripLogging() {
  const tracking = getTrackingData();
  if (!tracking.tripActive) {
    setTrackingMessage({ mode: "Ready" });
    return;
  }

  const startLoop = () => {
    if (trackingRuntime.intervalId) {
      window.clearInterval(trackingRuntime.intervalId);
    }
    submitTripCheckpoint("start");
    trackingRuntime.intervalId = window.setInterval(() => submitTripCheckpoint("interval"), 60000);
  };

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      setTrackingMessage({ mode: "Tracking paused" });
      return;
    }
    submitTripCheckpoint("resume");
  });

  const capacitorApp = window.Capacitor?.Plugins?.App;
  if (capacitorApp?.addListener) {
    capacitorApp.addListener("appStateChange", ({ isActive }) => {
      if (isActive) {
        submitTripCheckpoint("resume");
      } else {
        setTrackingMessage({ mode: "Tracking paused" });
      }
    });
  }

  window.addEventListener("focus", () => submitTripCheckpoint("resume"));
  window.addEventListener("online", () => submitTripCheckpoint("resume"));
  startLoop();
}

function renderTripMaps() {
  const routes = window.FLEETCARE_TRIP_ROUTES || {};
  const maps = document.querySelectorAll("[data-trip-map]");
  for (const container of maps) {
    const points = routes[container.dataset.tripId] || [];
    if (points.length < 2) {
      container.textContent = points.length === 1 ? "Only one GPS point captured so far." : "No route points saved yet.";
      continue;
    }

    const minLat = Math.min(...points.map((point) => point.lat));
    const maxLat = Math.max(...points.map((point) => point.lat));
    const minLng = Math.min(...points.map((point) => point.lng));
    const maxLng = Math.max(...points.map((point) => point.lng));
    const latRange = Math.max(maxLat - minLat, 0.0001);
    const lngRange = Math.max(maxLng - minLng, 0.0001);
    const mapped = points.map((point) => {
      const x = 12 + ((point.lng - minLng) / lngRange) * 296;
      const y = 148 - ((point.lat - minLat) / latRange) * 136;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    const start = mapped[0].split(",");
    const end = mapped[mapped.length - 1].split(",");

    container.innerHTML = `
      <svg viewBox="0 0 320 160" role="img" aria-label="Trip route map">
        <rect x="0" y="0" width="320" height="160" rx="18" fill="rgba(255,255,255,0.78)"></rect>
        <polyline fill="none" stroke="#1e7e61" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" points="${mapped.join(" ")}"></polyline>
        <circle cx="${start[0]}" cy="${start[1]}" r="8" fill="#cf7b30"></circle>
        <circle cx="${end[0]}" cy="${end[1]}" r="8" fill="#d92525"></circle>
      </svg>
    `;
  }
}

async function syncLocalReminderNotifications() {
  const reminders = Array.isArray(window.FLEETCARE_REMINDERS) ? window.FLEETCARE_REMINDERS : [];
  const localNotifications = window.Capacitor?.Plugins?.LocalNotifications;
  if (!reminders.length || !localNotifications?.requestPermissions || !localNotifications?.schedule) {
    return;
  }

  try {
    const permission = await localNotifications.requestPermissions();
    if (permission.display !== "granted") {
      return;
    }

    const notifications = [];
    for (const reminder of reminders) {
      const scheduleAt = new Date(`${reminder.dueDate}T08:00:00`);
      if (Number.isNaN(scheduleAt.getTime()) || scheduleAt <= new Date()) {
        continue;
      }
      notifications.push({
        id: reminder.id + 1000,
        title: reminder.title,
        body: `${reminder.vehicle} reminder is due on ${reminder.dueDate}. ${reminder.notes || ""}`.trim(),
        schedule: { at: scheduleAt },
      });
    }

    if (notifications.length) {
      await localNotifications.schedule({ notifications });
    }
  } catch (error) {
    // Keep the dashboard usable even if native notifications are unavailable.
  }
}

window.addEventListener("online", updateOfflineBanner);
window.addEventListener("offline", () => {
  updateOfflineBanner();
  setTrackingMessage({ mode: getTrackingData().tripActive ? "Tracking paused" : "Ready" });
});

window.addEventListener("DOMContentLoaded", async () => {
  updateOfflineBanner();
  setTrackingMessage();
  await bindEncodedUploads();
  bindShareButton();
  bindPdfDownloads();
  bindLocationAccessButton();
  bindGpsCapture();
  bindAutoTripLogging();
  renderTripMaps();
  await syncLocalReminderNotifications();
});
