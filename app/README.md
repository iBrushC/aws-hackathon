# Whisker

Chest-cam powered meet-logger. Pure HTML / CSS / JS, no build step.

## Run

Pick any one:

- Python 3: `python -m http.server 5173`
- Node: `npx serve .`
- PHP: `php -S localhost:5173`

Then open http://localhost:5173

## Files

- `index.html` - markup
- `styles.css` - DM Sans + Lora, black/white with pale-blue accent
- `app.js` - camera, controls, people/summary state (mock data; no backend)

## Notes

Camera capture uses `getUserMedia` locally. Person detection and summary
generation are stubbed in `app.js` (look for `simulateEncounters`,
`buildMockSummary`, `buildMockActionItems`) - swap these for real
inference / API calls when the backend lands.
