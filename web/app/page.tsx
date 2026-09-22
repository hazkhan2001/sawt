import SawtGlobe from "@/components/SawtGlobe";
import { hubs, tracks } from "@/lib/data";

// A SERVER component. It runs once when the site is built, reads the JSON, and hands
// it to the client component as props. The browser therefore never fetches the data:
// it arrives already inside the page.
export default function Page() {
  return <SawtGlobe hubs={hubs} tracks={tracks} />;
}
