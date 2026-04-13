export function Dashboard() {
  return (
    <div>
      <h1 className="text-xl sm:text-2xl font-bold text-foreground">Dashboard</h1>
      <p className="text-sm text-muted-foreground mt-1">
        Bem-vindo ao {{PRODUCT_NAME}}
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6 mt-6">
        {/* Stat cards go here */}
        <div className="bg-card rounded-lg border border-border shadow-sm p-6">
          <p className="text-sm text-muted-foreground">Metrica 1</p>
          <p className="text-2xl font-bold text-foreground mt-1">0</p>
        </div>
        <div className="bg-card rounded-lg border border-border shadow-sm p-6">
          <p className="text-sm text-muted-foreground">Metrica 2</p>
          <p className="text-2xl font-bold text-foreground mt-1">0</p>
        </div>
        <div className="bg-card rounded-lg border border-border shadow-sm p-6">
          <p className="text-sm text-muted-foreground">Metrica 3</p>
          <p className="text-2xl font-bold text-foreground mt-1">0</p>
        </div>
      </div>
    </div>
  );
}
