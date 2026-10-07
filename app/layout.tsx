import "@fontsource-variable/dm-sans";
import "@fontsource-variable/newsreader";
import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Local Via — Sala de computación",
  description: "Estudio audiovisual con IA local para la sala de computación, basado en WanGP.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}

