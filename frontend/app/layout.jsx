import { Fraunces, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import Providers from "@/components/Providers";
import Nav from "@/components/Nav";
import ApiConfigBanner from "@/components/ApiConfigBanner";

const appSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-board-sans",
  display: "swap",
});

const appDisplay = Fraunces({
  subsets: ["latin"],
  weight: ["600", "700"],
  variable: "--font-board-display",
  display: "swap",
});

export const metadata = {
  title: "JobAI",
  description: "AI-powered job search pipeline",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className={`${appSans.className} ${appSans.variable} ${appDisplay.variable}`}>
        <Providers>
          <ApiConfigBanner />
          <div className="app-shell">
            <Nav />
            <main className="app-main">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
