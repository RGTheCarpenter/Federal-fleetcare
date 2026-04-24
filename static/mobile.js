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
  await syncLocalReminderNotifications();
});
