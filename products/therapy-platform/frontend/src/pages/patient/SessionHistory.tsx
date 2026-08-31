import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Clock, FileText, ChevronRight, Loader2 } from 'lucide-react';
import { Card, CardContent } from '@noctusai/seed/components/ui/card';
import { Badge } from '@noctusai/seed/components/ui/badge';
import { Button } from '@noctusai/seed/components/ui/button';
import { useSessionJournal } from '@/hooks/useJournal';

export default function SessionHistory() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const { data, isPending } = useSessionJournal(page, pageSize);
  const showSkeleton = isPending && !data;

  const sessions = data?.data ?? [];
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Minhas Sessoes</h1>
        <p className="mt-1 text-sm text-gray-500">Historico de sessoes e resumos</p>
      </div>

      {showSkeleton && (
        <div className="flex h-40 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
        </div>
      )}

      {!isPending && sessions.length === 0 && (
        <div className="flex h-40 items-center justify-center rounded-lg border border-dashed">
          <div className="text-center">
            <FileText className="mx-auto h-8 w-8 text-gray-300" />
            <p className="mt-2 text-sm text-gray-500">Nenhuma sessao registrada ainda.</p>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {sessions.map((session) => {
          const date = new Date(session.created_at).toLocaleDateString('pt-BR', {
            day: '2-digit',
            month: 'long',
            year: 'numeric',
          });
          const time = new Date(session.created_at).toLocaleTimeString('pt-BR', {
            hour: '2-digit',
            minute: '2-digit',
          });

          // Preview text from combined transcript or a summary if available
          const preview = session.combined_transcript_text
            ? session.combined_transcript_text.slice(0, 150) + (session.combined_transcript_text.length > 150 ? '...' : '')
            : 'Resumo sendo processado...';

          return (
            <Card
              key={session.id}
              className="cursor-pointer transition-colors hover:bg-gray-50"
              onClick={() => navigate(`/patient/sessoes/${session.id}`)}
            >
              <CardContent className="flex items-center gap-4 p-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-blue-50">
                  <FileText className="h-5 w-5 text-blue-600" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-gray-900">{date}</span>
                    <span className="text-xs text-gray-400">{time}</span>
                    {session.ai_generated_at && (
                      <Badge variant="secondary" className="text-[10px]">Resumo disponivel</Badge>
                    )}
                  </div>
                  <p className="mt-1 truncate text-sm text-gray-500">{preview}</p>
                </div>
                <ChevronRight className="h-5 w-5 shrink-0 text-gray-300" />
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Anterior
          </Button>
          <span className="text-sm text-gray-500">
            Pagina {page} de {totalPages}
          </span>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            Proxima
          </Button>
        </div>
      )}
    </div>
  );
}
