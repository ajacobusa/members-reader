// `redirect` is a Next.js helper that sends the visitor to a different URL.
import { redirect } from "next/navigation";

// This is the page component for the site root ("/").
// It is a Server Component (no "use client"), so this code runs on the server.
export default function Home() {
  // As soon as someone visits "/", immediately send them to "/dashboard".
  // The root page itself renders nothing because the redirect stops execution.
  redirect("/dashboard");
}
