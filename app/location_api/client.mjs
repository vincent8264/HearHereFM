const GEO_OPTIONS = {
  enableHighAccuracy: true,
  maximumAge: 0,
  timeout: 15_000,
};

export const PRESET_LOCATIONS = {
  hollywood_boulevard: { label: "Hollywood Boulevard (Hollywood & Vine)", latitude: 34.10164, longitude: -118.32667 },
  cairo_egyptian_museum: { label: "Cairo Egyptian Museum", latitude: 30.04785, longitude: 31.23360 },
  jeju: { label: "Jeju City", latitude: 33.509722, longitude: 126.521944 },
  rio_de_janeiro: { label: "Rio de Janeiro", latitude: -22.903, longitude: -43.208 },
};

export function getDeviceCoordinates(geolocation) {
  if (!geolocation) {
    return Promise.reject(new Error("Device location is unavailable in this browser."));
  }
  return new Promise((resolve, reject) => {
    geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude, accuracy } = position.coords;
        if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90 ||
            !Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
          reject(new Error("The device returned invalid coordinates."));
          return;
        }
        resolve({ latitude, longitude, accuracy });
      },
      (error) => reject(new Error(error.message || "Could not get device location.")),
      GEO_OPTIONS,
    );
  });
}

export function radioContext(coordinates, conditions) {
  const localTime = /T(\d{2}:\d{2})/.exec(conditions.time)?.[1];
  const temperature = conditions.temperature_f;
  const precipitation = conditions.precipitation_in;
  if (!localTime || !Number.isFinite(temperature) || !Number.isFinite(precipitation)) {
    throw new Error("The weather service returned incomplete current conditions.");
  }
  return {
    latitude: coordinates.latitude,
    longitude: coordinates.longitude,
    weather: `${temperature} F, ${precipitation} in precipitation`,
    time: localTime,
  };
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) {
    throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${response.status}).`);
  }
  return body;
}

if (typeof document !== "undefined") {
  const locationChoice = document.querySelector("#location-choice");
  const status = document.querySelector("#status");
  const error = document.querySelector("#error");
  const retry = document.querySelector("#retry");
  const preview = document.querySelector("#preview");
  const coordinatesOutput = document.querySelector("#coordinates");
  const weatherOutput = document.querySelector("#weather");
  const result = document.querySelector("#result");
  let requestVersion = 0;

  async function refreshContext() {
    const version = ++requestVersion;
    const selection = locationChoice.value;
    const preset = Object.hasOwn(PRESET_LOCATIONS, selection)
      ? PRESET_LOCATIONS[selection]
      : undefined;
    status.textContent = preset ? `Using ${preset.label}…` : "Requesting device location…";
    error.textContent = "";
    retry.hidden = true;
    preview.disabled = true;
    let coordinates;
    if (preset) {
      coordinates = preset;
    } else if (selection === "device") {
      if (!window.isSecureContext) {
        throw new Error("Device location requires HTTPS, or localhost on this device.");
      }
      coordinates = await getDeviceCoordinates(navigator.geolocation);
    } else {
      throw new Error("Unknown location preset.");
    }
    if (version !== requestVersion) return null;
    const accuracy = Number.isFinite(coordinates.accuracy)
      ? ` (estimated accuracy ±${Math.round(coordinates.accuracy)} m)`
      : "";
    const label = preset?.label || "Current device";
    coordinatesOutput.textContent = `${label}: ${coordinates.latitude.toFixed(5)}, ${coordinates.longitude.toFixed(5)}${accuracy}`;
    status.textContent = "Fetching current weather…";
    const params = new URLSearchParams({
      latitude: String(coordinates.latitude),
      longitude: String(coordinates.longitude),
    });
    const conditions = await fetchJson(`/weather?${params}`);
    if (version !== requestVersion) return null;
    const context = radioContext(coordinates, conditions);
    weatherOutput.textContent = `${context.weather} at ${context.time} local time`;
    status.textContent = "Location and weather are ready.";
    preview.disabled = false;
    return context;
  }

  async function loadLocation() {
    const version = requestVersion + 1;
    try {
      await refreshContext();
    } catch (cause) {
      if (version !== requestVersion) return;
      status.textContent = "Location is unavailable.";
      error.textContent = cause.message;
      retry.hidden = false;
    }
  }

  retry.addEventListener("click", loadLocation);
  locationChoice.addEventListener("change", () => {
    result.textContent = "";
    return loadLocation();
  });
  preview.addEventListener("click", async () => {
    result.textContent = "";
    const version = requestVersion + 1;
    try {
      const context = await refreshContext();
      if (!context) return;
      status.textContent = "Preparing a radio section…";
      preview.disabled = true;
      const action = await fetchJson("/radio/next", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...context, current_state: "music", played_history: [] }),
      });
      if (version !== requestVersion) return;
      result.textContent = action.mode === "music"
        ? `${action.song_title} — ${action.artist}`
        : action.text;
      status.textContent = "Radio preview is ready.";
    } catch (cause) {
      if (version !== requestVersion) return;
      status.textContent = "Could not prepare a radio preview.";
      error.textContent = cause.message;
      retry.hidden = false;
    } finally {
      if (version === requestVersion) preview.disabled = !retry.hidden;
    }
  });

  loadLocation();
}
