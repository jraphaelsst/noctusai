# Design System - Sistema de Gestão de Metas

## Estados de Foco

### Remoção de Indicadores de Foco
**CRÍTICO**: Todos os indicadores de foco (outlines, rings) foram removidos globalmente da plataforma.

```css
/* Configurado em src/index.css */
*:focus,
*:focus-visible {
  @apply outline-none ring-0;
}
```

**Importante**: 
- Não adicionar `focus-visible`, `focus:ring`, ou `focus:outline` em novos componentes
- Esta regra se aplica a todos os inputs, botões, e elementos interativos
- Manter este padrão para todas as criações futuras

## Paleta de Cores Pastel

### Cores Principais
```css
/* Primary - Cinza-Chumbo */
--primary: 220 10% 40%  /* Light mode */
--primary: 220 10% 50%  /* Dark mode */
--primary-foreground: 0 0% 100%
--primary-light: 220 10% 60%
--primary-dark: 220 10% 25%

/* Secondary - Cinza Neutro */
--secondary: 0 0% 70%
--secondary-foreground: 0 0% 10%
--secondary-light: 0 0% 88%

/* Accent - Cinza claro para hovers */
--accent: 0 0% 92%
--accent-foreground: 0 0% 10%
```

### Cores de Feedback (Pastel)
```css
/* Success - Verde Pastel */
--success: 140 50% 70%
--success-foreground: 140 100% 15%
--success-light: 140 40% 90%

/* Warning - Amarelo Pastel */
--warning: 45 70% 75%
--warning-foreground: 45 100% 20%
--warning-light: 45 60% 92%

/* Danger - Vermelho Pastel */
--danger: 0 60% 75%
--danger-foreground: 0 80% 25%
--danger-light: 0 50% 92%

/* Info - Azul Claro Pastel */
--info: 200 60% 75%
--info-foreground: 200 100% 20%
```

### Cores por Categoria (Metas)
```css
/* Captação - Azul Pastel */
captacao: hsl(200, 60%, 75%)

/* Visitas - Roxo Pastel */
visitas: hsl(280, 50%, 75%)

/* Contatos - Verde Pastel */
contatos: hsl(160, 50%, 70%)

/* Propostas - Amarelo Pastel */
propostas: hsl(40, 60%, 75%)

/* Fechamento - Rosa Pastel */
fechamento: hsl(340, 50%, 75%)
```

## Tipografia

### Títulos de Cards e Seções
```tsx
// Padrão para todos os títulos de cards de gráficos e seções importantes
<CardTitle className="text-2xl font-semibold mb-4">
  Título da Seção
</CardTitle>
```

### Hierarquia de Texto
- **Títulos Principais (H1)**: `text-3xl font-bold`
- **Títulos de Cards (H2)**: `text-2xl font-semibold mb-4`
- **Subtítulos (H3)**: `text-lg font-medium`
- **Texto Normal**: `text-base`
- **Texto Pequeno**: `text-sm`
- **Micro Texto**: `text-xs`

## Componentes de Progresso

### Barras de Progresso
Todas as barras de progresso no sistema seguem o padrão:
```tsx
// Altura padrão: h-2
<div className="w-full bg-muted rounded-full h-2 overflow-hidden">
  <div 
    className="h-full transition-all duration-500 rounded-full"
    style={{ 
      width: `${percentage}%`,
      backgroundColor: getProgressColor(percentage)
    }}
  />
</div>
```

### Progress Component
```tsx
// Componente base reutilizável
<Progress value={percentage} className="optional-custom" />
// Altura padrão já definida: h-2
```

## Função de Cores Dinâmicas

### getProgressColor
Função para determinar cores baseadas em porcentagem:
```typescript
const getProgressColor = (percentage: number): string => {
  if (percentage >= 80) return "hsl(var(--success))";  // Verde
  if (percentage >= 50) return "hsl(var(--warning))";  // Amarelo
  return "hsl(var(--danger))";                         // Vermelho
};
```

## Cards e Containers

### Card Padrão
```tsx
<Card>
  <CardHeader>
    <CardTitle className="text-2xl font-semibold mb-4">Título</CardTitle>
    <CardDescription>Descrição opcional</CardDescription>
  </CardHeader>
  <CardContent>
    {/* Conteúdo */}
  </CardContent>
</Card>
```

### Espaçamento Interno
- Cards principais: `space-y-6`
- Seções dentro de cards: `space-y-4`
- Elementos próximos: `space-y-2`
- Elementos inline: `gap-2`, `gap-3`, `gap-4`

## Badges e Indicators

### Badges de Status
```tsx
// Usar cores semânticas do sistema
<Badge variant="default">Status</Badge>
<Badge 
  style={{ backgroundColor: 'hsl(var(--success))' }}
>
  Ativo
</Badge>
```

### Indicadores de Cor
```tsx
// Círculo de cor para categorias
<div 
  className="w-3 h-3 rounded-full" 
  style={{ backgroundColor: categoriaColors[categoria] }}
/>
```

## Animações e Transições

### Transições Suaves
```tsx
className="transition-all duration-500"
className="hover:shadow-lg hover:scale-[1.02]"
```

### Duração Padrão
- Rápida: `duration-300`
- Média: `duration-500`
- Lenta: `duration-700`

## Responsividade

### Grid Layouts
```tsx
// Métricas em linha
<div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">

// Gráficos lado a lado
<div className="grid gap-6 md:grid-cols-2">
```

## Hover States

### Sidebar e Navegação
```css
/* Hover em itens de navegação */
--accent: 0 0% 92%  /* Cinza claro */
```

### Cards Interativos
```tsx
className="transition-all hover:shadow-lg hover:scale-[1.02] cursor-pointer"
```

## Princípios do Design System

1. **Sempre use tokens semânticos** - Nunca cores diretas como `text-white`, `bg-black`
2. **Consistência de altura** - Barras de progresso sempre `h-2`
3. **Títulos padronizados** - Sempre `text-2xl font-semibold mb-4` para títulos de cards
4. **Cores pastel** - Priorizar tons suaves e agradáveis
5. **Transições suaves** - Sempre incluir `transition-all` em elementos interativos
6. **Espaçamento uniforme** - Seguir a escala de spacing do Tailwind
7. **HSL para cores** - Todas as cores devem usar formato HSL para consistência

## Exemplos de Uso

### Metric Card
```tsx
<MetricCard
  title="Total de Metas"
  value={100}
  icon={Target}
  description="20 ativas"
  onClick={() => handleClick()}
/>
```

### Progress Section
```tsx
<div className="space-y-2">
  <div className="flex justify-between text-sm">
    <span>Taxa de Conclusão</span>
    <span className="font-medium" style={{ color: getProgressColor(percentage) }}>
      {percentage.toFixed(1)}%
    </span>
  </div>
  <div className="w-full bg-muted rounded-full h-2 overflow-hidden">
    <div 
      className="h-full transition-all duration-500 rounded-full"
      style={{ 
        width: `${Math.min(percentage, 100)}%`,
        backgroundColor: getProgressColor(percentage)
      }}
    />
  </div>
</div>
```

## Manutenção

**IMPORTANTE**: Sempre que alterar algo no design (cores, tipografia, espaçamentos, etc.), faça a atualização correspondente neste documento para manter a documentação sincronizada com o código.

Este design system deve ser consultado sempre que:
- Criar novos componentes visuais
- Adicionar gráficos ou dashboards
- Implementar novos cards ou seções
- Definir cores para novos elementos
- Padronizar barras de progresso
- Criar títulos e hierarquia de texto

**Última atualização**: 2025
