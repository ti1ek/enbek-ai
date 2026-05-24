export default function LogoMark() {
  // Stroke-based wordmark. stroke-width=5, round caps/joins, baseline y=24, top y=4, mid y=14
  return (
    <svg
      viewBox="0 0 162 30"
      height="22"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-label="enbek ai"
    >
      <g
        stroke="#141413"
        strokeWidth="5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {/* e — circle arc + midbar, center (14,14) r=9 */}
        <path d="M 23,14 A 9,9 0 1,0 20,23" />
        <line x1="5" y1="14" x2="23" y2="14" />

        {/* n — arch, x start 30 */}
        <path d="M 32,24 V 14 Q 32,5 41,5 Q 50,5 50,14 V 24" />

        {/* b — tall stroke + right circle, x start 57 */}
        <line x1="58" y1="4" x2="58" y2="24" />
        <path d="M 58,15 Q 58,7 66,7 Q 74,7 74,15 Q 74,23 66,23 Q 58,23 58,16" />

        {/* e — same as first, center (87,14) */}
        <path d="M 96,14 A 9,9 0 1,0 93,23" />
        <line x1="78" y1="14" x2="96" y2="14" />

        {/* k — tall stroke + diagonals, x start 103 */}
        <line x1="104" y1="4" x2="104" y2="24" />
        <path d="M 104,15 L 114,5" />
        <path d="M 104,15 L 114,24" />
      </g>

      {/* space + ai in sage */}
      <g
        stroke="#5f7a5f"
        strokeWidth="5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {/* a — circle + right stroke, x start 121 */}
        <path d="M 130,8 Q 130,5 122,5 Q 114,5 114,13" />
        <path d="M 121,5 Q 129,5 129,13 Q 129,24 121,24 Q 113,24 113,16" />
        <line x1="129" y1="8" x2="129" y2="24" />

        {/* i — dot + stroke, x=140 */}
        <circle cx="140" cy="5" r="2.5" fill="#5f7a5f" stroke="none" />
        <line x1="140" y1="10" x2="140" y2="24" />
      </g>
    </svg>
  );
}
