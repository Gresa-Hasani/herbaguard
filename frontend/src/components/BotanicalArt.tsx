import { ClassBadge } from './ClassBadge'

/**
 * Original botanical line art: a flowering branch whose nodes read as an evidence graph. Purely
 * decorative; it carries no data.
 */

// Leaves along the main stem: x, y, rotation (deg), scale.
const LEAVES: [number, number, number, number][] = [
  [78, 410, -62, 1.05],
  [92, 372, 28, 0.95],
  [110, 330, -70, 1.0],
  [128, 292, 22, 0.9],
  [158, 252, -64, 0.95],
  [186, 214, 18, 0.85],
  [222, 178, -58, 0.9],
  [256, 148, 12, 0.8],
  [296, 118, -50, 0.8],
  [334, 92, 8, 0.7],
  [372, 70, -40, 0.65],
]

const NODES: [number, number][] = [
  [128, 292],
  [222, 178],
  [334, 92],
  [92, 372],
]

function Leaf({ x, y, r, s, i }: { x: number; y: number; r: number; s: number; i: number }) {
  return (
    <g transform={`translate(${x} ${y}) rotate(${r}) scale(${s})`}>
      <g className="leaf-in" style={{ animationDelay: `${0.5 + i * 0.16}s` }}>
        <path
          d="M0 0C16-14 42-14 58 0 42 14 16 14 0 0Z"
          fill="rgb(140 194 173 / 0.12)"
          stroke="#8cc2ad"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
        <path d="M2 0H52" stroke="#8cc2ad" strokeWidth="1" strokeLinecap="round" opacity="0.7" />
      </g>
    </g>
  )
}

export function BotanicalBranch({ className = '' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 440 460"
      className={className}
      fill="none"
      aria-hidden="true"
      focusable="false"
    >
      <g className="sway">
        <path
          d="M60 452C84 380 96 320 134 270S222 190 262 150 340 96 392 52"
          stroke="#bcdccf"
          strokeWidth="2"
          strokeLinecap="round"
          pathLength={1}
          className="draw"
        />
        {LEAVES.map(([x, y, r, s], i) => (
          <Leaf key={`${x}-${y}`} x={x} y={y} r={r} s={s} i={i} />
        ))}
        {NODES.map(([x, y], i) => (
          <g key={`${x}-${y}`} className="leaf-in" style={{ animationDelay: `${1.6 + i * 0.2}s` }}>
            <circle cx={x} cy={y} r="9" fill="#0b2f25" stroke="#55a287" strokeWidth="1.5" />
            <circle cx={x} cy={y} r="3" fill="#8cc2ad" />
          </g>
        ))}
        <path
          d="M128 292C190 300 260 270 300 300M222 178C270 210 330 190 360 230M92 372C140 410 200 400 250 372"
          stroke="#55a287"
          strokeWidth="1"
          strokeDasharray="3 5"
          opacity="0.55"
        />
      </g>
    </svg>
  )
}

/** Faint leaf outline used as a quiet section ornament. */
export function LeafOrnament({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 120 120" className={className} fill="none" aria-hidden="true" focusable="false">
      <path
        d="M20 100C20 52 50 20 100 14c2 46-22 82-66 86-5.6.5-9.6 0-14-0z"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <path d="M22 98C46 70 66 50 92 28" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M44 78c4-12 14-22 28-28M58 90c4-10 12-18 24-24" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
    </svg>
  )
}

/**
 * The hero "specimen plate": dark panel, botanical branch, and a miniature of the real result
 * layout. The sample is labelled as an illustration of the layout, not a live result.
 */
export function SpecimenPlate() {
  return (
    <div className="relative isolate overflow-hidden rounded-3xl bg-forest-900 shadow-glow ring-1 ring-forest-700/60">
      <div className="bg-dots absolute inset-0 -z-10 opacity-70" />
      <div className="absolute -right-24 -top-24 -z-10 h-80 w-80 rounded-full bg-forest-500/30 blur-3xl" />
      <div className="absolute -bottom-32 -left-16 -z-10 h-72 w-72 rounded-full bg-teal-600/25 blur-3xl" />

      <BotanicalBranch className="absolute -top-2 right-0 h-[108%] w-auto -scale-x-100 opacity-95" />

      <div className="relative flex min-h-[27rem] flex-col justify-end p-5 sm:min-h-[32rem] sm:p-8">
        <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-forest-300">
          Example result layout
        </p>
        <div className="float-y max-w-sm rounded-2xl bg-canvas p-4 shadow-lift sm:p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wider text-muted">
                Herb + medication
              </p>
              <p className="font-display text-lg font-semibold leading-tight text-ink">
                St John&rsquo;s wort + warfarin
              </p>
            </div>
            <ClassBadge letter="A" label="Documented" size="sm" />
          </div>
          <ul className="mt-4 space-y-2.5 text-sm">
            <li className="flex gap-2.5 rounded-lg border border-line bg-surface p-2.5">
              <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-ev-regulatory" />
              <span>
                <span className="block font-medium text-ink">Regulatory monograph</span>
                <span className="block text-xs text-muted">
                  Verbatim excerpt, section and link to the source document
                </span>
              </span>
            </li>
            <li className="flex gap-2.5 rounded-lg border border-line bg-surface p-2.5">
              <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-ev-clinical" />
              <span>
                <span className="block font-medium text-ink">Mechanism context</span>
                <span className="block text-xs text-muted">
                  Enzyme and transporter paths, hedged as the source words them
                </span>
              </span>
            </li>
          </ul>
          <p className="mt-3 border-t border-line pt-3 text-xs text-muted">
            Illustration of the layout. Run the checker for live results with full provenance.
          </p>
        </div>
      </div>
    </div>
  )
}
