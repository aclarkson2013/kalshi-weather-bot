"use client";

import {
  BarChart3,
  ClipboardList,
  LayoutDashboard,
  Settings,
  TrendingUp,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useWebSocketStatus } from "@/lib/websocket";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/markets", label: "Markets", icon: TrendingUp },
  { href: "/queue", label: "Queue", icon: ClipboardList },
  { href: "/trades", label: "Trades", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings },
];

export default function BottomNav() {
  const pathname = usePathname();
  const { isConnected } = useWebSocketStatus();

  // Hide nav on onboarding page
  if (pathname === "/onboarding") return null;

  return (
    <>
      {/* Mobile: Fixed bottom nav */}
      <nav className="fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-gray-200 lg:hidden">
        <div className="flex justify-around">
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            const Icon = item.icon;

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex flex-col items-center justify-center min-w-[44px] min-h-[44px] py-2 px-3 ${
                  isActive
                    ? "text-boz-primary"
                    : "text-boz-neutral hover:text-gray-900"
                }`}
              >
                <Icon size={20} />
                <span className="text-xs mt-1">{item.label}</span>
              </Link>
            );
          })}
        </div>
      </nav>

      {/* Desktop: Fixed left sidebar */}
      <aside className="hidden lg:flex lg:flex-col lg:fixed lg:inset-y-0 lg:left-0 lg:w-64 lg:bg-white lg:border-r lg:border-gray-200 lg:z-50">
        <div className="flex items-center h-16 px-6 border-b border-gray-200">
          <h1 className="text-lg font-bold text-boz-primary">
            Boz Weather Trader
          </h1>
          <span
            className={`ml-2 h-2 w-2 rounded-full ${
              isConnected ? "bg-green-500" : "bg-gray-400"
            }`}
            title={isConnected ? "Live" : "Disconnected"}
          />
        </div>
        <nav className="flex-1 px-3 py-4 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === "/"
                : pathname.startsWith(item.href);
            const Icon = item.icon;

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 min-h-[44px] px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-blue-50 text-boz-primary"
                    : "text-boz-neutral hover:bg-gray-50 hover:text-gray-900"
                }`}
              >
                <Icon size={20} />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
    </>
  );
}
