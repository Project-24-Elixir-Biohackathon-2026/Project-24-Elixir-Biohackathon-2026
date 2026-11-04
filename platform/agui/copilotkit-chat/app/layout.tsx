import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "@copilotkit/react-core/v2/styles.css";
import "./globals.css";

export const metadata: Metadata = { title: "SPE agent" };
// Light or dark, as the system or the sidebar's theme control is set (globals.css holds both
// palettes, keyed off the `data-theme` attribute the script below and the theme control set).
export const viewport: Viewport = { colorScheme: "light dark" };

// Applied before paint, so there is no flash of the wrong theme. A plain <script> can't import
// lib/theme.ts (it runs before any bundle), so it re-parses the same localStorage key by hand —
// keep the two in step if the stored values ever change. Static and free of user data on
// purpose: it only ever writes the literal strings "light" or "dark" it just read back out.
const THEME_SCRIPT = `try {
  var t = localStorage.getItem("spe.theme");
  if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
} catch (e) {}`;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // suppressHydrationWarning: the script above may set data-theme before React hydrates,
    // which would otherwise be flagged as a server/client mismatch on <html>.
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
