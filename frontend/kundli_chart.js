/**
 * kundli_chart.js — Vedic Kundli Chart Renderer
 * ==============================================
 * Renders North Indian (diamond) and South Indian (square) kundli chart styles
 * as inline SVG. No external dependencies.
 *
 * Usage:
 *   const svg = KundliChart.renderNorth(planetData, { size: 400 });
 *   const svg = KundliChart.renderSouth(planetData, { size: 400 });
 *   document.getElementById('chartContainer').innerHTML = svg;
 *
 * planetData: { "1": ["As","Su"], "2": ["Mo"], ... }  — house number → planet abbreviations
 *
 * Supported planet abbreviations:
 *   As=Ascendant, Su=Sun, Mo=Moon, Ma=Mars, Me=Mercury, Ju=Jupiter,
 *   Ve=Venus, Sa=Saturn, Ra=Rahu, Ke=Ketu, Ur=Uranus, Ne=Neptune, Pl=Pluto
 */
const KundliChart = (() => {
  // Planet display colours
  const PLANET_COLORS = {
    As: '#f39c12', Su: '#e67e22', Mo: '#95a5a6', Ma: '#e74c3c',
    Me: '#27ae60', Ju: '#f1c40f', Ve: '#9b59b6', Sa: '#2980b9',
    Ra: '#7f8c8d', Ke: '#16a085', Ur: '#1abc9c', Ne: '#3498db', Pl: '#8e44ad',
  };
  const SIGNS = ['Ar','Ta','Ge','Ca','Le','Vi','Li','Sc','Sg','Cp','Aq','Pi'];
  const SIGN_SYMBOLS = ['♈','♉','♊','♋','♌','♍','♎','♏','♐','♑','♒','♓'];

  // ── North Indian chart (diamond / square rotated 45°) ─────────────────────
  // Layout: 12 triangular houses arranged in a diamond grid
  // House positions relative to centre (as fractions of size)
  const NORTH_HOUSES = [
    // [houseNum, polygon points as [x,y] fractions of size]
    { h: 1,  pts: [[0.5,0],[0.25,0.25],[0.5,0.5],[0.75,0.25]] },              // top
    { h: 2,  pts: [[0.25,0.25],[0,0],[0,0.5],[0.25,0.5]] },                   // top-left
    { h: 3,  pts: [[0,0],[0,0.5],[0.25,0.5],[0.25,0.25]] },                   // left (top half)
    { h: 4,  pts: [[0,0.5],[0.25,0.5],[0.5,0.5],[0.25,0.75]] },              // left
    { h: 5,  pts: [[0,0.5],[0,1],[0.25,0.75],[0.25,0.5]] },                   // left (bottom)
    { h: 6,  pts: [[0,1],[0.25,0.75],[0.5,0.5],[0.25,0.75]] },                // bottom-left
    { h: 7,  pts: [[0.5,0.5],[0.25,0.75],[0.5,1],[0.75,0.75]] },              // bottom
    { h: 8,  pts: [[0.5,1],[0.75,0.75],[1,1],[1,0.5]] },                      // bottom-right
    { h: 9,  pts: [[0.75,0.75],[1,0.5],[0.75,0.5],[0.5,0.5]] },              // right (bottom)
    { h: 10, pts: [[0.75,0.5],[1,0.5],[1,0],[0.75,0.25]] },                   // right (top)
    { h: 11, pts: [[0.75,0.25],[1,0],[0.5,0],[0.5,0.25]] },                   // top-right
    { h: 12, pts: [[0.5,0.25],[0.5,0],[0.25,0.25],[0.5,0.5]] },              // centre-top
  ];

  // ── South Indian chart (fixed sign grid, 3×4 arrangement) ────────────────
  // Grid: signs are fixed in position (Pi top-left, Ar top-2nd, etc.)
  // Houses are derived from Ascendant position
  const SOUTH_GRID = [
    // row, col for signs 1-12 (Aries=0)
    [0,1],[0,2],[0,3],[1,3],[2,3],[2,2],[2,1],[2,0],[1,0],[0,0],
    // wait — classic South Indian fixed layout:
    // Pi Ar Ta Ge
    // Aq    (  Ca
    // Cp Sg Sc Le
    // Wait, correct South Indian layout (Pisces top-left):
  ];

  // Correct South Indian positions: [sign_0_based -> [row, col]]
  // 0=Ar,1=Ta,...,11=Pi  →  grid 4 cols × 3 rows
  const SOUTH_POS = {
    // Pi Ar Ta Ge
    // Aq  .  .  Ca
    // Cp Sg Sc Le
    0: [0,1], 1: [0,2], 2: [0,3], 3: [1,3],
    4: [2,3], 5: [2,2], 6: [2,1], 7: [2,0],
    8: [1,0], 9: [0,0],10: [0,1], // placeholder
  };
  // Proper positions (Pisces=11 top-left)
  const SOUTH_FIXED = [
    [0,1],[0,2],[0,3],[1,3],[2,3],[2,2],[2,1],[2,0],[1,0],[0,0],
    [0,1],[0,2] // overflow guard
  ];
  // Correct mapping: Pi(11),Ar(0),Ta(1),Ge(2) / Aq(10),[c],[c],Ca(3) / Cp(9),Sg(8),Sc(7),Le(4)...
  const SOUTH_SIGN_POSITIONS = {
    11:[0,0],0:[0,1],1:[0,2],2:[0,3],
    10:[1,0],              3:[1,3],
    9:[2,0],8:[2,1],7:[2,2],4:[2,3],5:[2,2],6:[2,1] // signs 5,6 share for now
  };
  // Final corrected version
  const SOUTH_GRID_LAYOUT = {
    11:[0,0], 0:[0,1], 1:[0,2],  2:[0,3],
    10:[1,0],                     3:[1,3],
    9:[2,0],  8:[2,1], 7:[2,2],  4:[2,3],
              5:null,  6:null              // signs 5(Vi),6(Li) inside? No...
  };
  // Definitive South Indian 4×3 grid (Pisces top-left, clockwise)
  const SOUTH_SIGN_CELL = [
    //sign: [row, col]
    [0,1],  // 0=Aries
    [0,2],  // 1=Taurus
    [0,3],  // 2=Gemini
    [1,3],  // 3=Cancer
    [2,3],  // 4=Leo
    [2,2],  // 5=Virgo
    [2,1],  // 6=Libra
    [2,0],  // 7=Scorpio
    [1,0],  // 8=Sagittarius
    [0,0],  // 9=Capricorn
    [0,0],  // 10=Aquarius — overlaps with Cap in 3×4; use 4×4 instead
    [0,0],  // 11=Pisces
  ];

  // Use a proper 4×4 South Indian grid (12 outer cells + 4 inner empty)
  // Signs go clockwise from top-left:
  // Pi  Ar  Ta  Ge
  // Aq  [c] [c] Ca
  // Cp  [c] [c] Le
  // Sg  Sc  Vi  Vi — nope
  // Correct: Pi Ar Ta Ge / Aq _ _ Ca / Cp _ _ Le / Sg Sc Vi Li
  const SOUTH_4X4 = [
    [0,0],[0,1],[0,2],[0,3],  // Pi Ar Ta Ge  (signs 11,0,1,2)
    [1,3],                    // Ca (sign 3)
    [2,3],                    // Le (sign 4)
    [3,3],[3,2],[3,1],[3,0],  // Li Vi Sc Sg  (signs 6,5,7,8) — wait, Li=6 Sg=8
    [2,0],                    // Cp (sign 9)
    [1,0],                    // Aq (sign 10)
  ];
  // sign index → [row, col] in 4×4 grid
  const S4 = [
    [0,1],[0,2],[0,3],[1,3],[2,3],[3,2],[3,1],[3,0],[2,0],[1,0],[0,0],[3,3]
  ];
  // Hmm, sign 11 (Pi) → [0,0], 5(Vi)→[3,2], 6(Li)→[3,1]... let me do it right:
  // Clockwise from Pi at [0,0]:
  // [0,0]=Pi [0,1]=Ar [0,2]=Ta [0,3]=Ge [1,3]=Ca [2,3]=Le [3,3]=Vi [3,2]=Li [3,1]=Sc [3,0]=Sg [2,0]=Cp [1,0]=Aq
  const SOUTH_SIGN_MAP = [
    [0,1],  // Ar(0)  -> row0,col1
    [0,2],  // Ta(1)
    [0,3],  // Ge(2)
    [1,3],  // Ca(3)
    [2,3],  // Le(4)
    [3,3],  // Vi(5)
    [3,2],  // Li(6)
    [3,1],  // Sc(7)
    [3,0],  // Sg(8)
    [2,0],  // Cp(9)
    [1,0],  // Aq(10)
    [0,0],  // Pi(11)
  ];

  function _pts(points, size) {
    return points.map(([x,y]) => `${x*size},${y*size}`).join(' ');
  }

  function _planetText(planets, cx, cy, lineH) {
    if (!planets || !planets.length) return '';
    return planets.map((p, i) => {
      const color = PLANET_COLORS[p] || '#ecf0f1';
      const y = cy + (i - (planets.length-1)/2) * lineH;
      return `<text x="${cx}" y="${y}" text-anchor="middle" dominant-baseline="central"
        font-size="${lineH*0.85}" font-weight="bold" fill="${color}">${p}</text>`;
    }).join('');
  }

  // ── North Indian render ───────────────────────────────────────────────────
  function renderNorth(planetData = {}, opts = {}) {
    const size    = opts.size || 400;
    const bg      = opts.bg   || 'var(--surface, #1e1e2e)';
    const stroke  = opts.stroke || 'var(--border, #44475a)';
    const textColor = opts.textColor || '#cdd6f4';
    const lagna   = parseInt(opts.ascendant || '1', 10);

    // Build house → planets map
    const housePlanets = {};
    for (const [h, ps] of Object.entries(planetData)) {
      housePlanets[parseInt(h)] = ps;
    }

    // North Indian houses: house 1 at top diamond, going clockwise
    // Simplified 12-house positions (polygons)
    const housePolygons = [
      { h:1,  cx:0.5,  cy:0.2  },  // top
      { h:2,  cx:0.15, cy:0.22 },  // top-left inner
      { h:3,  cx:0.1,  cy:0.42 },  // left
      { h:4,  cx:0.25, cy:0.62 },  // bottom-left inner
      { h:5,  cx:0.1,  cy:0.78 },  // left-bottom
      { h:6,  cx:0.35, cy:0.82 },  // bottom inner-left
      { h:7,  cx:0.5,  cy:0.8  },  // bottom
      { h:8,  cx:0.65, cy:0.82 },  // bottom inner-right
      { h:9,  cx:0.9,  cy:0.78 },  // right-bottom
      { h:10, cx:0.75, cy:0.62 },  // bottom-right inner
      { h:11, cx:0.9,  cy:0.42 },  // right
      { h:12, cx:0.85, cy:0.22 },  // top-right inner
    ];

    // Build SVG polygons for the 12 north-Indian triangular houses
    const northPoly = [
      // [houseNum, [[x,y],...]]  — coordinates as fractions of size
      [1, [[.5,0],[.25,.25],[.5,.5],[.75,.25]]],
      [2, [[0,0],[.25,.25],[.25,.5],[0,.5]]],
      [3, [[0,0],[.25,0],[.25,.25],[0,.25]]],  // simplified
      [4, [[0,.5],[.25,.5],[.5,.5],[.25,.75]]],
      [5, [[0,.5],[0,.75],[.25,.75],[.25,.5]]],
      [6, [[0,.75],[0,1],[.25,1],[.25,.75]]],
      [7, [[.25,.75],[.5,1],[.75,.75],[.5,.5]]],
      [8, [[.75,.75],[1,1],[1,.75],[.75,.75]]],
      [9, [[.75,.5],[1,.5],[1,.75],[.75,.75]]],
      [10,[[.5,.5],[.75,.5],[.75,.25],[.5,.25]]],
      [11,[[.75,.25],[1,.5],[1,0],[.75,0]]],
      [12,[[.5,0],[.75,0],[.75,.25],[.5,.25]]],
    ];

    let polygons = '';
    for (const [h, pts] of northPoly) {
      const fill = h === lagna ? 'rgba(243,156,18,0.15)' : 'transparent';
      const scaled = pts.map(([x,y]) => `${x*size},${y*size}`).join(' ');
      polygons += `<polygon points="${scaled}" fill="${fill}" stroke="${stroke}" stroke-width="1.5"/>`;
    }

    // House labels + planets
    let labels = '';
    for (const { h, cx, cy } of housePolygons) {
      const ps  = housePlanets[h] || [];
      const x   = cx * size, y = cy * size;
      const sign = ((lagna + h - 2) % 12 + 12) % 12;
      labels += `<text x="${x}" y="${y-10}" text-anchor="middle" font-size="9"
        fill="${textColor}" opacity="0.5">${h}${SIGN_SYMBOLS[sign]}</text>`;
      labels += _planetText(ps, x, y+4, 12);
    }

    // Centre label
    labels += `<text x="${size/2}" y="${size/2}" text-anchor="middle" dominant-baseline="central"
      font-size="10" fill="${textColor}" opacity="0.4">NORTH</text>`;

    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"
      xmlns="http://www.w3.org/2000/svg" style="border-radius:8px;background:${bg}">
      ${polygons}${labels}
    </svg>`;
  }

  // ── South Indian render ───────────────────────────────────────────────────
  function renderSouth(planetData = {}, opts = {}) {
    const size    = opts.size || 400;
    const bg      = opts.bg || 'var(--surface, #1e1e2e)';
    const stroke  = opts.stroke || 'var(--border, #44475a)';
    const textColor = opts.textColor || '#cdd6f4';
    const asc     = parseInt(opts.ascendant || '1', 10);
    const rows    = 4, cols = 4;
    const cw = size / cols, ch = size / rows;
    const innerCols = [1,2], innerRows = [1,2];

    // Build house → sign map (house 1 = Ascendant's sign)
    // South Indian: signs are FIXED, houses move with Ascendant
    // ascendant is the sign number (1=Ar..12=Pi) where Lagna falls
    const lagnaSign = ((asc - 1 + 12) % 12); // 0-based
    // sign → house number
    const signToHouse = {};
    for (let s = 0; s < 12; s++) {
      signToHouse[s] = ((s - lagnaSign + 12) % 12) + 1;
    }
    // house → planets
    const housePlanets = {};
    for (const [h, ps] of Object.entries(planetData)) {
      housePlanets[parseInt(h)] = ps;
    }

    let cells = '';
    for (let s = 0; s < 12; s++) {
      const [r, c] = SOUTH_SIGN_MAP[s];
      const house  = signToHouse[s];
      const ps     = housePlanets[house] || [];
      const x = c * cw, y = r * ch;
      const isLagna = house === 1;
      const fill = isLagna ? 'rgba(243,156,18,0.15)' : 'transparent';
      cells += `<rect x="${x+1}" y="${y+1}" width="${cw-2}" height="${ch-2}"
        fill="${fill}" stroke="${stroke}" stroke-width="1.5" rx="2"/>`;
      // Sign symbol + number
      cells += `<text x="${x+cw/2}" y="${y+14}" text-anchor="middle"
        font-size="10" fill="${textColor}" opacity="0.5">${SIGN_SYMBOLS[s]} ${house}</text>`;
      if (isLagna) {
        cells += `<text x="${x+4}" y="${y+ch-4}" font-size="8" fill="#f39c12">As</text>`;
      }
      // Planets
      cells += _planetText(ps, x + cw/2, y + ch/2, 12);
    }

    // Draw inner blank cells
    for (const r of innerRows) for (const c of innerCols) {
      cells += `<rect x="${c*cw+1}" y="${r*ch+1}" width="${cw-2}" height="${ch-2}"
        fill="${bg}" stroke="${stroke}" stroke-width="1" rx="2" opacity="0.6"/>`;
    }
    cells += `<text x="${size/2}" y="${size/2}" text-anchor="middle" dominant-baseline="central"
      font-size="10" fill="${textColor}" opacity="0.4">SOUTH</text>`;

    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}"
      xmlns="http://www.w3.org/2000/svg" style="border-radius:8px;background:${bg}">
      ${cells}
    </svg>`;
  }

  // ── Parse planet data from kundli_json ────────────────────────────────────
  function parsePlanetData(kundliJson, lagnaHouse) {
    /**
     * Convert backend kundli_json into { houseNum: [abbrevs] } map.
     * kundliJson.planets: [{name, house, sign, ...}, ...]
     */
    const result = {};
    const planets = kundliJson?.planets || [];
    for (const p of planets) {
      const h = p.house || 1;
      if (!result[h]) result[h] = [];
      result[h].push(_abbrev(p.name || p.planet || ''));
    }
    if (lagnaHouse) {
      if (!result[lagnaHouse]) result[lagnaHouse] = [];
      if (!result[lagnaHouse].includes('As')) result[lagnaHouse].unshift('As');
    }
    return result;
  }

  function _abbrev(name) {
    const map = {
      'sun':'Su','moon':'Mo','mars':'Ma','mercury':'Me','jupiter':'Ju',
      'venus':'Ve','saturn':'Sa','rahu':'Ra','ketu':'Ke',
      'uranus':'Ur','neptune':'Ne','pluto':'Pl','ascendant':'As','lagna':'As',
    };
    return map[name.toLowerCase()] || name.substring(0,2);
  }

  return { renderNorth, renderSouth, parsePlanetData, PLANET_COLORS };
})();
