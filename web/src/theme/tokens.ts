// Every colour, size and duration the dashboard uses.
// The page is a signal box for releases: concrete grey board, a track per release, and railway signal colours
// for what the path decided (go, stop, hold). The platform is drawn in blue, the old ways in grey; a status
// always carries a word or a shape as well as a colour.

export const color = {
  page: "#e6e9e7",
  surface: "#f6f7f5",
  card: "#ffffff",
  ink: "#1b2026",
  ink2: "#4b545e",
  muted: "#7a838c",
  rule: "#c9cfcc",
  track: "#9aa29f",
  wash: "rgba(36,87,166,0.08)",
  platform: "#2457a6",
  baseline: "#8a8d8f",
  baseline2: "#b3ada3",
  go: "#23774a",
  stop: "#b3362c",
  hold: "#a87412",
  focus: "#2457a6",
} as const;

export const font = {
  body: "'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif",
  narrow: "'IBM Plex Sans Condensed', 'IBM Plex Sans', system-ui, sans-serif",
  // Modular scale, ratio 1.2, from a 16px body.
  size: { xs: 12, sm: 14, md: 16, lg: 19, xl: 23, xxl: 28, xxxl: 40 },
  weight: { regular: 400, medium: 500, semibold: 600 },
  leading: { tight: 1.1, snug: 1.3, body: 1.55 },
} as const;

export const space = { 1: 4, 2: 8, 3: 12, 4: 16, 5: 20, 6: 24, 8: 32, 10: 40, 12: 48, 16: 64 } as const;

export const radius = { sm: 2, md: 4 } as const;

export const stroke = { hair: 1, track: 2, mark: 2, focus: 2.5 } as const;

export const layout = { maxWidth: 1180, measure: 68 } as const;

export const motion = {
  fast: 0.15,
  base: 0.3,
  travel: 1.1,
  stagger: 0.035,
  ease: [0.22, 1, 0.36, 1] as [number, number, number, number],
} as const;

// The stations every release passes, in order. "shipped" is past the last canary step.
export const stations = ["offline", "shadow", "canary_0", "canary_1", "canary_2", "shipped"] as const;
export const stationLabel: Record<(typeof stations)[number], string> = {
  offline: "Offline",
  shadow: "Shadow",
  canary_0: "5%",
  canary_1: "25%",
  canary_2: "50%",
  shipped: "All customers",
};

export const chart = {
  stopWidth: 900,
  stopRow: 92,
  stopLabel: 220,
  stopPadRight: 70,
  stopAxis: 40,
  stopTop: 10,
  stopFirst: 22,
  stopCols: 6,
  mark: 4.5,
  markGap: 11,
  trackRow: 30,
  trackLabel: 300,
  station: 5,
  intervalWidth: 520,
  intervalHeight: 190,
  intervalPad: { top: 16, right: 20, bottom: 34, left: 56 },
  barHeight: 14,
  barLabel: 210,
  barArea: 420,
  verdictWidth: 150,
  skeleton: 260,
  noteWidth: 320,
  trackWidth: 300,
} as const;

export const breakpoint = { narrow: 860 } as const;
