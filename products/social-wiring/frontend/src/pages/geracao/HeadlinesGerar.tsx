/**
 * Gerar headlines — landing (P7, `/media-creation/chat/gerar-headlines`, contract §7.7,
 * page-map-v2 §16). Three cards that open the form: `?who=me|public|viral`.
 */
import { BookOpen, Flame, User, Users } from "lucide-react";
import { Link } from "react-router-dom";

import { PaginaCabecalho, usePaginaPadding } from "@/components/geracao/PaginaCabecalho";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export const HEADLINES_FORM_PATH = "/media-creation/headlines";

const CARTOES = [
  {
    who: "me",
    titulo: "Sobre mim",
    descricao: "Headlines com base nas suas convicções, hábitos e histórias de vida.",
    Icone: User,
  },
  {
    who: "public",
    titulo: "Sobre meu público",
    descricao: "Headlines com base em dores, desejos, crenças e demais características do seu público alvo.",
    Icone: Users,
  },
  {
    who: "viral",
    titulo: "Assuntos do Virais",
    descricao: "Headlines com assuntos em alta que conectam com o seu público-alvo.",
    Icone: Flame,
  },
] as const;

export default function HeadlinesGerar() {
  const padding = usePaginaPadding();
  return (
    <div className={`space-y-6 ${padding}`}>
      <PaginaCabecalho
        titulo={
          <span className="flex items-center gap-2">
            <BookOpen className="h-6 w-6" /> Gerar headlines
          </span>
        }
        descricao="Selecione o assunto que deseja gerar suas headlines"
      />

      <div className="grid gap-4 md:grid-cols-3">
        {CARTOES.map(({ who, titulo, descricao, Icone }) => (
          <Card key={who} data-testid={`card-${who}`}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-lg">
                <Icone className="h-5 w-5" /> {titulo}
              </CardTitle>
              <CardDescription>{descricao}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild>
                <Link to={`${HEADLINES_FORM_PATH}?who=${who}`}>Gerar Headlines</Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
