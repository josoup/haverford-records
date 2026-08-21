# Dashboard

React + TypeScript (Vite), built to a **single self-contained HTML file** so the
prototype can be emailed or opened on a laptop with no server running.

```sh
npm install
npm run dev      # local dev server
npm run build    # -> dist/index.html, everything inlined
```

Data comes from `src/data/athletes.json`, regenerated from the saved roster
fixtures by:

```sh
python3 ../scripts/export_athletes.py
```

Design tokens are the athletics site's own: `#A20000` and black, taken from
`window.site_colors` in the roster pages, with Rokkitt and Roboto — the two
faces the site itself loads from Google Fonts.
