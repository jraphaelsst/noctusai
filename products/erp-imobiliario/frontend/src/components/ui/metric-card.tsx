import { Card, CardContent, CardHeader, CardTitle } from "@noctusai/seed/components/ui/card";
import { cn } from "@/lib/utils";
import { LucideIcon } from "lucide-react";

interface MetricCardProps {
  title: string;
  value: string | number;
  description?: string;
  icon: LucideIcon;
  variant?: "default" | "success" | "warning" | "danger";
  trend?: {
    value: number;
    isPositive: boolean;
  };
  onClick?: () => void;
}

export function MetricCard({
  title,
  value,
  description,
  icon: Icon,
  variant = "default",
  trend,
  onClick,
}: MetricCardProps) {
  const variantStyles = {
    default: "border-border",
    success: "border-success/20 bg-success-light/50",
    warning: "border-warning/20 bg-warning-light/50",
    danger: "border-danger/20 bg-danger-light/50",
  };

  return (
    <Card 
      className={cn(
        "transition-all hover:shadow-lg hover:scale-[1.02]", 
        variantStyles[variant],
        onClick && "cursor-pointer"
      )}
      onClick={onClick}
    >
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold text-foreground mb-1">{value}</div>
        {description && (
          <p className="text-xs text-muted-foreground">{description}</p>
        )}
        {trend && (
          <div className="flex items-center mt-2">
            <span
              className={cn(
                "text-xs font-medium",
                trend.isPositive ? "text-success" : "text-danger"
              )}
            >
              {trend.isPositive ? "+" : ""}{trend.value}%
            </span>
            <span className="text-xs text-muted-foreground ml-1">
              vs. período anterior
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}