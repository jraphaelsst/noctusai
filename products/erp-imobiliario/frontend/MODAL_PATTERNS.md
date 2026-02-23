# Padrões de Implementação de Modais

## 🎯 Objetivo
Este documento define os padrões obrigatórios para implementação de modais no projeto, garantindo consistência e melhor experiência do usuário.

## ✅ Regra Principal: Atualização Automática de UI

**TODA alteração feita em um modal DEVE refletir imediatamente na interface, sem necessidade de recarregar ou fechar o modal.**

### Por que isso é importante?
- **Feedback Instantâneo**: O usuário vê as mudanças acontecendo em tempo real
- **Melhor UX**: Evita confusão sobre se a alteração foi salva ou não
- **Consistência**: Todos os modais se comportam da mesma forma

## 📋 Padrão de Implementação

### 1. Estrutura de Estado Local

```typescript
const [formData, setFormData] = useState({
  campo1: entidade.campo1 || valorPadrao,
  campo2: entidade.campo2 || valorPadrao,
  // ... outros campos
});
```

### 2. Exibir Dados do formData, NÃO da prop original

❌ **ERRADO:**
```typescript
<div>
  <h3>{meta.nome}</h3> {/* Não atualiza automaticamente */}
  <p>{meta.descricao}</p>
</div>
```

✅ **CORRETO:**
```typescript
<div>
  <h3>{formData.nome}</h3> {/* Atualiza automaticamente */}
  <p>{formData.descricao}</p>
</div>
```

### 3. Atualizar formData ao Salvar

```typescript
const handleSave = async () => {
  await updateMutation.mutateAsync({
    id: entidade.id,
    ...formData
  });
  
  // NÃO feche o modal imediatamente se o usuário pode continuar editando
  // setIsEditing(false); // Apenas mude o estado de edição se aplicável
};
```

### 4. Sincronizar formData com Props quando necessário

```typescript
useEffect(() => {
  setFormData({
    campo1: entidade.campo1 || valorPadrao,
    campo2: entidade.campo2 || valorPadrao,
  });
}, [entidade]); // Atualiza quando a entidade externa mudar
```

## 🔄 Padrão de Edição Inline

Para campos editáveis diretamente no modal (sem modo de edição):

```typescript
const [isEditingCampo, setIsEditingCampo] = useState(false);

const handleSaveCampo = async () => {
  await updateMutation.mutateAsync({
    id: entidade.id,
    campo: formData.campo
  });
  setIsEditingCampo(false);
  // formData já está atualizado, a UI reflete automaticamente
};

// Na UI:
{isEditingCampo ? (
  <>
    <Input
      value={formData.campo}
      onChange={(e) => setFormData({ ...formData, campo: e.target.value })}
    />
    <Button onClick={handleSaveCampo}>
      <Check />
    </Button>
    <Button onClick={() => {
      setIsEditingCampo(false);
      setFormData({ ...formData, campo: entidade.campo }); // Restaura valor original
    }}>
      <X />
    </Button>
  </>
) : (
  <>
    <p>{formData.campo}</p>
    <Button onClick={() => setIsEditingCampo(true)}>
      <Edit2 />
    </Button>
  </>
)}
```

## 📝 Exemplos de Implementação

### Exemplo 1: Modal de Detalhes com Edição

```typescript
export function EntityDetalhesModal({ entity, open, onOpenChange }) {
  const [isEditing, setIsEditing] = useState(false);
  const [formData, setFormData] = useState({
    nome: entity.nome || '',
    descricao: entity.descricao || '',
    valor: entity.valor || 0,
  });
  
  const updateEntity = useUpdateEntity();
  
  const handleSave = async () => {
    await updateEntity.mutateAsync({
      id: entity.id,
      ...formData
    });
    setIsEditing(false);
    // UI já reflete as mudanças via formData
  };
  
  const handleCancel = () => {
    setIsEditing(false);
    // Restaura valores originais
    setFormData({
      nome: entity.nome || '',
      descricao: entity.descricao || '',
      valor: entity.valor || 0,
    });
  };
  
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        {isEditing ? (
          <form onSubmit={(e) => { e.preventDefault(); handleSave(); }}>
            <Input
              value={formData.nome}
              onChange={(e) => setFormData({ ...formData, nome: e.target.value })}
            />
            {/* ... outros campos ... */}
            <Button type="submit">Salvar</Button>
            <Button type="button" onClick={handleCancel}>Cancelar</Button>
          </form>
        ) : (
          <div>
            <h3>{formData.nome}</h3>
            <p>{formData.descricao}</p>
            <p>{formData.valor}</p>
            <Button onClick={() => setIsEditing(true)}>Editar</Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

### Exemplo 2: Modal de Criação

```typescript
export function NovoEntityModal({ onSuccess }) {
  const [open, setOpen] = useState(false);
  const [formData, setFormData] = useState({
    nome: '',
    descricao: '',
    valor: 0,
  });
  
  const createEntity = useCreateEntity();
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    await createEntity.mutateAsync(formData);
    
    // Limpar formulário
    setFormData({
      nome: '',
      descricao: '',
      valor: 0,
    });
    
    setOpen(false);
    onSuccess?.();
  };
  
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Nova Entidade</Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <Input
            value={formData.nome}
            onChange={(e) => setFormData({ ...formData, nome: e.target.value })}
            required
          />
          {/* ... outros campos ... */}
          <Button type="submit">Criar</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

## 🚫 Anti-Padrões (Evitar)

### ❌ Não usar props diretamente na exibição durante edição

```typescript
// ERRADO
<div>
  <h3>{entity.nome}</h3> {/* Não reflete mudanças do formData */}
  <Input
    value={formData.nome}
    onChange={(e) => setFormData({ ...formData, nome: e.target.value })}
  />
</div>
```

### ❌ Não fechar modal imediatamente após salvar se usuário pode continuar editando

```typescript
// ERRADO
const handleSave = async () => {
  await updateEntity.mutateAsync(formData);
  onOpenChange(false); // Fecha antes do usuário ver a mudança
};

// CERTO
const handleSave = async () => {
  await updateEntity.mutateAsync(formData);
  setIsEditing(false); // Apenas sai do modo de edição
  // Deixa o usuário ver as mudanças e decidir se quer continuar
};
```

### ❌ Não misturar exibição de props e formData

```typescript
// ERRADO - Inconsistente
<div>
  <h3>{formData.nome}</h3> {/* Usa formData */}
  <p>{entity.descricao}</p> {/* Usa prop original */}
</div>

// CERTO - Consistente
<div>
  <h3>{formData.nome}</h3>
  <p>{formData.descricao}</p>
</div>
```

## 🔍 Checklist de Revisão

Ao criar ou revisar um modal, verifique:

- [ ] ✅ Estado local `formData` criado com valores iniciais da entidade
- [ ] ✅ Todos os campos exibidos usam `formData`, não a prop original
- [ ] ✅ Inputs atualizam `formData` no `onChange`
- [ ] ✅ Função de salvar persiste dados mas mantém modal aberto (quando aplicável)
- [ ] ✅ Botão cancelar restaura `formData` aos valores originais
- [ ] ✅ useEffect sincroniza `formData` quando a prop externa mudar (se necessário)
- [ ] ✅ Feedback visual de loading durante salvamento
- [ ] ✅ Validação de campos antes de salvar

## 📚 Modais de Referência

Os seguintes modais já implementam esse padrão corretamente:

- ✅ `MetaDetalhesModal.tsx` - Edição inline de nome com atualização automática
- ✅ `NovaMetaModal.tsx` - Criação com limpeza de formulário

## 🎓 Quando Implementar Novo Modal

1. **Copie a estrutura** de um dos modais de referência
2. **Adapte os campos** para sua entidade
3. **Teste a atualização automática**: faça uma edição e veja se reflete imediatamente na UI
4. **Verifique o checklist** acima
5. **Adicione seu modal** à lista de modais de referência se ele implementa algo novo

## 🔄 Manutenção

Este documento deve ser:
- Consultado antes de criar qualquer novo modal
- Atualizado quando novos padrões forem estabelecidos
- Revisado em code reviews para garantir conformidade

---

**Última atualização**: Após implementação do campo "nome" em MetaDetalhesModal
**Responsável**: Sistema de padrões do projeto
**Status**: 🟢 Ativo e obrigatório
