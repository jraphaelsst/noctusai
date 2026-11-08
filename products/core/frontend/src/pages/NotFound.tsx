import { Link } from 'react-router-dom';

/** Core's single unknown-path page. Admin URLs render this too for anyone who is not a platform admin. */
export function NotFound() {
  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-3 p-4 text-center">
      <h1 className="text-xl font-semibold">Página não encontrada</h1>
      <p className="text-sm text-muted-foreground">O endereço que você abriu não existe.</p>
      <Link to="/" className="mt-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground">
        Ir para o início
      </Link>
    </div>
  );
}
