import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";

interface BreadcrumbItem {
  label: string;
  href?: string;
}

export default function Breadcrumbs({ items }: { items: BreadcrumbItem[] }) {
  return (
    <nav className="flex items-center gap-1.5 text-sm text-muted-foreground mb-4">
      {items.map((item, i) => {
        const isLast = i === items.length - 1;
        return (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && <ChevronRight className="w-3.5 h-3.5" />}
            {isLast || !item.href ? (
              <span className={isLast ? "font-medium text-foreground" : ""}>{item.label}</span>
            ) : (
              <Link to={item.href} className="hover:text-foreground transition">{item.label}</Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
