# Design Tokens & Theme Specification (sys_info Flet GUI)

## 1. Visual World & Direction
- **Mode**: Operate (Real-time telemetry, mission-critical hardware observability).
- **Aesthetic**: Neon Cyberpunk on Dark Space Deep Violet (`#07050f`).
- **Typography**: Outfit (`woff2`), geometric tech-sans with distinct numbers.
- **Contrast Floor**: High readability against dark backgrounds (WCAG AA compliant).

## 2. Color Tokens

### Surfaces & Backgrounds
- `BG_APP`: `#07050f` (Dark Space deep void canvas)
- `BG_CARD`: `#110b1f` (Primary card surface)
- `BG_SUB`: `#0a0814` (Inset expandable sub-surface)
- `BG_INPUT`: `#100b1a` (Dropdown and chart container background)
- `BG_BAR`: `#1a122e` (Progress bar track)
- `BG_BUTTON_DEFAULT`: `#120e24` (Segmented button unselected)
- `BG_BUTTON_SELECTED`: `#22173b` (Segmented button active state)

### Borders & Dividers
- `BORDER_SUBTLE`: `#22173b` (Card edges, chart frame, dividers)
- `BORDER_FOCUS`: `#00d4ff` (Neon Cyan highlight ring on focus)

### Typography / Text Colors
- `TEXT_PRIMARY`: `#e6edf3` (Off-white high contrast: 15.6:1 on BG_APP)
- `TEXT_SECONDARY`: `#9ea7b3` (Refined technical gray: 6.8:1 on BG_CARD, exceeds WCAG AA 4.5:1)
- `TEXT_DIM`: `#7d8590` (Muted timestamps/symbols)

### Metric Accents
- `ACCENT_CYAN`: `#00d4ff` (Primary brand accent, header, network upload)
- `ACCENT_GREEN`: `#00f5a0` (Healthy status, CPU & network download)
- `ACCENT_MAGENTA`: `#f857a6` (RAM, AI inference, memory badges)
- `ACCENT_ORANGE`: `#ff8a00` (Power consumption, warnings)
- `ACCENT_VIOLET`: `#b388ff` (Disks, timeline, system totals)
- `ACCENT_RED`: `#ff5252` (High-severity threshold alerts)

## 3. Component Standards
- **Buttons / Click Targets**: Minimum target area 36x36px with explicit padding and hover glow.
- **Badges**: Standardized padding `(6, 2)`, border radius `6px`, and safe opacity channel.
- **UX Copy**: Standardized Technical English (Processor, Memory, Video Cards, Storage, Network, AI Inference).
