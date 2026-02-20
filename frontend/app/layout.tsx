import type { Metadata, Viewport } from "next";

import Providers from "@/components/providers";
import BottomNav from "@/components/ui/bottom-nav";

import "./globals.css";

export const metadata: Metadata = {
  title: "Boz Weather Trader",
  description: "Automated weather prediction market trading",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "default",
    title: "Boz Weather Trader",
  },
};

export const viewport: Viewport = {
  themeColor: "#2563eb",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900 min-h-screen">
        <Providers>
          <BottomNav />
          <main className="pb-16 lg:pb-0 lg:pl-64">
            <div className="max-w-lg mx-auto px-4 py-4 lg:max-w-4xl">
              {children}
            </div>
          </main>
        </Providers>
      </body>
    </html>
  );
}
