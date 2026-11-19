# 🚀 hass-foscam v0.1.0-alpha.5 — Optical Zoom, Focus Controls & Action UI Selectors

## Optical Zoom & Focus Services

Added dedicated entity services for cameras supporting motorized lens adjustment:
- **`foscam.zoom`**: Control optical zoom with `direction: in | out | stop` and optional `travel_time` (default 0.125s).
- **`foscam.focus`**: Adjust lens focus manually with `direction: near | far | stop` and optional `travel_time` (default 0.125s).
- **`foscam.ptz`**: Added support for `movement: stop`.

## Home Assistant Action UI Integration

All entity services (`ptz`, `ptz_preset`, `zoom`, `focus`, and `prune_recordings`) now declare explicit target filters:
```yaml
target:
  entity:
    integration: foscam
    domain: camera
```
When using the Developer Tools → Actions or automations editor:
- Target selection is restricted to Foscam camera entities and placed in `target.entity_id`.
- Direction and movement options appear in structured dropdown menus with bounds-checked numeric selectors for travel times and retention days.

## Dependency Updates

- Pinned `pyfoscam` requirement to [`v0.1.0-alpha.3`](https://github.com/twrecked/pyfoscam/releases/tag/v0.1.0-alpha.3).
