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
      title: button.dataset.shareTitle || "FleetCare",
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
        window.prompt("Copy this FleetCare link:", payload.url);
      }
    }
  });
}

function populateGpsFields(form, coords) {
  const latitude = form.querySelector("input[name='latitude']");
  const longitude = form.querySelector("input[name='longitude']");
  const accuracy = form.querySelector("input[name='accuracy_meters']");
  if (latitude) latitude.value = String(coords.latitude);
  if (longitude) longitude.value = String(coords.longitude);
  if (accuracy) accuracy.value = String(coords.accuracy || "");
}

function getCurrentPosition() {
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      (position) => resolve(position.coords),
      reject,
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 },
    );
  });
}

function bindGpsCapture() {
  const forms = document.querySelectorAll("[data-gps-form]");
  for (const form of forms) {
    const button = form.querySelector("[data-capture-gps]");
    if (!button) {
      continue;
    }

    button.addEventListener("click", () => {
      if (!navigator.geolocation) {
        window.alert("This device does not support GPS location capture.");
        return;
      }

      button.disabled = true;
      button.textContent = "Getting location...";

      navigator.geolocation.getCurrentPosition(
        (position) => {
          populateGpsFields(form, position.coords);
          button.disabled = false;
          button.textContent = "Refresh current location";
        },
        () => {
          button.disabled = false;
          button.textContent = "Use my current location";
          window.alert("FleetCare could not get your location. Make sure location access is allowed.");
        },
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 },
      );
    });
  }
}

function bindAutoTripLogging() {
  const tripInput = document.querySelector("[data-gps-form] input[name='trip_id']");
  if (!tripInput || !tripInput.value || !navigator.geolocation) {
    return;
  }

  const gpsForm = tripInput.form;
  if (!gpsForm) {
    return;
  }

  const submitLog = async () => {
    if (document.hidden) {
      return;
    }
    try {
      const coords = await getCurrentPosition();
      populateGpsFields(gpsForm, coords);
      const body = new URLSearchParams(new FormData(gpsForm));
      await fetch("/gps/add", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: body.toString(),
      });
    } catch (error) {
      // Quiet failure for background-like auto logging.
    }
  };

  submitLog();
  window.setInterval(submitLog, 60000);
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
window.addEventListener("offline", updateOfflineBanner);

window.addEventListener("DOMContentLoaded", async () => {
  updateOfflineBanner();
  await bindEncodedUploads();
  bindShareButton();
  bindGpsCapture();
  bindAutoTripLogging();
  renderTripMaps();
  await syncLocalReminderNotifications();
});
