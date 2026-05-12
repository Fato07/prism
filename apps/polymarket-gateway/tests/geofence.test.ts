/** Tests for VAL-TRADE-006: Polymarket geofencing gate.

- Estonia (EE) is allowed.
- All 33 restricted countries refuse.
- Missing LOCALE refuses.
*/

import { describe, expect, it } from "vitest";

import {
  POLYMARKET_RESTRICTED_COUNTRIES,
  assertGeoEligibleForLive,
  checkGeofence,
} from "../src/geofence.js";

describe("VAL-TRADE-006: geofence checks", () => {
  it("Estonia (EE) is allowed", () => {
    expect(checkGeofence("EE").allowed).toBe(true);
  });

  it("lower-case input is normalised", () => {
    expect(checkGeofence("ee").allowed).toBe(true);
  });

  it("US is refused", () => {
    const r = checkGeofence("US");
    expect(r.allowed).toBe(false);
    expect(r.reason).toMatch(/geofence_restricted/);
  });

  it("GB is refused", () => {
    expect(checkGeofence("GB").allowed).toBe(false);
  });

  it("DE is refused", () => {
    expect(checkGeofence("DE").allowed).toBe(false);
  });

  it("empty locale is refused", () => {
    expect(checkGeofence("").allowed).toBe(false);
  });

  it("undefined locale is refused", () => {
    expect(checkGeofence(undefined).allowed).toBe(false);
  });

  it("contains all 33 restricted countries", () => {
    expect(POLYMARKET_RESTRICTED_COUNTRIES.size).toBe(33);
  });

  it("assertGeoEligibleForLive throws on restricted locale", () => {
    expect(() => assertGeoEligibleForLive("US")).toThrow(/geofence_restricted/);
  });

  it("assertGeoEligibleForLive does not throw on EE", () => {
    expect(() => assertGeoEligibleForLive("EE")).not.toThrow();
  });
});
