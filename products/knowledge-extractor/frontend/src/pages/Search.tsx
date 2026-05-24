/**
 * Search — query the vector knowledge base.
 *
 * GET /api/kb/search?q=&k= → { query, configured, results }. When
 * `configured === false` the KB isn't wired (no embeddings backend) so
 * we show a dedicated empty state rather than "zero results".
 */
import { useState } from "react";
import { Loader2, Search as SearchIcon, ServerCrash } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

import { useSearch } from "@/hooks/useSearch";

export default function Search() {
  const [query, setQuery] = useState("");
  const { data, loading, error, searched, run } = useSearch(8);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void run(query);
  };

  return (
    <div className="container max-w-3xl space-y-6 py-6">
      <div className="flex items-center gap-3">
        <SearchIcon className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Busca</h1>
          <p className="text-sm text-muted-foreground">
            Pesquise no conhecimento processado por similaridade semântica.
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          placeholder="Ex.: como estruturar uma oferta irresistível"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Termo de busca"
        />
        <Button type="submit" disabled={loading || !query.trim()}>
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <>
              <SearchIcon className="mr-2 h-4 w-4" /> Buscar
            </>
          )}
        </Button>
      </form>

      {error && (
        <Card>
          <CardContent className="p-4 text-sm text-destructive">
            {error.message}
          </CardContent>
        </Card>
      )}

      {/* KB not configured */}
      {data && !data.configured && (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-card py-12 text-center text-sm text-muted-foreground">
          <ServerCrash className="h-8 w-8" />
          <p className="max-w-md">
            KB não configurada. A busca semântica precisa de um backend de
            embeddings. Configure-o nas variáveis de ambiente do servidor.
          </p>
        </div>
      )}

      {/* Results */}
      {data && data.configured && (
        <>
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-12 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
              Buscando…
            </div>
          ) : data.results.length === 0 ? (
            <div className="flex flex-col items-center gap-2 py-12 text-center text-sm text-muted-foreground">
              <SearchIcon className="h-8 w-8" />
              {searched
                ? `Nenhum resultado para "${data.query}".`
                : "Digite um termo e busque."}
            </div>
          ) : (
            <div className="space-y-3">
              {data.results.map((r) => (
                <Card key={r.document_id}>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between gap-3">
                      <CardTitle className="flex items-center gap-2 text-sm">
                        {r.module && (
                          <Badge variant="outline">{r.module}</Badge>
                        )}
                        <span className="font-mono text-xs text-muted-foreground">
                          {r.document_id}
                        </span>
                      </CardTitle>
                      <Badge variant="secondary" className="tabular-nums">
                        {r.score.toFixed(3)}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm leading-relaxed text-foreground">
                      {r.text}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </>
      )}

      {/* Initial state — nothing searched yet */}
      {!data && !loading && (
        <div className="flex flex-col items-center gap-2 py-12 text-center text-sm text-muted-foreground">
          <SearchIcon className="h-8 w-8" />
          Digite um termo e busque no conhecimento processado.
        </div>
      )}
    </div>
  );
}
