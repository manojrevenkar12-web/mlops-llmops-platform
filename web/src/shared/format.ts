export const int = (n: number) => Math.round(n).toLocaleString("en-US");
export const usd = (n: number) => `$${Math.round(n).toLocaleString("en-US")}`;
export const pct = (n: number, digits = 1) => `${n >= 0 ? "+" : "−"}${Math.abs(n * 100).toFixed(digits)}%`;
export const pp = (n: number, digits = 1) => `${n >= 0 ? "+" : "−"}${Math.abs(n * 100).toFixed(digits)} pts`;
export const hours = (h: number) => (h >= 48 ? `${(h / 24).toFixed(h % 24 ? 1 : 0)} days` : `${Math.round(h)} h`);

export const policyName: Record<string, string> = {
  platform: "This release path",
  fixed_canary: "10% canary, one z-test",
  offline_only: "Offline metric, then 100%",
};

export const decisionWord: Record<string, string> = {
  promoted: "shipped",
  blocked: "blocked",
  rolled_back: "rolled back",
  held: "held",
};
