/** @type {import('next').NextConfig} */
const nextConfig = {
  // The whole site is static: there is no database and no user accounts, only JSON
  // and audio files. "export" tells Next to produce a folder of plain files that any
  // host will serve, which is the cheapest and most durable way to publish this.
  output: "export",
  images: { unoptimized: true },

  // Next 15 refuses dev-server requests whose Host header it does not recognise.
  // Replit and Codespaces both serve the page from a generated subdomain, so
  // those two patterns have to be allowed or the repl shows a blank page.
  // This affects `next dev` only. It has no bearing on the exported site.
  allowedDevOrigins: ["*.replit.dev", "*.repl.co", "*.app.github.dev"],
};
export default nextConfig;
