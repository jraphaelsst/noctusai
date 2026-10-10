/**
 * Carrosséis e posts de imagem (CoreStudio, `/media-creation/carrosseis`) — the
 * legacy "Criação de mídia" Biblioteca + Novo post tabs, unchanged
 * (esteira-contract §A.5 A-2): storyboard → prompts de imagem → render → legenda
 * → avaliação (Método Audience).
 */
import { useState } from "react";
import { Library, Plus, Wand2 } from "lucide-react";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ComposeTab } from "@/components/geracao/carrosseis/ComposeTab";
import { LibraryTab } from "@/components/geracao/carrosseis/LibraryTab";

export default function Carrosseis() {
  const [selectedPostId, setSelectedPostId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"library" | "compose">("library");

  return (
    <div className="space-y-6 p-6" data-testid="carrosseis-page">
      <header>
        <h1 className="flex items-center gap-2 text-2xl font-semibold">
          <Wand2 className="h-6 w-6 text-primary" />
          Carrosséis e posts de imagem
        </h1>
        <p className="text-sm text-muted-foreground">
          Brief → roteiro → prompts → legenda. Os prompts saem prontos para o GalilAI / Nano
          Banana / Midjourney.
        </p>
      </header>

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as typeof activeTab)}>
        <TabsList>
          <TabsTrigger value="library" className="gap-2">
            <Library className="h-4 w-4" />
            Biblioteca
          </TabsTrigger>
          <TabsTrigger value="compose" className="gap-2">
            <Plus className="h-4 w-4" />
            Novo post
          </TabsTrigger>
        </TabsList>

        <TabsContent value="library" className="mt-4">
          <LibraryTab selectedPostId={selectedPostId} onSelect={setSelectedPostId} />
        </TabsContent>

        <TabsContent value="compose" className="mt-4">
          <ComposeTab
            onCreated={(id) => {
              setSelectedPostId(id);
              setActiveTab("library");
            }}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
