# UI maintenance

Read ../docs/ui/chart-interactions.md before changing charts or interactions. It is the authoritative UI reference; the root chart specification owns the data contract.

- English only. Keep the page focused on charts and list selection.
- Use native Lightweight Charts APIs for panes, crosshairs, scrolling and scaling.
- Keep indicators and provisional candles in Python; never duplicate their calculations here.
- Remove unused DOM and rendering paths when removing UI, rather than hiding them with CSS.
- Rebuild public/main.js and any other generated modules with npm run build after editing src.
- Production and simulator use the same UI/API. No random-data branch in the frontend.
