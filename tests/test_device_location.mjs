import assert from "node:assert/strict";
import test from "node:test";

import { getDeviceCoordinates, PRESET_LOCATIONS, radioContext } from "../app/location_api/client.mjs";

test("gets a fresh high-accuracy position from the device", async () => {
  const geolocation = {
    getCurrentPosition(success, _failure, options) {
      assert.deepEqual(options, {
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: 15_000,
      });
      success({ coords: { latitude: 32.7157, longitude: -117.1611, accuracy: 12 } });
    },
  };
  assert.deepEqual(await getDeviceCoordinates(geolocation), {
    latitude: 32.7157,
    longitude: -117.1611,
    accuracy: 12,
  });
});

test("propagates denied location permission", async () => {
  const geolocation = {
    getCurrentPosition(_success, failure) {
      failure({ message: "Permission denied" });
    },
  };
  await assert.rejects(getDeviceCoordinates(geolocation), /Permission denied/);
});

test("builds radio context from device coordinates and local weather", () => {
  assert.deepEqual(
    radioContext(
      { latitude: 32.7157, longitude: -117.1611 },
      { time: "2026-10-24T18:30", temperature_f: 68, precipitation_in: 0 },
    ),
    {
      latitude: 32.7157,
      longitude: -117.1611,
      weather: "68 F, 0 in precipitation",
      time: "18:30",
    },
  );
});

test("demo presets use distinct locations on the requested streets and cities", () => {
  assert.deepEqual(Object.keys(PRESET_LOCATIONS), [
    "hollywood_boulevard",
    "cairo_egyptian_museum",
    "jeju",
    "rio_de_janeiro",
  ]);
  for (const location of Object.values(PRESET_LOCATIONS)) {
    assert.ok(location.latitude >= -90 && location.latitude <= 90);
    assert.ok(location.longitude >= -180 && location.longitude <= 180);
  }
});

test("page sends device coordinates to weather and radio", async () => {
  const elements = Object.fromEntries(
    ["location-choice", "status", "error", "retry", "preview", "coordinates", "weather", "result"]
      .map((id) => [id, {
        textContent: "",
        value: id === "location-choice" ? "device" : undefined,
        hidden: id === "retry",
        disabled: id === "preview",
        addEventListener(event, listener) { this[event] = listener; },
      }]),
  );
  const original = {
    document: Object.getOwnPropertyDescriptor(globalThis, "document"),
    window: Object.getOwnPropertyDescriptor(globalThis, "window"),
    navigator: Object.getOwnPropertyDescriptor(globalThis, "navigator"),
    fetch: Object.getOwnPropertyDescriptor(globalThis, "fetch"),
  };
  const requests = [];
  let positionCalls = 0;
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: { querySelector: (selector) => elements[selector.slice(1)] },
  });
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { isSecureContext: true },
  });
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: { geolocation: {
      getCurrentPosition(success) {
        positionCalls += 1;
        success({ coords: { latitude: 32.7157, longitude: -117.1611, accuracy: 12 } });
      },
    } },
  });
  Object.defineProperty(globalThis, "fetch", {
    configurable: true,
    value: async (url, options) => {
      requests.push({ url, options });
      return {
        ok: true,
        json: async () => url.startsWith("/weather?")
          ? { time: "2026-10-24T18:30", temperature_f: 68, precipitation_in: 0 }
          : { mode: "narration", text: "A sunny evening." },
      };
    },
  });
  try {
    await import("../app/location_api/client.mjs?integration-test");
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(elements.preview.disabled, false);
    await elements.preview.click();
    assert.equal(positionCalls, 2);
    assert.equal(requests.length, 3);
    assert.equal(new URL(requests[0].url, "http://localhost").searchParams.get("latitude"), "32.7157");
    assert.equal(new URL(requests[1].url, "http://localhost").searchParams.get("longitude"), "-117.1611");
    assert.equal(requests[2].url, "/radio/next");
    assert.deepEqual(JSON.parse(requests[2].options.body), {
      latitude: 32.7157,
      longitude: -117.1611,
      weather: "68 F, 0 in precipitation",
      time: "18:30",
      current_state: "music",
      played_history: [],
    });
    assert.equal(elements.result.textContent, "A sunny evening.");

    elements["location-choice"].value = "cairo_egyptian_museum";
    await elements["location-choice"].change();
    assert.equal(positionCalls, 2);
    assert.equal(new URL(requests[3].url, "http://localhost").searchParams.get("latitude"), "30.04785");
    await elements.preview.click();
    assert.equal(positionCalls, 2);
    assert.deepEqual(JSON.parse(requests[5].options.body), {
      latitude: 30.04785,
      longitude: 31.2336,
      weather: "68 F, 0 in precipitation",
      time: "18:30",
      current_state: "music",
      played_history: [],
    });
  } finally {
    for (const [name, descriptor] of Object.entries(original)) {
      if (descriptor) {
        Object.defineProperty(globalThis, name, descriptor);
      } else {
        delete globalThis[name];
      }
    }
  }
});
