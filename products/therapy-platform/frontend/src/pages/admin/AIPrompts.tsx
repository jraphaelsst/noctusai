import { useState } from 'react';
import { Brain, Save, ChevronDown, ChevronUp, History, Clock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
  Collapsible, CollapsibleContent, CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { useAIPrompts, useUpdateAIPrompt, useAIPromptHistory } from '@/hooks/useSettings';

interface PromptConfig {
  type: string;
  label: string;
  description: string;
}

const PROMPT_TYPES: PromptConfig[] = [
  {
    type: 'transcricao',
    label: 'Transcricao',
    description: 'Prompt utilizado para transcrever audio de sessoes em texto',
  },
  {
    type: 'resumo_base',
    label: 'Resumo Base (Track 1)',
    description: 'Prompt para gerar resumo visible ao paciente (Track 1)',
  },
  {
    type: 'resumo_clinico',
    label: 'Resumo Clinico (Track 2)',
    description: 'Prompt para gerar resumo clinico visible apenas ao terapeuta (Track 2)',
  },
  {
    type: 'longitudinal_clinica',
    label: 'Longitudinal Clinica',
    description: 'Prompt para gerar resumo longitudinal clinico (Track 2)',
  },
  {
    type: 'longitudinal_paciente',
    label: 'Longitudinal Paciente',
    description: 'Prompt para gerar resumo longitudinal do paciente (Track 1)',
  },
  {
    type: 'tags',
    label: 'Geracao de Tags',
    description: 'Prompt para gerar tags automaticas de sessoes',
  },
];

function PromptCard({ config }: { config: PromptConfig }) {
  const { data: prompts } = useAIPrompts();
  const updatePrompt = useUpdateAIPrompt();
  const [expanded, setExpanded] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [editValue, setEditValue] = useState<string | null>(null);

  const { data: history } = useAIPromptHistory(historyOpen ? config.type : '');

  const promptsMap = (prompts as Record<string, string>) ?? {};
  const currentPrompt = promptsMap[config.type] ?? '';

  const startEdit = () => {
    setEditValue(currentPrompt);
    setExpanded(true);
  };

  const save = () => {
    if (editValue == null) return;
    updatePrompt.mutate({ type: config.type, prompt: editValue });
    setEditValue(null);
  };

  const isEditing = editValue != null;
  const historyItems = (history as Array<Record<string, unknown>>) ?? [];

  return (
    <Card>
      <Collapsible open={expanded} onOpenChange={setExpanded}>
        <CollapsibleTrigger asChild>
          <CardHeader className="cursor-pointer hover:bg-accent/50 transition-colors">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Brain className="h-5 w-5 text-primary" />
                <div>
                  <CardTitle className="text-base">{config.label}</CardTitle>
                  <p className="text-xs text-muted-foreground mt-0.5">{config.description}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={currentPrompt ? 'default' : 'outline'}>
                  {currentPrompt ? 'Configurado' : 'Nao configurado'}
                </Badge>
                {expanded ? (
                  <ChevronUp className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                )}
              </div>
            </div>
          </CardHeader>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <CardContent className="space-y-4 pt-0">
            <textarea
              className="w-full min-h-[200px] p-3 text-sm border rounded-md bg-background resize-y focus:outline-none focus:ring-2 focus:ring-ring"
              value={isEditing ? editValue : currentPrompt}
              onChange={e => setEditValue(e.target.value)}
              onFocus={() => { if (!isEditing) startEdit(); }}
              placeholder="Cole ou escreva o prompt aqui..."
            />

            <div className="flex items-center justify-between">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setHistoryOpen(!historyOpen)}
              >
                <History className="h-3.5 w-3.5 mr-1" />
                {historyOpen ? 'Fechar historico' : 'Ver historico'}
              </Button>

              {isEditing && (
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setEditValue(null)}
                  >
                    Cancelar
                  </Button>
                  <Button
                    size="sm"
                    onClick={save}
                    disabled={updatePrompt.isPending || editValue === currentPrompt}
                  >
                    <Save className="h-3.5 w-3.5 mr-1" /> Salvar
                  </Button>
                </div>
              )}
            </div>

            {/* History */}
            {historyOpen && (
              <div className="space-y-3 mt-4">
                <Separator />
                <h4 className="text-sm font-medium flex items-center gap-2">
                  <Clock className="h-4 w-4" /> Historico de Versoes
                </h4>
                {historyItems.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Nenhuma alteracao registrada.</p>
                ) : (
                  <div className="space-y-3">
                    {historyItems.map((entry, i) => (
                      <Card key={i} className="bg-muted/50">
                        <CardContent className="p-3 space-y-2">
                          <div className="flex items-center justify-between text-xs text-muted-foreground">
                            <span>Alterado por: {(entry.changed_by as string) ?? 'Sistema'}</span>
                            <span>
                              {entry.changed_at
                                ? new Date(entry.changed_at as string).toLocaleString('pt-BR')
                                : '-'}
                            </span>
                          </div>
                          <details className="text-xs">
                            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                              Ver prompt anterior
                            </summary>
                            <pre className="mt-2 p-2 bg-background rounded text-xs whitespace-pre-wrap">
                              {(entry.old_value as string) ?? '(vazio)'}
                            </pre>
                          </details>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
}

export default function AdminAIPrompts() {
  return (
    <div className="container mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Brain className="h-6 w-6" /> Prompts de IA
        </h1>
        <p className="text-muted-foreground">
          Configure os prompts utilizados pelo sistema de inteligencia artificial
        </p>
      </div>

      <div className="space-y-4">
        {PROMPT_TYPES.map(config => (
          <PromptCard key={config.type} config={config} />
        ))}
      </div>
    </div>
  );
}
