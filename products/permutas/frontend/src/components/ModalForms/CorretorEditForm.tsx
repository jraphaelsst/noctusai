import { useState, useEffect } from 'react'
import styled from 'styled-components'
import swal from 'sweetalert2'
import useAxios from '../../utils/useAxios'
import { color, spacing } from '../../styles'
import PhoneInput from '../PhoneInput'

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

type CorretorType = {
  id: number
  nome: string
  telefone: string
  email: string
  creci: string
}

type Props = {
  onSuccess: (corretor: CorretorType) => void
  onClose: () => void
  initialData?: CorretorType | null
}

const CorretorEditForm = ({ onSuccess, onClose, initialData }: Props) => {
  const api = useAxios()

  const [loading, setLoading] = useState(false)
  const [nome, setNome] = useState('')
  const [telefone, setTelefone] = useState('')
  const [email, setEmail] = useState('')
  const [creci, setCreci] = useState('')

  useEffect(() => {
    if (initialData) {
      setNome(initialData.nome || '')
      setTelefone(initialData.telefone || '')
      setEmail(initialData.email || '')
      setCreci(initialData.creci || '')
    } else {
      setNome('')
      setTelefone('')
      setEmail('')
      setCreci('')
    }
  }, [initialData])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    e.stopPropagation()
    
    if (!nome.trim()) {
      swal.fire({
        title: 'Digite o nome do corretor',
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
      const payload = {
        nome: nome.trim(),
        telefone: telefone.trim(),
        email: email.trim(),
        creci: creci.trim()
      }

      let response
      if (initialData) {
        response = await api.patch(`/corretor/${initialData.id}/`, payload)
        swal.fire({
          title: 'Corretor atualizado!',
          icon: 'success',
          toast: true,
          timer: 3000,
          position: 'top-right',
          timerProgressBar: true,
          showConfirmButton: false
        })
      } else {
        response = await api.post('/corretor/', payload)
        swal.fire({
          title: 'Corretor cadastrado!',
          icon: 'success',
          toast: true,
          timer: 3000,
          position: 'top-right',
          timerProgressBar: true,
          showConfirmButton: false
        })
      }

      onSuccess(response.data)
    } catch (error) {
      console.error('Error saving corretor:', error)
      swal.fire({
        title: initialData ? 'Erro ao atualizar' : 'Erro ao cadastrar',
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
        <Label>Nome *</Label>
        <Input
          type="text"
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          placeholder="Nome do corretor"
          required
        />
      </FormField>

      <FormField>
        <Label>Telefone</Label>
        <PhoneInput
          value={telefone}
          onChange={setTelefone}
        />
      </FormField>

      <FormField>
        <Label>Email</Label>
        <Input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="email@exemplo.com"
        />
      </FormField>

      <FormField>
        <Label>CRECI</Label>
        <Input
          type="text"
          value={creci}
          onChange={(e) => setCreci(e.target.value)}
          placeholder="Número do CRECI"
        />
      </FormField>

      <Button type="submit" disabled={loading}>
        {loading ? (initialData ? 'Atualizando...' : 'Cadastrando...') : (initialData ? 'Atualizar Corretor' : 'Cadastrar Corretor')}
      </Button>
    </Form>
  )
}

export default CorretorEditForm
