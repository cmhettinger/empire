# Open-Meteo and Meteocons Integration Plan

## Objective

Integrate Open-Meteo into the existing `empire-weather` package as an additional weather-data provider while preserving the current normalized snapshot, raw-source retention, artifact storage, attribution, and audit/debugging conventions.

Add Meteocons as a reusable, provider-independent weather icon set that can render normalized Empire weather conditions rather than depending directly on Open-Meteo-specific codes.

The implementation should not replace the existing OpenWeather, NWS, AccuWeather, or government imagery integrations.

## Scope

The first implementation should:

* Add Open-Meteo forecast data for Ashburn, Virginia, and Savannah, Georgia.
* Retain the complete raw Open-Meteo response for every successful fetch.
* Normalize selected Open-Meteo data into the existing Empire weather snapshot.
* Preserve source-specific forecast values without silently averaging providers.
* Add Meteocons static SVG assets under the appropriate license.
* Create provider-independent condition and icon mappings.
* Support both daily forecast icons and day/night hourly forecast icons.
* Generate at least one reusable forecast-summary graphic using the normalized data and Meteocons.
* Include Open-Meteo and Meteocons attribution and license metadata.
* Follow the package’s existing configuration, logging, retry, object-store, testing, and reporting conventions.

## Out of Scope for Initial Integration

Do not include these items in the first implementation unless they are already trivial within the current package architecture:

* Replacing OpenWeather as the canonical forecast provider.
* Replacing NWS alerts, forecast discussions, or official products.
* Replacing AccuWeather health and activity indexes.
* Replacing NOAA, WPC, SPC, NHC, UV, drought, satellite, or other government imagery.
* Open-Meteo air-quality integration.
* Historical forecast verification or forecast-provider scoring.
* Ensemble-member analysis.
* Automatic consensus or averaging across forecast providers.
* Interactive maps.
* Reproducing Home Assistant’s frontend weather card exactly.

---

# Buildout Plan

| ID    | Status | Goal                                                       | Complete When                                                                                                                                                                                                                                                                                  | Depends On   |
| ----- | ------ | ---------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| OM1.1 | [ ]    | Review the existing `empire-weather` provider architecture | Document how OpenWeather, NWS, AccuWeather, and image providers are configured, fetched, normalized, persisted, logged, and tested. Identify the exact interfaces and conventions the Open-Meteo implementation must follow.                                                                   | —            |
| OM1.2 | [ ]    | Review the current normalized weather snapshot schema      | Document the current canonical structures for locations, current conditions, hourly forecasts, daily forecasts, source attribution, raw-source references, units, timestamps, alerts, astronomy, air quality, and imagery. Identify fields Open-Meteo can populate without changing semantics. | OM1.1        |
| OM1.3 | [ ]    | Define the Open-Meteo integration boundary                 | Document which Open-Meteo endpoints and variables are included in the initial implementation. Use the general forecast API or the NOAA/GFS API only where it provides a clear benefit. Do not add unrelated APIs such as air quality or historical forecasts in this phase.                    | OM1.1, OM1.2 |
| OM1.4 | [ ]    | Define provider precedence and non-blending rules          | Document that Open-Meteo is initially supplemental. Preserve OpenWeather, NWS, and Open-Meteo values independently. Do not average or overwrite canonical values unless an existing explicit provider-priority rule already allows it.                                                         | OM1.2, OM1.3 |
| OM1.5 | [ ]    | Define supported Open-Meteo locations                      | Add or confirm configuration for Ashburn, Virginia, and Savannah, Georgia using stable latitude, longitude, display name, location identifier, timezone, and unit preferences. Reuse existing location configuration where possible.                                                           | OM1.1        |
| OM1.6 | [ ]    | Define Open-Meteo source attribution requirements          | Document the required Open-Meteo attribution, underlying model attribution where available, CC BY 4.0 data licensing, retrieval timestamp, endpoint, model selection, coordinates, timezone, and request parameters to retain in source metadata.                                              | OM1.3        |

## Open-Meteo Client

| ID    | Status | Goal                                          | Complete When                                                                                                                                                                                                                                                                          | Depends On                 |
| ----- | ------ | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| OM2.1 | [ ]    | Add Open-Meteo configuration models           | Add typed configuration for enabling the provider, base URL, endpoint, forecast horizon, requested variables, timeout, retry policy, units, timezone behavior, and location selection. Use the package’s existing configuration conventions.                                           | OM1.3, OM1.5               |
| OM2.2 | [ ]    | Add the Open-Meteo HTTP client                | Implement a provider client using the package’s existing HTTP abstraction or `httpx` conventions. Include explicit timeout handling, retry behavior, user agent, structured logging, and response validation.                                                                          | OM2.1                      |
| OM2.3 | [ ]    | Build the Open-Meteo request parameter set    | Request only the current, hourly, and daily variables required by the approved integration scope. Include `weather_code`, relevant temperatures, apparent temperature, precipitation, precipitation probability, humidity, wind, gusts, sunrise, sunset, and `is_day` where supported. | OM1.3, OM2.2               |
| OM2.4 | [ ]    | Use explicit U.S. units and local timezones   | Ensure temperatures use Fahrenheit, wind uses miles per hour, precipitation uses inches, and timestamps are returned or normalized for the configured location timezone. Do not rely on implicit defaults.                                                                             | OM2.3                      |
| OM2.5 | [ ]    | Validate Open-Meteo response structure        | Add typed parsing or explicit schema validation for latitude, longitude, generation time, timezone, UTC offset, units, current values, hourly arrays, and daily arrays. Fail clearly on mismatched array lengths or missing required fields.                                           | OM2.3                      |
| OM2.6 | [ ]    | Handle optional and unavailable fields safely | Permit individual optional variables to be absent without failing the entire provider run. Record missing fields and degraded results using existing package status and warning conventions.                                                                                           | OM2.5                      |
| OM2.7 | [ ]    | Add provider-level error classification       | Distinguish transport errors, timeouts, rate limits, invalid requests, malformed responses, partial responses, and upstream server failures. Preserve enough context for audit and debugging without exposing secrets.                                                                 | OM2.2, OM2.5               |
| OM2.8 | [ ]    | Add Open-Meteo provider tests                 | Add deterministic tests for request construction, units, timezones, successful parsing, missing fields, malformed arrays, HTTP failures, retries, and partial responses. Mock network calls using the package’s established test pattern.                                              | OM2.2, OM2.5, OM2.6, OM2.7 |

## Raw Response and Artifact Retention

| ID    | Status | Goal                                           | Complete When                                                                                                                                                                          | Depends On                 |
| ----- | ------ | ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| OM3.1 | [ ]    | Retain the raw Open-Meteo response             | Store the complete upstream JSON response for each location and run using the existing run-level object-store conventions. Do not retain only the normalized subset.                   | OM2.5                      |
| OM3.2 | [ ]    | Retain Open-Meteo request metadata             | Store the endpoint, query parameters, location, retrieval timestamp, response status, content type, and relevant response headers alongside or within the raw-source metadata.         | OM2.3, OM3.1               |
| OM3.3 | [ ]    | Define stable Open-Meteo object-store keys     | Add predictable logical names and object keys for Ashburn and Savannah raw responses. Follow the package’s existing domain, provider, location, run, and retention naming conventions. | OM1.1, OM3.1               |
| OM3.4 | [ ]    | Link normalized snapshot data to raw artifacts | Ensure the normalized Open-Meteo source block references the corresponding raw object-store artifact or logical object identifier for auditability.                                    | OM3.1, OM3.3               |
| OM3.5 | [ ]    | Test raw-response persistence                  | Verify successful, partial, and failed provider attempts produce the expected raw artifacts and metadata according to existing retention rules.                                        | OM3.1, OM3.2, OM3.3, OM3.4 |

## Open-Meteo Normalization

| ID    | Status | Goal                                        | Complete When                                                                                                                                                                                                           | Depends On                        |
| ----- | ------ | ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| OM4.1 | [ ]    | Add an Open-Meteo source model              | Add typed source-specific models for Open-Meteo current, hourly, and daily forecast values before conversion into the canonical snapshot. Preserve upstream units and timestamps during parsing.                        | OM2.5                             |
| OM4.2 | [ ]    | Normalize current conditions                | Map supported Open-Meteo current-condition fields into the package’s normalized source representation without replacing values from existing providers. Include source attribution and retrieval metadata.              | OM4.1, OM1.4                      |
| OM4.3 | [ ]    | Normalize hourly forecasts                  | Convert Open-Meteo hourly arrays into ordered timestamped records. Preserve weather code, day/night state, temperatures, precipitation, humidity, wind, and gust values included in the approved request.               | OM4.1                             |
| OM4.4 | [ ]    | Normalize daily forecasts                   | Convert Open-Meteo daily arrays into ordered local-date records. Preserve weather code, high and low temperature, precipitation probability and amount, wind, gusts, sunrise, and sunset where requested.               | OM4.1                             |
| OM4.5 | [ ]    | Preserve Open-Meteo model provenance        | Record the requested endpoint, requested model or best-match behavior, returned model metadata where available, and underlying-source attribution without overstating model certainty.                                  | OM1.6, OM4.2, OM4.3, OM4.4        |
| OM4.6 | [ ]    | Add Open-Meteo to the consolidated snapshot | Add a clearly named Open-Meteo source section to each configured location in the run-level snapshot. Keep source data separate from canonical or consolidated values unless current package rules explicitly select it. | OM4.2, OM4.3, OM4.4, OM4.5        |
| OM4.7 | [ ]    | Add source-comparison metadata              | Where equivalent values exist, calculate non-authoritative comparison fields such as provider spread or agreement only if the package already has a suitable derived-data area. Do not alter source values.             | OM4.6                             |
| OM4.8 | [ ]    | Add normalization tests                     | Add fixture-based tests for current, hourly, and daily normalization, timestamp ordering, timezone handling, missing values, unit consistency, provenance, and raw-artifact references.                                 | OM4.2, OM4.3, OM4.4, OM4.5, OM4.6 |

## Provider Orchestration

| ID    | Status | Goal                                       | Complete When                                                                                                                                                                                                                        | Depends On   |
| ----- | ------ | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------ |
| OM5.1 | [ ]    | Register Open-Meteo as a package provider  | Add Open-Meteo to the provider registry, dependency wiring, command entry point, or service container used by the package. Preserve the package’s existing provider enable/disable behavior.                                         | OM2.8, OM4.8 |
| OM5.2 | [ ]    | Add Open-Meteo to the weather run workflow | Invoke the Open-Meteo provider once per configured location during the normal snapshot build. A provider failure must follow the package’s established degraded-run policy rather than preventing unrelated sources from completing. | OM5.1        |
| OM5.3 | [ ]    | Add Open-Meteo status to run summaries     | Include success, partial, skipped, or failed status for each location, plus request counts, normalized record counts, and raw artifact references where the current summary format supports them.                                    | OM5.2        |
| OM5.4 | [ ]    | Confirm rate-limit-safe request behavior   | Verify the implementation performs the minimum required calls, does not request each variable separately, and remains comfortably within Open-Meteo’s free non-commercial usage limits.                                              | OM2.3, OM5.2 |
| OM5.5 | [ ]    | Add end-to-end provider workflow tests     | Test a complete weather run with successful Open-Meteo responses, one-location failure, provider disabled, partial data, and raw artifact persistence.                                                                               | OM5.2, OM5.3 |

## Canonical Weather Conditions

| ID    | Status | Goal                                                | Complete When                                                                                                                                                                                                                   | Depends On          |
| ----- | ------ | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| MC1.1 | [ ]    | Review existing condition normalization             | Identify whether the package already has canonical condition names or enums for clear, partly cloudy, overcast, fog, drizzle, rain, snow, sleet, thunderstorms, and unknown conditions. Reuse existing concepts where possible. | OM1.2               |
| MC1.2 | [ ]    | Define a provider-independent Empire condition enum | Add or refine a compact versioned condition enum that represents the conditions required for display and reporting. Avoid provider-specific names and avoid creating a generic rules engine.                                    | MC1.1               |
| MC1.3 | [ ]    | Add Open-Meteo WMO-code mapping                     | Map every Open-Meteo weather code supported by the API into an Empire canonical condition and severity where appropriate. Include an explicit unknown fallback and tests for every documented code.                             | MC1.2, OM4.1        |
| MC1.4 | [ ]    | Map existing OpenWeather conditions                 | Map the current OpenWeather weather identifiers into the same Empire canonical condition enum without changing existing normalized data semantics.                                                                              | MC1.2               |
| MC1.5 | [ ]    | Map existing NWS conditions where feasible          | Map NWS forecast condition text or existing normalized condition fields into the same enum only where deterministic mappings already exist. Preserve the original NWS text.                                                     | MC1.2               |
| MC1.6 | [ ]    | Define day/night rendering inputs                   | Standardize how renderers determine daytime versus nighttime. Prefer provider-supplied `is_day` for hourly Open-Meteo records and local sunrise/sunset or an existing astronomy helper for other providers.                     | MC1.2, OM4.3, OM4.4 |
| MC1.7 | [ ]    | Add condition normalization tests                   | Cover all Open-Meteo WMO codes, representative OpenWeather codes, unknown values, severity distinctions, and day/night inputs.                                                                                                  | MC1.3, MC1.4, MC1.6 |

## Meteocons Asset Integration

| ID    | Status | Goal                                           | Complete When                                                                                                                                                                                                                                     | Depends On          |
| ----- | ------ | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| MC2.1 | [ ]    | Select the Meteocons asset package and style   | Choose a specific Meteocons release and asset style suitable for static rendering. Prefer static SVG assets. Document whether the package will vendor the assets or retrieve them through the build system.                                       | —                   |
| MC2.2 | [ ]    | Verify Meteocons licensing                     | Confirm the selected Meteocons assets are covered by the MIT license. Add the upstream license text, copyright notice, source URL, selected version, and attribution to the repository’s third-party notices.                                     | MC2.1               |
| MC2.3 | [ ]    | Vendor or package the approved SVG assets      | Add only the icons required by the Empire condition mapping, plus an unknown/not-available fallback. Store them in a stable package resource path and ensure they are included in Python package builds.                                          | MC2.1, MC2.2        |
| MC2.4 | [ ]    | Define the canonical condition-to-icon mapping | Map each Empire condition and day/night state to an exact Meteocons SVG filename. Use one central mapping shared by all providers and renderers.                                                                                                  | MC1.2, MC1.6, MC2.3 |
| MC2.5 | [ ]    | Handle severity-specific icon selection        | Where the canonical model distinguishes ordinary and severe rain, snow, or thunderstorms, map those states to distinct Meteocons assets only when the distinction is supported by normalized source data.                                         | MC2.4               |
| MC2.6 | [ ]    | Add a safe icon resolver                       | Implement a resolver that accepts canonical condition, day/night state, and optional severity and returns a validated package-resource reference. Unknown or missing values must return the fallback icon rather than raising an unhandled error. | MC2.4, MC2.5        |
| MC2.7 | [ ]    | Add package-resource loading support           | Ensure SVG files can be loaded reliably from source checkouts, installed wheels, containers, tests, and report-rendering environments using the project’s preferred resource-loading mechanism.                                                   | MC2.3               |
| MC2.8 | [ ]    | Add icon mapping tests                         | Verify every canonical condition resolves to an existing asset, day/night variants are selected correctly, all referenced package files exist, and unknown conditions use the fallback icon.                                                      | MC2.6, MC2.7        |
| MC2.9 | [ ]    | Add an icon contact sheet test artifact        | Generate a development-only contact sheet or HTML/PDF test artifact showing every canonical condition, its name, day/night variant, and selected Meteocons asset. Use it for visual review and regression testing.                                | MC2.6, MC2.8        |

## Forecast Graphic Rendering

| ID     | Status | Goal                                                 | Complete When                                                                                                                                                                                                                                                          | Depends On                 |
| ------ | ------ | ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| FG1.1  | [ ]    | Review existing image-generation conventions         | Identify the package’s current approach for rendering, storing, naming, and retaining generated PNG, SVG, or PDF-support graphics. Reuse the existing reporting and object-store infrastructure.                                                                       | OM1.1                      |
| FG1.2  | [ ]    | Define a provider-independent forecast graphic model | Create a small rendering input model containing location, generated timestamp, daily date, label, canonical condition, icon reference, high, low, precipitation probability, and optional source label. It must not depend directly on Open-Meteo response objects.    | MC1.2, MC2.6               |
| FG1.3  | [ ]    | Define source-selection rules for graphics           | Document which normalized provider supplies the values used by the initial forecast graphic. Preserve OpenWeather as the source if it is currently canonical, or explicitly configure Open-Meteo for the new graphic. Include the selected source in graphic metadata. | OM1.4, OM4.6, FG1.2        |
| FG1.4  | [ ]    | Implement a multi-day forecast strip                 | Generate a polished static forecast summary showing several days with weekday/date, Meteocons icon, high/low temperatures, and precipitation probability. Follow Empire brand standards and existing report typography.                                                | FG1.1, FG1.2, FG1.3, MC2.7 |
| FG1.5  | [ ]    | Support configurable forecast length                 | Allow the renderer to generate a reasonable configurable range, such as five, seven, or ten days, while maintaining readable layout and deterministic output dimensions.                                                                                               | FG1.4                      |
| FG1.6  | [ ]    | Add accessible weather labels                        | Ensure every icon has a corresponding textual condition label in graphic metadata and any HTML/SVG accessibility fields supported by the renderer. Do not rely on artwork alone to communicate the forecast.                                                           | FG1.4                      |
| FG1.7  | [ ]    | Retain generated forecast graphics                   | Store the generated image as a run-level artifact with stable logical name, source-provider metadata, location, generation timestamp, selected forecast range, and content type.                                                                                       | FG1.4, FG1.5               |
| FG1.8  | [ ]    | Reference the graphic from the run snapshot          | Add the generated forecast graphic’s artifact reference to the appropriate location or report-artifacts section of the normalized run snapshot.                                                                                                                        | FG1.7                      |
| FG1.9  | [ ]    | Add deterministic rendering tests                    | Test layout construction, source selection, missing values, fallback icons, forecast truncation, and artifact naming. Use visual regression or image-dimension checks where supported by the repository.                                                               | FG1.4, FG1.5, FG1.6, FG1.7 |
| FG1.10 | [ ]    | Add a representative rendered fixture                | Commit or generate a test artifact using fictional or fixed forecast data for visual review. Do not make tests depend on live Open-Meteo data.                                                                                                                         | FG1.9                      |

## Reporting and Attribution

| ID    | Status | Goal                                             | Complete When                                                                                                                                                                                      | Depends On                        |
| ----- | ------ | ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| RA1.1 | [ ]    | Add Open-Meteo attribution to snapshot metadata  | Include Open-Meteo attribution, data license, endpoint, retrieval timestamp, coordinates, timezone, and model information in the source metadata.                                                  | OM1.6, OM4.5                      |
| RA1.2 | [ ]    | Add Meteocons attribution to generated artifacts | Include Meteocons project name, selected version, MIT license, and upstream attribution in generated artifact metadata or package-level third-party notices.                                       | MC2.2, FG1.7                      |
| RA1.3 | [ ]    | Update weather report source notes               | Add Open-Meteo to any generated report source list while clearly distinguishing it from NWS official products and downloaded government imagery.                                                   | OM4.6, RA1.1                      |
| RA1.4 | [ ]    | Update package documentation                     | Document configuration, endpoints, requested variables, provider role, raw-response retention, normalized output, icon mapping, asset licensing, forecast graphic generation, and troubleshooting. | OM5.3, MC2.8, FG1.8, RA1.1, RA1.2 |
| RA1.5 | [ ]    | Add sample normalized output                     | Add a sanitized example showing the Open-Meteo source block, canonical condition, Meteocons icon reference, provenance, raw-artifact reference, and generated forecast graphic reference.          | OM4.6, MC2.6, FG1.8               |
| RA1.6 | [ ]    | Update operational runbooks                      | Add provider enablement, expected artifacts, common failures, rate-limit behavior, upstream outage behavior, license notes, and procedures for upgrading the Meteocons version.                    | OM5.3, MC2.2, RA1.4               |

## Validation and Release

| ID    | Status | Goal                                       | Complete When                                                                                                                                                                                                                                                                                       | Depends On                                      |
| ----- | ------ | ------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| VR1.1 | [ ]    | Run the complete automated test suite      | All existing package tests and all new Open-Meteo, normalization, icon, artifact, and rendering tests pass without weakening unrelated assertions.                                                                                                                                                  | OM5.5, MC2.9, FG1.10, RA1.5                     |
| VR1.2 | [ ]    | Validate live Ashburn output               | Run a live integration for Ashburn and verify current, hourly, and daily Open-Meteo data, local timestamps, units, raw artifact retention, attribution, icon selection, and generated graphic output.                                                                                               | VR1.1                                           |
| VR1.3 | [ ]    | Validate live Savannah output              | Run a live integration for Savannah and verify current, hourly, and daily Open-Meteo data, local timestamps, units, raw artifact retention, attribution, icon selection, and generated graphic output.                                                                                              | VR1.1                                           |
| VR1.4 | [ ]    | Compare provider outputs without blending  | Produce a validation summary comparing representative OpenWeather, NWS, and Open-Meteo values. Confirm differences remain source-specific and no undocumented averaging or overwriting occurs.                                                                                                      | VR1.2, VR1.3                                    |
| VR1.5 | [ ]    | Validate degraded-run behavior             | Simulate Open-Meteo timeout, malformed response, missing variables, and one-location failure. Confirm the overall weather run follows existing partial-success rules and retains useful diagnostics.                                                                                                | VR1.1                                           |
| VR1.6 | [ ]    | Validate packaged asset availability       | Build the distributable package and container image, install them in a clean environment, and confirm all required Meteocons assets can be resolved and rendered.                                                                                                                                   | MC2.7, VR1.1                                    |
| VR1.7 | [ ]    | Perform visual review of forecast graphics | Review Ashburn and Savannah forecast graphics for alignment, clipping, icon clarity, contrast, typography, missing-data behavior, and consistency with Empire brand standards.                                                                                                                      | VR1.2, VR1.3, VR1.6                             |
| VR1.8 | [ ]    | Record implementation decisions            | Add an architecture decision or implementation note documenting why Open-Meteo is supplemental, why Meteocons is provider-independent, how condition mappings work, and how future providers should integrate with the same renderer.                                                               | VR1.4, VR1.7                                    |
| VR1.9 | [ ]    | Mark the integration production-ready      | The integration is enabled through configuration, both locations complete successfully, raw and normalized artifacts are retained, icons resolve from packaged assets, forecast graphics render correctly, attribution is present, documentation is complete, and degraded runs behave as designed. | VR1.2, VR1.3, VR1.4, VR1.5, VR1.6, VR1.7, VR1.8 |

---

# Recommended Initial Open-Meteo Variables

Codex should confirm these against the current Open-Meteo API documentation and the existing normalized schema before implementation.

## Current

* `temperature_2m`
* `relative_humidity_2m`
* `apparent_temperature`
* `is_day`
* `precipitation`
* `rain`
* `showers`
* `snowfall`
* `weather_code`
* `cloud_cover`
* `pressure_msl`
* `surface_pressure`
* `wind_speed_10m`
* `wind_direction_10m`
* `wind_gusts_10m`

## Hourly

* `temperature_2m`
* `relative_humidity_2m`
* `dew_point_2m`
* `apparent_temperature`
* `precipitation_probability`
* `precipitation`
* `rain`
* `showers`
* `snowfall`
* `weather_code`
* `cloud_cover`
* `visibility`
* `wind_speed_10m`
* `wind_direction_10m`
* `wind_gusts_10m`
* `is_day`

## Daily

* `weather_code`
* `temperature_2m_max`
* `temperature_2m_min`
* `apparent_temperature_max`
* `apparent_temperature_min`
* `sunrise`
* `sunset`
* `daylight_duration`
* `sunshine_duration`
* `precipitation_sum`
* `rain_sum`
* `showers_sum`
* `snowfall_sum`
* `precipitation_hours`
* `precipitation_probability_max`
* `wind_speed_10m_max`
* `wind_gusts_10m_max`
* `wind_direction_10m_dominant`

Do not request variables that are not consumed, retained for a documented purpose, or used in future approved work.

---

# Recommended Internal Mapping Flow

```text
Open-Meteo weather code
        ↓
Empire canonical weather condition
        ↓
Empire day/night and severity context
        ↓
Meteocons asset resolver
        ↓
Provider-independent forecast graphic
```

Existing providers should converge into the same middle layer:

```text
OpenWeather condition code ─┐
Open-Meteo WMO code ────────┼─> Empire canonical condition
NWS normalized condition ───┘
                                      ↓
                              Meteocons resolver
                                      ↓
                          Shared Empire renderers
```

---

# Implementation Constraints

* Follow existing package architecture instead of introducing a parallel framework.
* Reuse the existing HTTP, retry, configuration, logging, run-context, object-store, and artifact abstractions.
* Keep raw provider responses immutable.
* Keep normalized source values distinct by provider.
* Do not silently average weather values.
* Preserve original provider condition codes and text alongside canonical conditions.
* Use a single central condition-to-icon mapping.
* Treat missing and unknown conditions explicitly.
* Use deterministic local timestamps and explicit timezones.
* Use explicit U.S. units.
* Pin the Meteocons version.
* Include all required third-party license notices.
* Package SVG assets so they work from installed wheels and containers.
* Do not depend on network access to render icons.
* Do not make tests depend on live provider responses.
* Ensure one provider failure does not unnecessarily fail the whole weather snapshot.
