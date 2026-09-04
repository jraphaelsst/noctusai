import { useState } from 'react'
import styled from 'styled-components'
import swal from 'sweetalert2'
import useAxios from '../../utils/useAxios'
import { color, spacing } from '../../styles'

const Form = styled.form`
  display: flex;
  flex-direction: column;
  gap: ${spacing.md};
`

const FormField = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${spacing.xs};
`

const Label = styled.label`
  font-size: 14px;
  font-weight: 500;
  color: ${color.text};
`

const Input = styled.input`
  padding: ${spacing.sm} ${spacing.md};
  border: 1px solid ${color.border};
  font-size: 14px;
  transition: border-color 0.2s ease;

  &:focus {
    outline: none;
    border-color: ${color.primary};
  }
`

const Button = styled.button`
  padding: ${spacing.md} ${spacing.lg};
  background: ${color.primary};
  color: ${color.textInverse};
  border: none;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease;
  margin-top: ${spacing.md};

  &:hover {
    background: ${color.primaryDark};
  }

  &:disabled {
    background: ${color.textMuted};
    cursor: not-allowed;
  }
`

type Props = {
  onSuccess: (newTipo: { id: number; nome: string }) => void
  onClose: () => void
}

const TipoImovelForm = ({ onSuccess, onClose }: Props) => {
  const api = useAxios()

  const [loading, setLoading] = useState(false)
  const [nome, setNome] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    e.stopPropagation()
    
    if (!nome.trim()) {
      swal.fire({
        title: 'Digite o nome do tipo',
        icon: 'warning',
        toast: true,
        timer: 3000,
        position: 'top-right',
        timerProgressBar: true,
        showConfirmButton: false
      })
      return
    }
    
    setLoading(true)

    try {
      const response = await api.post('/tipo-imovel/', {
        nome: nome.trim()
      })

      swal.fire({
        title: 'Tipo cadastrado!',
        icon: 'success',
        toast: true,
        timer: 3000,
        position: 'top-right',
        timerProgressBar: true,
        showConfirmButton: false
      })

      onSuccess(response.data)
    } catch (error: any) {
      console.error('Error creating tipo imovel:', error)
      let errorMessage = 'Erro ao cadastrar'
      if (error?.response?.status === 400) {
        const responseData = error?.response?.data
        if (responseData?.nome) {
          errorMessage = 'Esse tipo de imóvel já existe'
        } else {
          errorMessage = 'Dados inválidos'
        }
      }
      swal.fire({
        title: errorMessage,
        icon: 'error',
        toast: true,
        timer: 3000,
        position: 'top-right',
        timerProgressBar: true,
        showConfirmButton: false
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <Form onSubmit={handleSubmit} onClick={(e) => e.stopPropagation()}>
      <FormField>
        <Label>Nome do Tipo *</Label>
        <Input
          type="text"
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          placeholder="Ex: Casa, Apartamento, Terreno..."
          required
        />
      </FormField>

      <Button type="submit" disabled={loading}>
        {loading ? 'Cadastrando...' : 'Cadastrar Tipo'}
      </Button>
    </Form>
  )
}

export default TipoImovelForm
