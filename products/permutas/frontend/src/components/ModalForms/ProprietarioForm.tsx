import { useState, useContext } from 'react'
import styled from 'styled-components'
import { jwtDecode } from 'jwt-decode'
import swal from 'sweetalert2'
import useAxios from '../../utils/useAxios'
import { color, spacing } from '../../styles'
import AuthContext from '../../context/AuthContext'
import PhoneInput from '../PhoneInput'

const Form = styled.form`
  display: flex;
  flex-direction: column;
  gap: ${spacing.md};
`

const FormRow = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: ${spacing.md};

  @media (max-width: 600px) {
    grid-template-columns: 1fr;
  }
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
  onSuccess: (newProprietario: { id: number; nome: string; telefone: string; email: string }) => void
  onClose: () => void
}

const ProprietarioForm = ({ onSuccess, onClose }: Props) => {
  const api = useAxios()
  const { authTokens } = useContext(AuthContext)
  
  let user_id = ''
  if (authTokens?.access) {
    const decoded: { user_id: string } = jwtDecode(authTokens.access)
    user_id = decoded.user_id
  }

  const [loading, setLoading] = useState(false)
  const [nome, setNome] = useState('')
  const [telefone, setTelefone] = useState('')
  const [email, setEmail] = useState('')

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
      const response = await api.post('/proprietario/', {
        criado_por: Number(user_id),
        nome,
        telefone,
        email
      })

      swal.fire({
        title: 'Proprietário cadastrado!',
        icon: 'success',
        toast: true,
        timer: 3000,
        position: 'top-right',
        timerProgressBar: true,
        showConfirmButton: false
      })

      onSuccess(response.data)
      onClose()
    } catch {
      swal.fire({
        title: 'Erro ao cadastrar',
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
          placeholder="Nome do proprietário"
          required
        />
      </FormField>

      <FormRow>
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
      </FormRow>

      <Button type="submit" disabled={loading}>
        {loading ? 'Cadastrando...' : 'Cadastrar Proprietário'}
      </Button>
    </Form>
  )
}

export default ProprietarioForm
