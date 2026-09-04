import { useState, useContext, useEffect } from 'react'
import styled from 'styled-components'
import swal from 'sweetalert2'
import useAxios from '../../utils/useAxios'
import { color, spacing } from '../../styles'
import AuthContext from '../../context/AuthContext'
import CorretorAutocomplete from '../CorretorAutocomplete'
import SelectWithAdd from '../SelectWithAdd'

const MOTOR_OPTIONS = [
  { value: '1.0', label: '1.0' },
  { value: '1.4', label: '1.4' },
  { value: '1.6', label: '1.6' },
  { value: '1.8', label: '1.8' },
  { value: '2.0', label: '2.0' }
]

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

const Select = styled.select`
  padding: ${spacing.sm} ${spacing.md};
  border: 1px solid ${color.border};
  font-size: 14px;
  background: white;
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

type PermutaAutomovelType = {
  id: number
  proprietario: number
  proprietario_nome: string
  criado_por: number
  criado_por_nome: string
  corretor: number | null
  corretor_nome: string | null
  tipo: number | null
  tipo_nome: string | null
  marca: string
  modelo: string
  motor: string
  valor: number
}

type Props = {
  onSuccess: () => void
  onClose: () => void
  initialData: PermutaAutomovelType
}

const PermutaAutomovelEditForm = ({ onSuccess, onClose, initialData }: Props) => {
  const api = useAxios()
  const { user } = useContext(AuthContext)

  const [loading, setLoading] = useState(false)

  const [corretor, setCorretor] = useState(initialData.corretor ? String(initialData.corretor) : '')
  const [tipoAutomovel, setTipoAutomovel] = useState(initialData.tipo ? String(initialData.tipo) : '')
  const [marca, setMarca] = useState(initialData.marca ?? '')
  const [modelo, setModelo] = useState(initialData.modelo ?? '')
  const [motor, setMotor] = useState(initialData.motor ?? '')
  const [valor, setValor] = useState(String(initialData.valor ?? 0))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!user) {
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
      await api.patch(`/permuta/automovel/${initialData.id}/`, {
        corretor: corretor ? Number(corretor) : null,
        tipo: tipoAutomovel ? Number(tipoAutomovel) : null,
        marca,
        modelo,
        motor,
        valor: Number(valor)
      })

      swal.fire({
        title: 'Permuta atualizada!',
        icon: 'success',
        toast: true,
        timer: 3000,
        position: 'top-right',
        timerProgressBar: true,
        showConfirmButton: false
      })

      onSuccess()
      onClose()
    } catch {
      swal.fire({
        title: 'Erro ao atualizar',
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
      <FormRow>
        <FormField>
          <Label>Corretor</Label>
          <CorretorAutocomplete
            value={corretor}
            onChange={(id) => setCorretor(id)}
          />
        </FormField>
        <FormField>
          <Label>Tipo de Automóvel</Label>
          <SelectWithAdd
            type="tipo_automovel"
            value={tipoAutomovel}
            onChange={(value) => setTipoAutomovel(value)}
            required
          />
        </FormField>
      </FormRow>

      <FormRow>
        <FormField>
          <Label>Marca</Label>
          <Input
            type="text"
            value={marca}
            onChange={(e) => setMarca(e.target.value)}
          />
        </FormField>
        <FormField>
          <Label>Modelo</Label>
          <Input
            type="text"
            value={modelo}
            onChange={(e) => setModelo(e.target.value)}
          />
        </FormField>
      </FormRow>

      <FormRow>
        <FormField>
          <Label>Motor</Label>
          <Select
            value={motor}
            onChange={(e) => setMotor(e.target.value)}
          >
            <option value="">Selecione...</option>
            {MOTOR_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </Select>
        </FormField>
        <FormField>
          <Label>Valor</Label>
          <Input
            type="number"
            value={valor}
            onChange={(e) => setValor(e.target.value)}
            required
          />
        </FormField>
      </FormRow>

      <Button type="submit" disabled={loading}>
        {loading ? 'Salvando...' : 'Salvar Alterações'}
      </Button>
    </Form>
  )
}

export default PermutaAutomovelEditForm
