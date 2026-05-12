/** Polymarket geofencing.

Polymarket restricts users in 33 countries. Estonia (EE) is allowed.
This module mirrors the trader's restricted list (apps/trader/src/trader/config.py)
and enforces a hard startup gate for live mode and a per-order check.

Source of truth: https://help.polymarket.com/en/articles/13364163-geographic-restrictions
*/

export const POLYMARKET_RESTRICTED_COUNTRIES: ReadonlySet<string> = new Set([
  "AU",
  "BE",
  "BY",
  "BI",
  "CF",
  "CD",
  "CU",
  "DE",
  "ET",
  "FR",
  "GB",
  "IR",
  "IQ",
  "IT",
  "JP",
  "KP",
  "LB",
  "LY",
  "MM",
  "NI",
  "PL",
  "RU",
  "SG",
  "SO",
  "SS",
  "SD",
  "SY",
  "TH",
  "TW",
  "US",
  "VE",
  "YE",
  "ZW",
]);

export interface GeofenceResult {
  allowed: boolean;
  locale: string;
  reason?: string;
}

/** Pure check used by both startup gate and per-request gate. */
export function checkGeofence(locale: string | undefined | null): GeofenceResult {
  const normalised = (locale ?? "").trim().toUpperCase();
  if (!normalised) {
    return {
      allowed: false,
      locale: "",
      reason: "LOCALE is not set; live mode requires an explicit non-restricted locale",
    };
  }
  if (POLYMARKET_RESTRICTED_COUNTRIES.has(normalised)) {
    return {
      allowed: false,
      locale: normalised,
      reason: `geofence_restricted: locale ${normalised} is on Polymarket's restricted list`,
    };
  }
  return { allowed: true, locale: normalised };
}

/** Startup gate. Throws on restricted locale so the service refuses to start in live mode. */
export function assertGeoEligibleForLive(locale: string | undefined | null): void {
  const result = checkGeofence(locale);
  if (!result.allowed) {
    throw new Error(result.reason ?? "geofence_restricted");
  }
}
