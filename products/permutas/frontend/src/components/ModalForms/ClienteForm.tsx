import { useState, useContext, useEffect } from 'react'
import styled from 'styled-components'
import { jwtDecode } from 'jwt-decode'
import swal from 'sweetalert2'
import useAxios from '../../utils/useAxios'
import { color, radius, spacing } from '../../styles'
import AuthContext from '../../context/AuthContext'
import { ClienteType } from '../../pages/Clientes'
import CorretorAutocomplete from '../CorretorAutocomplete'
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
  border-radius: ${radius.md};
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
  border-radius: ${radius.md};
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
  onSuccess: () => void
  onClose: () => void
  initialData?: ClienteType | null
}

const ClienteForm = ({ onSuccess, onClose, initialData }: Props) => {
  const api = useAxios()
  const { authTokens } = useContext(AuthContext)
  
  let user_id = ''
  if (authTokens?.access) {
    const decoded: { user_id: string } = jwtDecode(authTokens.access)
    user_id = decoded.user_id
  }

  const [loading, setLoading] = useState(false)
  const [nome, setNome] = useState('')
  const [corretor, setCorretor] = useState('')
  const [telefone, setTelefone] = useState('')
  const [email, setEmail] = useState('')

  const isEditing = !!initialData

  useEffect(() => {
    if (initialData) {
      setNome(initialData.nome || '')
      setCorretor(initialData.corretor ? String(initialData.corretor) : '')
      setTelefone(initialData.telefone || '')
      setEmail(initialData.email || '')
    } else {
      setNome('')
      setCorretor('')
      setTelefone('')
      setEmail('')
    }
  }, [initialData])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!user_id) {
      swal.fire({
        title: 'Usuário não autenticado',
        icon: 'error',
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
      const data = {
        criado_por: user_id,
        nome,
        corretor: corretor ? Number(corretor) : null,
        telefone,
        email
      }

      if (isEditing) {
        await api.put(`/proprietario/${initialData.id}/`, data)
        swal.fire({
          title: 'Cliente atualizado!',
          icon: 'success',
          toast: true,
          timer: 3000,
          position: 'top-right',
          timerProgressBar: true,
          showConfirmButton: false
        })
      } else {
        await api.post('/proprietario/', data)
        swal.fire({
          title: 'Cliente cadastrado!',
          icon: 'success',
          toast: true,
          timer: 3000,
          position: 'top-right',
          timerProgressBar: true,
          showConfirmButton: false
        })
      }

      onSuccess()
      onClose()
    } catch {
      swal.fire({
        title: isEditing ? 'Erro ao atualizar' : 'Erro ao cadastrar',
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
    <Form onSubmit={handleSubmit}>
      <FormField>
        <Label>Nome *</Label>
        <Input
          type="text"
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          required
        />
      </FormField>

      <FormField>
        <Label>Corretor</Label>
        <CorretorAutocomplete
          value={corretor}
          onChange={(id) => setCorretor(id)}
        />
      </FormField>

      <FormField>
        <Label>Telefone *</Label>
        <PhoneInput
          value={telefone}
          onChange={setTelefone}
          required
        />
      </FormField>

      <FormField>
        <Label>Email</Label>
        <Input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </FormField>

      <Button type="submit" disabled={loading}>
        {loading ? (isEditing ? 'Atualizando...' : 'Cadastrando...') : (isEditing ? 'Atualizar Cliente' : 'Cadastrar Cliente')}
      </Button>
    </Form>
  )
}

export default ClienteForm
