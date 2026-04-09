/**
 * NoctusAI Global Header Component
 *
 * Generic header with hamburger menu, notification slot, and user avatar dropdown.
 * Products provide user data and callbacks — no product-specific imports.
 */
import { Menu, LogOut } from "lucide-react";

export interface HeaderProps {
  userEmail: string;
  onMenuToggle?: () => void;
  onLogout: () => void;
  /** Slot for product-specific actions (notification bell, etc.) */
  actions?: React.ReactNode;
}

export function Header({ userEmail, onMenuToggle, onLogout, actions }: HeaderProps) {
  const getInitials = (email: string) => email.substring(0, 2).toUpperCase();

  return (
    <header className="h-14 sm:h-16 bg-card border-b border-border px-4 sm:px-6 flex items-center justify-between">
      <div className="flex items-center gap-2">
        {onMenuToggle && (
          <button
            type="button"
            className="md:hidden h-9 w-9 inline-flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
            onClick={onMenuToggle}
          >
            <Menu className="h-5 w-5" />
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 sm:gap-4">
        {actions}

        <div className="relative group">
          <div className="flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity">
            <div className="text-right hidden sm:block">
              <p className="text-sm font-medium text-foreground">{userEmail}</p>
            </div>
            <div className="h-8 w-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-medium">
              {getInitials(userEmail)}
            </div>
          </div>

          {/* Simple dropdown on hover — products can replace with Radix DropdownMenu */}
          <div className="absolute right-0 top-full mt-1 w-56 bg-card border border-border rounded-md shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
            <div className="px-3 py-2 border-b border-border">
              <p className="text-sm font-medium text-foreground">{userEmail}</p>
            </div>
            <button
              onClick={onLogout}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-destructive hover:bg-accent transition-colors"
            >
              <LogOut className="h-4 w-4" />
              Sair
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
