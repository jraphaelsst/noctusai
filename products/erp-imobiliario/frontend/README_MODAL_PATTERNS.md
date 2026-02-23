# 🎯 Guia Rápido: Padrões de Modais

## 📌 Regra de Ouro

**TODA alteração em modal DEVE aparecer instantaneamente na UI sem fechar o modal.**

## ✅ Implementação Correta

### 1️⃣ Use formData, NÃO props

```typescript
// ❌ ERRADO
<h3>{entity.nome}</h3>

// ✅ CORRETO  
<h3>{formData.nome}</h3>
```

### 2️⃣ Inicialize formData

```typescript
const [formData, setFormData] = useState({
  campo1: entity.campo1 || '',
  campo2: entity.campo2 || '',
});
```

### 3️⃣ Não feche após salvar

```typescript
const handleSave = async () => {
  await updateEntity.mutateAsync({ id: entity.id, ...formData });
  setIsEditing(false); // ✅ Apenas sai do modo edição
  // onOpenChange(false); // ❌ NÃO feche o modal!
};
```

## 📚 Documentação Completa

Veja [MODAL_PATTERNS.md](./MODAL_PATTERNS.md) para detalhes completos.

## 🔍 Modais de Referência

- ✅ `MetaDetalhesModal.tsx`
- ✅ `UsuarioDetalhesModal.tsx`
- ✅ `ConfiguracoesMetasModal.tsx`

---

**Lembre-se**: Sempre use formData para exibição, não as props originais!
