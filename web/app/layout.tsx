import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Sawt: the Islamic soundscape map",
  description:
    "Click a place and hear the sound of it: adhan, dhikr, maqam and mugham, " +
    "from open archives and field recordings, with its context beside it.",
};

// The root layout wraps every page. It is a SERVER component, meaning it runs during
// the build and ships as finished HTML, which is why it must not touch the browser.
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="h-full overflow-hidden">{children}</body>
    </html>
  );
}
