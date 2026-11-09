import { breakpoint, color, font, layout, radius, space, stroke } from "./tokens";

export const globalCss = `
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:${color.page};color:${color.ink};font-family:${font.body};font-size:${font.size.md}px;line-height:${font.leading.body}}
h1,h2,h3{margin:0;font-weight:${font.weight.semibold};line-height:${font.leading.tight}}
p{margin:0}
a{color:${color.platform}}
:focus-visible{outline:${stroke.focus}px solid ${color.focus};outline-offset:2px}
.page{max-width:${layout.maxWidth}px;margin:0 auto;padding:${space[10]}px ${space[6]}px ${space[16]}px}
.measure{max-width:${layout.measure}ch}
.ink2{color:${color.ink2}}
.muted{color:${color.muted}}
.narrow{font-family:${font.narrow}}
.num{font-family:${font.narrow};font-variant-numeric:tabular-nums}
.section{margin-top:${space[12]}px}
.section h2{font-size:${font.size.xl}px;margin-bottom:${space[2]}px}
.lede{font-size:${font.size.lg}px;color:${color.ink2};margin-top:${space[3]}px}
.board{background:${color.surface};border:${stroke.hair}px solid ${color.rule};border-radius:${radius.md}px;padding:${space[6]}px;margin-top:${space[4]}px}
.tabs{display:flex;gap:${space[1]}px;margin-top:${space[6]}px;border-bottom:${stroke.hair}px solid ${color.rule}}
.tab{appearance:none;border:0;background:none;font:inherit;font-size:${font.size.sm}px;color:${color.ink2};padding:${space[2]}px ${space[3]}px;cursor:pointer;border-bottom:${stroke.track}px solid transparent;margin-bottom:-1px}
.tab[aria-selected="true"]{color:${color.ink};border-bottom-color:${color.ink};font-weight:${font.weight.medium}}
.chips{display:flex;flex-wrap:wrap;gap:${space[2]}px;margin-top:${space[4]}px}
.chip{appearance:none;font:inherit;font-size:${font.size.sm}px;border:${stroke.hair}px solid ${color.rule};background:${color.card};color:${color.ink2};border-radius:${radius.md}px;padding:${space[1]}px ${space[3]}px;cursor:pointer}
.chip[aria-pressed="true"]{border-color:${color.ink};color:${color.ink}}
.btn{appearance:none;font:inherit;font-size:${font.size.sm}px;border:${stroke.hair}px solid ${color.ink};background:${color.card};color:${color.ink};border-radius:${radius.md}px;padding:${space[1]}px ${space[4]}px;cursor:pointer;align-self:flex-start}
.state{display:flex;flex-direction:column;gap:${space[2]}px;padding:${space[6]}px;border:${stroke.hair}px dashed ${color.rule};border-radius:${radius.md}px;background:${color.surface}}
.skeleton{background:linear-gradient(90deg,${color.rule}55,${color.rule}99,${color.rule}55);background-size:200% 100%;animation:shimmer 1.4s linear infinite;border-radius:${radius.sm}px}
@keyframes shimmer{to{background-position:-200% 0}}
.row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:${space[4]}px;align-items:center}
.track-row{appearance:none;width:100%;text-align:left;font:inherit;background:none;border:0;border-top:${stroke.hair}px solid ${color.rule};padding:${space[2]}px 0;cursor:pointer;color:inherit}
.track-row:hover{background:${color.wash}}
.track-row[aria-expanded="true"]{background:${color.wash}}
.detail{border-top:${stroke.hair}px solid ${color.rule};padding:${space[4]}px 0 ${space[6]}px;overflow:hidden}
.checks{width:100%;border-collapse:collapse;font-size:${font.size.sm}px}
.checks td,.checks th{padding:${space[1]}px ${space[2]}px;border-bottom:${stroke.hair}px solid ${color.rule};text-align:left;vertical-align:top}
.checks th{font-weight:${font.weight.medium};color:${color.ink2}}
.figures{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:${space[6]}px;margin-top:${space[6]}px}
.figure strong{display:block;font-family:${font.narrow};font-size:${font.size.xxxl}px;font-weight:${font.weight.medium};line-height:${font.leading.tight};font-variant-numeric:tabular-nums}
.legend{display:flex;flex-wrap:wrap;gap:${space[4]}px;font-size:${font.size.sm}px;color:${color.ink2};margin-top:${space[3]}px}
.legend span{display:inline-flex;align-items:center;gap:${space[1]}px}
.table{width:100%;border-collapse:collapse;font-size:${font.size.sm}px}
.table th,.table td{text-align:left;padding:${space[2]}px;border-bottom:${stroke.hair}px solid ${color.rule}}
.table td.r,.table th.r{text-align:right}
@media (max-width:${breakpoint.narrow}px){.page{padding:${space[6]}px ${space[4]}px}.row{grid-template-columns:1fr}}
@media (prefers-reduced-motion:reduce){.skeleton{animation:none}*{transition:none!important}}
`;
