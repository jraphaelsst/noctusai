/**
 * NoctusAI Global Header Component
 *
 * Full-featured header with:
 * - Hamburger menu toggle (mobile)
 * - Notification slot (product-specific)
 * - User card with HoverCard (avatar, name, role, edit profile, change password)
 * - Dark/light theme toggle
 * - Logout
 *
 * Products pass user data and callbacks via props — no product-specific imports.
 */
import { useState } from "react";
import { Menu, LogOut, Moon, Sun, Edit2, Lock } from "lucide-react";
import { HoverCard, HoverCardTrigger, HoverCardContent } from "../ui/hover-card";

export interface HeaderUser {
  id?: string;
  name: string;
  email: string;
  phone?: string;
  avatar?: string;
  role: string;
}

export interface HeaderProps {
  user: HeaderUser;
  onMenuToggle?: () => void;
  /**
   * Logout behavior:
   * - "signout": Actually signs out the user (Core platform only)
   * - "redirect": Redirects to platformUrl without signing out (products — SSO stays active)
   * Defaults to "signout".
   */
  logoutBehavior?: "signout" | "redirect";
  /** URL to redirect to when logoutBehavior is "redirect" (e.g., Core dashboard URL) */
  platformUrl?: string;
  /** Called when logoutBehavior is "signout". Performs the actual sign-out. */
  onLogout: () => void;
  /** Current theme: 'light' or 'dark' */
  theme: "light" | "dark";
  /** Called when user toggles theme */
  onThemeToggle: () => void;
  /** Slot for product-specific actions (notification bell, etc.) */
  actions?: React.ReactNode;
  /** Whether the user can edit their email (admin-only in some products) */
  canEditEmail?: boolean;
  /** Called when user saves profile edits */
  onUpdateProfile?: (data: { name: string; email: string; phone: string }) => Promise<void>;
  /** Called when user changes password */
  onUpdatePassword?: (newPassword: string) => Promise<void>;
  /** Visual variant: 'default' uses bg-card, 'dark' uses sidebar colors for the header bar */
  variant?: "default" | "dark";
}

export function Header({
  user,
  onMenuToggle,
  logoutBehavior = "signout",
  platformUrl,
  onLogout,
  theme,
  onThemeToggle,
  actions,
  canEditEmail = false,
  onUpdateProfile,
  onUpdatePassword,
  variant = "default",
}: HeaderProps) {
  const [editMode, setEditMode] = useState<"profile" | "password" | null>(null);
  const [formData, setFormData] = useState({
    name: user.name,
    email: user.email,
    phone: user.phone || "",
  });
  const [passwordData, setPasswordData] = useState({
    newPassword: "",
    confirmPassword: "",
  });
  const [saving, setSaving] = useState(false);

  const getInitials = (name: string) => {
    const parts = name.split(" ");
    if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    return name.substring(0, 2).toUpperCase();
  };

  const formatName = (name: string) =>
    name
      .toLowerCase()
      .split(" ")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");

  const handleSaveProfile = async () => {
    if (!onUpdateProfile) return;
    setSaving(true);
    try {
      await onUpdateProfile({
        name: formData.name,
        email: formData.email,
        phone: formData.phone,
      });
      setEditMode(null);
    } finally {
      setSaving(false);
    }
  };

  const handleSavePassword = async () => {
    if (!onUpdatePassword) return;
    if (passwordData.newPassword !== passwordData.confirmPassword) return;
    if (passwordData.newPassword.length < 8) return;
    setSaving(true);
    try {
      await onUpdatePassword(passwordData.newPassword);
      setPasswordData({ newPassword: "", confirmPassword: "" });
      setEditMode(null);
    } finally {
      setSaving(false);
    }
  };

  return (
    <header className={`h-14 sm:h-16 border-b px-4 sm:px-6 flex items-center justify-between ${
      variant === "dark"
        ? "bg-sidebar border-sidebar-border"
        : "bg-card border-border"
    }`}>
      <div className="flex items-center gap-2">
        {onMenuToggle && (
          <button
            type="button"
            className={`md:hidden h-9 w-9 inline-flex items-center justify-center rounded-md transition-colors ${
              variant === "dark"
                ? "text-sidebar-foreground/70 hover:text-sidebar-foreground hover:bg-sidebar-accent"
                : "text-muted-foreground hover:text-foreground hover:bg-accent"
            }`}
            onClick={onMenuToggle}
          >
            <Menu className="h-5 w-5" />
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 sm:gap-4">
        {actions}

        <HoverCard openDelay={0} closeDelay={0}>
          <HoverCardTrigger asChild>
            <div className="flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity">
              <div className="text-right hidden sm:block">
                <p className={`text-sm font-medium ${variant === "dark" ? "text-sidebar-foreground" : "text-foreground"}`}>{formatName(user.name)}</p>
                <p className={`text-xs ${variant === "dark" ? "text-sidebar-foreground/60" : "text-muted-foreground"}`}>{user.role}</p>
              </div>
              <div className="h-8 w-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-medium overflow-hidden">
                {user.avatar ? (
                  <img src={user.avatar} alt={user.name} className="h-full w-full object-cover" />
                ) : (
                  getInitials(user.name)
                )}
              </div>
            </div>
          </HoverCardTrigger>

          <HoverCardContent className="w-[calc(100vw-2rem)] sm:w-80 md:w-96" align="end">
            <div className="space-y-3 md:space-y-4">
              {/* User info + actions */}
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                  <div className="h-10 w-10 md:h-12 md:w-12 shrink-0 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs md:text-sm font-medium overflow-hidden">
                    {user.avatar ? (
                      <img src={user.avatar} alt={user.name} className="h-full w-full object-cover" />
                    ) : (
                      getInitials(user.name)
                    )}
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm md:text-base font-semibold truncate">{formatName(user.name)}</p>
                    <p className="text-[11px] sm:text-xs text-muted-foreground truncate">{user.role}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => {
                      if (logoutBehavior === "redirect" && platformUrl) {
                        window.location.href = platformUrl;
                      } else {
                        onLogout();
                      }
                    }}
                    title={logoutBehavior === "redirect" ? "Voltar ao NoctusAI" : "Sair"}
                    className="h-8 w-8 inline-flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                  >
                    <LogOut className="h-4 w-4" />
                  </button>
                  <button
                    onClick={onThemeToggle}
                    className="h-8 w-8 inline-flex items-center justify-center rounded-md text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                  >
                    {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              {/* Separator */}
              <div className="h-px bg-border" />

              {/* Edit profile form */}
              {editMode === "profile" && onUpdateProfile ? (
                <div className="space-y-3">
                  <div>
                    <label className="text-sm font-medium">Nome</label>
                    <input
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      className="mt-1 w-full h-10 md:h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
                    />
                  </div>
                  <div>
                    <label className="text-sm font-medium">Email</label>
                    <input
                      type="email"
                      value={formData.email}
                      onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                      disabled={!canEditEmail}
                      className="mt-1 w-full h-9 rounded-md border border-input bg-background px-3 text-sm disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
                    />
                    {!canEditEmail && (
                      <p className="text-xs text-muted-foreground mt-1">
                        Apenas administradores podem alterar o email
                      </p>
                    )}
                  </div>
                  <div>
                    <label className="text-sm font-medium">Telefone</label>
                    <input
                      value={formData.phone}
                      onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                      className="mt-1 w-full h-10 md:h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
                    />
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        setEditMode(null);
                        setFormData({ name: user.name, email: user.email, phone: user.phone || "" });
                      }}
                      className="flex-1 h-10 md:h-8 rounded-md border border-input bg-background text-sm hover:bg-accent transition-colors"
                    >
                      Cancelar
                    </button>
                    <button
                      onClick={handleSaveProfile}
                      disabled={saving}
                      className="flex-1 h-10 md:h-8 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
                    >
                      {saving ? "Salvando..." : "Salvar"}
                    </button>
                  </div>
                </div>
              ) : editMode === "password" && onUpdatePassword ? (
                <div className="space-y-3">
                  <div>
                    <label className="text-sm font-medium">Nova Senha</label>
                    <input
                      type="password"
                      value={passwordData.newPassword}
                      onChange={(e) => setPasswordData({ ...passwordData, newPassword: e.target.value })}
                      className="mt-1 w-full h-10 md:h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
                    />
                  </div>
                  <div>
                    <label className="text-sm font-medium">Confirmar Senha</label>
                    <input
                      type="password"
                      value={passwordData.confirmPassword}
                      onChange={(e) => setPasswordData({ ...passwordData, confirmPassword: e.target.value })}
                      className="mt-1 w-full h-10 md:h-9 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1"
                    />
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => {
                        setEditMode(null);
                        setPasswordData({ newPassword: "", confirmPassword: "" });
                      }}
                      className="flex-1 h-10 md:h-8 rounded-md border border-input bg-background text-sm hover:bg-accent transition-colors"
                    >
                      Cancelar
                    </button>
                    <button
                      onClick={handleSavePassword}
                      disabled={saving}
                      className="flex-1 h-10 md:h-8 rounded-md bg-primary text-primary-foreground text-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
                    >
                      Atualizar Senha
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-1">
                  {onUpdateProfile && (
                    <button
                      onClick={() => {
                        setFormData({ name: user.name, email: user.email, phone: user.phone || "" });
                        setEditMode("profile");
                      }}
                      className="w-full flex items-center gap-2 px-3 py-3 md:py-2 text-sm rounded-md hover:bg-accent transition-colors"
                    >
                      <Edit2 className="h-4 w-4" />
                      Editar Perfil
                    </button>
                  )}
                  {onUpdatePassword && (
                    <button
                      onClick={() => setEditMode("password")}
                      className="w-full flex items-center gap-2 px-3 py-3 md:py-2 text-sm rounded-md hover:bg-accent transition-colors"
                    >
                      <Lock className="h-4 w-4" />
                      Trocar Senha
                    </button>
                  )}
                </div>
              )}
            </div>
          </HoverCardContent>
        </HoverCard>
      </div>
    </header>
  );
}
