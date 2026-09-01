import "@fontsource-variable/dm-sans";
import "@fontsource-variable/newsreader";
import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Local Via — AI audiovisual studio",
  description: "A local-first audiovisual AI studio powered by WanGP.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}

