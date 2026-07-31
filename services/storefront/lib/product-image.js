// Deterministic placeholder product image: an inline SVG data URI derived from
// the product id (gradient hue) and name (initials). No external image hosts.

function initialsOf(name) {
  const words = String(name || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (words.length === 0) return "SV";
  return words
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}

export function productImage(id, name) {
  const n = Number(id) || 0;
  const hue = (n * 47 + 13) % 360;
  const hue2 = (hue + 40) % 360;
  const initials = initialsOf(name);
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300" viewBox="0 0 400 300">` +
    `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">` +
    `<stop offset="0" stop-color="hsl(${hue},62%,52%)"/>` +
    `<stop offset="1" stop-color="hsl(${hue2},62%,38%)"/>` +
    `</linearGradient></defs>` +
    `<rect width="400" height="300" fill="url(#g)"/>` +
    `<circle cx="332" cy="52" r="90" fill="hsl(${hue2},70%,62%)" opacity="0.35"/>` +
    `<circle cx="40" cy="270" r="70" fill="hsl(${hue},70%,66%)" opacity="0.25"/>` +
    `<text x="200" y="152" fill="#ffffff" font-family="Arial, Helvetica, sans-serif" ` +
    `font-size="92" font-weight="700" text-anchor="middle" dominant-baseline="central">` +
    `${initials}</text></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}
