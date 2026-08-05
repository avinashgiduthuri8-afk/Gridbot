import { useState } from "react";
import { Link, useLocation } from "wouter";
import {
  LayoutDashboard,
  Grid3x3,
  Wallet,
  ListOrdered,
  History,
  PieChart,
  BarChart3,
  Settings as SettingsIcon,
  Menu,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useIsMobile } from "@/hooks/use-mobile";
import { Button } from "@/components/ui/button";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/grids", label: "Live Grids", icon: Grid3x3 },
  { href: "/positions", label: "Positions", icon: Wallet },
  { href: "/orders", label: "Orders", icon: ListOrdered },
  { href: "/trade-history", label: "Trade History", icon: History },
  { href: "/portfolio", label: "Portfolio", icon: PieChart },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const [location] = useLocation();
  return (
    <nav className="flex flex-col gap-1 p-2">
      {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
        const active = location === href;
        return (
          <Link key={href} href={href} onClick={onNavigate}>
            <span
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground hover-elevate",
              )}
              data-testid={`link-nav-${label.toLowerCase().replace(/\s+/g, "-")}`}
            >
              <Icon className="h-4 w-4" />
              {label}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}

export function Layout({ children }: { children: React.ReactNode }) {
  const isMobile = useIsMobile();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      {!isMobile && (
        <aside className="hidden w-56 shrink-0 border-r bg-sidebar md:flex md:flex-col">
          <div className="flex h-14 items-center border-b px-4 font-semibold">Grid Bot</div>
          <NavLinks />
        </aside>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
          {isMobile && (
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setMobileOpen((v) => !v)}
              data-testid="button-mobile-menu"
            >
              {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>
          )}
          <span className="font-semibold">Grid Bot Dashboard</span>
        </header>

        {isMobile && mobileOpen && (
          <div className="border-b bg-sidebar">
            <NavLinks onNavigate={() => setMobileOpen(false)} />
          </div>
        )}

        <main className="min-w-0 flex-1 overflow-auto p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
