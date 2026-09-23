/** @type {import('next').NextConfig} */

// GitHub Pages serves a project site from a subfolder, not a domain root:
// hazkhan2001.github.io/sawt/ rather than hazkhan2001.github.io/. Next has to be
// told, or every link and every /_next/ asset points one level too high and the
// page loads as unstyled text.
//
// It is read from the environment rather than hardcoded so that the SAME code
// runs correctly in three places: empty locally (npm run dev at localhost:3000),
// empty on a root-domain host like Vercel, and "/sawt" only in the Pages workflow.
// Hardcoding it would fix deployment by breaking local development.
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig = {
  // The whole site is static: there is no database and no user accounts, only JSON
  // and audio files. "export" tells Next to produce a folder of plain files that any
  // host will serve, which is the cheapest and most durable way to publish this.
  output: "export",

  // Setting basePath alone is enough for Next's own assets. Do not also set
  // assetPrefix to the same value: that prefixes them twice and yields /sawt/sawt/.
  basePath,

  images: { unoptimized: true },

  // Next 15 refuses dev-server requests whose Host header it does not recognise.
  // Replit and Codespaces both serve the page from a generated subdomain, so
  // those two patterns have to be allowed or the repl shows a blank page.
  // This affects `next dev` only. It has no bearing on the exported site.
  allowedDevOrigins: ["*.replit.dev", "*.repl.co", "*.app.github.dev"],
};
export default nextConfig;
