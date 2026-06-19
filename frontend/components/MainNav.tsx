"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/apps", label: "Apps" },
  { href: "/apps/new", label: "Register" },
  { href: "/settings", label: "Settings" },
];

export function MainNav() {
  const pathname = usePathname();

  return (
    <nav className="mb-6 flex flex-wrap gap-4 border-b border-[var(--border)] pb-3 text-sm">
      {links.map((link) => {
        const active =
          link.href === "/"
            ? pathname === "/"
            : pathname === link.href || pathname.startsWith(`${link.href}/`);
        return (
          <Link
            key={link.href}
            href={link.href}
            className={
              active
                ? "font-medium text-blue-400"
                : "text-[var(--muted)] hover:text-[var(--text)]"
            }
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
